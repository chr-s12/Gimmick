"""Queue Management classes from the SDS class diagram, plus entry/exit events."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Iterable, List, Optional

TIME_LIMIT_SECONDS = 3600      # 1 hour - only enforced when the gym is full and someone is waiting
DEFAULT_VISIT_SECONDS = 3600   # used until there is visit history
MIN_REMAINING_SECONDS = 120    # someone past the average still needs a moment to leave


class Direction(str, Enum):
    IN = "in"
    OUT = "out"


class EntryStatus(str, Enum):
    WAITING = "Waiting"
    ADMITTED = "Admitted"
    REMOVED = "Removed"


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat(timespec="seconds") if value else None


def _dt(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None


@dataclass
class EntryExitEvent:
    """One check-in or check-out logged by gym staff (SRS 2.1.1.1)."""
    uwiId: str
    direction: Direction
    timestamp: datetime
    recordedBy: Optional[str] = None

    def toDict(self) -> dict:
        return {"uwiId": self.uwiId, "direction": self.direction.value,
                "timestamp": _iso(self.timestamp), "recordedBy": self.recordedBy}

    @classmethod
    def fromDict(cls, d: dict) -> "EntryExitEvent":
        return cls(d["uwiId"], Direction(d["direction"]), _dt(d["timestamp"]), d.get("recordedBy"))


@dataclass
class QueueEntry:
    """A student's place in the queue, with when they joined and left it."""
    uwiId: str
    joinTime: datetime
    entryId: str = field(default_factory=lambda: uuid.uuid4().hex)
    leftQueueTime: Optional[datetime] = None
    status: EntryStatus = EntryStatus.WAITING
    notifiedTime: Optional[datetime] = None   # when they were told it is their turn
    removalReason: Optional[str] = None       # "staff", "missedWindow" or "closed"

    def isCalled(self) -> bool:
        return self.status == EntryStatus.WAITING and self.notifiedTime is not None

    def callSecondsLeft(self, now: datetime, window: int) -> int:
        if not self.isCalled():
            return 0
        return max(0, int(window - (now - self.notifiedTime).total_seconds()))

    def getTotalWaitTime(self) -> Optional[int]:
        """Seconds spent in the queue (None while still waiting)."""
        if self.leftQueueTime is None:
            return None
        return int((self.leftQueueTime - self.joinTime).total_seconds())

    def calcEstimatedEntry(self, openingNumber: int, remaining: List[float], avgVisit: float) -> int:
        """Seconds until this student can enter (AC-03.4).

        Spots open as the people inside leave, soonest first. If the queue is
        longer than the number inside, later spots open one average visit later.
        """
        if self.isCalled() or not remaining:
            return 0
        rounds, i = divmod(openingNumber - 1, len(remaining))
        return int(remaining[i] + rounds * avgVisit)

    def leave(self, now: datetime, status: EntryStatus, reason: Optional[str] = None) -> None:
        self.status, self.leftQueueTime, self.removalReason = status, now, reason

    def toDict(self) -> dict:
        return {"entryId": self.entryId, "uwiId": self.uwiId, "joinTime": _iso(self.joinTime),
                "leftQueueTime": _iso(self.leftQueueTime), "status": self.status.value,
                "notifiedTime": _iso(self.notifiedTime), "removalReason": self.removalReason}

    @classmethod
    def fromDict(cls, d: dict) -> "QueueEntry":
        return cls(d["uwiId"], _dt(d["joinTime"]), d["entryId"], _dt(d.get("leftQueueTime")),
                   EntryStatus(d["status"]), _dt(d.get("notifiedTime")), d.get("removalReason"))


class Queue:
    """Tracks how many people are inside and the waiting queue (AC-03.1 - AC-03.3)."""
    MAX_CAPACITY = 20  # gym policy, based on the facility's size

    def __init__(self, entries: Iterable[QueueEntry], currentCapacity: int):
        self.entries = sorted((e for e in entries if e.status == EntryStatus.WAITING), key=lambda e: e.joinTime)
        self.currentCapacity = currentCapacity

    def getNumInQueue(self) -> int:
        return len(self.entries)

    def getCurrentCapacity(self) -> int:
        return self.currentCapacity

    def freeSpots(self) -> int:
        """Spots a walk-in may take. Spots held for called students don't count."""
        called = sum(e.isCalled() for e in self.entries)
        return max(0, self.MAX_CAPACITY - self.currentCapacity - called)

    def nextUncalled(self) -> Optional[QueueEntry]:
        return next((e for e in self.entries if not e.isCalled()), None)

    def mustQueue(self) -> bool:
        return self.freeSpots() == 0 or self.nextUncalled() is not None

    def find(self, uwiId: str = None, entryId: str = None) -> Optional[QueueEntry]:
        return next((e for e in self.entries if e.uwiId == uwiId or e.entryId == entryId), None)

    def getPlaceInQueue(self, entry: QueueEntry) -> int:
        return self.entries.index(entry) + 1

    def enqueue(self, entry: QueueEntry) -> bool:
        """Add to the end of the queue. Returns False if the gym has space (no need to wait)."""
        if self.find(uwiId=entry.uwiId):
            raise ValueError("This student is already in the queue.")
        if not self.mustQueue():
            return False
        self.entries.append(entry)
        return True

    def dequeue(self) -> Optional[QueueEntry]:
        return self.entries.pop(0) if self.entries else None

    def remove(self, entry: QueueEntry) -> None:
        self.entries.remove(entry)  # everyone behind moves forward

    def sendEntryNotif(self, entry: QueueEntry, now: datetime) -> None:
        entry.notifiedTime = now

    def clearForClosing(self, now: datetime, gymClosed: bool) -> None:
        """The queue empties when the gym closes, and never carries over to the next day."""
        for e in list(self.entries):
            if gymClosed or e.joinTime.date() < now.date():
                self.remove(e)
                e.leave(now, EntryStatus.REMOVED, "closed")

    def expireMissedCalls(self, now: datetime, window: int) -> List[QueueEntry]:
        """Remove called students who did not check in within the window. Returns them."""
        missed = [e for e in self.entries if e.isCalled() and (now - e.notifiedTime).total_seconds() > window]
        for e in missed:
            self.remove(e)
            e.leave(now, EntryStatus.REMOVED, "missedWindow")
        return missed

    def callNextStudents(self, now: datetime) -> List[QueueEntry]:
        """Call waiting students, in order, for every free spot. Returns who was called."""
        called = []
        while self.freeSpots() > 0 and self.nextUncalled():
            e = self.nextUncalled()
            self.sendEntryNotif(e, now)
            called.append(e)
        return called


@dataclass
class Staff:
    """Gym staff (and the gym operator) - manage the queue and review usage."""
    staffId: str

    def addToQueue(self, queue: Queue, entry: QueueEntry) -> bool:
        return queue.enqueue(entry)

    def removeFromQueue(self, queue: Queue, entry: QueueEntry, now: datetime) -> bool:
        if entry not in queue.entries:
            return False
        queue.remove(entry)
        entry.leave(now, EntryStatus.REMOVED, "staff")
        return True

    def reviewGymUsage(self, analytics) -> dict:
        return analytics.summary()


def averageVisitSeconds(events: Iterable[EntryExitEvent]) -> float:
    """Average visit length from past check-in/check-out pairs (historical data for AC-03.4)."""
    entered, lengths = {}, []
    for e in sorted(events, key=lambda e: e.timestamp):
        if e.direction == Direction.IN:
            entered[e.uwiId] = e.timestamp
        elif e.uwiId in entered:
            start = entered.pop(e.uwiId)
            if start.date() == e.timestamp.date():
                lengths.append((e.timestamp - start).total_seconds())
    return sum(lengths) / len(lengths) if lengths else DEFAULT_VISIT_SECONDS


def whoIsInside(events: Iterable[EntryExitEvent], now: datetime) -> Dict[str, datetime]:
    """uwiId -> check-in time, for everyone inside now. Replays today's check-ins and check-outs."""
    inside = {}
    for e in sorted(events, key=lambda e: e.timestamp):
        if e.timestamp.date() == now.date() and e.timestamp <= now:
            if e.direction == Direction.IN:
                inside[e.uwiId] = e.timestamp
            else:
                inside.pop(e.uwiId, None)
    return inside


def remainingTimes(secondsInside: Iterable[float], avgVisit: float) -> List[float]:
    """Expected seconds until each person inside leaves, soonest first."""
    return sorted(max(avgVisit - s, MIN_REMAINING_SECONDS) for s in secondsInside)
