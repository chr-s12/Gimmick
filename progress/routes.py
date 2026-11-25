
from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for

from progress.mock_dependencies import (
    get_student,
    get_student_routines,
    get_student_routine
)

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
        abort(404)

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
        abort(500, description="Your workout history could not be loaded. Please try again.")

    return render_template("progress/workout_history.html", workouts=workouts)


@progress_bp.get("/workouts/<workout_id>")
def workout_summary(workout_id):
    service = current_app.extensions["progress_service"]
    try:
        workout = service.get_workout(_DEMO_STUDENT_ID, workout_id)
    except WorkoutLogStorageError:
        current_app.logger.exception("Could not retrieve completed workout")
        abort(500, description="Your workout could not be loaded. Please try again.")

    if workout is None:
        abort(404)
    return render_template("progress/workout_summary.html", workout=workout)
