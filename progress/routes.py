
from flask import Blueprint, render_template

from progress.mock_dependencies import (
    get_student,
    get_student_routines
)


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
