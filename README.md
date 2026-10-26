# SalesPredict AI – Sales Prediction and Forecasting System

A local-first sales dashboard built with Flask, SQLite, pandas, NumPy, scikit-learn, and Chart.js. It includes real sales entry and CSV import, dashboard metrics, analytics, time-aware forecasts, model evaluation, saved forecast history, and CSV/PDF reports. There are no hard-coded sample scores or automatically inserted sales; use the clearly labelled `sample_sales.csv` demo file if you want example records.

## Requirements

- Windows 10/11
- Python 3.10 or newer (64-bit recommended)
- Internet access for first dependency installation and the Chart.js / web font CDN used by the UI

## Install and run on Windows

Open PowerShell in the project folder:

```powershell
cd "C:\Users\ASUS\OneDrive\Desktop\College Project\Python"
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python app.py
```

If PowerShell blocks environment activation, run this once in that PowerShell window and activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Open <http://127.0.0.1:5000>. The SQLite database is created automatically at `instance/salespredict.sqlite3` the first time the app starts. There is no separate database initialization command. To use the alternate compatibility entry point, run `python Sales.py`.

To load the included demo data, open **Sales data → Import CSV** and choose `sample_sales.csv`. It contains explicitly illustrative stationery transactions and should not be mistaken for real business data. Import validates the entire file before inserting any rows.

## Features

- **Dashboard:** date-filtered sales totals, average sale value, latest saved prediction, month-over-month growth when comparable months exist, monthly revenue chart, top products, and recent records.
- **Sales prediction:** choose a future start date and 1–90 day horizon. Prediction requires positive sales revenue on at least three distinct dates and a forecast start within 90 days of the newest observation; every forecast is saved to history.
- **Sales data:** add, view, edit, and delete records; search/filter and paginate; import CSV files up to 5 MB and 10,000 rows. Required CSV headers are `sale_date`, `product`, `quantity`, and `unit_price`; `category` is optional. Dates must be ISO `YYYY-MM-DD`, quantities positive whole numbers, and prices finite non-negative values.
- **Analytics:** actual daily, weekly, and monthly sales, highest/lowest day, product revenue comparisons, and completed-period actual-versus-predicted charts where all dates are recorded.
- **Forecast history:** saved predictions and model metadata. A forecast's actual total is populated only after sales have been recorded for every date in the forecast horizon.
- **Model performance:** MAE, RMSE, and R² from a chronological holdout, only when sufficient real historical data exists. The latest portion of the timeline is never shuffled into training.
- **Reports:** date-filtered transaction-level CSV/PDF, a sales summary PDF with run date and monthly revenue totals, and saved forecast reports in CSV/PDF with actual comparison values where they are available.

## Machine-learning approach

`models/forecasting.py` aggregates transaction revenue by calendar day and fills missing calendar days with zero. A scikit-learn `LinearRegression` model fits daily revenue against a time index and annual sine/cosine terms based on the actual day of year. Future predictions are bounded below by zero. The same feature construction is used for the chronological holdout and future predictions. No future test rows are used to fit the evaluation model.

The evaluation reserves the final 20% of days as a holdout (at least one test day), and trains on earlier days. Mean Absolute Error and Root Mean Squared Error are expressed in the same currency units as revenue. R² is not reported for a one-observation test. Forecasts require positive sales revenue on at least three distinct dates; performance metrics require positive sales revenue on at least eight distinct dates. More history and sensible source data generally improve usefulness, but do not guarantee accuracy.

With `n` daily observations and a fixed three-feature matrix, feature preparation and the linear-model fit are approximately **O(n)** time and **O(n)** memory. The general least-squares fit is O(n p² + p³) for `p` features; here `p=3` is constant. Forecasting `h` future days is O(h). Data aggregation and sorting may add O(n log n) overhead.

No serialized model is kept: each forecast trains from current database history, so new records are reflected automatically. This avoids stale model files and makes the training data transparent. Do not reuse the development secret key for a public deployment.

## Project structure

```text
Python/
├── app.py
├── Sales.py                     # compatibility startup entry point
├── requirements.txt
├── README.md
├── sample_sales.csv             # clearly labelled illustrative data
├── database/
│   ├── __init__.py
│   └── db.py                    # SQLite schema and parameterized access
├── models/
│   ├── __init__.py
│   └── forecasting.py           # training, evaluation, forecasts, history
├── services/
│   ├── __init__.py
│   └── sales.py                 # sales persistence and validation
├── routes/
│   ├── __init__.py
│   └── web.py                   # pages, import, and report endpoints
├── templates/                   # shared layout and page templates
├── static/
│   ├── css/style.css
│   └── js/app.js                 # interactive Chart.js charts
├── tests/
│   ├── __init__.py
│   └── test_app.py
└── instance/
    └── salespredict.sqlite3     # created on first launch; do not commit
```

## Database notes

SQLite schema creation runs on application startup and is idempotent. The `sales` table stores date, product, category, quantity, price, and creation timestamp. `forecasts` stores the selected horizon, model label, serialized prediction points, optional evaluation metrics, and an actual total when a full horizon is later observed. All SQL values are parameterized. Database access is isolated in `database/db.py`; a future MySQL adapter can preserve the same service-level operations.

Back up `instance/salespredict.sqlite3` before upgrading or moving the project. To start with an empty database, stop the app and remove this specific database file; it will be recreated at startup.

## Tests

With the virtual environment activated:

```powershell
python -m unittest discover -s tests -v
```

The tests use a temporary SQLite file and cover empty-data behavior, record entry, CSV all-or-nothing validation, report formats, chronological model evaluation, forecast persistence, and insufficient-data handling. Manual checks: add a record and edit/delete it; import the sample CSV; filter sales; generate a forecast; view it in history; inspect performance; download both reports.

## Deployment notes

For a local network demonstration on Windows:

```powershell
$env:SALESPREDICT_SECRET_KEY = "replace-with-a-long-random-secret"
$env:SALESPREDICT_DATABASE = "C:\data\salespredict.sqlite3"
waitress-serve --listen=0.0.0.0:8000 app:app
```

Set the database directory to a persistent, access-controlled location and back it up. Use HTTPS and restrict network access through a firewall/reverse proxy. The app is a single-workspace student project and does not include accounts, CSRF protection, or multi-tenant authorization; do not expose it publicly with sensitive business data without adding those protections. For a managed Linux host, use a production WSGI server such as Gunicorn behind HTTPS, configure the same environment variables, and provide persistent writable storage for SQLite (or implement and test a MySQL adapter before switching databases). Never deploy Flask's development server or enable debug mode in production.

## Troubleshooting

- `ModuleNotFoundError`: activate `.venv`, then rerun `python -m pip install -r requirements.txt`.
- No forecast: add sales with positive revenue on at least three distinct dates; the forecast start must be later than the newest recorded sale date, not in the past, and within 90 days of the newest observation.
- No performance scores: the system needs positive revenue on at least eight distinct dates. It intentionally displays no fabricated metrics.
- Blank charts: confirm Chart.js CDN access or use a network connection; sales records and summaries remain available without chart scripts.
