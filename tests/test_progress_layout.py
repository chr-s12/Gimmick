import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app import create_app


class ProgressLayoutTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.app = create_app({
            "TESTING": True, "PROGRESS_FIXTURES": True, "WORKOUT_STORAGE_PATH": Path(directory) / "workouts.json",
        })
        self.client = self.app.test_client()

    def test_signed_in_progress_pages_use_the_shared_navigation(self):
        directory = Path(self.enterContext(TemporaryDirectory()))
        app = create_app({"TESTING": True, "DATA_DIR": directory / "data", "LOG_DIR": directory / "logs"})
        app.extensions["gymmick"]["accounts"].createAccount("620100001", "Alex Brown", "student", "secret123")
        client = app.test_client()
        self.assertEqual(client.post("/login", data={"uwiId": "620100001", "password": "secret123"}).status_code, 302)
        for path, active in (("/progress/", "/progress/"), ("/progress/history", "/progress/"),
                             ("/progress/analytics", "/progress/analytics")):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(b'aria-label="Main navigation"', response.data)
                self.assertNotIn(b'aria-label="Progress navigation"', response.data)
                self.assertIn(f'href="{active}" aria-current="page"'.encode(), response.data)
                self.assertIn(b'href="/static/app.css"', response.data)
                self.assertIn(b'href="/progress/static/css/feature4.css"', response.data)

    def assert_layout(self, response, active_path, current="page"):
        self.assertIn(b'aria-label="Progress navigation"', response.data)
        self.assertIn(b'href="/progress/static/css/feature4.css"', response.data)
        for path, label in (
            ("/progress/", "Log Workout"),
            ("/progress/history", "History"),
            ("/progress/analytics", "My Progress"),
        ):
            active = f' aria-current="{current}"' if path == active_path else ""
            self.assertIn(f'<a href="{path}"{active}>{label}</a>'.encode(), response.data)
        self.assertEqual(response.data.count(b"aria-current="), 1)

    def test_primary_pages_render_and_have_working_navigation(self):
        for path, heading in (
            ("/progress/", "Log Workout"),
            ("/progress/history", "Workout History"),
            ("/progress/analytics", "My Progress"),
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(f"<h1>{heading}</h1>".encode(), response.data)
                self.assert_layout(response, path)

    def test_analytics_page_uses_mock_identity_and_has_no_chart_controls(self):
        service = self.app.extensions["progress_service"]
        with patch.object(service, "get_analytics", wraps=service.get_analytics) as analytics:
            response = self.client.get("/progress/analytics?student_id=ST002")
        analytics.assert_called_once()
        self.assertEqual(analytics.call_args.args, ("ST001",))
        self.assertIsNone(analytics.call_args.kwargs["start_date"])
        self.assertIsNone(analytics.call_args.kwargs["end_date"])
        self.assertIsNotNone(analytics.call_args.kwargs["as_of"].utcoffset())
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"<svg", response.data)
        self.assertIn(b'id="period"', response.data)
        self.assertNotIn(b'id="exercise-chart-exercise"', response.data)
        self.assertNotIn(b'id="record-exercise"', response.data)

    def test_blueprint_stylesheet_is_served_locally(self):
        with self.client.get("/progress/static/css/feature4.css") as response:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, "text/css")
            self.assertIn(b".gymmick-progress", response.data)
            self.assertNotIn(b"@import", response.data)

    def test_chart_export_module_is_served_locally(self):
        with self.client.get("/progress/static/js/chart_export.js") as response:
            self.assertEqual(response.status_code, 200)
            self.assertIn(response.mimetype, ("text/javascript", "application/javascript"))
            self.assertIn(b"export async function exportChart", response.data)

    def test_weekly_download_integration_module_is_served_locally(self):
        with self.client.get("/progress/static/js/weekly_chart_download.js") as response:
            self.assertEqual(response.status_code, 200)
            self.assertIn(response.mimetype, ("text/javascript", "application/javascript"))
            self.assertIn(b'from "./chart_export.js"', response.data)

    def test_exercise_download_modules_are_served_locally(self):
        for module in ("exercise_chart_download", "chart_download"):
            with self.subTest(module=module):
                with self.client.get(f"/progress/static/js/{module}.js") as response:
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(response.mimetype, ("text/javascript", "application/javascript"))

    def test_logging_support_page_preserves_values_and_announces_validation(self):
        form = self.client.get("/progress/log/RT001")
        self.assert_layout(form, "/progress/", current="location")
        self.assertIn(b"Back to My Routines", form.data)
        invalid = self.client.post("/progress/log/RT001", data={"weight_0": "42.5"})
        self.assertEqual(invalid.status_code, 400)
        self.assert_layout(invalid, "/progress/", current="location")
        self.assertIn(b'aria-invalid="true" aria-describedby="sets_0-error"', invalid.data)
        self.assertIn(b'id="sets_0-error"', invalid.data)
        self.assertRegex(invalid.get_data(as_text=True), r'name="weight_0"\s+value="42\.5"')

    def test_saved_summary_inherits_layout_and_links_back_to_history(self):
        form = {
            f"{field}_{index}": value
            for index in range(3)
            for field, value in (("sets", "2"), ("reps", "7"), ("weight", "42.5"))
        }
        submission = self.client.post("/progress/log/RT001", data=form)
        self.assertEqual(submission.status_code, 303)
        summary = self.client.get(submission.location)
        self.assertEqual(summary.status_code, 200)
        self.assert_layout(summary, "/progress/history", current="location")
        self.assertIn(b"Back to Workout History", summary.data)
        self.assertIn(b"<td>42.5</td>", summary.data)

    def test_feature_errors_use_shared_layout_and_preserve_http_status(self):
        for path, active_path in (
            ("/progress/log/unknown", "/progress/"),
            ("/progress/workouts/unknown", "/progress/history"),
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 404)
                self.assert_layout(response, active_path, current="location")
