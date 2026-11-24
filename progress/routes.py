
from flask import Blueprint, render_template

progress_bp = Blueprint(
    "progress",
    __name__,
    template_folder="templates",
    static_folder="static"
)


@progress_bp.route("/")
def dashboard():
    return render_template("progress/dashboard.html")
