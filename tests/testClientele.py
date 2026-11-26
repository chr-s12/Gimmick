"""Feature 6 - View Clientele acceptance scenarios (SRS 2.3.6)."""
from datetime import datetime, timedelta

import pytest

from viewClientele import AccessDeniedError, ClienteleError, SharingDisabledError, buildClienteleService
from viewClientele.models import Booking, BookingStatus
from viewClientele.repositories import BookingRepository, UserRepository, WorkoutLogRepository

NOW = datetime(2026, 11, 23, 10, 0)   # Monday 10:00
SQUAT = {"excerName": "Squat", "numSets": 3, "numReps": 8, "restTime": 90, "weightKG": 60}


class FakeClock:
    def __init__(self, start):
        self.now = start

    def __call__(self):
        return self.now


def workout(studentId, when, name="Leg Day"):
    return {"workout_id": f"w-{studentId}-{when}", "student_id": studentId, "routine_id": "r1",
            "routine_name": name, "completed_at": when,
            "exercises": [{"exercise_id": "e1", "exercise_name": "Squat", "sets": 3, "reps": 8, "weight_kg": 60.0}]}


@pytest.fixture
def dataDir(tmp_path):
    d = str(tmp_path)
    UserRepository(d).saveMany([
        {"uwiId": "T1", "name": "Trainer One", "role": "trainer"},
        {"uwiId": "T2", "name": "Trainer Two", "role": "trainer"},
        {"uwiId": "T3", "name": "Trainer Three", "role": "trainer"},
        {"uwiId": "S1", "name": "Front Desk", "role": "staff"},
        {"uwiId": "620200001", "name": "Amy Brown", "role": "student", "workoutSharing": True},
        {"uwiId": "620200002", "name": "Ben Clarke", "role": "student", "workoutSharing": False},
        {"uwiId": "620200003", "name": "Cara Dixon", "role": "student", "workoutSharing": True},
        {"uwiId": "620200004", "name": "Dan Ellis", "role": "student"},
        {"uwiId": "620200005", "name": "Eve Ford", "role": "student"},
    ])
    BookingRepository(d).add(
        Booking("620200001", "T1", NOW + timedelta(days=2), BookingStatus.ACCEPTED),
        Booking("620200001", "T1", NOW + timedelta(days=1), BookingStatus.ACCEPTED),
        Booking("620200001", "T2", NOW + timedelta(hours=5), BookingStatus.ACCEPTED),     # other trainer
        Booking("620200002", "T1", NOW - timedelta(minutes=30), BookingStatus.ACCEPTED),  # in progress
        Booking("620200003", "T2", NOW + timedelta(days=1), BookingStatus.ACCEPTED),      # T2's client only
        Booking("620200004", "T1", NOW - timedelta(days=3), BookingStatus.ACCEPTED),      # past only
        Booking("620200005", "T1", NOW + timedelta(days=1), BookingStatus.PENDING),       # not confirmed
        Booking("620200005", "T1", NOW + timedelta(days=2), BookingStatus.DECLINED),
        Booking("620200004", "T3", NOW - timedelta(days=1), BookingStatus.ACCEPTED),      # T3: nothing upcoming
    )
    WorkoutLogRepository(d).add(workout("620200001", "2026-11-20T18:00:00-05:00", "Push Day"),
                                workout("620200001", "2026-11-22T07:30:00-05:00", "Leg Day"),
                                workout("620200002", "2026-11-21T17:00:00-05:00"))
    return d


@pytest.fixture
def clientele(dataDir):
    return buildClienteleService(dataDir, clock=FakeClock(NOW))


def testTrainerSeesOnlyTheirActiveClients(clientele):
    roster = clientele.listClients("T1")
    assert roster["message"] is None
    assert [c["uwiId"] for c in roster["clients"]] == ["620200002", "620200001"]   # in-session client first
    amy = roster["clients"][1]
    assert amy["upcomingSessions"] == 2 and amy["nextSession"] == "2026-11-24T10:00"
    assert roster["clients"][0]["inSessionNow"]


def testTrainerWithNoUpcomingSessionsSeesEmptyState(clientele):
    roster = clientele.listClients("T3")
    assert roster["clients"] == [] and "no active clients" in roster["message"]


def testSharingClientProfileShowsWorkoutsNewestFirst(clientele):
    profile = clientele.getClientProfile("T1", "620200001")
    assert [w["routineName"] for w in profile["workouts"]] == ["Leg Day", "Push Day"]
    assert profile["workouts"][0]["exercises"][0] == {"name": "Squat", "sets": 3, "reps": 8, "weightKg": 60.0}


def testNonSharingClientWorkoutsAreHidden(clientele):
    profile = clientele.getClientProfile("T1", "620200002")
    assert profile["workouts"] is None
    assert "has not enabled workout sharing" in profile["workoutMessage"]
    assert "Leg Day" not in repr(profile)


def testUpcomingSessionsInDateOrderWithThisTrainerOnly(clientele):
    sessions = clientele.getUpcomingSessions("T1", "620200001")
    assert [s["start"] for s in sessions] == ["2026-11-24T10:00", "2026-11-25T10:00"]


def testAssignRoutineToSharingClient(clientele, dataDir):
    saved = clientele.assignRoutine("T1", "620200001", "Strength Block", [SQUAT])
    assert saved["trainerAdded"] and saved["addedBy"] == "T1"
    onProfile = clientele.getClientRoutines("620200001")
    assert onProfile[0]["routineName"] == "Strength Block"
    assert onProfile[0]["label"] == "Added by your trainer Trainer One"
    assert clientele.getClientProfile("T1", "620200001")["assignedRoutines"][0]["routineId"] == saved["routineId"]
    notes = [n["message"] for n in clientele.getNotifications("620200001")]
    assert notes == ["Your trainer Trainer One has assigned you a workout: Strength Block."]


def testAssignRoutineRefusedWithoutSharing(clientele, dataDir):
    with pytest.raises(SharingDisabledError, match="must enable workout sharing before routines can be assigned"):
        clientele.assignRoutine("T1", "620200002", "Strength Block", [SQUAT])
    assert clientele.getClientRoutines("620200002") == []
    assert clientele.getNotifications("620200002") == []


def testInvalidRoutinesRejected(clientele):
    for name, exercises in (("", [SQUAT]), ("Plan", []), ("Plan", [dict(SQUAT, numSets=-1)]),
                            ("Plan", [dict(SQUAT, excerName=" ")]), ("Plan", [dict(SQUAT, weightKG="heavy")])):
        with pytest.raises(ClienteleError):
            clientele.assignRoutine("T1", "620200001", name, exercises)
    assert clientele.getClientRoutines("620200001") == []


def testOnlyTrainersCanViewTheirOwnClients(clientele):
    for userId in ("620200001", "S1", "nobody"):
        with pytest.raises(AccessDeniedError, match="Only personal trainers"):
            clientele.listClients(userId)
        with pytest.raises(AccessDeniedError):
            clientele.getClientProfile(userId, "620200001")
    for clientId in ("620200003", "620200004", "620200005"):   # T2's client, past only, pending only
        with pytest.raises(AccessDeniedError, match="not one of your active clients"):
            clientele.getClientProfile("T1", clientId)
        with pytest.raises(AccessDeniedError):
            clientele.assignRoutine("T1", clientId, "Plan", [SQUAT])


def testStudentControlsWorkoutSharing(clientele):
    clientele.setWorkoutSharing("620200002", True)
    assert clientele.getClientProfile("T1", "620200002")["workouts"][0]["routineName"] == "Leg Day"
    clientele.setWorkoutSharing("620200002", False)
    assert clientele.getClientProfile("T1", "620200002")["workouts"] is None
    with pytest.raises(ClienteleError):
        clientele.setWorkoutSharing("T1", True)
