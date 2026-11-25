"""OccupancyService - Feature 3, Occupancy Monitoring (AC-03.0 - AC-03.5).

Rules:
- At most 20 people inside. When the gym is full, students wait in a queue.
- When a spot opens, the next student is called and has 1 minute to check in,
  otherwise the spot goes to the next person (SRS 3.2.1.1).
- 1-hour limit: while the gym is full and students are waiting, the people who
  have been inside longest and are past 1 hour are asked to leave (one per
  waiting student). Staff still log the actual check-out.

Every action returns a message to show, or raises OccupancyError with the reason it was refused.
"""
import math
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List

from .gymHours import hoursText, isOpen
from .models import (TIME_LIMIT_SECONDS, Direction, EntryExitEvent, EntryStatus, Queue, QueueEntry, Staff,
                     averageVisitSeconds, remainingTimes, whoIsInside)

CALL_WINDOW_SECONDS = 60
TIME_UP_MESSAGE = ("Your 1-hour time limit is up and the gym is full with people waiting. "
                   "Please check out at the front desk.")


class OccupancyError(Exception):
    """A request that breaks an occupancy rule; the message is shown to the user."""


@dataclass
class _State:
    now: datetime
    inside: Dict[str, datetime]     # uwiId -> when they checked in today
    history: List[EntryExitEvent]   # last 90 days, for average visit length
    entries: List[QueueEntry]       # every queue record (past and present)
    queue: Queue                    # only the students waiting now


class OccupancyService:
    _lock = threading.RLock()

    def __init__(self, events, queueRepo, notifications, users, clock=datetime.now, enforceGymHours=True):
        self.events, self.queueRepo, self.notifications, self.users = events, queueRepo, notifications, users
        self.clock, self.enforceHours = clock, enforceGymHours

    # ---------------------------------------------------------------- screens
    def getMemberStatus(self, uwiId: str = None) -> dict:
        """Headcount, level and estimated wait - counts only, never names (AC-03.0, SRS 3.2.2)."""
        with self._session() as s:
            view = self._summary(s)
            if uwiId:
                entry, entered = s.queue.find(uwiId=uwiId), s.inside.get(uwiId)
                view["you"] = {
                    "inside": entered is not None,
                    "minutesInside": int((s.now - entered).total_seconds() // 60) if entered else None,
                    "askedToLeave": uwiId in _askedToLeave(s),
                    "inQueue": entry is not None,
                    "position": s.queue.getPlaceInQueue(entry) if entry else None,
                    "etaMinutes": self._etas(s)[entry.entryId] if entry else None,
                    "called": bool(entry and entry.isCalled()),
                    "callSecondsLeft": entry.callSecondsLeft(s.now, CALL_WINDOW_SECONDS) if entry else 0,
                }
            return view

    def getStaffStatus(self) -> dict:
        """Headcount, the queue, and who should be checked out, for staff at the door."""
        with self._session() as s:
            view, etas = self._summary(s), self._etas(s)
            view["queue"] = [{
                "entryId": e.entryId, "position": i, "uwiId": e.uwiId, "called": e.isCalled(),
                "callSecondsLeft": e.callSecondsLeft(s.now, CALL_WINDOW_SECONDS), "etaMinutes": etas[e.entryId],
            } for i, e in enumerate(s.queue.entries, start=1)]
            view["askedToLeave"] = [{"uwiId": u, "minutesInside": int((s.now - s.inside[u]).total_seconds() // 60)}
                                    for u in _askedToLeave(s)]
            return view

    def getNotifications(self, uwiId: str) -> List[dict]:
        return self.notifications.listForUser(uwiId)

    def markNotificationsRead(self, uwiId: str) -> None:
        self.notifications.markAllRead(uwiId)

    # ---------------------------------------------------------------- actions
    def recordEntry(self, uwiId: str, staffId: str) -> str:
        """Staff check someone in (AC-03.1). When the gym is full, only the called student
        may enter (SRS 3.2.1.2); any other walk-in is put in the queue instead."""
        self._requireUser(uwiId, ("student", "trainer"))
        with self._session(mustBeOpen=True) as s:
            entry = s.queue.find(uwiId=uwiId)
            if uwiId in s.inside:
                raise OccupancyError("This person is already checked in.")
            if entry and not entry.isCalled():
                raise OccupancyError(f"This student is number {s.queue.getPlaceInQueue(entry)} "
                                     "in the queue and has not been called yet.")
            if not entry and s.queue.freeSpots() == 0:
                return self._addToQueue(s, uwiId, staffId)

            if entry:   # the called student takes their held spot
                s.queue.remove(entry)
                entry.leave(s.now, EntryStatus.ADMITTED)
            self.events.add(EntryExitEvent(uwiId, Direction.IN, s.now, staffId))
            s.inside[uwiId] = s.now   # their 1-hour timer starts now
            s.queue.currentCapacity += 1
            return f"Checked in. Occupancy: {s.queue.currentCapacity}/{Queue.MAX_CAPACITY}."

    def recordExit(self, uwiId: str, staffId: str) -> str:
        """Staff check someone out; the next student in the queue is called (AC-03.5)."""
        with self._session() as s:
            if uwiId not in s.inside:
                raise OccupancyError("This person is not checked in.")
            self.events.add(EntryExitEvent(uwiId, Direction.OUT, s.now, staffId))
            del s.inside[uwiId]
            s.queue.currentCapacity -= 1
            return f"Checked out. Occupancy: {s.queue.currentCapacity}/{Queue.MAX_CAPACITY}."

    def requestEntry(self, uwiId: str) -> str:
        """A student asks to enter from the app; they join the queue only if the gym is full (AC-03.3)."""
        with self._session(mustBeOpen=True) as s:
            return self._addToQueue(s, uwiId)

    def staffAddToQueue(self, staffId: str, uwiId: str) -> str:
        """Add to Queue use case."""
        with self._session(mustBeOpen=True) as s:
            return self._addToQueue(s, uwiId, staffId)

    def staffRemoveFromQueue(self, staffId: str, entryId: str) -> str:
        """Remove from Queue use case; everyone behind moves forward."""
        with self._session() as s:
            entry = s.queue.find(entryId=entryId)
            if entry is None:
                raise OccupancyError("That student is no longer in the queue.")
            Staff(staffId).removeFromQueue(s.queue, entry, s.now)
            self.notifications.add(entry.uwiId, "Gym staff removed you from the queue.", s.now)
            return "Removed from the queue."

    # -------------------------------------------------------------- internals
    @contextmanager
    def _session(self, mustBeOpen=False):
        """Load the live state and apply the rules; after the caller's changes, apply them again and save.
        If the caller raises an error, nothing it changed is saved."""
        with self._lock:
            s = self._load()
            self._applyRules(s)
            if mustBeOpen and self.enforceHours and not isOpen(s.now):
                raise OccupancyError(f"The gym is closed. Today's hours: {hoursText(s.now.date())}.")
            yield s
            self._applyRules(s)

    def _load(self) -> _State:
        now = self.clock()
        history = self.events.listEvents(since=now - timedelta(days=90))
        inside = whoIsInside(history, now)
        entries = self.queueRepo.listEntries()
        return _State(now, inside, history, entries, Queue(entries, len(inside)))

    def _applyRules(self, s: _State) -> None:
        """Bring the queue up to date, send any messages, and save."""
        s.queue.clearForClosing(s.now, gymClosed=self.enforceHours and not isOpen(s.now))
        for e in s.queue.expireMissedCalls(s.now, CALL_WINDOW_SECONDS):
            self.notifications.add(e.uwiId, "You did not check in within 1 minute, "
                                            "so your spot went to the next person.", s.now)
        for e in s.queue.callNextStudents(s.now):
            self.notifications.add(e.uwiId, "It's your turn! Check in at the front desk within 1 minute.", s.now)
        for uwiId in _askedToLeave(s):
            if not self._toldToLeaveThisVisit(uwiId, s.inside[uwiId]):
                self.notifications.add(uwiId, TIME_UP_MESSAGE, s.now)
        self.queueRepo.saveEntries(s.entries)

    def _addToQueue(self, s: _State, uwiId: str, staffId: str = None) -> str:
        """Put a student at the back of the queue (by staff if staffId is given) and notify them."""
        self._requireUser(uwiId, ("student",))
        entry = s.queue.find(uwiId=uwiId)
        if uwiId in s.inside:
            raise OccupancyError("This student is already inside the gym.")
        if entry:
            raise OccupancyError(f"This student is already number {s.queue.getPlaceInQueue(entry)} in the queue.")
        if not s.queue.mustQueue():
            raise OccupancyError("The gym has space - check in at the front desk.")

        entry = QueueEntry(uwiId, s.now)
        if staffId:
            Staff(staffId).addToQueue(s.queue, entry)
        else:
            s.queue.enqueue(entry)
        s.entries.append(entry)
        position, eta = s.queue.getPlaceInQueue(entry), self._etas(s)[entry.entryId]
        joined = "Gym staff added you to the queue" if staffId else "You joined the queue"
        self.notifications.add(uwiId, f"{joined}. You are number {position}. "
                                      f"Estimated wait: about {eta} min.", s.now)
        return f"Added to the queue at position {position}. Estimated wait: about {eta} min."

    def _toldToLeaveThisVisit(self, uwiId: str, entered: datetime) -> bool:
        since = entered.isoformat(timespec="seconds")
        return any(n["message"] == TIME_UP_MESSAGE and n["createdAt"] >= since
                   for n in self.notifications.listForUser(uwiId))

    def _etas(self, s: _State) -> Dict[str, int]:
        """Estimated wait in minutes for each queue entry, plus "new" for someone joining now (AC-03.4)."""
        # While people are queued nobody stays past the hour, so a visit is at most 1 hour.
        avg = min(averageVisitSeconds(e for e in s.history if e.timestamp.date() < s.now.date()),
                  TIME_LIMIT_SECONDS)
        remaining = remainingTimes(((s.now - t).total_seconds() for t in s.inside.values()), avg)
        etas, uncalled = {}, 0
        for e in s.queue.entries:
            uncalled += not e.isCalled()
            etas[e.entryId] = _minutes(e.calcEstimatedEntry(uncalled, remaining, avg))
        newcomer = QueueEntry("", s.now).calcEstimatedEntry(uncalled + 1, remaining, avg)
        etas["new"] = _minutes(newcomer) if s.queue.mustQueue() else 0
        return etas

    def _summary(self, s: _State) -> dict:
        count, free = s.queue.currentCapacity, s.queue.freeSpots()
        level = "Full" if free == 0 else "Almost full" if count >= 0.75 * Queue.MAX_CAPACITY else "Space available"
        return {
            "occupancy": count, "maxCapacity": Queue.MAX_CAPACITY, "freeSpots": free, "isFull": free == 0,
            "level": level, "numInQueue": s.queue.getNumInQueue(), "estimatedWaitMinutes": self._etas(s)["new"],
            "gymOpen": isOpen(s.now) or not self.enforceHours, "hoursToday": hoursText(s.now.date()),
        }

    def _requireUser(self, uwiId: str, roles) -> None:
        user = self.users.get(uwiId)
        if user is None:
            raise OccupancyError(f"No registered user has UWI ID {uwiId}.")
        if user["role"] not in roles:
            raise OccupancyError(f"A {user['role']} account cannot do this.")


def _askedToLeave(s: _State) -> List[str]:
    """Longest-staying people past 1 hour - one for each student still waiting to be called."""
    waiting = sum(not e.isCalled() for e in s.queue.entries)
    longestFirst = sorted(s.inside, key=s.inside.get)
    return [u for u in longestFirst if (s.now - s.inside[u]).total_seconds() >= TIME_LIMIT_SECONDS][:waiting]


def _minutes(seconds: float) -> int:
    """Whole minutes, rounded up (so 10 seconds shows as 1 min)."""
    return math.ceil(seconds / 60) if seconds > 0 else 0
