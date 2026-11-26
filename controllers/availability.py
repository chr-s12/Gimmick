"""Manage Availability pages (US-02): the trainer's schedule, requests and sessions."""
from datetime import timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for

from bookTrainers import BookingError

from .common import myId, rolesAllowed, svc

availability = Blueprint("availability", __name__, url_prefix="/schedule")


def _back():
    return redirect(url_for("availability.schedule"))


@availability.route("/")
@rolesAllowed("trainer")
def schedule():
    tomorrow = (svc("clock")() + timedelta(days=1)).date().isoformat()
    return render_template("availability/schedule.html", schedule=svc("availability").getSchedule(myId()),
                           defaultDate=tomorrow)


@availability.route("/slots", methods=["POST"])
@rolesAllowed("trainer")
def addSlot():
    f = request.form
    try:
        slot = svc("availability").addSlot(myId(), f.get("date"), f.get("start"), f.get("end"))
        flash(f"Added {slot.start:%a %d %b, %H:%M}-{slot.end:%H:%M}. Students can now book it.", "success")
    except BookingError as e:
        flash(str(e), "error")
    return _back()


@availability.route("/slots/<slotId>/edit", methods=["GET", "POST"])
@rolesAllowed("trainer")
def editSlot(slotId):
    service = svc("availability")
    try:
        if request.method == "POST":
            f = request.form
            slot = service.editSlot(myId(), slotId, f.get("date"), f.get("start"), f.get("end"))
            flash(f"Updated the slot to {slot.start:%a %d %b, %H:%M}-{slot.end:%H:%M}.", "success")
            return _back()
        slot = service.getSlot(myId(), slotId)
    except BookingError as e:
        flash(str(e), "error")
        if request.method == "POST":
            return redirect(url_for("availability.editSlot", slotId=slotId))
        return _back()
    return render_template("availability/editSlot.html", slot=slot)


@availability.route("/slots/<slotId>/remove", methods=["POST"])
@rolesAllowed("trainer")
def removeSlot(slotId):
    try:
        svc("availability").removeSlot(myId(), slotId)
        flash("Removed the slot. Students can no longer book it.", "success")
    except BookingError as e:
        flash(str(e), "error")
    return _back()


@availability.route("/requests/<bookingId>/<answer>", methods=["POST"])
@rolesAllowed("trainer")
def respond(bookingId, answer):
    if answer not in ("accept", "decline"):
        return _back()
    try:
        svc("availability").respondToRequest(myId(), bookingId, answer == "accept")
        flash("Session confirmed. The student has been told." if answer == "accept"
              else "Request declined. The student has been told.", "success")
    except BookingError as e:
        flash(str(e), "error")
    return _back()


@availability.route("/sessions/<bookingId>/cancel", methods=["GET", "POST"])
@rolesAllowed("trainer")
def cancelSession(bookingId):
    """Cancelling needs a confirmation step; leaving the page keeps the session (SRS 2.3.2)."""
    service = svc("availability")
    schedule = service.getSchedule(myId())
    session = next((s for s in schedule["sessions"] + schedule["requests"] if s["bookingId"] == bookingId), None)
    if session is None:
        flash("That session could not be found.", "error")
        return _back()
    if request.method == "POST":
        try:
            service.cancelSession(myId(), bookingId)
            flash(f"Cancelled the session with {session['studentName']}. They have been told.", "success")
        except BookingError as e:
            flash(str(e), "error")
        return _back()
    return render_template("availability/confirmCancel.html", session=session)


@availability.route("/sessions/<bookingId>/move", methods=["GET", "POST"])
@rolesAllowed("trainer")
def moveSession(bookingId):
    service = svc("availability")
    try:
        if request.method == "POST":
            booking = service.moveSession(myId(), bookingId, request.form.get("slotId"))
            flash(f"Moved the session to {booking.start:%a %d %b, %H:%M}. The student has been told.", "success")
            return _back()
        schedule = service.getSchedule(myId())
        session = next((s for s in schedule["sessions"] if s["bookingId"] == bookingId), None)
        if session is None:
            raise BookingError("Only a confirmed session can be moved.")
        options = service.freeSlotsForMove(myId(), bookingId)
    except BookingError as e:
        flash(str(e), "error")
        return _back()
    return render_template("availability/move.html", session=session, options=options)
