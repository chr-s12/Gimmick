"""Book Trainers pages (US-05): trainer list, profiles, requests, and the student's sessions."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from bookTrainers import BookingError

from .common import myId, rolesAllowed, svc

booking = Blueprint("booking", __name__)


@booking.route("/trainers")
@rolesAllowed("student")
def trainers():
    service = svc("booking")
    rows = []
    for t in service.listTrainers(myId()):
        profile = service.getTrainerProfile(myId(), t["uwiId"])
        rows.append(dict(t, freeCount=len(profile["availableSlots"]),
                         nextFree=profile["availableSlots"][0]["label"] if profile["availableSlots"] else None))
    return render_template("booking/trainers.html", trainers=rows)


@booking.route("/trainers/<trainerId>")
@rolesAllowed("student")
def trainer(trainerId):
    try:
        profile = svc("booking").getTrainerProfile(myId(), trainerId)
    except BookingError as e:
        flash(str(e), "error")
        return redirect(url_for("booking.trainers"))
    return render_template("booking/trainer.html", trainer=profile)


@booking.route("/trainers/<trainerId>/book", methods=["POST"])
@rolesAllowed("student")
def book(trainerId):
    try:
        svc("booking").requestBooking(myId(), request.form.get("slotId", ""))
        flash("Your request was sent to the trainer for confirmation. You'll get a notification when they answer.",
              "success")
        return redirect(url_for("booking.sessions"))
    except BookingError as e:
        flash(str(e), "error")
        return redirect(url_for("booking.trainer", trainerId=trainerId))


@booking.route("/sessions")
@rolesAllowed("student")
def sessions():
    return render_template("booking/sessions.html", sessions=svc("booking").getStudentSchedule(myId()))


def _mySession(bookingId):
    return next((s for s in svc("booking").getStudentSchedule(myId()) if s["bookingId"] == bookingId), None)


@booking.route("/sessions/<bookingId>/change", methods=["GET", "POST"])
@rolesAllowed("student")
def change(bookingId):
    session = _mySession(bookingId)
    if session is None:
        flash("That session could not be found.", "error")
        return redirect(url_for("booking.sessions"))
    if request.method == "POST":
        try:
            svc("booking").editBooking(myId(), bookingId, request.form.get("slotId", ""))
            flash("Your change request was sent to the trainer. Your current session stays booked until they "
                  "accept the new time.", "success")
            return redirect(url_for("booking.sessions"))
        except BookingError as e:
            flash(str(e), "error")
    profile = svc("booking").getTrainerProfile(myId(), session["trainerId"])
    return render_template("booking/change.html", session=session, slots=profile["availableSlots"])


@booking.route("/sessions/<bookingId>/cancel", methods=["GET", "POST"])
@rolesAllowed("student")
def cancel(bookingId):
    session = _mySession(bookingId)
    if session is None:
        flash("That session could not be found.", "error")
        return redirect(url_for("booking.sessions"))
    if request.method == "POST":
        try:
            svc("booking").cancelBooking(myId(), bookingId)
            flash("Cancelled. Your trainer has been told.", "success")
        except BookingError as e:
            flash(str(e), "error")
        return redirect(url_for("booking.sessions"))
    return render_template("booking/confirmCancel.html", session=session)
