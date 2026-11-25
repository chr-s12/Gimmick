import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app import create_app
from progress.models import LoggedExercise, WorkoutLog
from progress.repository import WorkoutLogRepository
from progress.service import ProgressService


class WorkoutHistoryTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.storage_path = Path(directory) / "workouts.json"
        self.config = {"TESTING": True, "WORKOUT_STORAGE_PATH": self.storage_path}
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.repository = WorkoutLogRepository(self.storage_path)

    def save_workout(
        self, workout_id, routine_name, completed_at="2026-11-25T15:00:00+00:00",
        student_id="ST001",
    ):
        workout = WorkoutLog(
            workout_id, student_id, "RT001", routine_name,
            datetime.fromisoformat(completed_at),
            [LoggedExercise("EX001", "Recorded Press", 2, 7, 23.5)],
        )
        self.repository.save(workout)
        return workout

    def test_empty_history_links_to_routines_without_creating_storage(self):
        response = self.client.get("/progress/history")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"You have no completed workouts yet.", response.data)
        self.assertIn(b'href="/progress/"', response.data)
        self.assertFalse(self.storage_path.exists())

    def test_history_orders_by_instant_across_offsets_and_keeps_saved_ties(self):
        older = self.save_workout("W1", "Older", "2026-11-25T13:00:00+02:00")
        newer = self.save_workout("W2", "Newer", "2026-11-25T08:00:00-05:00")
        tied = self.save_workout("W3", "Same instant", "2026-11-25T13:00:00+00:00")
        service = ProgressService(self.repository)
        self.assertEqual(service.get_workout_history("ST001"), [newer, tied, older])
        self.assertEqual(self.repository.get_by_student("ST001"), [older, newer, tied])
        data = self.client.get("/progress/history").data
        positions = [data.index(f'>{name}</h2>'.encode()) for name in ("Newer", "Same instant", "Older")]
        self.assertEqual(positions, sorted(positions))
        self.assertIn(b"2026-11-25 08:00:00 Jamaica time", data)
        self.assertIn(b"Completed exercises: 1", data)

    def test_history_and_summary_display_previous_jamaica_day_after_utc_midnight(self):
        completed_at = "2026-11-25T02:30:00+00:00"
        self.save_workout("W1", "Evening Workout", completed_at)
        saved = self.storage_path.read_bytes()
        for path in ("/progress/history", "/progress/workouts/W1"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(
                    b'<time datetime="2026-11-25T02:30:00+00:00">'
                    b'2026-11-24 21:30:00 Jamaica time</time>',
                    response.data,
                )
        self.assertEqual(self.storage_path.read_bytes(), saved)

    def test_history_handles_offset_timestamp_at_datetime_boundary(self):
        self.save_workout("W1", "Boundary workout", "0001-01-01T00:00:00+01:00")
        self.save_workout("W2", "Later workout", "0001-01-01T00:00:00+00:00")

        response = self.client.get("/progress/history")
        self.assertEqual(response.status_code, 200)
        self.assertLess(
            response.data.index(b"Later workout"), response.data.index(b"Boundary workout")
        )

        self.assertIn(b"0001-01-01 00:00:00+01:00", response.data)
        self.assertIn(b"0001-01-01 00:00:00+00:00", response.data)

    def test_history_and_summary_are_scoped_to_current_student(self):
        self.save_workout("W1", "My workout")
        self.save_workout("W2", "Other workout", student_id="ST002")
        response = self.client.get("/progress/history")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"My workout", response.data)
        self.assertNotIn(b"Other workout", response.data)
        self.assertNotIn(b"/progress/workouts/W2", response.data)
        self.assertEqual(self.client.get("/progress/workouts/W2").status_code, 404)

    def test_navigation_connects_dashboard_history_and_summary(self):
        self.save_workout("W1", "Recorded Routine")
        dashboard = self.client.get("/progress/")
        history = self.client.get("/progress/history")
        summary = self.client.get("/progress/workouts/W1")
        self.assertIn(b'href="/progress/history"', dashboard.data)
        self.assertIn(b'href="/progress/"', history.data)
        self.assertIn(b'href="/progress/workouts/W1"', history.data)
        self.assertEqual(summary.status_code, 200)
        self.assertIn(b'href="/progress/history"', summary.data)

    def test_removed_routine_does_not_affect_history_or_summary(self):
        self.save_workout("W1", "Original Routine")
        with patch("progress.routes.get_student_routine", return_value=None):
            self.assertEqual(self.client.get("/progress/log/RT001").status_code, 404)
            history = self.client.get("/progress/history")
            summary = self.client.get("/progress/workouts/W1")
        self.assertEqual(history.status_code, 200)
        self.assertIn(b"Original Routine", history.data)
        self.assertEqual(summary.status_code, 200)
        self.assertIn(b"Recorded Press", summary.data)
        self.assertIn(b"<td>23.5</td>", summary.data)

    def test_submitted_workout_appears_in_history_after_fresh_app_creation(self):
        form = {
            f"{field}_{index}": value
            for index in range(3)
            for field, value in (("sets", "2"), ("reps", "7"), ("weight", "23.5"))
        }
        submitted = self.client.post("/progress/log/RT001", data=form)
        self.assertEqual(submitted.status_code, 303)
        for client in (self.client, create_app(self.config).test_client()):
            history = client.get("/progress/history")
            self.assertEqual(history.status_code, 200)
            self.assertIn(submitted.location.encode(), history.data)
            self.assertIn(b"<td>23.5</td>", client.get(submitted.location).data)

    def test_refreshing_history_leaves_storage_untouched(self):
        self.save_workout("W1", "Original Routine")
        before = self.storage_path.read_bytes()
        with patch("progress.repository.os.replace") as replace_storage:
            for _ in range(2):
                self.assertEqual(self.client.get("/progress/history").status_code, 200)
        replace_storage.assert_not_called()
        self.assertEqual(self.storage_path.read_bytes(), before)

    def test_corrupt_storage_returns_generic_error_and_is_preserved(self):
        contents = b"[broken"
        self.storage_path.write_bytes(contents)
        with self.assertLogs(self.app.logger, level="ERROR"):
            response = self.client.get("/progress/history")
        self.assertEqual(response.status_code, 500)
        self.assertIn(b"Your workout history could not be loaded.", response.data)
        self.assertNotIn(b"You have no completed workouts yet.", response.data)
        self.assertNotIn(str(self.storage_path).encode(), response.data)
        self.assertEqual(self.storage_path.read_bytes(), contents)
