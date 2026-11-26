from datetime import datetime, timedelta

import pytest

from occupancyTrends.models import EntryStatus, Queue, QueueEntry, Staff, remainingTimes

T0 = datetime(2026, 11, 23, 10, 0)


def entry(uid, minutes=0):
    return QueueEntry(uid, T0 + timedelta(minutes=minutes))


def testEnqueueOnlyWhenFullAndOnlyOnce():
    assert Queue([], currentCapacity=5).enqueue(entry("a")) is False
    q = Queue([], currentCapacity=20)
    assert q.enqueue(entry("a")) is True
    with pytest.raises(ValueError):
        q.enqueue(entry("a", 1))


def testFirstInFirstOutAndCalledStudentHoldsASpot():
    a, b = entry("a", 1), entry("b", 2)
    q = Queue([b, a], currentCapacity=19)
    assert q.freeSpots() == 1
    q.sendEntryNotif(a, T0)
    assert q.freeSpots() == 0
    assert q.dequeue() is a and q.dequeue() is b


def testStaffRemoveMovesOthersForward():
    a, b, c = entry("a", 0), entry("b", 1), entry("c", 2)
    q = Queue([a, b, c], currentCapacity=20)
    assert Staff("S1").removeFromQueue(q, b, T0)
    assert b.status == EntryStatus.REMOVED and q.getPlaceInQueue(c) == 2


def testWaitTimeAndJsonRoundTrip():
    e = entry("a")
    e.leave(T0 + timedelta(minutes=12), EntryStatus.ADMITTED)
    assert e.getTotalWaitTime() == 720
    assert QueueEntry.fromDict(e.toDict()) == e


def testEtaSpotsOpenInOrderThenWrapAround():
    remaining = remainingTimes([50 * 60, 10 * 60], 3600)   # 10 and 50 minutes left
    e = entry("a")
    assert [e.calcEstimatedEntry(n, remaining, 3600) for n in (1, 2, 3)] == [600, 3000, 600 + 3600]
