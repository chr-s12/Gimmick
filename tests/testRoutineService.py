"""Tests for Build Routines (US-01) through RoutineService and the team's Routine classes."""
import pytest

from accounts import buildAccountService
from routineBuilder import RoutineError, buildRoutineService, parseExercises
from viewClientele import buildClienteleService
from viewClientele.repositories import BookingRepository
from viewClientele.models import Booking, BookingStatus
from datetime import datetime, timedelta


def rows(*exercises):
    """("Bench Press", "3", "8", "90", "40"), ... -> the builder's five form columns."""
    return [list(column) for column in zip(*exercises)] if exercises else [[], [], [], [], []]


@pytest.fixture
def service(tmp_path):
    accounts = buildAccountService(str(tmp_path))
    accounts.createAccount("620100001", "Sam Student", "student", "secret123", workoutSharing=True)
    accounts.createAccount("620100002", "Tia Student", "student", "secret123")
    accounts.createAccount("700000001", "Jo Trainer", "trainer", "coach1234", specialisations=["Strength"])
    return buildRoutineService(str(tmp_path))


def push():
    return parseExercises(*rows(("Bench Press", "3", "8", "90", "40"), ("Dips", "3", "10", "60", "")))


# AC-01.0 / AC-01.2
def test_createdRoutineIsSavedAndReopensTheSame(service, tmp_path):
    created = service.create("620100001", "Push day", push())
    reopened = buildRoutineService(str(tmp_path)).getOwn("620100001", created["routineId"])
    assert reopened == created
    assert [(e["name"], e["sets"], e["reps"], e["weight"]) for e in reopened["exercises"]] == \
        [("Bench Press", 3, 8, 40.0), ("Dips", 3, 10, 0.0)]


# AC-01.3
def test_routineWithNoExercisesIsRefused(service):
    with pytest.raises(RoutineError, match="at least one exercise"):
        parseExercises(*rows(("", "", "", "", "")))
    assert service.listOwn("620100001") == []


# AC-01.4
@pytest.mark.parametrize("row, message", [
    (("Squat", "-1", "8", "60", "50"), "Sets for Squat must be at least 1"),
    (("Squat", "3", "", "60", "50"), "Reps for Squat must be a whole number"),
    (("Squat", "3", "8", "60", "-5"), "Weight for Squat must be at least 0"),
    (("", "3", "8", "60", "50"), "Exercise 1 needs a name"),
])
def test_invalidExerciseDetailsAreRefused(row, message):
    with pytest.raises(RoutineError, match=message):
        parseExercises(*rows(row))


def test_routineNeedsAName(service):
    with pytest.raises(RoutineError, match="name"):
        service.create("620100001", "   ", push())


def test_editAndDeleteOwnRoutine(service):
    routine = service.create("620100001", "Push day", push())
    edited = service.edit("620100001", routine["routineId"], "Push day 2",
                          parseExercises(*rows(("Overhead Press", "4", "6", "120", "30"))))
    assert edited["name"] == "Push day 2" and [e["name"] for e in edited["exercises"]] == ["Overhead Press"]
    service.delete("620100001", routine["routineId"])
    assert service.listOwn("620100001") == []


def test_cannotTouchAnotherStudentsRoutine(service):
    routine = service.create("620100001", "Push day", push())
    with pytest.raises(RoutineError, match="isn't on your profile"):
        service.edit("620100002", routine["routineId"], "Mine now", push())
    with pytest.raises(RoutineError, match="isn't on your profile"):
        service.delete("620100002", routine["routineId"])
    assert service.listOwn("620100002") == []


# AC-01.1: templates
def test_onlyTrainersPublishTemplatesAndStudentsAdoptACopy(service):
    studentRoutine = service.create("620100001", "Mine", push(), isPublic=True)
    assert studentRoutine["isPublic"] is False
    template = service.create("700000001", "Beginner strength", push(), isPublic=True)
    assert [t["name"] for t in service.listTemplates("620100002")] == ["Beginner strength"]
    adopted = service.adopt("620100002", template["routineId"])
    assert adopted["routineId"] != template["routineId"] and adopted["isPublic"] is False
    service.edit("620100002", adopted["routineId"], "My strength", push())   # the copy can be changed
    assert service.getOwn("700000001", template["routineId"])["name"] == "Beginner strength"


def test_progressSeesOwnAndTrainerAddedRoutines(service, tmp_path):
    service.create("620100001", "Push day", push())
    now = datetime(2026, 11, 30, 9, 0)
    BookingRepository(str(tmp_path)).add(Booking("620100001", "700000001", now + timedelta(hours=2),
                                                 BookingStatus.ACCEPTED))
    clientele = buildClienteleService(str(tmp_path), lambda: now)
    clientele.assignRoutine("700000001", "620100001", "Legs",
                            [{"excerName": "Squat", "numSets": 5, "numReps": 5, "restTime": 120, "weightKG": 60}])
    names = [r["routine_name"] for r in service.progressRoutines("620100001")]
    assert names == ["Push day", "Legs (from Jo Trainer)"]
    legs = service.progressRoutines("620100001")[1]
    assert legs["exercises"][0] == {"exercise_id": "squat", "exercise_name": "Squat", "sets": 5, "reps": 5,
                                    "weight_kg": 60}
