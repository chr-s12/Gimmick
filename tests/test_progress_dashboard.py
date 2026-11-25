import re
from dataclasses import replace
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from xml.etree import ElementTree

from app import create_app
from progress.analytics import calculate_student_analytics
from progress.models import LoggedExercise, WorkoutLog
from progress.repository import WorkoutLogRepository, WorkoutLogStorageError


SVG = "{http://www.w3.org/2000/svg}"


class ProgressDashboardTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.storage_path = Path(directory) / "workouts.json"
        self.app = create_app({"TESTING": True, "WORKOUT_STORAGE_PATH": self.storage_path})
        self.client = self.app.test_client()
        self.repository = WorkoutLogRepository(self.storage_path)
        self.reference = datetime.fromisoformat("2026-11-26T03:00:00+00:00")
        clock = self.enterContext(patch("progress.routes.datetime", wraps=datetime))
        clock.now.return_value = self.reference

    def save_workout(self, identifier, timestamp, *exercises, student_id="ST001"):
        self.repository.save(WorkoutLog(
            identifier, student_id, "RT001", "Upper Body",
            datetime.fromisoformat(timestamp), list(exercises),
        ))

    def submit_workout(self, timestamp, weight, sets="2", reps="7"):
        form = {
            f"{field}_{index}": value
            for index in range(3)
            for field, value in (("sets", sets), ("reps", reps), ("weight", weight))
        }
        with patch("progress.service.datetime") as clock:
            clock.now.return_value = datetime.fromisoformat(timestamp)
            return self.client.post("/progress/log/RT001", data=form)

    def chart(self, html, chart_class="weekly-chart"):
        match = re.search(rf'<svg class="{chart_class}".*?</svg>', html, re.DOTALL)
        self.assertIsNotNone(match)
        return ElementTree.fromstring(match.group())

    def exercise_points(self, html):
        chart = self.chart(html, "exercise-chart")
        return [label.text for label in chart.findall(f"{SVG}circle/{SVG}title")]

    def metric_html(self, metric, exercise=None):
        query = {"metric": metric}
        if exercise is not None:
            query["exercise"] = exercise
        response = self.client.get("/progress/analytics", query_string=query)
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def dashboard_html(self, **query):
        response = self.client.get("/progress/analytics", query_string=query)
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def records_section(self, html):
        return html.split('id="personal-records"', 1)[1].split("</section>", 1)[0]

    def assert_achievement(self, html, key, value, unit, first_date):
        match = re.search(rf'id="{key}">(.*?)(?=<div class="record-achievement"|</section>)',
                          html, re.DOTALL)
        self.assertIsNotNone(match)
        self.assertIn(f'<p class="record-value">{value} <span>{unit}</span></p>', match.group())
        self.assertIn(f'First achieved <time datetime="{first_date}">{first_date}</time>', match.group())

    def column_values(self, chart, text_class):
        return [label.text for label in chart.findall(f"{SVG}g/{SVG}text[@class='{text_class}']")]

    def test_empty_student_shows_explanation_without_fabricated_statistics(self):
        self.save_workout(
            "W2", "2026-11-24T08:00:00-05:00", LoggedExercise("E2", "Other exercise", 1, 8, 77.0),
            student_id="ST002",
        )
        before = self.storage_path.read_bytes()
        response = self.client.get("/progress/analytics")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Log at least one completed workout", response.data)
        self.assertIn(b'href="/progress/">Log Workout</a>', response.data)
        self.assertNotIn(b"<table", response.data)
        self.assertNotIn(b"<svg", response.data)
        self.assertNotIn(b'id="record-exercise"', response.data)
        self.assertNotIn(b"Other exercise", response.data)
        self.assertNotIn(b"77.0 kg", response.data)
        self.assertEqual(self.storage_path.read_bytes(), before)

    def test_current_and_zero_day_weeks_and_all_metrics_show_saved_values_only(self):
        self.save_workout(
            "W1", "2026-11-10T08:00:00-05:00", LoggedExercise("E1", "Press", 1, 5, 65.0),
        )
        self.save_workout(
            "W2", "2026-11-24T08:00:00-05:00",
            LoggedExercise("E1", "Press", 2, 12, 20.0),
            LoggedExercise("E1", "Press", 1, 7, 40.0),
        )
        self.save_workout(
            "W3", "2026-11-25T08:00:00-05:00", LoggedExercise("E1", "Other name", 2, 15, 99.0),
            student_id="ST002",
        )
        before = self.storage_path.read_bytes()
        response = self.client.get("/progress/analytics?student_id=ST002")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        chart = self.chart(html)
        self.assertEqual(self.column_values(chart, "weekly-date"), ["2026-11-09", "2026-11-16", "2026-11-23"])
        self.assertEqual(self.column_values(chart, "weekly-value"), ["1", "0", "1"])
        self.assertEqual(self.column_values(chart, "weekly-status"), ["Current week"])
        self.assertIsNotNone(chart.find(f"{SVG}g[@class='weekly-column weekly-current']/{SVG}rect"))
        self.assertIsNotNone(chart.find(f"{SVG}g/{SVG}line[@class='weekly-zero']"))
        self.assertIn('<summary>View weekly data</summary>', html)
        self.assertRegex(html, r"2026-11-22</time></td>\s*<td>0</td>\s*<td>Completed</td>")
        self.assertRegex(html, r"2026-11-29</time></td>\s*<td>1</td>\s*<td>Current \(incomplete\)</td>")
        self.assertIn("Individual Exercise Progression", html)
        self.assertIn("Personal Records", html)
        self.assert_achievement(html, "heaviest-weight", "65.0", "kg", "2026-11-10")
        selected = self.dashboard_html(record_weight="40.0")
        self.assert_achievement(selected, "repetition-record", "7", "reps per set", "2026-11-24")
        self.assert_achievement(html, "highest-session-volume", "760.0", "kg", "2026-11-24")
        self.assertEqual(self.exercise_points(html), ["2026-11-10 · 65.0 kg", "2026-11-24 · 40.0 kg"])
        self.assertEqual(self.exercise_points(self.metric_html("reps"))[-1], "2026-11-24 · 12 reps")
        self.assertEqual(self.exercise_points(self.metric_html("volume"))[-1], "2026-11-24 · 760.0 kg")
        self.assertNotIn("Other name", html)
        self.assertNotIn("99.0 kg", html)
        self.assertEqual(self.storage_path.read_bytes(), before)

    def test_unweighted_records_keep_reps_without_zero_best_achievements(self):
        self.save_workout(
            "W1", "2026-11-24T08:00:00-05:00", LoggedExercise("E1", "Pushups", 2, 12, 0.0),
        )
        html = self.client.get("/progress/analytics").get_data(as_text=True)
        for metric, value in (("weight", "0.0 kg"), ("volume", "0.0 kg"), ("reps", "12 reps")):
            with self.subTest(metric=metric):
                selected = self.metric_html(metric)
                self.assertEqual(self.exercise_points(selected), [f"2026-11-24 · {value}"])
                self.assertEqual("Every recorded value for this metric is zero" in selected, metric != "reps")
        self.assert_achievement(html, "repetition-record", "12", "reps per set", "2026-11-24")
        self.assertIn("Unweighted (0 kg external weight)", html)
        self.assertNotIn('id="record-weight"', html)
        self.assertNotIn('id="heaviest-weight"', html)
        self.assertNotIn('id="highest-session-volume"', html)

    def test_page_refreshes_after_save_and_preserves_equal_best_after_another_save(self):
        self.assertEqual(self.submit_workout("2026-11-24T08:00:00-05:00", "42.5").status_code, 303)
        first = self.client.get("/progress/analytics").get_data(as_text=True)
        self.assertEqual(self.column_values(self.chart(first), "weekly-value"), ["1"])
        self.assertEqual(self.exercise_points(first), ["2026-11-24 · 42.5 kg"])
        self.assertEqual(self.submit_workout("2026-11-25T08:00:00-05:00", "50").status_code, 303)
        improved = self.client.get("/progress/analytics").get_data(as_text=True)
        self.assertEqual(self.column_values(self.chart(improved), "weekly-value"), ["2"])
        self.assertEqual(self.exercise_points(improved), ["2026-11-24 · 42.5 kg", "2026-11-25 · 50.0 kg"])
        self.assert_achievement(improved, "heaviest-weight", "50.0", "kg", "2026-11-25")
        self.assertEqual(self.submit_workout("2026-11-25T09:00:00-05:00", "50").status_code, 303)
        tied = self.client.get("/progress/analytics").get_data(as_text=True)
        self.assertEqual(self.column_values(self.chart(tied), "weekly-value"), ["2"])
        self.assertEqual(self.exercise_points(self.metric_html("volume"))[-1], "2026-11-25 · 1400.0 kg")
        self.assert_achievement(tied, "highest-session-volume", "700.0", "kg", "2026-11-25")

    def test_equal_best_on_later_date_and_invalid_post_leave_achievement_and_data_intact(self):
        self.assertEqual(self.submit_workout("2026-11-24T08:00:00-05:00", "42.5").status_code, 303)
        self.assertEqual(self.submit_workout("2026-11-25T08:00:00-05:00", "42.5").status_code, 303)
        dashboard = self.client.get("/progress/analytics")
        html = dashboard.get_data(as_text=True)
        self.assert_achievement(html, "heaviest-weight", "42.5", "kg", "2026-11-24")
        self.assert_achievement(html, "highest-session-volume", "595.0", "kg", "2026-11-24")
        self.assert_achievement(html, "repetition-record", "7", "reps per set", "2026-11-24")
        before = self.storage_path.read_bytes()
        self.assertEqual(self.submit_workout("2026-11-25T09:00:00-05:00", "99", sets="-1").status_code, 400)
        self.assertEqual(self.client.get("/progress/analytics").data, dashboard.data)
        self.assertEqual(self.storage_path.read_bytes(), before)

    def test_storage_and_calculation_failures_render_safe_error_page(self):
        self.storage_path.write_bytes(b"[broken")
        for failure in ("corrupted storage", "volume overflow"):
            with self.subTest(failure=failure):
                if failure == "volume overflow":
                    self.storage_path.write_text("[]", encoding="utf-8")
                    self.save_workout("W1", "2026-11-24T08:00:00-05:00",
                                      LoggedExercise("E1", "Hidden exercise", 2, 7, 1e308))
                before = self.storage_path.read_bytes()
                with self.assertLogs(self.app.logger, level="ERROR") as logger:
                    response = self.client.get("/progress/analytics")
                self.assertEqual(response.status_code, 500)
                self.assertIn("Could not calculate student progress", logger.output[0])
                self.assertIn(b"Your progress could not be loaded.", response.data)
                self.assertIn(b'aria-label="Progress navigation"', response.data)
                for private in (b"No completed workouts yet", str(self.storage_path).encode(),
                                b"Hidden exercise", b"finite float range", b"Traceback"):
                    self.assertNotIn(private, response.data)
                self.assertEqual(self.storage_path.read_bytes(), before)

    def test_one_week_with_seven_active_days_reaches_top_of_fixed_scale(self):
        exercise = LoggedExercise("E1", "Press", 1, 5, 40.0)
        for day in range(16, 23):
            self.save_workout(f"W{day}", f"2026-11-{day}T08:00:00-05:00", exercise)
        service = self.app.extensions["progress_service"]
        result = calculate_student_analytics(
            "ST001", self.repository.get_by_student("ST001"),
            as_of=datetime.fromisoformat("2026-11-22T12:00:00-05:00"),
        )
        with patch.object(service, "get_analytics", return_value=result):
            response = self.client.get("/progress/analytics")

        chart = self.chart(response.get_data(as_text=True))
        self.assertEqual(self.column_values(chart, "weekly-date"), ["2026-11-16"])
        self.assertEqual(self.column_values(chart, "weekly-value"), ["7"])
        ticks = chart.findall(f"{SVG}text[@class='weekly-scale']")
        self.assertEqual([tick.text for tick in ticks], list("01234567"))
        bar = chart.find(f"{SVG}g/{SVG}rect")
        grid = chart.findall(f"{SVG}line")
        self.assertEqual(bar.get("y"), grid[-1].get("y1"))
        self.assertEqual(int(bar.get("y")) + int(bar.get("height")), int(grid[0].get("y1")))

    def test_chart_reports_partial_selection_and_zero_day_current_week(self):
        self.save_workout("W1", "2026-11-17T08:00:00-05:00", LoggedExercise("E1", "Press", 1, 5, 40.0))
        result = calculate_student_analytics(
            "ST001", self.repository.get_by_student("ST001"),
            start_date=date(2026, 11, 17), end_date=date(2026, 11, 25),
            as_of=datetime.fromisoformat("2026-11-25T12:00:00-05:00"),
        )
        with patch.object(self.app.extensions["progress_service"], "get_analytics", return_value=result):
            html = self.client.get("/progress/analytics").get_data(as_text=True)
        chart = self.chart(html)
        self.assertEqual(self.column_values(chart, "weekly-value"), ["1", "0"])
        current = chart.find(f"{SVG}g[@class='weekly-column weekly-current weekly-partial']")
        self.assertIsNotNone(current)
        self.assertIsNotNone(current.find(f"{SVG}line[@class='weekly-zero']"))
        self.assertEqual(self.column_values(chart, "weekly-status"),
                         ["Partial selection", "Current week", "Partial selection"])
        self.assertIn("Current (incomplete) · Partial selection", html)

    def test_long_history_uses_scroll_region_and_preserves_bar_and_label_spacing(self):
        exercise = LoggedExercise("E1", "Press", 1, 5, 40.0)
        first_monday = date(2025, 11, 24)
        for index in range(53):
            monday = first_monday + timedelta(weeks=index)
            self.save_workout(f"W{index}", f"{monday}T08:00:00-05:00", exercise)

        html = self.client.get("/progress/analytics").get_data(as_text=True)
        chart = self.chart(html)
        self.assertIn('class="weekly-chart-scroll" role="region"', html)
        self.assertIn('tabindex="0"', html)
        bars = chart.findall(f"{SVG}g/{SVG}rect")
        self.assertEqual(len(bars), 53)
        self.assertEqual({bar.get("width") for bar in bars}, {bars[0].get("width")})
        self.assertGreater(int(bars[-1].get("x")), 1300)
        self.assertGreater(int(chart.get("width")), int(bars[-1].get("x")) + int(bars[-1].get("width")))
        self.assertEqual(self.column_values(chart, "weekly-date")[::52], ["2025-11-24", "2026-11-23"])

    def test_exercise_selection_keeps_duplicate_names_separate_and_ignores_unavailable_ids(self):
        self.save_workout(
            "W1", "2026-11-24T08:00:00-05:00",
            LoggedExercise("E2", "Press", 1, 8, 24.5),
            LoggedExercise("E1", "Press", 1, 6, 41.5),
        )
        self.save_workout(
            "W2", "2026-11-25T08:00:00-05:00",
            LoggedExercise("OTHER", "Other student's exercise", 1, 14, 77.0), student_id="ST002",
        )
        before = self.storage_path.read_bytes()
        default = self.metric_html("weight")
        self.assertIn('<option value="E1" selected>Press (E1)</option>', default)
        self.assertIn('<option value="E2">Press (E2)</option>', default)
        self.assertNotIn("OTHER", default)
        self.assertEqual(self.exercise_points(default), ["2026-11-24 · 41.5 kg"])

        selected = self.metric_html("reps", "E2")
        self.assertIn('<option value="E2" selected>Press (E2)</option>', selected)
        self.assertIn('<option value="reps" selected>Repetitions</option>', selected)
        self.assertEqual(self.exercise_points(selected), ["2026-11-24 · 8 reps"])
        self.assertEqual(self.exercise_points(self.metric_html("weight", "E2")), ["2026-11-24 · 24.5 kg"])
        self.assertEqual(self.metric_html("<bogus>", "OTHER"), default)
        self.assertEqual(self.storage_path.read_bytes(), before)

    def test_exercise_chart_spaces_irregular_dates_and_preserves_constant_values(self):
        for index, day in enumerate((25, 21, 22)):
            self.save_workout(
                f"W{index}", f"2026-11-{day}T08:00:00-05:00",
                LoggedExercise("E1", "Press", 1, 8, 41.25),
            )
        html = self.metric_html("weight")
        chart = self.chart(html, "exercise-chart")
        self.assertEqual(self.exercise_points(html), [
            "2026-11-21 · 41.25 kg", "2026-11-22 · 41.25 kg", "2026-11-25 · 41.25 kg",
        ])
        points = chart.findall(f"{SVG}circle")
        x1, x2, x3 = [float(point.get("cx")) for point in points]
        self.assertAlmostEqual(x3 - x2, 3 * (x2 - x1))
        self.assertEqual(len({point.get("cy") for point in points}), 1)
        self.assertIsNotNone(chart.find(f"{SVG}polyline"))
        self.assertIn('<summary>View exercise data</summary>', html)
        self.assertIn("<td>41.25</td>", html)

    def test_single_zero_point_and_extreme_finite_axis_have_valid_coordinates(self):
        self.save_workout(
            "W1", "2026-11-24T08:00:00-05:00",
            LoggedExercise("E1", "Unweighted", 1, 8, 0.0),
            LoggedExercise("E2", "Test load", 1, 1, 1.7e308),
        )
        for exercise, metric, value in (
            ("E1", "weight", "0.0 kg"), ("E1", "volume", "0.0 kg"),
            ("E2", "weight", "1.7e+308 kg"),
        ):
            with self.subTest(exercise=exercise, metric=metric):
                html = self.metric_html(metric, exercise)
                chart = self.chart(html, "exercise-chart")
                point, = chart.findall(f"{SVG}circle")
                baseline = chart.find(f"{SVG}line[@class='exercise-gridline exercise-baseline']")
                self.assertGreater(float(point.get("cx")), 0)
                self.assertGreaterEqual(float(point.get("cy")), 0)
                self.assertLessEqual(float(point.get("cy")), float(baseline.get("y1")))
                if exercise == "E1":
                    self.assertEqual(float(point.get("cy")), float(baseline.get("y1")))
                self.assertIsNone(chart.find(f"{SVG}polyline"))
                self.assertEqual(self.exercise_points(html), [f"2026-11-24 · {value}"])
                if exercise == "E2":
                    scientific_ticks = [
                        tick for tick in chart.findall(f"{SVG}text[@text-anchor='end']")
                        if "E" in tick.text
                    ]
                    self.assertTrue(scientific_ticks)
                    for tick in scientific_ticks:
                        self.assertGreaterEqual(int(tick.get("x")), 8 + 9 * len(tick.text))

    def test_missing_exercise_data_preserves_logging_link_and_weekly_chart(self):
        self.save_workout(
            "W1", "2026-11-24T08:00:00-05:00", LoggedExercise("E1", "Press", 1, 8, 41.25),
        )
        service = self.app.extensions["progress_service"]
        analytics = replace(service.get_analytics("ST001"), exercise_progression=())
        with patch.object(service, "get_analytics", return_value=analytics):
            html = self.metric_html("weight")
        self.assertIn("No eligible exercise performances were found.", html)
        self.assertIn('href="/progress/">Log Workout</a>', html)
        self.assertIn('class="weekly-chart"', html)
        self.assertNotIn('class="exercise-chart"', html)

    def test_metric_views_refresh_same_day_aggregates_after_logging(self):
        self.assertEqual(self.submit_workout("2026-11-25T08:00:00-05:00", "43.5").status_code, 303)
        self.assertEqual(self.submit_workout("2026-11-25T09:00:00-05:00", "50", reps="4").status_code, 303)
        self.assertEqual(self.submit_workout("2026-11-25T10:00:00-05:00", "20", reps="12").status_code, 303)

        before = self.storage_path.read_bytes()
        expected = {"weight": "50.0 kg", "reps": "12 reps", "volume": "1489.0 kg"}
        for metric, value in expected.items():
            with self.subTest(metric=metric):
                self.assertEqual(self.exercise_points(self.metric_html(metric, "EX001")),
                                 [f"2026-11-25 · {value}"])
        self.assertEqual(self.submit_workout("2026-11-25T11:00:00-05:00", "99", sets="-1").status_code, 400)
        self.assertEqual(self.exercise_points(self.metric_html("volume", "EX001")), ["2026-11-25 · 1489.0 kg"])
        self.assertEqual(self.storage_path.read_bytes(), before)

    def test_exercise_labels_are_escaped_in_svg_controls_and_data_table(self):
        exercise_name = "</title><script>alert(1)</script> & Press"
        exercise_id = 'EX"><img src=x>'
        self.save_workout(
            "W1", "2026-11-24T08:00:00-05:00", LoggedExercise(exercise_id, exercise_name, 1, 8, 41.25),
        )
        html = self.metric_html("weight", exercise_id)
        chart = self.chart(html, "exercise-chart")
        self.assertTrue(chart.find(f"{SVG}title").text.startswith(exercise_name))
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertIn("EX&#34;&gt;&lt;img src=x&gt;", html)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img src=x>", html)

    def test_record_selection_separates_duplicate_exercises_and_validates_weight(self):
        self.save_workout(
            "W1", "2026-11-25T02:00:00+00:00",
            LoggedExercise("E1", "Press", 1, 5, 40.125),
            LoggedExercise("E1", "Press", 1, 8, 40.25),
            LoggedExercise("E1", "Press", 1, 20, 0.0),
            LoggedExercise("E2", "Press", 1, 6, 20.5),
        )
        self.save_workout(
            "W2", "2026-11-24T08:00:00-05:00",
            LoggedExercise("OTHER", "Private exercise", 1, 15, 90.0), student_id="ST002",
        )
        before = self.storage_path.read_bytes()
        html = self.dashboard_html(record_exercise="E1", record_weight="40.125")
        section = self.records_section(html)
        self.assertIn('<option value="E1" selected>Press (E1)</option>', section)
        self.assertIn('<option value="E2">Press (E2)</option>', section)
        self.assertIn('<option value="40.125" selected>40.125 kg</option>', section)
        self.assertIn('<option value="40.25">40.25 kg</option>', section)
        self.assertIn('<option value="0.0">Unweighted (0 kg)</option>', section)
        self.assertNotIn("Private exercise", section)
        self.assert_achievement(html, "repetition-record", "5", "reps per set", "2026-11-24")
        unweighted = self.dashboard_html(record_exercise="E1", record_weight="0.0")
        self.assert_achievement(unweighted, "repetition-record", "20", "reps per set", "2026-11-24")
        self.assert_achievement(unweighted, "heaviest-weight", "40.25", "kg", "2026-11-24")

        changed = self.dashboard_html(record_exercise="E2", record_weight="40.125")
        self.assertIn('<option value="E2" selected>Press (E2)</option>', self.records_section(changed))
        self.assertNotIn('id="record-weight"', changed)
        self.assert_achievement(changed, "repetition-record", "6", "reps per set", "2026-11-24")
        self.assert_achievement(changed, "heaviest-weight", "20.5", "kg", "2026-11-24")
        invalid = self.dashboard_html(record_exercise="OTHER", record_weight="NaN")
        self.assertEqual(invalid, self.dashboard_html())
        self.assertEqual(self.storage_path.read_bytes(), before)

    def test_dashboard_forms_preserve_other_selections_and_resolved_date_bounds(self):
        self.save_workout(
            "W1", "2026-11-24T08:00:00-05:00",
            LoggedExercise("E1", "Press", 1, 5, 40.25),
            LoggedExercise("E2", "Squat", 1, 8, 50.25),
            LoggedExercise("E2", "Squat", 1, 7, 60.5),
        )
        html = self.dashboard_html(
            period="custom", start_date="2026-11-24", end_date="2026-11-24",
            exercise="E1", metric="volume", record_exercise="E2", record_weight="50.25",
        )
        period_form, chart_form, exercise_form, weight_form = re.findall(r"<form[^>]*>.*?</form>", html, re.DOTALL)
        self.assertIn('action="/progress/analytics#analytics-period"', period_form)
        for name, value in (("exercise", "E1"), ("metric", "volume"),
                            ("record_exercise", "E2"), ("record_weight", "50.25")):
            self.assertIn(f'type="hidden" name="{name}" value="{value}"', period_form)
        for name in ("period", "start_date", "end_date"):
            self.assertEqual(period_form.count(f'name="{name}"'), 1)
        self.assertIn('action="/progress/analytics#exercise-progression"', chart_form)
        for name, value in (("record_exercise", "E2"), ("record_weight", "50.25")):
            self.assertIn(f'type="hidden" name="{name}" value="{value}"', chart_form)
        for form in (exercise_form, weight_form):
            self.assertIn('action="/progress/analytics#personal-records"', form)
            self.assertIn('type="hidden" name="exercise" value="E1"', form)
            self.assertIn('type="hidden" name="metric" value="volume"', form)
        self.assertNotIn('name="record_weight"', exercise_form)
        self.assertIn('type="hidden" name="record_exercise" value="E2"', weight_form)
        for form in (chart_form, exercise_form, weight_form):
            self.assertIn('type="hidden" name="period" value="custom"', form)
            for boundary in ("start_date", "end_date"):
                self.assertIn(f'type="hidden" name="{boundary}" value="2026-11-24"', form)
        self.assertEqual(self.exercise_points(html), ["2026-11-24 · 201.25 kg"])
        self.assert_achievement(html, "repetition-record", "8", "reps per set", "2026-11-24")

    def test_repetition_and_session_records_refresh_and_remain_after_lower_performance(self):
        self.assertEqual(self.submit_workout("2026-11-24T08:00:00-05:00", "45.5", reps="6").status_code, 303)
        query = {"record_exercise": "EX001", "record_weight": "45.5"}
        before = self.dashboard_html(**query)
        self.assert_achievement(before, "repetition-record", "6", "reps per set", "2026-11-24")
        self.assertEqual(self.submit_workout("2026-11-25T08:00:00-05:00", "45.5", reps="10").status_code, 303)
        improved = self.dashboard_html(**query)
        self.assert_achievement(improved, "heaviest-weight", "45.5", "kg", "2026-11-24")
        self.assert_achievement(improved, "repetition-record", "10", "reps per set", "2026-11-25")
        self.assert_achievement(improved, "highest-session-volume", "910.0", "kg", "2026-11-25")
        self.assertEqual(self.submit_workout("2026-11-25T09:00:00-05:00", "45.5", reps="5").status_code, 303)
        self.assertEqual(self.records_section(self.dashboard_html(**query)), self.records_section(improved))

    def test_record_option_labels_escape_dynamic_names_and_ids(self):
        exercise_id = 'EX"><img src=x>'
        name = "</option><script>alert(1)</script>"
        self.save_workout(
            "W1", "2026-11-24T08:00:00-05:00", LoggedExercise(exercise_id, name, 1, 8, 41.25),
        )
        section = self.records_section(self.dashboard_html(record_exercise=exercise_id))
        self.assertIn('value="EX&#34;&gt;&lt;img src=x&gt;" selected', section)
        self.assertIn("&lt;/option&gt;&lt;script&gt;alert(1)&lt;/script&gt;", section)
        self.assertNotIn("<script>", section)
        self.assertNotIn("<img", section)

    def test_missing_record_results_show_logging_link_without_fictional_achievements(self):
        self.save_workout(
            "W1", "2026-11-24T08:00:00-05:00", LoggedExercise("E1", "Press", 1, 8, 41.25),
        )
        service = self.app.extensions["progress_service"]
        analytics = replace(service.get_analytics("ST001"), personal_records=())
        with patch.object(service, "get_analytics", return_value=analytics):
            html = self.dashboard_html()
        section = self.records_section(html)
        self.assertIn("No eligible personal records yet.", section)
        self.assertIn('href="/progress/">Log Workout</a>', section)
        self.assertNotIn('id="record-exercise"', section)
        self.assertIn('class="weekly-chart"', html)
        self.assertIn('class="exercise-chart"', html)

    def test_relative_presets_include_jamaica_today_and_exact_lower_bounds(self):
        exercise = LoggedExercise("E1", "Press", 1, 5, 42.5)
        for index, timestamp in enumerate((
            "2026-10-27T04:59:59+00:00", "2026-10-27T05:00:00+00:00",
            "2026-11-19T04:59:59+00:00", "2026-11-19T05:00:00+00:00",
            "2026-11-26T03:00:00+00:00",
        )):
            self.save_workout(f"W{index}", timestamp, exercise)
        self.save_workout(
            "FUTURE", "2026-11-26T03:00:01+00:00", LoggedExercise("E1", "Press", 1, 6, 99.0),
        )
        expected = {
            "all": ["2026-10-26", "2026-10-27", "2026-11-18", "2026-11-19", "2026-11-25"],
            "last30": ["2026-10-27", "2026-11-18", "2026-11-19", "2026-11-25"],
            "last7": ["2026-11-19", "2026-11-25"],
        }
        self.assertEqual(self.dashboard_html(), self.dashboard_html(period="all"))
        for period, dates in expected.items():
            with self.subTest(period=period):
                html = self.dashboard_html(period=period)
                self.assertEqual(self.exercise_points(html), [f"{day} · 42.5 kg" for day in dates])
                if period != "all":
                    self.assertIn(f'<time datetime="{dates[0]}">{dates[0]}</time>', html)
                    self.assertIn('<time datetime="2026-11-25">2026-11-25</time>', html)
                    chart_form = re.findall(r"<form[^>]*>.*?</form>", html, re.DOTALL)[1]
                    self.assertIn(f'type="hidden" name="period" value="{period}"', chart_form)
                    self.assertNotIn('name="start_date"', chart_form)
                    self.assertNotIn('name="end_date"', chart_form)
                    self.assertIn("Reset to All time", html)

    def test_custom_and_open_ended_ranges_filter_both_charts_with_partial_and_gap_weeks(self):
        for index, day in enumerate(("2026-11-09", "2026-11-11", "2026-11-24", "2026-11-25")):
            self.save_workout(
                f"W{index}", f"{day}T08:00:00-05:00", LoggedExercise("E1", "Press", 1, 5, 42.5),
            )
        html = self.dashboard_html(period="custom", start_date="2026-11-11", end_date="2026-11-24")
        self.assertEqual(self.exercise_points(html), ["2026-11-11 · 42.5 kg", "2026-11-24 · 42.5 kg"])
        chart = self.chart(html)
        self.assertEqual(self.column_values(chart, "weekly-value"), ["1", "0", "1"])
        self.assertEqual(self.column_values(chart, "weekly-status"),
                         ["Partial selection", "Current week", "Partial selection"])
        self.assertIn("Current (incomplete) · Partial selection", html)
        self.assertEqual(self.exercise_points(self.dashboard_html(period="custom", start_date="2026-11-24")),
                         ["2026-11-24 · 42.5 kg", "2026-11-25 · 42.5 kg"])
        self.assertEqual(self.exercise_points(self.dashboard_html(period="custom", end_date="2026-11-11")),
                         ["2026-11-09 · 42.5 kg", "2026-11-11 · 42.5 kg"])

    def test_invalid_filters_show_actionable_feedback_without_accessing_storage(self):
        service = self.app.extensions["progress_service"]
        cases = (
            ({"period": "unknown"}, "Choose an available period"),
            ({"period": "custom"}, "Enter a start date, an end date, or both"),
            ({"period": "custom", "start_date": "20261111"}, "Enter a valid start date"),
            ({"period": "custom", "end_date": "2026-11-31"}, "Enter a valid end date"),
            ({"period": "custom", "start_date": "2026-11-25", "end_date": "2026-11-24"},
             "The start date must be on or before the end date"),
        )
        with patch.object(service, "get_analytics") as get_analytics:
            for query, message in cases:
                with self.subTest(query=query):
                    response = self.client.get("/progress/analytics", query_string={**query, "metric": "reps"})
                    self.assertEqual(response.status_code, 400)
                    html = response.get_data(as_text=True)
                    self.assertIn(message, html)
                    self.assertIn('role="alert"', html)
                    self.assertIn("Reset to All time", html)
                    self.assertIn('name="metric" value="reps"', html)
                    self.assertNotIn("<strong>Applied:</strong>", html)
                    self.assertNotIn("<svg", html)
            get_analytics.assert_not_called()

    def test_period_and_exercise_empty_states_keep_all_time_records_and_validate_owner(self):
        self.save_workout(
            "W1", "2026-11-09T08:00:00-05:00",
            LoggedExercise("E1", "Press", 1, 5, 50.25),
            LoggedExercise("E1", "Press", 1, 8, 0.0),
        )
        self.save_workout("W2", "2026-11-24T08:00:00-05:00", LoggedExercise("E2", "Squat", 1, 6, 80.0))
        self.save_workout("OTHER", "2026-11-17T08:00:00-05:00",
                          LoggedExercise("E3", "Other student", 1, 10, 200.0), student_id="ST002")
        query = {"exercise": "E1", "metric": "volume", "record_exercise": "E1", "record_weight": "0.0"}
        first = self.dashboard_html(**query)
        before = self.storage_path.read_bytes()
        for start, end, expect_gap_week, expect_empty in (
            ("2026-11-16", "2026-11-22", True, True),
            ("2026-11-24", "2026-11-25", False, False),
            ("2026-11-01", "2026-11-03", False, True),
        ):
            html = self.dashboard_html(period="custom", start_date=start, end_date=end,
                                       student_id="ST002", **query)
            self.assertEqual("No workouts were recorded in the selected period." in html, expect_empty)
            self.assertNotIn('class="exercise-chart"', html)
            self.assertIn('<option value="E1" selected>Press</option>', html)
            self.assertIn("<h3>Press</h3>", html)
            self.assertIn("No performances for this exercise were recorded in the selected period.", html)
            self.assertNotIn("Other student", html)
            self.assert_achievement(html, "repetition-record", "8", "reps per set", "2026-11-09")
            self.assert_achievement(html, "heaviest-weight", "50.25", "kg", "2026-11-09")
            if expect_gap_week:
                self.assertEqual(self.column_values(self.chart(html), "weekly-value"), ["0"])
        self.assertEqual(self.exercise_points(first), ["2026-11-09 · 251.25 kg"])
        self.assertEqual(self.storage_path.read_bytes(), before)

    def test_logging_refreshes_in_range_charts_and_all_time_records_on_each_request(self):
        query = {"period": "custom", "start_date": "2026-11-24", "end_date": "2026-11-24"}
        self.assertEqual(self.submit_workout("2026-11-24T08:00:00-05:00", "42.5").status_code, 303)
        first = self.dashboard_html(**query)
        self.assertEqual(self.column_values(self.chart(first), "weekly-value"), ["1"])
        self.assertEqual(self.exercise_points(first), ["2026-11-24 · 42.5 kg"])
        self.assert_achievement(first, "heaviest-weight", "42.5", "kg", "2026-11-24")
        self.assertEqual(self.submit_workout("2026-11-25T08:00:00-05:00", "50.25").status_code, 303)
        outside = self.dashboard_html(**query)
        self.assertEqual(self.column_values(self.chart(outside), "weekly-value"), ["1"])
        self.assertEqual(self.exercise_points(outside), self.exercise_points(first))
        self.assert_achievement(outside, "heaviest-weight", "50.25", "kg", "2026-11-25")
        included = self.dashboard_html(period="last7")
        self.assertEqual(self.column_values(self.chart(included), "weekly-value"), ["2"])
        self.assertEqual(self.exercise_points(included), ["2026-11-24 · 42.5 kg", "2026-11-25 · 50.25 kg"])
        before = self.storage_path.read_bytes()
        self.assertEqual(self.submit_workout("2026-11-25T09:00:00-05:00", "99", sets="-1").status_code, 400)
        with patch.object(WorkoutLogRepository, "save", side_effect=WorkoutLogStorageError("test")):
            with self.assertLogs(self.app.logger, level="ERROR"):
                self.assertEqual(self.submit_workout("2026-11-25T09:00:00-05:00", "99").status_code, 500)
        self.assertEqual(self.dashboard_html(period="last7"), included)
        self.assertEqual(self.storage_path.read_bytes(), before)
