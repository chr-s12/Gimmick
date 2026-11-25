from collections import Counter
from datetime import datetime, timezone

from flask import Blueprint, current_app, redirect, render_template, request, url_for

from progress.charts import (
    EXERCISE_METRICS,
    build_exercise_chart,
    build_weekly_chart,
)
from progress.mock_dependencies import (
    get_student,
    get_student_routines,
    get_student_routine
)

from progress.periods import PERIOD_LABELS, PeriodFilterError, resolve_period
from progress.repository import WorkoutLogStorageError


_DEMO_STUDENT_ID = "ST001"


progress_bp = Blueprint(
    "progress",
    __name__,
    template_folder="templates",
    static_folder="static"
)


@progress_bp.route("/")
def dashboard():
    student_id = _DEMO_STUDENT_ID

    student = get_student(student_id)
    routines = get_student_routines(student_id)

    return render_template(
        "progress/dashboard.html",
        student=student,
        routines=routines
    )


@progress_bp.route("/log/<routine_id>", methods=["GET", "POST"])
def log_workout(routine_id):
    student_id = _DEMO_STUDENT_ID
    routine = get_student_routine(student_id, routine_id)

    if routine is None:
        return render_template(
            "progress/error.html",
            title="Routine unavailable",
            message="This saved routine could not be found.",
        ), 404

    form_data = request.form.to_dict() if request.method == "POST" else None
    service = current_app.extensions["progress_service"]
    errors = service.validate_workout(routine, form_data)
    status = 400 if errors else 200
    storage_error = None

    if form_data is not None and not errors:
        try:
            workout = service.log_workout(student_id, routine, form_data)
        except WorkoutLogStorageError:
            current_app.logger.exception("Could not save completed workout")
            storage_error = "Your workout could not be saved. Please try again."
            status = 500
        else:
            return redirect(
                url_for("progress.workout_summary", workout_id=workout.workout_id),
                code=303,
            )

    return render_template(
        "progress/log_workout.html",
        routine=routine,
        errors=errors,
        form_data=form_data or {},
        storage_error=storage_error,
    ), status


@progress_bp.get("/history")
def workout_history():
    service = current_app.extensions["progress_service"]
    try:
        workouts = service.get_workout_history(_DEMO_STUDENT_ID)
    except WorkoutLogStorageError:
        current_app.logger.exception("Could not retrieve workout history")
        return render_template(
            "progress/error.html",
            title="Workout history unavailable",
            message="Your workout history could not be loaded. Please try again.",
        ), 500

    return render_template("progress/workout_history.html", workouts=workouts)


@progress_bp.get("/workouts/<workout_id>")
def workout_summary(workout_id):
    service = current_app.extensions["progress_service"]
    try:
        workout = service.get_workout(_DEMO_STUDENT_ID, workout_id)
    except WorkoutLogStorageError:
        current_app.logger.exception("Could not retrieve completed workout")
        return render_template(
            "progress/error.html",
            title="Workout summary unavailable",
            message="Your workout could not be loaded. Please try again.",
        ), 500

    if workout is None:
        return render_template(
            "progress/error.html",
            title="Workout unavailable",
            message="This saved workout could not be found.",
        ), 404
    return render_template("progress/workout_summary.html", workout=workout)


def _exercise_options(exercises):
    """Label duplicate names with their stable exercise IDs."""
    name_counts = Counter(exercise.exercise_name.casefold() for exercise in exercises)
    return tuple(
        (exercise.exercise_id, (
            f"{exercise.exercise_name} ({exercise.exercise_id})"
            if name_counts[exercise.exercise_name.casefold()] > 1
            else exercise.exercise_name
        ))
        for exercise in exercises
    )


@progress_bp.get("/analytics")
def analytics_dashboard():
    as_of = datetime.now(timezone.utc)
    period = request.args.get("period", "all")
    start = request.args.get("start_date", "")
    end = request.args.get("end_date", "")
    try:
        start_date, end_date = resolve_period(period, start, end, as_of)
    except PeriodFilterError as error:
        return render_template(
            "progress/analytics.html",
            period=period,
            period_labels=PERIOD_LABELS,
            form_start=start,
            form_end=end,
            period_error=str(error),
            chart_selection={
                name: request.args.get(name)
                for name in ("exercise", "metric", "record_exercise", "record_weight")
                if name in request.args
            },
        ), 400

    service = current_app.extensions["progress_service"]
    try:
        analytics = service.get_analytics(
            _DEMO_STUDENT_ID, start_date=start_date, end_date=end_date, as_of=as_of,
        )
    except (WorkoutLogStorageError, ValueError):
        current_app.logger.exception("Could not calculate student progress")
        return render_template(
            "progress/error.html",
            title="My Progress unavailable",
            message="Your progress could not be loaded. Please try again.",
        ), 500

    records_by_exercise = {record.exercise_id: record for record in analytics.personal_records}
    progression = {item.exercise_id: item for item in analytics.exercise_progression}
    # All-time records keep exercises selectable even when the filtered series is empty.
    catalogue = progression | records_by_exercise
    first_exercise = min(catalogue, default=None)
    exercise_id = request.args.get("exercise", first_exercise)
    if exercise_id not in catalogue:
        exercise_id = first_exercise
    exercise = progression.get(exercise_id)
    metric_key = request.args.get("metric", "weight")
    if metric_key not in EXERCISE_METRICS:
        metric_key = "weight"
    exercise_chart = (
        build_exercise_chart(exercise, EXERCISE_METRICS[metric_key])
        if exercise is not None else None
    )
    selected_records = records_by_exercise.get(
        request.args.get("record_exercise"), next(iter(records_by_exercise.values()), None),
    )
    repetitions = selected_records.repetition_records if selected_records else ()
    repetitions_by_weight = {str(record.weight_kg): record for record in repetitions}
    selected_repetition = repetitions_by_weight.get(
        request.args.get("record_weight"), repetitions[-1] if repetitions else None,
    )
    chart_selection = {
        "exercise": exercise_id,
        "metric": metric_key,
        "record_exercise": selected_records.exercise_id if selected_records else None,
        "record_weight": str(selected_repetition.weight_kg) if selected_repetition else None,
    }
    selection = {
        **chart_selection,
        "period": period,
        "start_date": start_date if period == "custom" else None,
        "end_date": end_date if period == "custom" else None,
    }
    return render_template(
        "progress/analytics.html",
        analytics=analytics,
        weekly_chart=build_weekly_chart(analytics.weekly_consistency),
        exercise_chart=exercise_chart,
        exercise_options=_exercise_options(tuple(catalogue[key] for key in sorted(catalogue))),
        selected_chart_exercise=catalogue.get(exercise_id),
        record_options=_exercise_options(analytics.personal_records),
        selected_records=selected_records,
        selected_repetition=selected_repetition,
        selection=selection,
        chart_selection=chart_selection,
        period=period,
        period_labels=PERIOD_LABELS,
        form_start=selection["start_date"] or "",
        form_end=selection["end_date"] or "",
        exercise_id=exercise_id,
        exercise_metrics=EXERCISE_METRICS,
        metric_key=metric_key,
    )
