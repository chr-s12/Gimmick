"""View Clientele pages (US-06): client list, client profiles and assigning routines."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from routineBuilder import RoutineError, parseExercises
from viewClientele import ClienteleError

from .common import formRows, myId, rolesAllowed, svc
from .routines import ROW_FIELDS

clients = Blueprint("clients", __name__, url_prefix="/clients")


@clients.route("/")
@rolesAllowed("trainer")
def clientList():
    return render_template("clients/list.html", **svc("clientele").listClients(myId()))


@clients.route("/<clientId>")
@rolesAllowed("trainer")
def profile(clientId):
    try:
        client = svc("clientele").getClientProfile(myId(), clientId)
    except ClienteleError as e:
        flash(str(e), "error")
        return redirect(url_for("clients.clientList"))
    return render_template("clients/profile.html", client=client, myRoutines=svc("routines").listOwn(myId()),
                           common=svc("routines").commonExercises())


@clients.route("/<clientId>/assign", methods=["POST"])
@rolesAllowed("trainer")
def assign(clientId):
    form = request.form
    try:
        chosen = form.get("fromRoutine", "")
        if chosen:   # copy one of the trainer's saved routines
            routine = svc("routines").getOwn(myId(), chosen)
            name, exercises = routine["name"], routine["exercises"]
        else:        # or build one here
            name = form.get("routine_name", "")
            exercises = [{"name": e.getExcerName(), "sets": e.getNumSets(), "reps": e.getNumReps(),
                          "rest": e.getRestTime(), "weight": e.getWeightKG()}
                         for e in parseExercises(*formRows(form, *ROW_FIELDS))]
        items = [{"excerName": e["name"], "numSets": e["sets"], "numReps": e["reps"], "restTime": e["rest"],
                  "weightKG": e["weight"]} for e in exercises]
        svc("clientele").assignRoutine(myId(), clientId, name, items)
        flash(f"Assigned {name}. Your client has been notified.", "success")
    except (ClienteleError, RoutineError) as e:   # includes SharingDisabledError
        flash(str(e), "error")
    return redirect(url_for("clients.profile", clientId=clientId))
