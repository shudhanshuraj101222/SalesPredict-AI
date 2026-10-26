from __future__ import annotations

from datetime import date
import json
from math import cos, pi, sin

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from database.db import execute, query
from services.sales import sales_frame

MODEL_NAME = "Linear Regression (time-aware)"


def _features(days: np.ndarray, calendar_dates: pd.DatetimeIndex) -> np.ndarray:
    day_of_year = calendar_dates.dayofyear.to_numpy(dtype=float)
    return np.column_stack((days, np.sin(2 * pi * day_of_year / 365.25), np.cos(2 * pi * day_of_year / 365.25)))


def _daily_series(frame: pd.DataFrame) -> pd.Series:
    daily = frame.groupby("sale_date")["revenue"].sum().sort_index()
    if daily.empty:
        return daily
    full_index = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    return daily.reindex(full_index, fill_value=0.0)


def train_and_evaluate(database: str) -> dict:
    frame = sales_frame(database)
    daily = _daily_series(frame) if not frame.empty else pd.Series(dtype=float)
    if len(daily) < 8 or int(np.count_nonzero(daily.to_numpy(dtype=float))) < 8:
        return {
            "available": False,
            "message": "Add sales with positive revenue on at least 8 different dates to evaluate the model.",
        }
    values = daily.to_numpy(dtype=float)
    split = max(1, int(len(values) * 0.8))
    if split >= len(values):
        split = len(values) - 1
    positions = np.arange(len(values), dtype=float)
    features = _features(positions, pd.DatetimeIndex(daily.index))
    model = LinearRegression().fit(features[:split], values[:split])
    predicted = np.maximum(0, model.predict(features[split:]))
    actual = values[split:]
    metrics = {
        "mae": float(mean_absolute_error(actual, predicted)),
        "rmse": float(np.sqrt(mean_squared_error(actual, predicted))),
        "r2": float(r2_score(actual, predicted)) if len(actual) > 1 else None,
        "train_days": split,
        "test_days": len(actual),
        "actual": actual.round(2).tolist(),
        "predicted": predicted.round(2).tolist(),
        "labels": [timestamp.strftime("%Y-%m-%d") for timestamp in daily.index[split:]],
    }
    return {"available": True, "metrics": metrics, "message": _performance_text(metrics)}


def _performance_text(metrics: dict) -> str:
    error = metrics["mae"]
    mean_actual = float(np.mean(metrics["actual"]))
    if mean_actual == 0:
        return "Chronological holdout results are available; interpret errors carefully because the test period has no average sales."
    relative_error = error / mean_actual
    if relative_error < 0.15:
        quality = "closely tracked"
    elif relative_error < 0.4:
        quality = "followed the broad sales pattern"
    else:
        quality = "had substantial error against"
    return f"On {metrics['test_days']} later day(s) kept out of training, predictions {quality} actual sales. Results may change as more history is added."


def predict(database: str, start_date: date, periods: int) -> dict:
    frame = sales_frame(database)
    if frame.empty:
        raise ValueError("Add historical sales records before requesting a forecast.")
    daily = _daily_series(frame)
    if len(daily) < 3 or int(np.count_nonzero(daily.to_numpy(dtype=float))) < 3:
        raise ValueError("Sales with positive revenue on at least 3 different dates are required to forecast.")
    if start_date <= daily.index[-1].date():
        raise ValueError("Forecast start date must be after the latest recorded sales date.")
    if (start_date - daily.index[-1].date()).days > 90:
        raise ValueError("Forecast start date is too far after the latest sales. Add recent history before forecasting.")
    values = daily.to_numpy(dtype=float)
    positions = np.arange(len(values), dtype=float)
    model = LinearRegression().fit(_features(positions, pd.DatetimeIndex(daily.index)), values)
    future_dates = pd.date_range(start=start_date, periods=periods, freq="D")
    gap = (start_date - daily.index[-1].date()).days
    offsets = np.arange(len(values), len(values) + periods, dtype=float) + gap - 1
    amounts = np.maximum(0, model.predict(_features(offsets, future_dates)))
    predictions = [
        {"date": day.date().isoformat(), "revenue": round(float(amount), 2)}
        for day, amount in zip(future_dates, amounts)
    ]
    evaluation = train_and_evaluate(database)
    metrics = evaluation.get("metrics") if evaluation["available"] else None
    forecast_id = execute(
        database,
        """INSERT INTO forecasts (start_date, periods, model_name, predicted_total, predictions_json, metrics_json)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            start_date.isoformat(),
            periods,
            MODEL_NAME,
            round(sum(item["revenue"] for item in predictions), 2),
            json.dumps(predictions),
            json.dumps(metrics) if metrics is not None else None,
        ),
    )
    return {
        "id": forecast_id,
        "start_date": start_date.isoformat(),
        "periods": periods,
        "model_name": MODEL_NAME,
        "predictions": predictions,
        "total": round(sum(item["revenue"] for item in predictions), 2),
        "evaluation": evaluation,
    }


def forecast_history(database: str) -> list[dict]:
    rows = query(database, "SELECT * FROM forecasts ORDER BY created_at DESC, id DESC")
    frame = sales_frame(database)
    actual_by_date = (
        frame.groupby(frame["sale_date"].dt.strftime("%Y-%m-%d"))["revenue"].sum().to_dict()
        if not frame.empty else {}
    )
    result = []
    for row in rows:
        item = dict(row)
        item["predictions"] = json.loads(item.pop("predictions_json"))
        item["metrics"] = json.loads(item.pop("metrics_json")) if item.get("metrics_json") else None
        prediction_dates = [prediction["date"] for prediction in item["predictions"]]
        if prediction_dates and all(day in actual_by_date for day in prediction_dates):
            actual_total = round(sum(float(actual_by_date[day]) for day in prediction_dates), 2)
        else:
            actual_total = None
        if item["actual_total"] != actual_total:
            execute(database, "UPDATE forecasts SET actual_total = ? WHERE id = ?", (actual_total, item["id"]))
        item["actual_total"] = actual_total
        result.append(item)
    return result
