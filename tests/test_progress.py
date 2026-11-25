import unittest
from unittest.mock import patch
from uuid import UUID

from app import create_app
from progress.mock_dependencies import get_student, get_student_routine, get_student_routines
from progress.models import LoggedExercise, WorkoutLog
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
        app = create_app()
        app.config["TESTING"] = True
        self.client = app.test_client()
        self.service = ProgressService()
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

    def test_root_has_no_route(self):
        self.assertEqual(self.client.get("/").status_code, 404)

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

    def test_valid_submission_shows_temporary_summary(self):
        response = self.client.post(self.url, data=self.form)
        self.assertEqual(response.status_code, 200)
        for text in (
            b"Completed Workout Summary", b"Bench Press", b"<td>7</td>",
            b"<td>0.0</td>", b"<td>12.5</td>", b"not yet been saved permanently",
        ):
            self.assertIn(text, response.data)

    def test_invalid_values_report_errors_for_the_affected_fields(self):
        cases = (
            ("sets_0", "", "Sets must be a positive whole number."),
            ("reps_0", "-1", "Repetitions must be a positive whole number."),
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
        with self.assertRaises(ValueError):
            self.service.create_workout("ST001", empty_routine, {})
