"""Feature 3 - Occupancy Monitoring acceptance scenarios (SRS 2.3.3)."""
from datetime import datetime, timedelta

import pytest

from occupancyTrends import OccupancyError
from occupancyTrends.models import Direction, EntryExitEvent, EntryStatus
from conftest import fillGym, student


def testHeadcountUpdatesAndRejectsBadCheckIns(occupancy):
    occupancy.recordEntry(student(1), "S1")
    occupancy.recordEntry(student(2), "S1")
    occupancy.recordExit(student(1), "S1")
    assert occupancy.getMemberStatus()["occupancy"] == 1
    for bad in (lambda: occupancy.recordEntry(student(2), "S1"),   # already inside
                lambda: occupancy.recordExit(student(3), "S1"),    # not inside
                lambda: occupancy.recordEntry("999", "S1"),        # unknown ID
                lambda: occupancy.recordEntry("S1", "S1")):        # staff aren't counted
        with pytest.raises(OccupancyError):
            bad()


def testFullGymBlocksCheckInAndQueuesStudents(occupancy, clock):
    with pytest.raises(OccupancyError, match="has space"):   # space: not queued
        occupancy.requestEntry(student(21))
    fillGym(occupancy, clock)
    status = occupancy.getMemberStatus()
    assert status["isFull"] and status["level"] == "Full"
    assert "position 1" in occupancy.requestEntry(student(21))
    assert "position 2" in occupancy.requestEntry(student(22))
    first, second = (occupancy.getMemberStatus(student(i))["you"] for i in (21, 22))
    assert second["etaMinutes"] >= first["etaMinutes"] > 0
    with pytest.raises(OccupancyError, match="already number 1"):
        occupancy.requestEntry(student(21))


def testMemberViewShowsCountsOnly(occupancy, clock):
    fillGym(occupancy, clock)
    occupancy.requestEntry(student(21))
    text = repr(occupancy.getMemberStatus(student(22)))
    assert student(1) not in text and student(21) not in text and "Student" not in text


def testCalledStudentGetsTheSpotAndWaitIsRecorded(occupancy, clock, queueRepo):
    fillGym(occupancy, clock)
    occupancy.requestEntry(student(21))
    occupancy.requestEntry(student(22))
    occupancy.recordExit(student(1), "S1")
    you = occupancy.getMemberStatus(student(21))["you"]
    assert you["called"] and you["callSecondsLeft"] == 60
    assert any("your turn" in n["message"] for n in occupancy.getNotifications(student(21)))
    occupancy.recordEntry(student(23), "S1")       # walk-in can't take the held spot: queued behind
    assert occupancy.getMemberStatus(student(23))["you"]["position"] == 3
    with pytest.raises(OccupancyError, match="not been called"):
        occupancy.recordEntry(student(22), "S1")   # no jumping the queue

    clock.advance(seconds=30)
    occupancy.recordEntry(student(21), "S1")
    assert occupancy.getMemberStatus(student(22))["you"]["position"] == 1
    admitted = next(e for e in queueRepo.listEntries() if e.uwiId == student(21))
    assert admitted.status == EntryStatus.ADMITTED and admitted.getTotalWaitTime() == 30


def testMissedOneMinuteWindowRollsOverToNext(occupancy, clock, queueRepo):
    fillGym(occupancy, clock)
    occupancy.requestEntry(student(21))
    occupancy.requestEntry(student(22))
    occupancy.recordExit(student(1), "S1")
    clock.advance(seconds=61)
    you = occupancy.getMemberStatus(student(22))["you"]
    assert you["called"] and you["position"] == 1
    missed = next(e for e in queueRepo.listEntries() if e.uwiId == student(21))
    assert missed.status == EntryStatus.REMOVED and missed.removalReason == "missedWindow"


def testStaffAddAndRemove(occupancy, clock):
    with pytest.raises(OccupancyError, match="space"):
        occupancy.staffAddToQueue("S1", student(21))
    fillGym(occupancy, clock)
    for i in (21, 22, 23):
        occupancy.staffAddToQueue("S1", student(i))
        clock.advance(seconds=1)
    queue = occupancy.getStaffStatus()["queue"]
    occupancy.staffRemoveFromQueue("S1", queue[0]["entryId"])
    queue = occupancy.getStaffStatus()["queue"]
    assert [(q["position"], q["uwiId"]) for q in queue] == [(1, student(22)), (2, student(23))]


def testClosedGymAndDailyReset(occupancy, clock):
    occupancy.recordEntry(student(1), "S1")
    clock.now = datetime(2026, 11, 24, 13, 0)   # next day, Tuesday afternoon
    assert occupancy.getMemberStatus()["occupancy"] == 0
    clock.now = datetime(2026, 11, 22, 10, 0)   # Sunday - closed
    with pytest.raises(OccupancyError, match="closed"):
        occupancy.requestEntry(student(2))


def testEtaUsesHistoryAndTimeAlreadyInside(occupancy, clock, events):
    lastWeek = clock.now - timedelta(days=7)
    for i in range(5):   # past visits all lasted 40 minutes
        t = lastWeek + timedelta(minutes=i)
        events.add(EntryExitEvent(f"H{i}", Direction.IN, t), EntryExitEvent(f"H{i}", Direction.OUT, t + timedelta(minutes=40)))
    fillGym(occupancy, clock)
    clock.advance(minutes=30)
    occupancy.requestEntry(student(21))
    assert 9 <= occupancy.getMemberStatus(student(21))["you"]["etaMinutes"] <= 11


def testWalkInAtFullGymIsAddedToQueueByStaff(occupancy, clock):
    fillGym(occupancy, clock)
    occupancy.requestEntry(student(21))
    message = occupancy.recordEntry(student(22), "S1")   # walk-in at the front desk
    assert "Added to the queue at position 2" in message
    you = occupancy.getMemberStatus(student(22))["you"]
    assert you["inQueue"] and not you["inside"] and you["position"] == 2
    assert occupancy.getMemberStatus()["occupancy"] == 20
    assert any("Gym staff added you" in n["message"] for n in occupancy.getNotifications(student(22)))


def testTrainersDontCountTowardsTheLimit(occupancy):
    with pytest.raises(OccupancyError, match="Trainers don't count"):
        occupancy.recordEntry("T1", "S1")
    with pytest.raises(OccupancyError, match="Trainers don't count"):
        occupancy.requestEntry("T1")
    assert occupancy.getMemberStatus()["occupancy"] == 0


# ---------------------------------------------------------------- 1-hour time limit
def askedToLeave(occupancy):
    return [p["uwiId"] for p in occupancy.getStaffStatus()["askedToLeave"]]


def testNoTimeLimitWhileNobodyIsWaiting(occupancy, clock):
    fillGym(occupancy, clock)
    clock.advance(hours=3)
    assert askedToLeave(occupancy) == []
    you = occupancy.getMemberStatus(student(1))["you"]
    assert you["minutesInside"] == 180 and not you["askedToLeave"]


def testLongestStayingPersonOverAnHourIsAskedToLeave(occupancy, clock):
    fillGym(occupancy, clock)
    clock.advance(minutes=30)
    occupancy.requestEntry(student(21))
    assert askedToLeave(occupancy) == []          # someone waiting, but nobody is past 1 hour yet
    clock.advance(minutes=30)
    assert askedToLeave(occupancy) == [student(1)]   # first in, so longest inside
    assert occupancy.getMemberStatus(student(1))["you"]["askedToLeave"]
    occupancy.getStaffStatus()                       # refreshing doesn't ask again
    timeUp = [n for n in occupancy.getNotifications(student(1)) if "time limit" in n["message"]]
    assert len(timeUp) == 1

    occupancy.recordExit(student(1), "S1")           # they leave; the waiting student is called
    assert occupancy.getMemberStatus(student(21))["you"]["called"]
    assert askedToLeave(occupancy) == []             # nobody else waiting, so nobody else asked


def testOnePersonAskedPerWaitingStudent(occupancy, clock):
    fillGym(occupancy, clock)
    clock.advance(hours=1)
    occupancy.requestEntry(student(21))
    occupancy.requestEntry(student(22))
    assert askedToLeave(occupancy) == [student(1), student(2)]
    occupancy.requestEntry(student(23))
    assert askedToLeave(occupancy) == [student(1), student(2), student(3)]
