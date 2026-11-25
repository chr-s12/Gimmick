
from flask import Blueprint, render_template, abort, request

from progress.mock_dependencies import (
    get_student,
    get_student_routines,
    get_student_routine
)

from progress.service import ProgressService


progress_bp = Blueprint(
    "progress",
    __name__,
    template_folder="templates",
    static_folder="static"
)


@progress_bp.route("/")
def dashboard():
    student_id = "ST001"

    student = get_student(student_id)
    routines = get_student_routines(student_id)

    return render_template(
        "progress/dashboard.html",
        student=student,
        routines=routines
    )


@progress_bp.route("/log/<routine_id>", methods=["GET", "POST"])
def log_workout(routine_id):
    student_id = "ST001"
    routine = get_student_routine(student_id, routine_id)

    if routine is None:
        abort(404)

    form_data = request.form.to_dict() if request.method == "POST" else None
    service = ProgressService()
    errors = service.validate_workout(routine, form_data)

    if request.method == "POST" and not errors:
        workout = service.create_workout(student_id, routine, form_data)
        return render_template("progress/workout_summary.html", workout=workout)

    return render_template(
        "progress/log_workout.html",
        routine=routine,
        errors=errors,
        form_data=form_data or {}
    ), 400 if errors else 200
