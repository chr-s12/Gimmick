
import math

from datetime import date, datetime, timezone
from uuid import uuid4

from progress.analytics import StudentProgressAnalytics, calculate_student_analytics
from progress.models import LoggedExercise, WorkoutLog
from progress.repository import WorkoutLogRepository


class ProgressService:

    def __init__(self, repository: WorkoutLogRepository | None = None):
        self._repository = WorkoutLogRepository() if repository is None else repository

    def log_workout(self, student_id, routine, form_data) -> WorkoutLog:
        """Create and persist a completed workout."""
        workout = self.create_workout(student_id, routine, form_data)
        self._repository.save(workout)
        return workout

    def get_workout(self, student_id, workout_id) -> WorkoutLog | None:
        """Look up a saved workout scoped to the student."""
        return self._repository.get_by_id(student_id, workout_id)

    def get_workout_history(self, student_id: str) -> list[WorkoutLog]:
        """Return newest workouts first, retaining saved order for equal instants."""
        # Stored timestamps have fixed offsets. Comparing them directly
        # avoids overflow when an instant falls outside datetime's UTC range.
        return sorted(
            self._repository.get_by_student(student_id),
            key=lambda workout: workout.completed_at,
            reverse=True,
        )

    def get_analytics(
        self,
        student_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
        as_of: datetime | None = None,
    ) -> StudentProgressAnalytics:
        """Calculate analytics from the student's current saved workout history."""
        workouts = self._repository.get_by_student(student_id)
        return calculate_student_analytics(
            student_id, workouts, start_date=start_date, end_date=end_date, as_of=as_of,
        )

    @staticmethod
    def validate_positive_integer(value):
        try:
            number = int(value)

            if number <= 0:
                return False

            return True

        except (ValueError, TypeError):
            return False

    @staticmethod
    def validate_weight(value):
        try:
            number = float(value)

            if not math.isfinite(number) or number < 0:
                return False

            return True

        except (ValueError, TypeError):
            return False

    def validate_workout(self, routine, form_data=None):
        if not routine["exercises"]:
            return {"routine": "This routine has no exercises. Choose another saved routine."}

        # Opening the form checks the routine without validating unsubmitted fields.
        if form_data is None:
            return {}

        errors = {}

        for index, exercise in enumerate(routine["exercises"]):

            sets_field = f"sets_{index}"
            reps_field = f"reps_{index}"
            weight_field = f"weight_{index}"

            if not self.validate_positive_integer(
                form_data.get(sets_field)
            ):
                errors[sets_field] = (
                    "Sets must be a positive whole number."
                )

            if not self.validate_positive_integer(
                form_data.get(reps_field)
            ):
                errors[reps_field] = (
                    "Repetitions must be a positive whole number."
                )

            if not self.validate_weight(
                form_data.get(weight_field)
            ):
                errors[weight_field] = (
                    "Weight must be a finite, nonnegative number."
                )

        return errors


    def create_workout(self, student_id, routine, form_data):
        errors = self.validate_workout(routine, form_data)

        if errors:
            raise ValueError("Cannot create an invalid workout.")

        if routine["student_id"] != student_id:
            raise ValueError("Routine does not belong to student.")

        logged_exercises = []

        for index, exercise in enumerate(routine["exercises"]):

            logged_exercise = LoggedExercise(
                exercise_id=exercise["exercise_id"],
                exercise_name=exercise["exercise_name"],
                sets=int(form_data[f"sets_{index}"]),
                reps=int(form_data[f"reps_{index}"]),
                weight_kg=float(form_data[f"weight_{index}"])
            )

            logged_exercises.append(logged_exercise)

        workout = WorkoutLog(
            workout_id=str(uuid4()),
            student_id=student_id,
            routine_id=routine["routine_id"],
            routine_name=routine["routine_name"],
            completed_at=datetime.now(timezone.utc),
            exercises=logged_exercises
        )

        return workout
