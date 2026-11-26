import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import UUID

from app import create_app
from progress.mock_dependencies import get_student, get_student_routine, get_student_routines
from progress.models import LoggedExercise, WorkoutLog
from progress.repository import WorkoutLogRepository, WorkoutLogStorageError
from progress.service import ProgressService


class MockDependencyTests(unittest.TestCase):
    def test_student_lookup(self):
        self.assertEqual(get_student("ST001")["username"], "Alex")
        self.assertEqual(get_student("ST002")["username"], "Jordan")
        self.assertIsNone(get_student("unknown"))

    def test_routines_are_filtered_by_student(self):
        self.assertEqual(
            [routine["routine_id"] for routine in get_student_routines("ST001")],
            ["RT001", "RT002"],
        )
        self.assertEqual(
            [routine["routine_id"] for routine in get_student_routines("ST002")],
            ["RT003"],
        )
        self.assertEqual(get_student_routines("unknown"), [])


class ProgressTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.storage_path = Path(directory) / "workouts.json"
        self.config = {"TESTING": True, "PROGRESS_FIXTURES": True, "WORKOUT_STORAGE_PATH": self.storage_path}
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.repository = WorkoutLogRepository(self.storage_path)
        self.service = ProgressService(self.repository)
        self.routine = get_student_routine("ST001", "RT001")
        self.url = "/progress/log/RT001"
        self.form = {
            f"{field}_{index}": value
            for index in range(len(self.routine["exercises"]))
            for field, value in (("sets", "2"), ("reps", "7"), ("weight", "12.5"))
        }
        self.form["weight_0"] = "0"

    def test_dashboard_renders_current_students_routines(self):
        response = self.client.get("/progress/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Welcome, Alex", response.data)
        self.assertIn(b'href="/progress/log/RT001"', response.data)
        self.assertIn(b"Full Body", response.data)
        self.assertNotIn(b"Lower Body", response.data)

    def test_root_is_the_app_home_and_needs_login(self):
        # The whole app now shares this server; its home page sends visitors to log in first.
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.startswith("/login"))

    def test_selecting_saved_routine_prefills_form(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Upper Body", response.data)
        self.assertIn(b"Bench Press", response.data)
        self.assertRegex(response.get_data(as_text=True), r'name="weight_0"\s+value="40"')

    def test_missing_routine_is_rejected(self):
        self.assertEqual(self.client.get("/progress/log/unknown").status_code, 404)
        self.assertEqual(
            self.client.post("/progress/log/unknown", data=self.form).status_code, 404
        )

    def test_other_students_routine_is_rejected(self):
        self.assertEqual(self.client.get("/progress/log/RT003").status_code, 404)
        self.assertEqual(
            self.client.post("/progress/log/RT003", data=self.form).status_code, 404
        )
        self.assertFalse(self.storage_path.exists())

    def test_valid_submission_redirects_to_saved_summary(self):
        submission = self.client.post(self.url, data=self.form)
        self.assertEqual(submission.status_code, 303)
        saved, = self.repository.get_by_student("ST001")
        self.assertEqual(
            submission.headers["Location"], f"/progress/workouts/{saved.workout_id}"
        )
        self.assertEqual(saved.exercises[0], LoggedExercise("EX001", "Bench Press", 2, 7, 0.0))
        self.assertEqual(saved.exercises[1].weight_kg, 12.5)
        response = self.client.get(submission.headers["Location"])
        self.assertEqual(response.status_code, 200)
        for text in (
            b"Completed Workout Summary", b"Bench Press", b"<td>7</td>",
            b"<td>0.0</td>", b"<td>12.5</td>", b"Workout saved successfully.",
        ):
            self.assertIn(text, response.data)

    def test_invalid_values_report_errors_for_the_affected_fields(self):
        cases = (
            ("sets_0", "", "Sets must be a positive whole number."),
            ("sets_0", "-1", "Sets must be a positive whole number."),
            ("reps_0", "", "Repetitions must be a positive whole number."),
            ("reps_0", "-1", "Repetitions must be a positive whole number."),
            ("weight_0", "", "Weight must be a finite, nonnegative number."),
            ("weight_0", "-1", "Weight must be a finite, nonnegative number."),
            ("weight_0", "NaN", "Weight must be a finite, nonnegative number."),
        )
        for field, value, message in cases:
            with self.subTest(field=field, value=value):
                form = {**self.form, field: value}
                self.assertEqual(self.service.validate_workout(self.routine, form), {field: message})
                response = self.client.post(self.url, data=form)
                self.assertEqual(response.status_code, 400)
                self.assertIn(message.encode(), response.data)
                self.assertNotIn(b"Completed Workout Summary", response.data)

        self.assertFalse(self.storage_path.exists())

    def test_workout_contains_completed_exercises(self):
        workout = self.service.create_workout("ST001", self.routine, self.form)
        self.assertIsInstance(workout, WorkoutLog)
        self.assertEqual(workout.student_id, "ST001")
        self.assertEqual(workout.routine_id, "RT001")
        self.assertEqual(workout.routine_name, "Upper Body")
        self.assertIsNotNone(workout.completed_at.utcoffset())
        self.assertEqual(len(workout.exercises), 3)
        self.assertEqual(workout.exercises[0], LoggedExercise("EX001", "Bench Press", 2, 7, 0.0))

    def test_successive_workouts_have_unique_ids(self):
        first = self.service.create_workout("ST001", self.routine, self.form)
        second = self.service.create_workout("ST001", self.routine, self.form)
        self.assertEqual(UUID(first.workout_id).version, 4)
        self.assertNotEqual(first.workout_id, second.workout_id)

    def test_service_rejects_invalid_or_unowned_workouts(self):
        with self.assertRaisesRegex(ValueError, "invalid workout"):
            self.service.create_workout("ST001", self.routine, {})
        with self.assertRaisesRegex(ValueError, "does not belong to student"):
            self.service.create_workout("ST002", self.routine, self.form)

    def test_empty_routine_is_rejected_with_feedback_before_creation(self):
        empty_routine = {**self.routine, "exercises": []}
        with patch("progress.routes.get_student_routine", return_value=empty_routine):
            with patch.object(ProgressService, "create_workout") as create_workout:
                for method in ("GET", "POST"):
                    with self.subTest(method=method):
                        response = self.client.open(self.url, method=method)
                        self.assertEqual(response.status_code, 400)
                        self.assertIn(b"This routine has no exercises.", response.data)
                        self.assertIn(b"Back to My Routines", response.data)
                        self.assertNotIn(b"<form", response.data)
                create_workout.assert_not_called()
        self.assertFalse(self.storage_path.exists())
        with self.assertRaises(ValueError):
            self.service.create_workout("ST001", empty_routine, {})

    def test_multiple_submissions_preserve_earlier_workouts(self):
        first = self.client.post(self.url, data=self.form)
        second = self.client.post(self.url, data={**self.form, "sets_0": "5"})
        self.assertEqual((first.status_code, second.status_code), (303, 303))
        workouts = self.repository.get_by_student("ST001")
        self.assertEqual([record.exercises[0].sets for record in workouts], [2, 5])
        self.assertEqual(
            [first.location, second.location],
            [f"/progress/workouts/{record.workout_id}" for record in workouts],
        )

    def test_refreshing_summary_does_not_save_again(self):
        submission = self.client.post(self.url, data=self.form)
        self.assertEqual(submission.status_code, 303)
        before = self.storage_path.read_bytes()
        for _ in range(2):
            self.assertEqual(self.client.get(submission.location).status_code, 200)
        self.assertEqual(self.storage_path.read_bytes(), before)
        self.assertEqual(len(self.repository.get_by_student("ST001")), 1)

    def test_another_students_summary_is_not_available(self):
        workout = self.service.create_workout("ST001", self.routine, self.form)
        other_workout = replace(workout, student_id="ST002")
        self.repository.save(other_workout)
        response = self.client.get(f"/progress/workouts/{other_workout.workout_id}")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(b"Upper Body", response.data)

    def test_missing_summary_returns_404(self):
        self.assertEqual(self.client.get("/progress/workouts/missing").status_code, 404)

    def test_save_failure_preserves_form_values_and_hides_internal_error(self):
        with (
            patch.object(
                WorkoutLogRepository, "save",
                side_effect=WorkoutLogStorageError("private path /internal/workouts.json"),
            ),
            self.assertLogs(self.app.logger, level="ERROR"),
        ):
            response = self.client.post(self.url, data=self.form)

        self.assertEqual(response.status_code, 500)
        self.assertIn(b"Your workout could not be saved.", response.data)
        self.assertNotIn(b"Workout saved successfully", response.data)
        self.assertNotIn(b"/internal/workouts.json", response.data)
        self.assertIsNone(response.location)
        self.assertRegex(response.get_data(as_text=True), r'name="reps_0"\s+value="7"')
        self.assertRegex(response.get_data(as_text=True), r'name="weight_1"\s+value="12\.5"')
        self.assertFalse(self.storage_path.exists())

    def test_corrupt_store_survives_failed_submission_and_summary_lookup(self):
        original = b"[broken"
        self.storage_path.write_bytes(original)
        with self.assertLogs(self.app.logger, level="ERROR"):
            submission = self.client.post(self.url, data=self.form)
            summary = self.client.get("/progress/workouts/missing")
        self.assertEqual(submission.status_code, 500)
        self.assertEqual(summary.status_code, 500)
        self.assertIn(b"Your workout could not be loaded.", summary.data)
        self.assertNotIn(str(self.storage_path).encode(), summary.data)
        self.assertEqual(self.storage_path.read_bytes(), original)

    def test_fresh_app_can_display_previously_saved_workout(self):
        submission = self.client.post(self.url, data=self.form)
        self.assertEqual(submission.status_code, 303)
        fresh_client = create_app(self.config).test_client()
        response = fresh_client.get(submission.location)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Workout saved successfully.", response.data)
