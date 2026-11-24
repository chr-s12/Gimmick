
from dataclasses import dataclass
from datetime import datetime


@dataclass
class LoggedExercise:
    exercise_id: str
    exercise_name: str
    sets: int
    reps: int
    weight_kg: float


@dataclass
class WorkoutLog:
    workout_id: str
    student_id: str
    routine_id: str
    routine_name: str
    completed_at: datetime
    exercises: list[LoggedExercise]
