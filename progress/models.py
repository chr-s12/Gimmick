from dataclasses import dataclass, fields
from datetime import datetime
from math import isfinite


def _validate_record(data, model, text_fields):
    """Check the shape of a stored record before reconstructing a model."""
    name = model.__name__
    if not isinstance(data, dict):
        raise ValueError(f"{name} record must be a dictionary.")

    expected = {field.name for field in fields(model)}
    missing = expected - data.keys()
    if missing:
        raise ValueError(f"{name} record is missing fields: {', '.join(sorted(missing))}.")
    extra = data.keys() - expected
    if extra:
        names = ", ".join(sorted(map(repr, extra)))
        raise ValueError(f"{name} record has unexpected fields: {names}.")

    for field in text_fields:
        if not isinstance(data[field], str) or not data[field].strip():
            raise ValueError(f"{name}.{field} must be a nonempty string.")


def _weight_as_float(value):
    message = "LoggedExercise.weight_kg must be a finite, nonnegative number."
    if type(value) not in (int, float):
        raise ValueError(message)
    try:
        weight = float(value)
    except OverflowError as error:
        raise ValueError(message) from error
    if not isfinite(weight) or weight < 0:
        raise ValueError(message)
    return weight


@dataclass
class LoggedExercise:
    exercise_id: str
    exercise_name: str
    sets: int
    reps: int
    weight_kg: float

    def to_dict(self) -> dict:
        """Return a new JSON-compatible record for the exercise."""
        return {
            "exercise_id": self.exercise_id,
            "exercise_name": self.exercise_name,
            "sets": self.sets,
            "reps": self.reps,
            "weight_kg": _weight_as_float(self.weight_kg),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LoggedExercise":
        """Reconstruct an exercise from a validated stored record."""
        _validate_record(data, cls, ("exercise_id", "exercise_name"))
        for field in ("sets", "reps"):
            if type(data[field]) is not int or data[field] <= 0:
                raise ValueError(f"LoggedExercise.{field} must be a positive integer.")
        return cls(
            exercise_id=data["exercise_id"],
            exercise_name=data["exercise_name"],
            sets=data["sets"],
            reps=data["reps"],
            weight_kg=_weight_as_float(data["weight_kg"]),
        )


@dataclass
class WorkoutLog:
    workout_id: str
    student_id: str
    routine_id: str
    routine_name: str
    completed_at: datetime
    exercises: list[LoggedExercise]

    def to_dict(self) -> dict:
        """Return a new JSON-compatible record with an offset-bearing timestamp."""
        if self.completed_at.utcoffset() is None:
            raise ValueError("WorkoutLog.completed_at must include a timezone offset.")
        return {
            "workout_id": self.workout_id,
            "student_id": self.student_id,
            "routine_id": self.routine_id,
            "routine_name": self.routine_name,
            "completed_at": self.completed_at.isoformat(),
            "exercises": [exercise.to_dict() for exercise in self.exercises],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorkoutLog":
        """Reconstruct a workout, including its timestamp and nested exercises."""
        _validate_record(data, cls, ("workout_id", "student_id", "routine_id", "routine_name"))
        timestamp = data["completed_at"]
        if not isinstance(timestamp, str):
            raise ValueError("WorkoutLog.completed_at must be an ISO 8601 string.")
        try:
            completed_at = datetime.fromisoformat(timestamp)
        except ValueError as error:
            raise ValueError("WorkoutLog.completed_at must be an ISO 8601 timestamp.") from error
        if completed_at.utcoffset() is None:
            raise ValueError("WorkoutLog.completed_at must include a timezone offset.")

        records = data["exercises"]
        if not isinstance(records, list) or not records:
            raise ValueError("WorkoutLog.exercises must be a nonempty list.")

        exercises = []
        for index, record in enumerate(records):
            try:
                exercises.append(LoggedExercise.from_dict(record))
            except ValueError as error:
                raise ValueError(f"WorkoutLog.exercises[{index}]: {error}") from error

        return cls(
            workout_id=data["workout_id"],
            student_id=data["student_id"],
            routine_id=data["routine_id"],
            routine_name=data["routine_name"],
            completed_at=completed_at,
            exercises=exercises,
        )
