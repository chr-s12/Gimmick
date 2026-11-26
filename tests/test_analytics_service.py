import unittest
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app import create_app
from progress.analytics import StudentProgressAnalytics
from progress.models import LoggedExercise, WorkoutLog
from progress.repository import WorkoutLogRepository, WorkoutLogStorageError
from progress.service import ProgressService


class ProgressAnalyticsServiceTests(unittest.TestCase):
    as_of = datetime.fromisoformat("2026-11-25T12:00:00-05:00")

    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.path = Path(directory) / "workouts.json"
        self.repository = WorkoutLogRepository(self.path)
        self.service = ProgressService(self.repository)
        self.routine = {
            "student_id": "ST001",
            "routine_id": "RT001",
            "routine_name": "Upper Body",
            "exercises": [{"exercise_id": "E1", "exercise_name": "Press"}],
        }

    def workout(self, workout_id, completed_at, weight=42.5, student="ST001"):
        return WorkoutLog(
            workout_id, student, "RT001", "Upper Body",
            datetime.fromisoformat(completed_at),
            [LoggedExercise("E1", "Press", 2, 7, weight)],
        )

    def get_analytics(self, student_id="ST001", **bounds):
        return self.service.get_analytics(student_id, as_of=self.as_of, **bounds)

    def log_workout(self, completed_at, weight):
        form = {"sets_0": "2", "reps_0": "7", "weight_0": str(weight)}
        with patch("progress.service.datetime") as clock:
            clock.now.return_value = datetime.fromisoformat(completed_at)
            return self.service.log_workout("ST001", self.routine, form)

    def test_empty_store_returns_empty_analytics_without_creating_file(self):
        result = self.get_analytics()
        self.assertIsInstance(result, StudentProgressAnalytics)
        self.assertEqual((result.student_id, result.as_of), ("ST001", self.as_of))
        self.assertFalse(result.has_workouts)
        self.assertFalse(result.has_workouts_in_period)
        self.assertEqual(
            (result.weekly_consistency, result.exercise_progression, result.personal_records),
            ((), (), ()),
        )
        self.assertFalse(self.path.exists())

    def test_saved_analytics_are_scoped_to_the_requested_student_and_read_only(self):
        self.repository.save(self.workout("W1", "2026-11-24T08:00:00-05:00", 40.0))
        self.repository.save(self.workout("W2", "2026-11-25T08:00:00-05:00", 99.0, "ST002"))
        before = self.path.read_bytes()
        for student, day, weight in (("ST001", 24, 40.0), ("ST002", 25, 99.0)):
            with self.subTest(student=student):
                result = self.get_analytics(student)
                self.assertEqual(result.student_id, student)
                self.assertEqual(result.weekly_consistency[0].active_dates, (date(2026, 11, day),))
                series, = result.exercise_progression
                point, = series.daily_history
                self.assertEqual(point.max_weight_kg, weight)
                self.assertEqual(result.personal_records[0].heaviest_weight.value, weight)
        self.assertEqual(self.path.read_bytes(), before)

    def test_date_filter_keeps_all_time_records_and_distinguishes_empty_period(self):
        self.repository.save(self.workout("W1", "2026-11-17T08:00:00-05:00", 60.0))
        self.repository.save(self.workout("W2", "2026-11-24T08:00:00-05:00", 40.0))
        self.repository.save(self.workout("W3", "2026-11-25T12:00:01-05:00", 90.0))
        day = date(2026, 11, 24)
        selected = self.get_analytics(start_date=day, end_date=day)
        self.assertTrue(selected.has_workouts_in_period)
        week, = selected.weekly_consistency
        self.assertEqual(week.active_dates, (day,))
        self.assertTrue(week.is_partial_week)
        self.assertTrue(week.is_current_week)
        self.assertEqual(selected.exercise_progression[0].daily_history[0].max_weight_kg, 40.0)
        self.assertEqual(selected.personal_records[0].heaviest_weight.value, 60.0)

        empty = self.get_analytics(start_date=date(2026, 11, 25))
        self.assertTrue(empty.has_workouts)
        self.assertFalse(empty.has_workouts_in_period)
        self.assertEqual(empty.weekly_consistency[0].active_days, 0)
        self.assertEqual(empty.exercise_progression, ())
        self.assertEqual(empty.personal_records, selected.personal_records)

    def test_successive_logs_refresh_all_metrics_and_equal_bests_keep_first_date(self):
        first = self.log_workout("2026-11-24T08:00:00-05:00", 40.0)
        baseline = self.get_analytics()
        best = self.log_workout("2026-11-25T08:00:00-05:00", 45.0)
        improved = self.get_analytics()
        self.log_workout("2026-11-25T10:00:00-05:00", 45.0)
        tied = self.get_analytics()

        self.assertEqual(baseline.weekly_consistency[0].active_days, 1)
        self.assertEqual(baseline.personal_records[0].heaviest_weight.workout_id, first.workout_id)
        self.assertEqual(improved.weekly_consistency[0].active_days, 2)
        self.assertEqual(tied.weekly_consistency, improved.weekly_consistency)
        points = tied.exercise_progression[0].daily_history
        self.assertEqual([point.max_weight_kg for point in points], [40.0, 45.0])
        self.assertEqual(points[-1].total_volume_kg, 1260.0)
        self.assertEqual(improved.personal_records, tied.personal_records)
        records, = tied.personal_records
        self.assertEqual(records.heaviest_weight.workout_id, best.workout_id)
        self.assertEqual(records.repetition_records[-1].workout_id, best.workout_id)
        self.assertEqual(records.highest_session_volume.value, 630.0)
        self.assertEqual(records.highest_session_volume.workout_id, best.workout_id)
        self.assertEqual(records.highest_session_volume.achieved_date, date(2026, 11, 25))

    def test_invalid_and_unowned_logging_leave_storage_and_analytics_unchanged(self):
        self.repository.save(self.workout("W1", "2026-11-24T08:00:00-05:00"))
        expected = self.get_analytics()
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "invalid workout"):
            self.service.log_workout("ST001", self.routine, {"weight_0": "-1"})
        with self.assertRaisesRegex(ValueError, "does not belong"):
            self.service.log_workout(
                "ST002", self.routine, {"sets_0": "2", "reps_0": "6", "weight_0": "40"},
            )
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.get_analytics(), expected)

    def test_failed_save_preserves_previous_analytics(self):
        self.repository.save(self.workout("W1", "2026-11-24T08:00:00-05:00"))
        expected = self.get_analytics()
        before = self.path.read_bytes()
        with patch("progress.repository.os.replace", side_effect=OSError("simulated failure")):
            with self.assertRaisesRegex(WorkoutLogStorageError, "Cannot write"):
                self.log_workout("2026-11-25T08:00:00-05:00", 50.0)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.get_analytics(), expected)

    def test_corrupt_storage_propagates_error_without_replacing_bytes(self):
        original = b"[broken"
        self.path.write_bytes(original)
        with self.assertRaisesRegex(WorkoutLogStorageError, "Cannot read"):
            self.get_analytics()
        self.assertEqual(self.path.read_bytes(), original)

    def test_calculation_errors_propagate_and_successful_save_needs_no_analytics(self):
        with self.assertRaisesRegex(ValueError, "start_date.*on or before"):
            self.get_analytics(start_date=date(2026, 11, 25), end_date=date(2026, 11, 24))

        # Valid logging can succeed even when a derived metric exceeds float range.
        workout = self.log_workout("2026-11-24T08:00:00-05:00", 1e308)
        self.assertEqual(self.repository.get_by_id("ST001", workout.workout_id), workout)
        with self.assertRaisesRegex(ValueError, "finite float range"):
            self.get_analytics()

    def test_mixed_student_result_from_repository_is_still_rejected(self):
        other = self.workout("W2", "2026-11-24T08:00:00-05:00", student="ST002")
        with patch.object(self.repository, "get_by_student", return_value=[other]) as load:
            with self.assertRaisesRegex(ValueError, "W2 does not belong to student 'ST001'"):
                self.get_analytics()
        load.assert_called_once_with("ST001")

    def test_existing_flask_save_is_visible_in_fresh_app_service(self):
        config = {"TESTING": True, "WORKOUT_STORAGE_PATH": self.path}
        app = create_app(config)
        form = {
            f"{field}_{index}": value
            for index in range(3)
            for field, value in (("sets", "2"), ("reps", "7"), ("weight", "42.5"))
        }
        with patch("progress.service.datetime") as clock:
            clock.now.return_value = datetime.fromisoformat("2026-11-24T08:00:00-05:00")
            response = app.test_client().post("/progress/log/RT001", data=form)
        self.assertEqual(response.status_code, 303)
        original = app.extensions["progress_service"].get_analytics("ST001", as_of=self.as_of)
        fresh = create_app(config).extensions["progress_service"]
        self.assertTrue(original.has_workouts_in_period)
        self.assertEqual(fresh.get_analytics("ST001", as_of=self.as_of), original)
