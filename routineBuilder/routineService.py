"""RoutineService (SDS 2.3.1): Build Routines, US-01 (SRS 2.3.1).

Uses the team's Routine, Exercise and Student classes for storage. Adds the
rules from the SRS: every routine needs a name and at least one valid exercise
(AC-01.3, AC-01.4), users only ever touch their own routines, and only
trainers publish the pre-designed templates students can adopt (Assumption 9).
Routines a trainer assigned through View Clientele are listed as trainer-added.
"""
import re
from typing import List, Optional

from accounts.repositories import UserRepository
from Exercise import Exercise
from Routine import Routine
from Student import Student
from viewClientele.repositories import AssignedRoutineRepository

MAX_EXERCISES = 20


class RoutineError(Exception):
    """Shown to the user as-is; nothing is saved when one is raised."""


def _number(text, label: str, exercise: str, minimum, whole=True):
    text = (str(text) if text is not None else "").strip()
    try:
        value = int(text) if whole else float(text)
    except ValueError:
        kind = "whole number" if whole else "number"
        raise RoutineError(f"{label} for {exercise} must be a {kind}.") from None
    if value != value or value in (float("inf"), float("-inf")) or value < minimum:
        raise RoutineError(f"{label} for {exercise} must be at least {minimum}.")
    return value


def parseExercises(names, sets, reps, rests, weights) -> List[Exercise]:
    """Turn the builder's form rows into Exercise objects. Fully blank rows are ignored."""
    exercises = []
    rows = max(len(names), len(sets), len(reps), len(rests), len(weights))
    for i in range(rows):
        cell = lambda column: (column[i] if i < len(column) else "").strip()
        name, row = cell(names), [cell(sets), cell(reps), cell(rests), cell(weights)]
        if not name and not any(row):
            continue
        if not name:
            raise RoutineError(f"Exercise {i + 1} needs a name.")
        if len(name) > 60:
            raise RoutineError(f"The name of exercise {i + 1} must be 60 characters or fewer.")
        exercises.append(Exercise(
            excer_name=name,
            num_sets=_number(row[0], "Sets", name, 1),
            num_reps=_number(row[1], "Reps", name, 1),
            rest_time=_number(row[2] or "0", "Rest time", name, 0),
            weight_kg=_number(row[3] or "0", "Weight", name, 0, whole=False),
        ))
    if not exercises:
        raise RoutineError("A routine needs at least one exercise.")
    if len(exercises) > MAX_EXERCISES:
        raise RoutineError(f"A routine can have at most {MAX_EXERCISES} exercises.")
    return exercises


def routineView(r: Routine) -> dict:
    return {"routineId": r.getRoutineId(), "name": r.getRoutineName(), "isPublic": r.getIsPublic(),
            "exercises": [{"name": e.getExcerName(), "sets": e.getNumSets(), "reps": e.getNumReps(),
                           "rest": e.getRestTime(), "weight": e.getWeightKG(), "isCustom": e.getIsCustom()}
                          for e in r.getExerciseList()]}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "exercise"


class RoutineService:
    def __init__(self, users: UserRepository, assigned: AssignedRoutineRepository):
        self.users, self.assigned = users, assigned

    # ---- checks -----------------------------------------------------------------------------------

    def _account(self, uwiId: str) -> dict:
        user = self.users.get(uwiId)
        if not user or user.get("role") not in ("student", "trainer"):
            raise RoutineError("Only students and personal trainers have routines.")
        return user

    def _owner(self, uwiId: str) -> Student:
        account = self._account(uwiId)
        owner = Student.loadUser(uwiId)
        return owner if owner is not None else Student(account["name"], uwiId)

    def _own(self, owner: Student, routineId: str) -> Routine:
        routine = owner.getRoutineById(routineId)
        if routine is None:   # someone else's routine, or one that doesn't exist (scenario: assign to another student)
            raise RoutineError("That routine isn't on your profile.")
        return routine

    @staticmethod
    def _name(name: str) -> str:
        name = " ".join((name or "").split())
        if not name:
            raise RoutineError("Give the routine a name.")
        if len(name) > 60:
            raise RoutineError("The routine name must be 60 characters or fewer.")
        return name

    @staticmethod
    def _public(uwiId: str, isPublic: bool) -> bool:
        """Any student or trainer can publish a routine as a template (test plan TC-0.1.0, TC-0.1.10)."""
        return bool(isPublic)

    # ---- AC-01.0 / AC-01.2: create, edit, delete ---------------------------------------------------

    def listOwn(self, uwiId: str) -> List[dict]:
        return [routineView(r) for r in self._owner(uwiId)._routine_list]

    def getOwn(self, uwiId: str, routineId: str) -> dict:
        return routineView(self._own(self._owner(uwiId), routineId))

    def create(self, uwiId: str, name: str, exercises: List[Exercise], isPublic: bool = False) -> dict:
        owner = self._owner(uwiId)
        routine = owner.buildRoutine(self._name(name), exercises, self._public(uwiId, isPublic))
        return routineView(routine)

    def edit(self, uwiId: str, routineId: str, name: str, exercises: List[Exercise], isPublic: bool = False) -> dict:
        owner = self._owner(uwiId)
        routine = self._own(owner, routineId)
        routine.setRoutineName(self._name(name))
        routine.setExercises(exercises)
        routine.setIspublic(self._public(uwiId, isPublic))
        if not routine.saveRoutine():
            raise RoutineError("The routine could not be saved. Please try again.")
        return routineView(routine)

    def delete(self, uwiId: str, routineId: str) -> str:
        owner = self._owner(uwiId)
        routine = self._own(owner, routineId)
        owner.deleteRoutine(routine)
        owner.userSave()
        return f"Deleted {routine.getRoutineName()}."

    # ---- AC-01.1: pre-designed templates --------------------------------------------------------------

    def listTemplates(self, uwiId: str) -> List[dict]:
        mine = {r["routineId"] for r in self.listOwn(uwiId)}
        authors = {}
        for u in self.users.listAll():
            for rid in u.get("routineIds", u.get("Routine List", [])):
                authors[rid] = u.get("name", u.get("Username", ""))
        return [dict(routineView(r), author=authors.get(r.getRoutineId(), "Gym team"))
                for r in Routine.getPublicRoutines() if r.getRoutineId() not in mine]

    def adopt(self, uwiId: str, routineId: str) -> dict:
        owner = self._owner(uwiId)
        template = next((r for r in Routine.getPublicRoutines() if r.getRoutineId() == routineId), None)
        if template is None:
            raise RoutineError("That template is no longer available.")
        if owner.getRoutineById(routineId):
            raise RoutineError("This is already your routine.")
        if not owner.adoptRoutine(template):
            raise RoutineError("The routine could not be added. Please try again.")
        return routineView(owner._routine_list[-1])

    # ---- trainer-added routines (View Clientele) and Track Progress ---------------------------------

    def trainerAdded(self, uwiId: str) -> List[dict]:
        routines = sorted(self.assigned.forStudent(uwiId), key=lambda r: r.assignedAt, reverse=True)
        return [{"routineId": r.routineId, "name": r.routineName, "addedByName": r.addedByName,
                 "assignedAt": r.assignedAt,
                 "exercises": [{"name": e.excerName, "sets": e.numSets, "reps": e.numReps, "rest": e.restTime,
                                "weight": e.weightKG} for e in r.exercises]} for r in routines]

    def progressRoutines(self, uwiId: str) -> List[dict]:
        """The student's routines in the shape Track Progress (progress/) logs workouts from."""
        if (self.users.get(uwiId) or {}).get("role") != "student":
            return []
        result = []
        for r in self.listOwn(uwiId) + self.trainerAdded(uwiId):
            seen, exercises = {}, []
            for e in r["exercises"]:
                slug = _slug(e["name"])
                seen[slug] = seen.get(slug, 0) + 1
                exercises.append({"exercise_id": slug if seen[slug] == 1 else f"{slug}-{seen[slug]}",
                                  "exercise_name": e["name"], "sets": e["sets"], "reps": e["reps"],
                                  "weight_kg": e["weight"]})
            name = r["name"] + (f" (from {r['addedByName']})" if "addedByName" in r else "")
            result.append({"routine_id": r["routineId"], "student_id": uwiId, "routine_name": name,
                           "exercises": exercises})
        return result

    def progressRoutine(self, uwiId: str, routineId: str) -> Optional[dict]:
        return next((r for r in self.progressRoutines(uwiId) if r["routine_id"] == routineId), None)

    @staticmethod
    def commonExercises() -> List[str]:
        return Exercise.getCommonExercises()
