from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo
from fractions import Fraction
from zoneinfo import ZoneInfo

from progress.models import LoggedExercise, WorkoutLog


_JAMAICA = ZoneInfo("America/Jamaica")
_WEEK = timedelta(days=7)
_SIX_DAYS = timedelta(days=6)


@dataclass(frozen=True)
class WeeklyConsistency:
    week_start: date
    week_end: date
    active_dates: tuple[date, ...]
    is_current_week: bool
    is_partial_week: bool = False

    @property
    def active_days(self) -> int:
        return len(self.active_dates)


@dataclass(frozen=True)
class ExerciseDailyProgress:
    date: date
    max_weight_kg: float
    max_reps: int
    total_volume_kg: float


@dataclass(frozen=True)
class ExerciseProgression:
    exercise_id: str
    exercise_name: str
    daily_history: tuple[ExerciseDailyProgress, ...]


@dataclass(frozen=True)
class PersonalBest:
    value: float
    achieved_at: datetime
    achieved_date: date
    workout_id: str


@dataclass(frozen=True)
class RepetitionRecord:
    weight_kg: float
    reps: int
    achieved_at: datetime
    achieved_date: date
    workout_id: str


@dataclass(frozen=True)
class ExercisePersonalRecords:
    exercise_id: str
    exercise_name: str
    heaviest_weight: PersonalBest | None
    repetition_records: tuple[RepetitionRecord, ...]
    highest_session_volume: PersonalBest | None


@dataclass(frozen=True)
class StudentProgressAnalytics:
    student_id: str
    weekly_consistency: tuple[WeeklyConsistency, ...]
    exercise_progression: tuple[ExerciseProgression, ...]
    personal_records: tuple[ExercisePersonalRecords, ...]
    start_date: date | None
    end_date: date | None
    as_of: datetime
    has_workouts: bool
    has_workouts_in_period: bool


def _require_aware(value: datetime, field: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime.")


def _convert_timezone(value: datetime, target: tzinfo, field: str) -> datetime:
    try:
        return value.astimezone(target)
    except OverflowError as error:
        raise ValueError(f"{field} falls outside the supported datetime range.") from error


def _reference_times(as_of: datetime | None) -> tuple[datetime, date]:
    if as_of is None:
        as_of = datetime.now(timezone.utc)
    _require_aware(as_of, "as_of")
    reference = _convert_timezone(as_of, timezone.utc, "as_of")
    return reference, _convert_timezone(reference, _JAMAICA, "as_of").date()


def _eligible_workouts(
    workouts: Iterable[WorkoutLog], reference: datetime,
) -> Iterator[tuple[WorkoutLog, date]]:
    for workout in workouts:
        completed_at = workout.completed_at
        field = f"Workout {workout.workout_id} completed_at"
        _require_aware(completed_at, field)
        if completed_at <= reference:
            yield workout, _convert_timezone(completed_at, _JAMAICA, field).date()


def _workout_order(workout: WorkoutLog) -> tuple[datetime, str]:
    return (
        _convert_timezone(
            workout.completed_at, timezone.utc, f"Workout {workout.workout_id} completed_at"
        ),
        workout.workout_id,
    )


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _validate_date_range(start_date: date | None, end_date: date | None) -> None:
    for name, boundary in (("start_date", start_date), ("end_date", end_date)):
        if boundary is not None and (
            not isinstance(boundary, date) or isinstance(boundary, datetime)
        ):
            raise ValueError(f"{name} must be a calendar date.")
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError("start_date must be on or before end_date.")


def calculate_weekly_consistency(
    workouts: Iterable[WorkoutLog],
    as_of: datetime | None = None,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[WeeklyConsistency]:
    """Count distinct Jamaica training dates within the selected history."""
    _validate_date_range(start_date, end_date)
    reference, reference_date = _reference_times(as_of)
    current_week = _week_start(reference_date)

    dates_by_week: dict[date, set[date]] = {}
    for _, active_date in _eligible_workouts(workouts, reference):
        dates_by_week.setdefault(_week_start(active_date), set()).add(active_date)

    if not dates_by_week:
        return []

    first_week = min(dates_by_week)
    first_day = max(first_week, start_date) if start_date is not None else first_week
    last_day = min(reference_date, end_date) if end_date is not None else reference_date
    if first_day > last_day:
        return []

    # Both ends retain their calendar week labels, even when only some days are selected.
    last_week = _week_start(last_day)
    if last_week > date.max - _SIX_DAYS:
        raise ValueError("The last Jamaica week's Sunday is outside the supported date range.")

    history = []
    week = _week_start(first_day)
    while week <= last_week:
        week_end = week + _SIX_DAYS
        history.append(WeeklyConsistency(
            week_start=week,
            week_end=week_end,
            active_dates=tuple(sorted(
                day for day in dates_by_week.get(week, ())
                if first_day <= day <= last_day
            )),
            is_current_week=week == current_week,
            is_partial_week=(
                (start_date is not None and week < start_date)
                or (end_date is not None and week_end > end_date)
            ),
        ))
        if week == last_week:
            break
        week += _WEEK
    return history


def _total_volume(
    entries: list[LoggedExercise], context: str,
) -> tuple[Fraction, float]:
    """Sum the decimal values of recorded weights and convert only the total."""
    try:
        exact = sum(
            (entry.sets * entry.reps * Fraction(str(entry.weight_kg)) for entry in entries),
            start=Fraction(),
        )
        return exact, float(exact)
    except (OverflowError, ValueError) as error:
        raise ValueError(f"{context} is outside the finite float range.") from error


def _daily_progress(
    exercise_id: str, day: date, entries: list[LoggedExercise],
) -> ExerciseDailyProgress:
    _, volume = _total_volume(entries, f"Exercise {exercise_id} volume on {day}")
    return ExerciseDailyProgress(
        date=day,
        max_weight_kg=max(entry.weight_kg for entry in entries),
        max_reps=max(entry.reps for entry in entries),
        total_volume_kg=volume,
    )


def calculate_exercise_progression(
    workouts: Iterable[WorkoutLog],
    start_date: date | None = None,
    end_date: date | None = None,
    as_of: datetime | None = None,
) -> list[ExerciseProgression]:
    """Return daily progression by exercise ID for one student's workouts."""
    _validate_date_range(start_date, end_date)

    reference, _ = _reference_times(as_of)
    entries_by_exercise: dict[str, dict[date, list[LoggedExercise]]] = defaultdict(
        lambda: defaultdict(list)
    )
    latest_names: dict[str, tuple[datetime, str, int, str]] = {}

    for workout, day in _eligible_workouts(workouts, reference):
        if start_date is not None and day < start_date:
            continue
        if end_date is not None and day > end_date:
            continue
        completed_at, workout_id = _workout_order(workout)
        for index, entry in enumerate(workout.exercises):
            exercise_id = entry.exercise_id
            entries_by_exercise[exercise_id][day].append(entry)

            name_record = (completed_at, workout_id, index, entry.exercise_name)
            previous = latest_names.get(exercise_id)
            if previous is None or name_record > previous:
                latest_names[exercise_id] = name_record

    return [
        ExerciseProgression(
            exercise_id=exercise_id,
            exercise_name=latest_names[exercise_id][-1],
            daily_history=tuple(
                _daily_progress(exercise_id, day, entries)
                for day, entries in sorted(entries_by_exercise[exercise_id].items())
            ),
        )
        for exercise_id in sorted(entries_by_exercise)
    ]


def _exercise_records(
    exercise_id: str, sessions: list[tuple[WorkoutLog, date, list[LoggedExercise]]],
) -> ExercisePersonalRecords:
    heaviest_weight = None
    highest_session_volume = None
    best_volume = Fraction()
    repetitions_by_weight: dict[float, RepetitionRecord] = {}

    for workout, day, entries in sessions:
        achieved_at = workout.completed_at
        workout_id = workout.workout_id
        for entry in entries:
            weight = entry.weight_kg
            if weight > 0 and (heaviest_weight is None or weight > heaviest_weight.value):
                heaviest_weight = PersonalBest(weight, achieved_at, day, workout_id)

            previous = repetitions_by_weight.get(weight)
            if previous is None or entry.reps > previous.reps:
                repetitions_by_weight[weight] = RepetitionRecord(
                    weight, entry.reps, achieved_at, day, workout_id,
                )

        exact, volume = _total_volume(
            entries, f"Exercise {exercise_id} session volume in workout {workout_id}"
        )
        if exact > best_volume:
            best_volume = exact
            highest_session_volume = PersonalBest(volume, achieved_at, day, workout_id)

    return ExercisePersonalRecords(
        exercise_id=exercise_id,
        exercise_name=sessions[-1][2][-1].exercise_name,
        heaviest_weight=heaviest_weight,
        repetition_records=tuple(repetitions_by_weight[weight] for weight in sorted(repetitions_by_weight)),
        highest_session_volume=highest_session_volume,
    )


def calculate_personal_records(
    workouts: Iterable[WorkoutLog], as_of: datetime | None = None,
) -> list[ExercisePersonalRecords]:
    """Return all-time exercise records for one student's eligible workouts."""
    reference, _ = _reference_times(as_of)
    sessions_by_exercise: dict[str, list[tuple[WorkoutLog, date, list[LoggedExercise]]]] = (
        defaultdict(list)
    )
    for workout, day in sorted(
        _eligible_workouts(workouts, reference), key=lambda item: _workout_order(item[0])
    ):
        entries_by_exercise: dict[str, list[LoggedExercise]] = defaultdict(list)
        for entry in workout.exercises:
            entries_by_exercise[entry.exercise_id].append(entry)
        for exercise_id, entries in entries_by_exercise.items():
            sessions_by_exercise[exercise_id].append((workout, day, entries))

    return [
        _exercise_records(exercise_id, sessions)
        for exercise_id, sessions in sorted(sessions_by_exercise.items())
    ]


def calculate_student_analytics(
    student_id: str,
    workouts: Iterable[WorkoutLog],
    start_date: date | None = None,
    end_date: date | None = None,
    as_of: datetime | None = None,
) -> StudentProgressAnalytics:
    """Combine the three analytics metrics for one student's saved history."""
    _validate_date_range(start_date, end_date)
    reference, _ = _reference_times(as_of)
    history = tuple(workouts)
    for workout in history:
        if workout.student_id != student_id:
            raise ValueError(f"Workout {workout.workout_id} does not belong to student {student_id!r}.")

    eligible = tuple(_eligible_workouts(history, reference))
    completed = tuple(workout for workout, _ in eligible)
    has_workouts_in_period = any(
        (start_date is None or start_date <= day)
        and (end_date is None or day <= end_date)
        for _, day in eligible
    )

    return StudentProgressAnalytics(
        student_id=student_id,
        weekly_consistency=tuple(calculate_weekly_consistency(
            completed, as_of=reference, start_date=start_date, end_date=end_date,
        )),
        exercise_progression=tuple(calculate_exercise_progression(
            completed, start_date=start_date, end_date=end_date, as_of=reference,
        )),
        personal_records=tuple(calculate_personal_records(completed, as_of=reference)),
        start_date=start_date,
        end_date=end_date,
        as_of=reference,
        has_workouts=bool(eligible),
        has_workouts_in_period=has_workouts_in_period,
    )
