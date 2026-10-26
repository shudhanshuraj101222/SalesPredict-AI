from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from io import BytesIO, StringIO
import sqlite3

import pandas as pd
from flask import Blueprint, Response, abort, current_app, flash, redirect, render_template, request, url_for
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from database.db import connect, query
from models.forecasting import MODEL_NAME, forecast_history, predict, train_and_evaluate
from services.sales import add_sale, delete_sale, get_sales, parse_sale, sale_by_id, sales_frame, update_sale

web = Blueprint("web", __name__)


def _db() -> str:
    return current_app.config["DATABASE"]


def _spreadsheet_text(value: str) -> str:
    if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{value}"
    return value


def _date_filter() -> tuple[str | None, str | None]:
    start = request.args.get("start", "").strip() or None
    end = request.args.get("end", "").strip() or None
    for value in (start, end):
        if value:
            try:
                date.fromisoformat(value)
            except ValueError:
                raise ValueError("Date filters must use YYYY-MM-DD format.") from None
    if start and end and start > end:
        raise ValueError("Start date must be on or before end date.")
    return start, end


def _summary(frame: pd.DataFrame) -> dict:
    if frame.empty:
        return {"total": 0.0, "average": 0.0, "count": 0, "growth": None, "months": [], "products": []}
    frame = frame.copy()
    frame["month"] = frame["sale_date"].dt.to_period("M").astype(str)
    monthly = frame.groupby("month")["revenue"].sum().sort_index()
    growth = None
    if len(monthly) >= 2 and monthly.iloc[-2] != 0:
        growth = (float(monthly.iloc[-1]) - float(monthly.iloc[-2])) / float(monthly.iloc[-2]) * 100
    product_totals = frame.groupby("product")["revenue"].sum().sort_values(ascending=False).head(5)
    return {
        "total": float(frame["revenue"].sum()),
        "average": float(frame["revenue"].mean()),
        "count": int(len(frame)),
        "growth": growth,
        "months": [{"label": label, "value": round(float(value), 2)} for label, value in monthly.items()],
        "products": [{"label": label, "value": round(float(value), 2)} for label, value in product_totals.items()],
    }


@web.app_errorhandler(413)
def too_large(_error):
    flash("Upload is too large. CSV files must be 5 MB or smaller.", "error")
    return redirect(url_for("web.records"))


@web.route("/")
def dashboard():
    try:
        start, end = _date_filter()
        records = get_sales(_db(), start, end)
        frame = sales_frame(_db())
        if start:
            frame = frame[frame["sale_date"] >= pd.Timestamp(start)] if not frame.empty else frame
        if end:
            frame = frame[frame["sale_date"] <= pd.Timestamp(end)] if not frame.empty else frame
        summary = _summary(frame)
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("web.dashboard"))
    forecast_row = query(_db(), "SELECT predicted_total FROM forecasts ORDER BY created_at DESC, id DESC LIMIT 1")
    return render_template(
        "dashboard.html", active="dashboard", summary=summary, records=records[:8],
        start=start or "", end=end or "", latest_forecast=float(forecast_row[0]["predicted_total"]) if forecast_row else None,
    )


@web.route("/sales")
def records():
    try:
        start, end = _date_filter()
        all_records = get_sales(_db(), start, end)
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("web.records"))
    search = request.args.get("q", "").strip().casefold()
    if search:
        all_records = [item for item in all_records if search in item["product"].casefold() or search in item["category"].casefold()]
    page = max(1, request.args.get("page", 1, type=int) or 1)
    per_page = 12
    pages = max(1, (len(all_records) + per_page - 1) // per_page)
    page = min(page, pages)
    return render_template(
        "records.html", active="sales", records=all_records[(page - 1) * per_page:page * per_page],
        page=page, pages=pages, total=len(all_records), start=start or "", end=end or "", q=search,
    )


@web.route("/sales/new", methods=["GET", "POST"])
@web.route("/sales/<int:sale_id>/edit", methods=["GET", "POST"])
def sale_form(sale_id: int | None = None):
    sale = sale_by_id(_db(), sale_id) if sale_id is not None else None
    if sale_id is not None and sale is None:
        abort(404)
    if request.method == "POST":
        try:
            values = parse_sale(request.form)
            if sale_id is None:
                add_sale(_db(), *values)
                flash("Sales record added.", "success")
            else:
                update_sale(_db(), sale_id, *values)
                flash("Sales record updated.", "success")
            return redirect(url_for("web.records"))
        except ValueError as error:
            flash(str(error), "error")
    return render_template("sale_form.html", active="sales", sale=sale)


@web.post("/sales/<int:sale_id>/delete")
def delete_sale_route(sale_id: int):
    if sale_by_id(_db(), sale_id) is None:
        abort(404)
    delete_sale(_db(), sale_id)
    flash("Sales record deleted.", "success")
    return redirect(url_for("web.records"))


@web.get("/sales/<int:sale_id>")
def view_sale(sale_id: int):
    sale = sale_by_id(_db(), sale_id)
    if sale is None:
        abort(404)
    return render_template("sale_detail.html", active="sales", sale=sale)


@web.post("/sales/import")
def import_csv():
    upload = request.files.get("file")
    if upload is None or not upload.filename or not upload.filename.lower().endswith(".csv"):
        flash("Choose a CSV file to import.", "error")
        return redirect(url_for("web.records"))
    try:
        frame = pd.read_csv(upload, dtype=str).fillna("")
        frame.columns = [str(column).strip().lower() for column in frame.columns]
        required = {"sale_date", "product", "quantity", "unit_price"}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"CSV is missing required columns: {', '.join(sorted(missing))}.")
        if frame.empty:
            raise ValueError("The CSV contains no sales rows.")
        if len(frame) > 10000:
            raise ValueError("Import is limited to 10,000 sales rows at a time.")
        validated = []
        for line, row in enumerate(frame.to_dict(orient="records"), start=2):
            try:
                validated.append(parse_sale({
                    "sale_date": row["sale_date"].strip(),
                    "product": row["product"].strip(),
                    "category": row.get("category", "").strip(),
                    "quantity": row["quantity"].strip(),
                    "unit_price": row["unit_price"].strip(),
                }))
            except ValueError as error:
                raise ValueError(f"CSV row {line}: {error}") from None
        with connect(_db()) as connection:
            connection.executemany(
                "INSERT INTO sales (sale_date, product, category, quantity, unit_price) VALUES (?, ?, ?, ?, ?)",
                validated,
            )
        flash(f"Imported {len(validated)} sales record(s).", "success")
    except (ValueError, pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as error:
        flash(str(error), "error")
    except (sqlite3.Error, OSError):
        current_app.logger.exception("Sales CSV import failed")
        flash("The CSV could not be imported because of a database or file error.", "error")
    return redirect(url_for("web.records"))


@web.route("/forecast", methods=["GET", "POST"])
def forecast_page():
    result = None
    if request.method == "POST":
        try:
            start = date.fromisoformat(request.form.get("start_date", ""))
            periods = int(request.form.get("periods", ""))
            if periods < 1 or periods > 90:
                raise ValueError("Forecast length must be between 1 and 90 days.")
            if start < date.today():
                raise ValueError("Forecast start date cannot be in the past.")
            result = predict(_db(), start, periods)
            flash("Forecast created and saved to forecast history.", "success")
        except ValueError as error:
            flash(str(error), "error")
    frame = sales_frame(_db())
    default_start = max(date.today(), frame["sale_date"].max().date() + timedelta(days=1)) if not frame.empty else date.today()
    return render_template(
        "forecast.html", active="forecast", result=result,
        default_start=default_start.isoformat(),
    )


@web.get("/analytics")
def analytics():
    try:
        start, end = _date_filter()
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("web.analytics"))
    frame = sales_frame(_db())
    if not frame.empty and start:
        frame = frame[frame["sale_date"] >= pd.Timestamp(start)]
    if not frame.empty and end:
        frame = frame[frame["sale_date"] <= pd.Timestamp(end)]
    if not frame.empty:
        daily = frame.groupby(frame["sale_date"].dt.strftime("%Y-%m-%d"))["revenue"].sum()
        weekly = frame.groupby(frame["sale_date"].dt.to_period("W").astype(str))["revenue"].sum()
        monthly = frame.groupby(frame["sale_date"].dt.to_period("M").astype(str))["revenue"].sum()
        products = frame.groupby("product")["revenue"].sum().sort_values(ascending=False).head(8)
        categories = frame[frame["category"].astype(str).str.strip() != ""].groupby("category")["revenue"].sum().sort_values(ascending=False).head(8)
        highest = {"label": str(daily.idxmax()), "value": float(daily.max())}
        lowest = {"label": str(daily.idxmin()), "value": float(daily.min())}
    else:
        daily, weekly, monthly, products = pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=float)
        categories = pd.Series(dtype=float)
        highest = lowest = None
    actual_comparison = None
    historical = sales_frame(_db())
    if not historical.empty:
        completed = next(
            (
                item for item in forecast_history(_db())
                if item["actual_total"] is not None
                and all((not start or prediction["date"] >= start) and (not end or prediction["date"] <= end) for prediction in item["predictions"])
            ),
            None,
        )
        if completed:
            actual_by_date = historical.groupby(historical["sale_date"].dt.strftime("%Y-%m-%d"))["revenue"].sum()
            actual_comparison = {
                "labels": [item["date"] for item in completed["predictions"]],
                "actual": [round(float(actual_by_date[item["date"]]), 2) for item in completed["predictions"]],
                "predicted": [item["revenue"] for item in completed["predictions"]],
            }
    chart = lambda series: [{"label": str(label), "value": round(float(value), 2)} for label, value in series.items()]
    return render_template(
        "analytics.html", active="analytics", daily=chart(daily), weekly=chart(weekly),
        monthly=chart(monthly), products=chart(products), highest=highest, lowest=lowest,
        actual_comparison=actual_comparison, categories=chart(categories), start=start or "", end=end or "",
    )


@web.get("/history")
def history():
    return render_template("history.html", active="history", forecasts=forecast_history(_db()))


@web.get("/history/<int:forecast_id>")
def history_detail(forecast_id: int):
    records = forecast_history(_db())
    selected = next((item for item in records if item["id"] == forecast_id), None)
    if selected is None:
        abort(404)
    return render_template("forecast_detail.html", active="history", forecast=selected)


@web.get("/performance")
def performance():
    evaluation = train_and_evaluate(_db())
    return render_template("performance.html", active="performance", evaluation=evaluation, model_name=MODEL_NAME)


@web.get("/reports")
def reports():
    try:
        start, end = _date_filter()
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("web.reports"))
    return render_template("reports.html", active="reports", summary=_summary(_report_frame(start, end)), start=start or "", end=end or "")


def _report_frame(start: str | None, end: str | None) -> pd.DataFrame:
    frame = sales_frame(_db())
    if not frame.empty and start:
        frame = frame[frame["sale_date"] >= pd.Timestamp(start)]
    if not frame.empty and end:
        frame = frame[frame["sale_date"] <= pd.Timestamp(end)]
    return frame


@web.get("/reports.csv")
def report_csv():
    try:
        start, end = _date_filter()
    except ValueError as error:
        abort(400, description=str(error))
    frame = _report_frame(start, end)
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["sale_date", "product", "category", "quantity", "unit_price", "revenue"])
    for row in frame.itertuples(index=False):
        writer.writerow([row.sale_date.strftime("%Y-%m-%d"), _spreadsheet_text(row.product), _spreadsheet_text(row.category), row.quantity, row.unit_price, round(row.revenue, 2)])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=sales_summary.csv"})


@web.get("/reports/forecast.csv")
def forecast_report_csv():
    try:
        start, end = _date_filter()
    except ValueError as error:
        abort(400, description=str(error))
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["forecast_id", "created_at", "forecast_date", "model_name", "predicted_revenue"])
    for item in forecast_history(_db()):
        for prediction in item["predictions"]:
            if start and prediction["date"] < start:
                continue
            if end and prediction["date"] > end:
                continue
            writer.writerow([item["id"], item["created_at"], prediction["date"], item["model_name"], prediction["revenue"]])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=forecast_report.csv"})


@web.get("/reports/forecast.pdf")
def forecast_report_pdf():
    try:
        start, end = _date_filter()
    except ValueError as error:
        abort(400, description=str(error))
    history_items = forecast_history(_db())
    frame = sales_frame(_db())
    actual_by_date = (
        frame.groupby(frame["sale_date"].dt.strftime("%Y-%m-%d"))["revenue"].sum().to_dict()
        if not frame.empty else {}
    )
    rows = []
    for item in history_items:
        for prediction in item["predictions"]:
            forecast_day = prediction["date"]
            if start and forecast_day < start:
                continue
            if end and forecast_day > end:
                continue
            rows.append((item["id"], forecast_day, item["model_name"], prediction["revenue"], actual_by_date.get(forecast_day)))
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=letter, title="SalesPredict AI forecast report")
    styles = getSampleStyleSheet()
    elements = [
        Paragraph("SalesPredict AI — Forecast Report", styles["Title"]),
        Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} · Forecast dates: {start or 'all'} to {end or 'all'}", styles["Normal"]),
        Spacer(1, 16),
    ]
    table_data = [["ID", "Forecast date", "Model", "Predicted", "Actual"]]
    table_data.extend([
        [str(forecast_id), forecast_day, model_name, f"{predicted:,.2f}", f"{actual:,.2f}" if actual is not None else "—"]
        for forecast_id, forecast_day, model_name, predicted, actual in rows
    ])
    table = Table(table_data, repeatRows=1, colWidths=[32, 82, 157, 88, 75])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16243a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d8dee8")),
        ("PADDING", (0, 0), (-1, -1), 5),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
    ]))
    elements.append(table)
    if not rows:
        elements.append(Paragraph("No saved forecast points match this date range.", styles["BodyText"]))
    document.build(elements)
    return Response(buffer.getvalue(), mimetype="application/pdf", headers={"Content-Disposition": "attachment; filename=forecast_report.pdf"})


@web.get("/reports.pdf")
def report_pdf():
    try:
        start, end = _date_filter()
    except ValueError as error:
        abort(400, description=str(error))
    frame = _report_frame(start, end)
    summary = _summary(frame)
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=letter, title="SalesPredict AI sales summary")
    styles = getSampleStyleSheet()
    elements = [
        Paragraph("SalesPredict AI — Sales Summary", styles["Title"]),
        Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} · Date range: {start or 'all'} to {end or 'all'}", styles["Normal"]),
        Spacer(1, 16),
        Paragraph(f"Recorded sales rows: {summary['count']}<br/>Total revenue: {summary['total']:,.2f}<br/>Average row revenue: {summary['average']:,.2f}", styles["BodyText"]),
        Spacer(1, 16),
    ]
    monthly = [["Month", "Revenue"]] + [[item["label"], f"{item['value']:,.2f}"] for item in summary["months"]]
    table = Table(monthly, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16243a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d8dee8")),
        ("PADDING", (0, 0), (-1, -1), 7),
    ]))
    elements.append(table)
    document.build(elements)
    return Response(buffer.getvalue(), mimetype="application/pdf", headers={"Content-Disposition": "attachment; filename=sales_summary.pdf"})


@web.errorhandler(404)
def not_found(_error):
    return render_template("404.html", active=""), 404
