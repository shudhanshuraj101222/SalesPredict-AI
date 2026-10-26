from __future__ import annotations

from datetime import date, timedelta
import io
import tempfile
import unittest
from pathlib import Path

from app import create_app


class SalesPredictAppTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = str(Path(self.temp_dir.name) / "test.sqlite3")
        self.app = create_app({"TESTING": True, "DATABASE": self.database, "SECRET_KEY": "test"})
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def add_history(self, count: int = 10):
        first_day = date.today() - timedelta(days=count)
        for offset in range(count):
            sale_day = first_day + timedelta(days=offset)
            response = self.client.post("/sales/new", data={
                "sale_date": sale_day.isoformat(),
                "product": "Notebook",
                "category": "Stationery",
                "quantity": str(offset + 1),
                "unit_price": "20.50",
            })
            self.assertEqual(response.status_code, 302)

    def test_dashboard_and_empty_model_state(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        response = self.client.get("/performance")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"not available yet", response.data)
        self.assertNotIn(b"MAE</span>", response.data)

    def test_primary_pages_render(self):
        for path in ("/forecast", "/sales", "/analytics", "/history", "/performance", "/reports", "/sales/new"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_sale_validation_crud_and_csv_exports(self):
        self.add_history(1)
        records = self.client.get("/sales")
        self.assertIn(b"Notebook", records.data)
        self.assertEqual(self.client.get("/sales/1").status_code, 200)
        updated = self.client.post("/sales/1/edit", data={
            "sale_date": (date.today() - timedelta(days=1)).isoformat(), "product": "Updated notebook", "category": "Stationery",
            "quantity": "2", "unit_price": "20.5",
        })
        self.assertEqual(updated.status_code, 302)
        self.assertIn(b"Updated notebook", self.client.get("/sales").data)
        self.assertEqual(self.client.post("/sales/1/delete").status_code, 302)
        self.assertNotIn(b"Updated notebook", self.client.get("/sales").data)
        self.add_history(1)
        self.assertEqual(self.client.get("/reports.csv").mimetype, "text/csv")
        self.assertEqual(self.client.get("/reports.pdf").mimetype, "application/pdf")
        self.assertEqual(self.client.get("/reports/forecast.csv").mimetype, "text/csv")
        self.assertEqual(self.client.get("/reports/forecast.pdf").mimetype, "application/pdf")

    def test_csv_import_validates_all_rows_before_saving(self):
        invalid = b"sale_date,product,quantity,unit_price\n2025-01-01,Good,1,10\nbad,Bad,1,20\n"
        response = self.client.post(
            "/sales/import",
            data={"file": (io.BytesIO(invalid), "bad.csv")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn(b"CSV row 3", response.data)
        self.assertNotIn(b"Good", self.client.get("/sales").data)
        valid = b"sale_date,product,quantity,unit_price,category\n2025-01-01,Pen,2,3.5,Stationery\n"
        response = self.client.post(
            "/sales/import",
            data={"file": (io.BytesIO(valid), "sales.csv")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn(b"Imported 1 sales record", response.data)
        self.assertIn(b"Pen", self.client.get("/sales").data)

    def test_forecast_history_and_chronological_performance(self):
        self.add_history()
        performance = self.client.get("/performance")
        self.assertIn(b"MAE", performance.data)
        self.assertIn(b"Actual vs predicted", performance.data)
        response = self.client.post("/forecast", data={
            "start_date": (date.today() + timedelta(days=1)).isoformat(),
            "periods": "7",
        }, follow_redirects=True)
        self.assertIn(b"Forecast result", response.data)
        history = self.client.get("/history")
        self.assertIn(b"7 days", history.data)
        self.assertIn(b"Forecast details", self.client.get("/history/1").data)
        forecast_start = date.today() + timedelta(days=1)
        for offset in range(7):
            self.client.post("/sales/new", data={
                "sale_date": (forecast_start + timedelta(days=offset)).isoformat(),
                "product": "Notebook", "category": "Stationery",
                "quantity": "3", "unit_price": "20.50",
            })
        self.assertIn(b"Actual vs predicted", self.client.get("/analytics").data)
        self.assertIn(b"430.50", self.client.get("/history").data)
        report_range = f"?start={forecast_start.isoformat()}&end={(forecast_start + timedelta(days=6)).isoformat()}"
        self.assertEqual(self.client.get(f"/reports/forecast.pdf{report_range}").mimetype, "application/pdf")

    def test_forecast_requires_sufficient_real_sales(self):
        response = self.client.post("/forecast", data={
            "start_date": (date.today() + timedelta(days=1)).isoformat(),
            "periods": "7",
        }, follow_redirects=True)
        self.assertIn(b"Add historical sales records", response.data)


if __name__ == "__main__":
    unittest.main()
