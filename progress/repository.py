import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock

from progress.models import WorkoutLog


_DEFAULT_STORAGE = Path(__file__).resolve().parents[1] / "data" / "workouts.json"
_WRITE_LOCK = Lock()


class WorkoutLogStorageError(Exception):
    """The workout store could not be read, validated, or updated."""


def _reject_constant(token):
    raise ValueError(f"Invalid JSON numeric constant: {token}")


def _unique_object(pairs):
    record = {}
    for key, value in pairs:
        if key in record:
            raise ValueError(f"Duplicate JSON field: {key!r}")
        record[key] = value
    return record


class WorkoutLogRepository:
    """Store completed workouts in a local JSON array."""

    def __init__(self, storage_path: str | Path = _DEFAULT_STORAGE):
        self._path = Path(storage_path).resolve()

    def save(self, workout: WorkoutLog) -> None:
        """Append a valid workout with a globally unique workout ID."""
        try:
            validated = WorkoutLog.from_dict(workout.to_dict())
        except (AttributeError, TypeError, ValueError) as error:
            raise WorkoutLogStorageError(f"Invalid workout to save: {error}") from error

        # Share one lock across repository instances in this process.
        with _WRITE_LOCK:
            workouts = self._read_workouts()
            if any(item.workout_id == validated.workout_id for item in workouts):
                raise WorkoutLogStorageError(
                    f"Duplicate workout ID: {validated.workout_id!r}"
                )
            workouts.append(validated)
            self._write_workouts(workouts)

    def get_by_student(self, student_id: str) -> list[WorkoutLog]:
        """Return the student's workouts in saved order."""
        return [
            workout for workout in self._read_workouts()
            if workout.student_id == student_id
        ]

    def get_by_id(self, student_id: str, workout_id: str) -> WorkoutLog | None:
        """Return a workout only if its ID and owner both match."""
        return next(
            (
                workout for workout in self._read_workouts()
                if workout.student_id == student_id and workout.workout_id == workout_id
            ),
            None,
        )

    def _read_workouts(self) -> list[WorkoutLog]:
        try:
            with self._path.open("r", encoding="utf-8") as source:
                records = json.load(
                    source, parse_constant=_reject_constant, object_pairs_hook=_unique_object
                )
        except FileNotFoundError:
            return []
        except (OSError, ValueError) as error:
            raise WorkoutLogStorageError(
                f"Cannot read workout storage at {self._path}: {error}"
            ) from error

        if not isinstance(records, list):
            raise WorkoutLogStorageError(
                f"Workout storage at {self._path} must contain a JSON array."
            )

        workouts = []
        seen_ids = set()
        for index, record in enumerate(records):
            try:
                workout = WorkoutLog.from_dict(record)
            except ValueError as error:
                raise WorkoutLogStorageError(
                    f"Invalid workout record at index {index} in {self._path}: {error}"
                ) from error
            if workout.workout_id in seen_ids:
                raise WorkoutLogStorageError(
                    f"Duplicate workout ID {workout.workout_id!r} in {self._path} "
                    f"at index {index}."
                )
            seen_ids.add(workout.workout_id)
            workouts.append(workout)
        return workouts

    def _write_workouts(self, workouts: list[WorkoutLog]) -> None:
        temporary_path = None
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self._path.parent,
                prefix=f".{self._path.name}.", suffix=".tmp", delete=False,
            ) as target:
                temporary_path = Path(target.name)
                json.dump(
                    [workout.to_dict() for workout in workouts],
                    target,
                    ensure_ascii=False,
                    allow_nan=False,
                    indent=2,
                )
                target.write("\n")
            os.replace(temporary_path, self._path)
        except (OSError, TypeError, ValueError) as error:
            raise WorkoutLogStorageError(
                f"Cannot write workout storage at {self._path}: {error}"
            ) from error
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    # Keep the original write error if cleanup also fails.
                    pass
