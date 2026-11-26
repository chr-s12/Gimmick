"""Build Routines pages (US-01): create, edit, delete with confirmation, and adopt templates."""
from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from routineBuilder import RoutineError, parseExercises

from .common import formRows, myId, rolesAllowed, svc

routines = Blueprint("routines", __name__, url_prefix="/routines")
ROW_FIELDS = ("excer_name", "num_sets", "num_reps", "rest_time", "weight_kg")


def _rowsFromForm(form):
    cols = formRows(form, *ROW_FIELDS)
    count = max(len(c) for c in cols)
    return [{"name": c0, "sets": c1, "reps": c2, "rest": c3, "weight": c4}
            for c0, c1, c2, c3, c4 in zip(*(c + [""] * (count - len(c)) for c in cols))]


def _builder(title, action, name="", rows=None, isPublic=False, status=200):
    rows = list(rows or [])
    rows += [{"name": "", "sets": "", "reps": "", "rest": "", "weight": ""}] * max(0, 3 - len(rows))
    return render_template("routines/builder.html", title=title, action=action, name=name, rows=rows,
                           isPublic=isPublic, common=svc("routines").commonExercises()), status


@routines.route("/")
@rolesAllowed("student", "trainer")
def myRoutines():
    service = svc("routines")
    trainerAdded = service.trainerAdded(myId()) if g.user["role"] == "student" else []
    return render_template("routines/list.html", routines=service.listOwn(myId()), trainerAdded=trainerAdded)


@routines.route("/new", methods=["GET", "POST"])
@rolesAllowed("student", "trainer")
def create():
    if request.method == "POST":
        form = request.form
        try:
            exercises = parseExercises(*formRows(form, *ROW_FIELDS))
            routine = svc("routines").create(myId(), form.get("routine_name"), exercises,
                                             form.get("is_public") == "on")
        except RoutineError as e:
            flash(str(e), "error")
            return _builder("New routine", url_for("routines.create"), form.get("routine_name", ""),
                            _rowsFromForm(form), form.get("is_public") == "on", 400)
        flash(f"Saved {routine['name']}.", "success")
        return redirect(url_for("routines.myRoutines"))
    return _builder("New routine", url_for("routines.create"))


@routines.route("/<routineId>/edit", methods=["GET", "POST"])
@rolesAllowed("student", "trainer")
def edit(routineId):
    service = svc("routines")
    try:
        routine = service.getOwn(myId(), routineId)
    except RoutineError as e:
        flash(str(e), "error")
        return redirect(url_for("routines.myRoutines"))
    action = url_for("routines.edit", routineId=routineId)
    if request.method == "POST":
        form = request.form
        try:
            exercises = parseExercises(*formRows(form, *ROW_FIELDS))
            saved = service.edit(myId(), routineId, form.get("routine_name"), exercises, form.get("is_public") == "on")
        except RoutineError as e:
            flash(str(e), "error")
            return _builder("Edit routine", action, form.get("routine_name", ""), _rowsFromForm(form),
                            form.get("is_public") == "on", 400)
        flash(f"Saved your changes to {saved['name']}.", "success")
        return redirect(url_for("routines.myRoutines"))
    rows = [{"name": e["name"], "sets": e["sets"], "reps": e["reps"], "rest": e["rest"],
             "weight": f"{e['weight']:g}"} for e in routine["exercises"]]
    return _builder("Edit routine", action, routine["name"], rows, routine["isPublic"])


@routines.route("/<routineId>/delete", methods=["GET", "POST"])
@rolesAllowed("student", "trainer")
def delete(routineId):
    """AC-01.0: the user must confirm before a routine is deleted."""
    service = svc("routines")
    try:
        routine = service.getOwn(myId(), routineId)
        if request.method == "POST":
            flash(service.delete(myId(), routineId), "success")
            return redirect(url_for("routines.myRoutines"))
    except RoutineError as e:
        flash(str(e), "error")
        return redirect(url_for("routines.myRoutines"))
    return render_template("routines/confirmDelete.html", routine=routine)


@routines.route("/templates")
@rolesAllowed("student", "trainer")
def templates():
    return render_template("routines/templates.html", templates=svc("routines").listTemplates(myId()))


@routines.route("/templates/<routineId>/adopt", methods=["POST"])
@rolesAllowed("student", "trainer")
def adopt(routineId):
    try:
        routine = svc("routines").adopt(myId(), routineId)
        flash(f"Added {routine['name']} to your routines. You can change it however you like.", "success")
        return redirect(url_for("routines.myRoutines"))
    except RoutineError as e:
        flash(str(e), "error")
        return redirect(url_for("routines.templates"))
