import json
import unittest
from datetime import datetime, timedelta, timezone

from progress.models import LoggedExercise, WorkoutLog


class ModelConversionTests(unittest.TestCase):
    def setUp(self):
        self.exercise = LoggedExercise("EX001", "Bench Press", 3, 8, 42.5)
        offset = timezone(timedelta(hours=-5))
        self.workout = WorkoutLog(
            "W001", "ST001", "RT001", "Upper Body",
            datetime(2026, 11, 25, 14, 30, 12, 123456, tzinfo=offset),
            [self.exercise, LoggedExercise("EX002", "Push-ups", 2, 12, 0.0)],
        )
        self.exercise_record = {
            "exercise_id": "EX001",
            "exercise_name": "Bench Press",
            "sets": 3,
            "reps": 8,
            "weight_kg": 42.5,
        }

    def test_exercise_to_dict(self):
        self.assertEqual(self.exercise.to_dict(), self.exercise_record)

    def test_exercise_from_dict(self):
        self.assertEqual(LoggedExercise.from_dict(self.exercise_record), self.exercise)

    def test_workout_to_dict_includes_all_fields_and_nested_exercises(self):
        self.assertEqual(self.workout.to_dict(), {
            "workout_id": "W001",
            "student_id": "ST001",
            "routine_id": "RT001",
            "routine_name": "Upper Body",
            "completed_at": "2026-11-25T14:30:12.123456-05:00",
            "exercises": [
                self.exercise_record,
                {
                    "exercise_id": "EX002", "exercise_name": "Push-ups",
                    "sets": 2, "reps": 12, "weight_kg": 0.0,
                },
            ],
        })

    def test_json_round_trip_preserves_objects_offset_and_numeric_types(self):
        payload = json.dumps(self.workout.to_dict(), allow_nan=False)
        restored = WorkoutLog.from_dict(json.loads(payload))
        self.assertEqual(restored, self.workout)
        self.assertEqual(restored.completed_at.utcoffset(), timedelta(hours=-5))
        self.assertEqual(restored.completed_at.isoformat(), self.workout.completed_at.isoformat())
        for exercise in restored.exercises:
            self.assertIsInstance(exercise, LoggedExercise)
            self.assertIs(type(exercise.sets), int)
            self.assertIs(type(exercise.reps), int)
            self.assertIs(type(exercise.weight_kg), float)

    def test_integer_json_weight_is_restored_as_float(self):
        exercise = LoggedExercise.from_dict({**self.exercise_record, "weight_kg": 20})
        self.assertIs(type(exercise.weight_kg), float)
        self.assertEqual(exercise.weight_kg, 20.0)

    def test_invalid_and_naive_timestamps_are_rejected(self):
        for timestamp in ("yesterday", "2026-11-25T14:30:12", None):
            with self.subTest(timestamp=timestamp):
                data = {**self.workout.to_dict(), "completed_at": timestamp}
                with self.assertRaisesRegex(ValueError, "completed_at"):
                    WorkoutLog.from_dict(data)

    def test_missing_fields_are_rejected(self):
        for model, data, field in (
            (LoggedExercise, self.exercise_record, "sets"),
            (WorkoutLog, self.workout.to_dict(), "student_id"),
        ):
            with self.subTest(model=model):
                del data[field]
                with self.assertRaisesRegex(ValueError, f"missing fields: {field}"):
                    model.from_dict(data)

    def test_invalid_numeric_values_are_rejected(self):
        for field in ("sets", "reps", "weight_kg"):
            invalid = [-1, True, "3", None, float("nan"), float("inf")]
            if field == "weight_kg":
                invalid.extend([float("-inf"), 10 ** 400])
            else:
                invalid.extend([0, 1.5, 3.0])
            for value in invalid:
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(ValueError, field):
                        LoggedExercise.from_dict({**self.exercise_record, field: value})

    def test_malformed_nested_data_identifies_the_exercise(self):
        data = self.workout.to_dict()
        data["exercises"][1]["sets"] = 2.5
        with self.assertRaisesRegex(ValueError, r"exercises\[1\].*sets"):
            WorkoutLog.from_dict(data)

    def test_invalid_record_shapes_and_unexpected_fields_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "dictionary"):
            LoggedExercise.from_dict([])
        with self.assertRaisesRegex(ValueError, "unexpected fields"):
            LoggedExercise.from_dict({**self.exercise_record, "unknown": None})
        with self.assertRaisesRegex(ValueError, "nonempty string"):
            LoggedExercise.from_dict({**self.exercise_record, "exercise_id": ""})
        for records in ({}, []):
            with self.subTest(records=records):
                with self.assertRaisesRegex(ValueError, "nonempty list"):
                    WorkoutLog.from_dict({**self.workout.to_dict(), "exercises": records})

    def test_conversion_keeps_input_and_output_independent(self):
        expected = self.workout.to_dict()
        data = self.workout.to_dict()
        restored = WorkoutLog.from_dict(data)
        self.assertEqual(data, expected)
        self.assertEqual(self.workout.to_dict(), expected)
        data["exercises"][0]["sets"] = 99
        data["exercises"].pop()
        self.assertEqual(self.workout.to_dict(), expected)
        self.assertEqual(restored.to_dict(), expected)
