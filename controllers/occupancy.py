"""Occupancy Monitoring pages (US-03): the member view and the staff front desk.

Both pages ask for /status.json every 5 seconds, so counts update within the
10 seconds the SRS requires (3.1.1). Members only ever see counts (SRS 3.2.2).
"""
from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from occupancyTrends import OccupancyError

from .common import myId, rolesAllowed, svc

occupancy = Blueprint("occupancy", __name__)


# ---- members ---------------------------------------------------------------------------------------

@occupancy.route("/occupancy")
@rolesAllowed("student")
def member():
    return render_template("occupancy/member.html", status=svc("occupancy").getMemberStatus(myId()))


@occupancy.route("/occupancy/status.json")
@rolesAllowed("student")
def memberStatus():
    return jsonify(svc("occupancy").getMemberStatus(myId()))


@occupancy.route("/occupancy/request", methods=["POST"])
@rolesAllowed("student")
def requestEntry():
    try:
        flash(svc("occupancy").requestEntry(myId()), "success")
    except OccupancyError as e:
        flash(str(e), "info")
    return redirect(url_for("occupancy.member"))


# ---- staff ------------------------------------------------------------------------------------------

def _withNames(status: dict) -> dict:
    accounts = svc("accounts")
    for group in ("queue", "inside", "askedToLeave"):
        for row in status.get(group, []):
            row["name"] = (accounts.get(row["uwiId"]) or {}).get("name", "Unknown")
    return status


@occupancy.route("/desk")
@rolesAllowed("staff")
def desk():
    return render_template("occupancy/desk.html", status=_withNames(svc("occupancy").getStaffStatus()))


@occupancy.route("/desk/status.json")
@rolesAllowed("staff")
def deskStatus():
    return jsonify(_withNames(svc("occupancy").getStaffStatus()))


def _act(action, *args):
    try:
        flash(action(*args), "success")
    except OccupancyError as e:
        flash(str(e), "error")
    return redirect(url_for("occupancy.desk"))


@occupancy.route("/desk/check-in", methods=["POST"])
@rolesAllowed("staff")
def checkIn():
    return _act(svc("occupancy").recordEntry, request.form.get("uwiId", "").strip(), myId())


@occupancy.route("/desk/check-out", methods=["POST"])
@rolesAllowed("staff")
def checkOut():
    return _act(svc("occupancy").recordExit, request.form.get("uwiId", "").strip(), myId())


@occupancy.route("/desk/queue", methods=["POST"])
@rolesAllowed("staff")
def addToQueue():
    return _act(svc("occupancy").staffAddToQueue, myId(), request.form.get("uwiId", "").strip())


@occupancy.route("/desk/queue/<entryId>/remove", methods=["POST"])
@rolesAllowed("staff")
def removeFromQueue(entryId):
    return _act(svc("occupancy").staffRemoveFromQueue, myId(), entryId)
