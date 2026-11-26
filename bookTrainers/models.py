"""Records used by Book Trainers: trainers' time slots and the bookings students make."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class BookingStatus(str, Enum):
    """Same values as Booking/booking.py and viewClientele."""
    PENDING = "Pending"
    ACCEPTED = "Accepted"
    DECLINED = "Declined"
    CANCELLED = "Cancelled"


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat(timespec="seconds") if value else None


def _dt(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None


@dataclass
class TimeSlot:
    """A time a trainer has said they are available (Manage Availability, Feature 2, creates these)."""
    trainerId: str
    start: datetime
    end: datetime
    slotId: str = field(default_factory=lambda: uuid.uuid4().hex)

    def overlaps(self, start: datetime, end: datetime) -> bool:
        return self.start < end and start < self.end

    def toDict(self) -> dict:
        return {"slotId": self.slotId, "trainerId": self.trainerId, "start": _iso(self.start), "end": _iso(self.end)}

    @classmethod
    def fromDict(cls, d: dict) -> "TimeSlot":
        return cls(d["trainerId"], _dt(d["start"]), _dt(d["end"]), d["slotId"])


@dataclass
class Booking:
    """A session request or confirmed session. Saved in the same shape View Clientele reads."""
    studentId: str
    trainerId: str
    start: datetime
    end: datetime
    status: BookingStatus = BookingStatus.PENDING
    slotId: Optional[str] = None
    replacesBookingId: Optional[str] = None   # set when this request moves an existing session
    studentReminded: bool = False
    bookingId: str = field(default_factory=lambda: uuid.uuid4().hex)
    trainerReminded: bool = False

    def isActive(self) -> bool:
        return self.status in (BookingStatus.PENDING, BookingStatus.ACCEPTED)

    def toDict(self) -> dict:
        return {"bookingId": self.bookingId, "studentId": self.studentId, "trainerId": self.trainerId,
                "start": _iso(self.start), "end": _iso(self.end), "status": self.status.value,
                "slotId": self.slotId, "replacesBookingId": self.replacesBookingId,
                "studentReminded": self.studentReminded, "trainerReminded": self.trainerReminded}

    @classmethod
    def fromDict(cls, d: dict) -> "Booking":
        return cls(d["studentId"], d["trainerId"], _dt(d["start"]), _dt(d["end"]), BookingStatus(d["status"]),
                   d.get("slotId"), d.get("replacesBookingId"), d.get("studentReminded", False), d["bookingId"],
                   d.get("trainerReminded", False))
