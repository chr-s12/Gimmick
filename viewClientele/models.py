"""Records used by View Clientele: bookings and routines a trainer assigns."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional

SESSION_LENGTH = timedelta(hours=1)   # trainers offer fixed 1-hour slots (SRS 1.6.3)


class BookingStatus(str, Enum):
    """Same values as Booking/booking.py, plus Cancelled from trainer.py."""
    PENDING = "Pending"
    ACCEPTED = "Accepted"
    DECLINED = "Declined"
    CANCELLED = "Cancelled"


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat(timespec="seconds") if value else None


def _dt(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None


@dataclass
class Booking:
    """A training session a student booked with a trainer (Feature 5 owns creating these)."""
    studentId: str
    trainerId: str
    start: datetime
    status: BookingStatus = BookingStatus.PENDING
    end: Optional[datetime] = None
    bookingId: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self):
        if self.end is None:
            self.end = self.start + SESSION_LENGTH

    def isConfirmed(self) -> bool:
        return self.status == BookingStatus.ACCEPTED

    def isUpcoming(self, now: datetime) -> bool:
        """Confirmed and not finished yet (a session in progress still counts)."""
        return self.isConfirmed() and self.end > now

    def isInProgress(self, now: datetime) -> bool:
        return self.isConfirmed() and self.start <= now < self.end

    def toDict(self) -> dict:
        return {"bookingId": self.bookingId, "studentId": self.studentId, "trainerId": self.trainerId,
                "start": _iso(self.start), "end": _iso(self.end), "status": self.status.value}

    @classmethod
    def fromDict(cls, d: dict) -> "Booking":
        return cls(d["studentId"], d["trainerId"], _dt(d["start"]), BookingStatus(d["status"]),
                   _dt(d.get("end")), d["bookingId"])


@dataclass
class AssignedExercise:
    """Same fields as Exercise.to_dict(), so Routine.from_dict() can load an assigned routine."""
    excerName: str
    numSets: int
    numReps: int
    restTime: int
    weightKG: float

    @classmethod
    def fromInput(cls, d: dict) -> "AssignedExercise":
        """Validate one exercise typed in by the trainer (SRS 3.3.2)."""
        name = str(d.get("excerName", "")).strip()
        if not name:
            raise ValueError("Every exercise needs a name.")
        values = {}
        for key, label, minimum in (("numSets", "Sets", 1), ("numReps", "Reps", 1), ("restTime", "Rest time", 0)):
            value = d.get(key)
            if isinstance(value, str) and value.strip().lstrip("-").isdigit():
                value = int(value)
            if type(value) is not int or value < minimum:
                raise ValueError(f"{label} for {name} must be a whole number of at least {minimum}.")
            values[key] = value
        weight = d.get("weightKG", 0)
        try:
            weight = float(weight)
        except (TypeError, ValueError):
            raise ValueError(f"Weight for {name} must be a number.") from None
        if weight < 0:
            raise ValueError(f"Weight for {name} can't be negative.")
        return cls(name, values["numSets"], values["numReps"], values["restTime"], weight)

    def toDict(self) -> dict:
        return {"excerName": self.excerName, "numSets": self.numSets, "numReps": self.numReps,
                "restTime": self.restTime, "isComplete": False, "weightKG": self.weightKG}


@dataclass
class AssignedRoutine:
    """A routine a trainer put on a client's profile. Stored like Routine.to_dict(), plus who added it."""
    routineName: str
    exercises: List[AssignedExercise]
    ownerId: str
    addedBy: str
    addedByName: str
    assignedAt: datetime
    routineId: str = field(default_factory=lambda: str(uuid.uuid4()))

    def toDict(self) -> dict:
        return {"routineId": self.routineId, "routineName": self.routineName, "isPublic": False,
                "exercises": [e.toDict() for e in self.exercises], "ownerId": self.ownerId,
                "trainerAdded": True, "addedBy": self.addedBy, "addedByName": self.addedByName,
                "assignedAt": _iso(self.assignedAt)}

    @classmethod
    def fromDict(cls, d: dict) -> "AssignedRoutine":
        exercises = [AssignedExercise(e["excerName"], e["numSets"], e["numReps"], e["restTime"], e["weightKG"])
                     for e in d["exercises"]]
        return cls(d["routineName"], exercises, d["ownerId"], d["addedBy"], d["addedByName"],
                   _dt(d["assignedAt"]), d["routineId"])
