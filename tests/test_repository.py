import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest.mock import patch

from progress.models import LoggedExercise, WorkoutLog
from progress.repository import WorkoutLogRepository, WorkoutLogStorageError


class WorkoutLogRepositoryTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.path = Path(directory) / "logs" / "workouts.json"
        self.repository = WorkoutLogRepository(self.path)
        self.workout = WorkoutLog(
            "W001", "ST001", "RT001", "Entraînement",
            datetime(2026, 11, 25, 14, 30, tzinfo=timezone(timedelta(hours=-5))),
            [LoggedExercise("EX001", "Bench Press", 3, 8, 42.5)],
        )

    def test_missing_file_returns_empty_history(self):
        self.assertEqual(self.repository.get_by_student("ST001"), [])
        self.assertIsNone(self.repository.get_by_id("ST001", "W001"))
        self.assertFalse(self.path.parent.exists())

    def test_first_save_creates_directory_and_utf8_json_array(self):
        self.repository.save(self.workout)
        contents = self.path.read_text(encoding="utf-8")
        self.assertIn("Entraînement", contents)
        self.assertEqual(json.loads(contents), [self.workout.to_dict()])

    def test_saved_workout_reconstructs_with_offset_and_nested_models(self):
        self.repository.save(self.workout)
        restored = self.repository.get_by_id("ST001", "W001")
        self.assertEqual(restored, self.workout)
        self.assertEqual(restored.completed_at.utcoffset(), timedelta(hours=-5))
        self.assertIsInstance(restored.exercises[0], LoggedExercise)

    def test_multiple_saves_keep_earlier_records_in_order(self):
        later = replace(self.workout, workout_id="W002")
        self.repository.save(self.workout)
        self.repository.save(later)
        self.assertEqual(self.repository.get_by_student("ST001"), [self.workout, later])

    def test_new_instance_can_read_saved_workouts(self):
        self.repository.save(self.workout)
        reader = WorkoutLogRepository(self.path)
        self.assertEqual(reader.get_by_student("ST001"), [self.workout])

    def test_list_and_individual_lookup_filter_by_owner(self):
        other = replace(self.workout, workout_id="W002", student_id="ST002")
        self.repository.save(self.workout)
        self.repository.save(other)
        self.assertEqual(self.repository.get_by_student("ST001"), [self.workout])
        self.assertEqual(self.repository.get_by_student("ST002"), [other])
        self.assertEqual(self.repository.get_by_student("ST003"), [])
        self.assertIsNone(self.repository.get_by_id("ST001", "W002"))
        self.assertEqual(self.repository.get_by_id("ST002", "W002"), other)
        self.assertIsNone(self.repository.get_by_id("ST001", "missing"))

    def test_duplicate_id_is_rejected_across_students(self):
        self.repository.save(self.workout)
        before = self.path.read_bytes()
        with self.assertRaisesRegex(WorkoutLogStorageError, "Duplicate workout ID"):
            self.repository.save(replace(self.workout, student_id="ST002"))
        self.assertEqual(self.path.read_bytes(), before)

    def test_malformed_json_and_empty_files_are_storage_errors(self):
        self.path.parent.mkdir()
        for contents in ("", "[", "[NaN]", '[{"sets": 3, "sets": 4}]'):
            with self.subTest(contents=contents):
                self.path.write_text(contents, encoding="utf-8")
                with self.assertRaisesRegex(WorkoutLogStorageError, "Cannot read"):
                    self.repository.get_by_student("ST001")

    def test_invalid_record_structures_and_stored_duplicates_are_rejected(self):
        record = self.workout.to_dict()
        self.path.parent.mkdir()
        for data, message in (
            ({}, "JSON array"),
            ([{}], "index 0.*missing fields"),
            ([record, record], "Duplicate workout ID"),
        ):
            with self.subTest(message=message):
                self.path.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaisesRegex(WorkoutLogStorageError, message):
                    self.repository.get_by_id("ST001", "W001")

    def test_save_does_not_overwrite_corrupted_storage(self):
        self.path.parent.mkdir()
        for contents in (b"", b"[broken", b"[{}]", b"\xff"):
            with self.subTest(contents=contents):
                self.path.write_bytes(contents)
                with self.assertRaises(WorkoutLogStorageError):
                    self.repository.save(self.workout)
                self.assertEqual(self.path.read_bytes(), contents)

    def test_save_rejects_invalid_workout_before_creating_storage(self):
        with self.assertRaisesRegex(WorkoutLogStorageError, "Invalid workout to save"):
            self.repository.save(replace(self.workout, exercises=[]))
        self.assertFalse(self.path.parent.exists())

    def test_write_and_replace_failures_preserve_file_and_clean_temporary_file(self):
        self.repository.save(self.workout)
        before = self.path.read_bytes()
        later = replace(self.workout, workout_id="W002")

        def fail_after_partial_write(records, target, **options):
            target.write("[")
            raise OSError("simulated partial write")

        for target, kwargs in (
            ("progress.repository.json.dump", {"side_effect": fail_after_partial_write}),
            ("progress.repository.os.replace", {"side_effect": OSError("simulated replace")}),
        ):
            with self.subTest(target=target), patch(target, **kwargs):
                with self.assertRaisesRegex(WorkoutLogStorageError, "Cannot write"):
                    self.repository.save(later)
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_overlapping_saves_across_instances_keep_every_record(self):
        count = 8
        ready = Barrier(count)
        workouts = [replace(self.workout, workout_id=f"W{index:03}") for index in range(count)]

        def save(workout):
            repository = WorkoutLogRepository(self.path)
            ready.wait(timeout=5)
            repository.save(workout)

        with ThreadPoolExecutor(max_workers=count) as executor:
            list(executor.map(save, workouts))

        self.assertCountEqual(self.repository.get_by_student("ST001"), workouts)
