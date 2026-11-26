"""Home pages, notifications, settings, and the staff/operator admin tools (SRS 3.2.2, 4.1)."""
import io
import os
import zipfile
from datetime import datetime

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, send_file, url_for

from accounts import AccountError
from viewClientele import ClienteleError

from .common import myId, rolesAllowed, svc

home = Blueprint("home", __name__)


@home.route("/")
def index():
    role = g.user["role"]
    if role == "trainer":
        return redirect(url_for("availability.schedule"))
    if role == "staff":
        return redirect(url_for("occupancy.desk"))
    if role == "operator":
        return redirect(url_for("reports.report"))
    # Student dashboard: their routines are one click from login (SRS 3.3.3)
    routines = svc("routines")
    return render_template("home/student.html",
                           myRoutines=routines.listOwn(myId()),
                           trainerRoutines=routines.trainerAdded(myId()),
                           sessions=svc("booking").getStudentSchedule(myId())[:3],
                           gym=svc("occupancy").getMemberStatus(myId()),
                           notifications=svc("notifications").listForUser(myId())[:3])


@home.route("/notifications")
def notifications():
    items = svc("notifications").listForUser(myId())
    svc("notifications").markAllRead(myId())
    return render_template("home/notifications.html", items=items)


@home.route("/settings", methods=["GET", "POST"])
@rolesAllowed("student", "trainer")
def settings():
    if request.method == "POST":
        try:
            if g.user["role"] == "student":
                message = svc("clientele").setWorkoutSharing(myId(), request.form.get("workoutSharing") == "on")
            else:
                message = svc("accounts").updateTrainerProfile(myId(), request.form.get("specialisations", ""),
                                                               request.form.get("bio", ""))
            flash(message, "success")
        except (AccountError, ClienteleError) as e:
            flash(str(e), "error")
        return redirect(url_for("home.settings"))
    return render_template("home/settings.html", user=svc("accounts").get(myId()))


@home.route("/staff/reset-password", methods=["GET", "POST"])
@rolesAllowed("staff")
def resetPassword():
    if request.method == "POST":
        try:
            flash(svc("accounts").resetPassword(myId(), request.form.get("uwiId"), request.form.get("password")),
                  "success")
            return redirect(url_for("home.resetPassword"))
        except AccountError as e:
            flash(str(e), "error")
    return render_template("home/resetPassword.html")


@home.route("/admin/backup")
@rolesAllowed("operator")
def backup():
    """Download every data file as one zip, so records can be restored after a failure (SRS 4.1)."""
    dataDir = current_app.config["DATA_DIR"]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(os.listdir(dataDir)):
            if name.endswith(".json"):
                z.write(os.path.join(dataDir, name), name)
    buffer.seek(0)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    return send_file(buffer, mimetype="application/zip", as_attachment=True,
                     download_name=f"gymmick-backup-{stamp}.zip")
