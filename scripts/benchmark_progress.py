"""Measure standalone Feature 4 with generated data and disposable JSON storage."""

import argparse
import json
from datetime import datetime, time, timedelta
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app import create_app
from progress.analytics import calculate_student_analytics
from progress.models import LoggedExercise, WorkoutLog
from progress.periods import resolve_period
from progress.repository import WorkoutLogRepository
from progress.service import ProgressService


STUDENT = "ST001"
JAMAICA = ZoneInfo("America/Jamaica")
AS_OF = datetime(2026, 11, 25, 23, tzinfo=JAMAICA)
SIZES = (30, 250, 1000)
REPEATS = 7
ROUTINES = (
    ("Upper Body", ((1, "Bench Press"), (2, "Bicep Curls"), (3, "Push-ups"))),
    ("Full Body", ((1, "Bench Press"), (4, "Squats"), (5, "Plank"))),
    ("Lower Body", ((4, "Squats"), (6, "Calf Raises"), (7, "Lunges"))),
)
PERIODS = (
    ("all", "", ""),
    ("last30", "", ""),
    ("last7", "", ""),
    ("custom", "2026-10-15", "2026-11-20"),
)


def make_workouts(size):
    workouts = []
    for index in range(size):
        # Four sessions per training week, some on the same day, with a gap every third week.
        block, session = divmod(index, 4)
        days_ago = (block + block // 2) * 7 + (0, 0, 2, 4)[session]
        day = AS_OF.date() - timedelta(days=days_ago)
        routine_index = index % len(ROUTINES)
        name, exercises = ROUTINES[routine_index]
        owner = "BENCH-OTHER" if index % 10 == 9 else STUDENT
        workouts.append(WorkoutLog(
            f"BENCH-{index:04}", owner, f"BENCH-R{routine_index + 1}",
            name if owner == STUDENT else "Other student only",
            datetime.combine(day, time(8 + 2 * session), tzinfo=JAMAICA),
            [
                LoggedExercise(
                    f"BENCH-E{number}", exercise_name, 2 + (index + number) % 3,
                    5 + (index + number) % 10,
                    0.0 if number in (3, 5) else 20.0 + (index + number) % 30 * 2.5,
                )
                for number, exercise_name in exercises
            ],
        ))
    return workouts


def write_fixture(path, workouts):
    records = [workout.to_dict() for workout in workouts]
    snapshot = (json.dumps(records, ensure_ascii=False, indent=2) + "\n").encode()
    path.write_bytes(snapshot)
    return snapshot


def measure(label, operation, validate, prepare=None):
    durations = []
    for repetition in range(REPEATS + 1):
        if prepare is not None:
            prepare()
        started = perf_counter()
        result = operation()
        elapsed = (perf_counter() - started) * 1000
        validate(result)
        if repetition:
            durations.append(elapsed)
    print(f"{label:31} {median(durations):9.2f} {max(durations):9.2f}")


def validate_analytics(result, owned, bounds):
    start, end = bounds
    selected = [
        workout for workout in owned
        if (start is None or workout.completed_at.date() >= start)
        and (end is None or workout.completed_at.date() <= end)
    ]
    assert result.student_id == STUDENT
    assert sum(week.active_days for week in result.weekly_consistency) == len({
        workout.completed_at.date() for workout in selected
    })
    assert {exercise.exercise_id for exercise in result.exercise_progression} == {
        exercise.exercise_id for workout in selected for exercise in workout.exercises
    }
    assert max(record.heaviest_weight.value for record in result.personal_records
               if record.heaviest_weight is not None) == max(
        exercise.weight_kg for workout in owned for exercise in workout.exercises
    )


def require_response(response, *markers):
    assert response.status_code == 200, response.status_code
    for marker in markers:
        assert marker in response.data, marker
    assert b"Other student only" not in response.data


def benchmark(path, size):
    workouts = make_workouts(size)
    snapshot = write_fixture(path, workouts)
    owned = [workout for workout in workouts if workout.student_id == STUDENT]
    target = owned[-1]
    repository = WorkoutLogRepository(path)
    service = ProgressService(repository)
    app = create_app({"TESTING": True, "WORKOUT_STORAGE_PATH": path})
    client = app.test_client()
    print(f"\n{size} total, {len(owned)} owned, {len(snapshot)} JSON bytes")
    print(f"{'Operation':31} {'Median ms':>9} {'Max ms':>9}")

    def validate_list(result):
        assert result == owned

    def validate_lookup(result):
        assert result == target

    def validate_save(_):
        assert repository.get_by_id(STUDENT, "BENCH-NEW") == extra

    extra = WorkoutLog("BENCH-NEW", STUDENT, target.routine_id, target.routine_name,
                       target.completed_at, target.exercises)
    measure("repository student", lambda: repository.get_by_student(STUDENT), validate_list)
    measure("repository summary", lambda: repository.get_by_id(STUDENT, target.workout_id), validate_lookup)
    measure("repository save", lambda: repository.save(extra), validate_save,
            prepare=lambda: path.write_bytes(snapshot))
    path.write_bytes(snapshot)

    all_time = (None, None)
    measure("calculation only / all",
            lambda: calculate_student_analytics(STUDENT, owned, as_of=AS_OF),
            lambda result: validate_analytics(result, owned, all_time))

    for period, start, end in PERIODS:
        bounds = resolve_period(period, start, end, AS_OF)
        measure(f"service analytics / {period}",
                lambda: service.get_analytics(STUDENT, *bounds, as_of=AS_OF),
                lambda result: validate_analytics(result, owned, bounds))

    measure("GET saved routines", lambda: client.get("/progress/"),
            lambda result: require_response(result, b"Upper Body"))
    measure("GET history", lambda: client.get("/progress/history"),
            lambda result: require_response(result, b"Workout History", target.workout_id.encode()))
    measure("GET summary", lambda: client.get(f"/progress/workouts/{target.workout_id}"),
            lambda result: require_response(result, b"Completed Workout Summary", target.routine_name.encode()))

    # Fix the request clock so relative presets stay repeatable on future runs.
    with patch("progress.routes.datetime", wraps=datetime) as clock:
        clock.now.return_value = AS_OF
        for period, start, end in PERIODS:
            query = {"period": period, "start_date": start, "end_date": end, "exercise": "BENCH-E1"}
            measure(f"GET analytics / {period}", lambda: client.get("/progress/analytics", query_string=query),
                    lambda result: require_response(
                        result, b"weekly-consistency-chart", b"exercise-progression-chart",
                        b"All-time Personal Records",
                    ))
    assert path.read_bytes() == snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", type=int, choices=SIZES, metavar="SIZE",
                        help="run a loopback browser preview using the given fixture size")
    parser.add_argument("--port", type=int, default=5094, help="loopback browser preview port")
    args = parser.parse_args()
    with TemporaryDirectory(prefix="gymmick-benchmark-") as directory:
        path = Path(directory) / "workouts.json"
        if args.serve:
            write_fixture(path, make_workouts(args.serve))
            app = create_app({"WORKOUT_STORAGE_PATH": path})
            app.run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False)
        else:
            for size in SIZES:
                benchmark(path, size)


if __name__ == "__main__":
    main()
