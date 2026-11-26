"""Data Access Layer: one repository per JSON file (SDS 2.3.1).

File names and record shapes match the other features: users.json and
notifications.json as in occupancyTrends and viewClientele, and bookings.json
as viewClientele reads it, so every feature can share one data folder.
"""
import json
import os
import threading
from datetime import datetime
from typing import List, Optional

from .models import Booking, TimeSlot


class JsonStore:
    _locks = {}

    def __init__(self, dataDir: str, filename: str):
        os.makedirs(dataDir, exist_ok=True)
        self.path = os.path.abspath(os.path.join(dataDir, filename))
        self.lock = JsonStore._locks.setdefault(self.path, threading.RLock())

    def read(self) -> list:
        with self.lock:
            if not os.path.exists(self.path):
                return []
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)

    def write(self, records: list) -> None:
        """Save immediately via a temp file, so a crash never leaves half a file (SRS 4.1)."""
        with self.lock:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2)
            os.replace(tmp, self.path)

    def append(self, *records) -> None:
        with self.lock:
            self.write(self.read() + list(records))


class UserRepository:
    """Shared users file: {"uwiId", "name", "role", ...}; trainers may also have "specialisations"."""

    def __init__(self, dataDir: str):
        self.store = JsonStore(dataDir, "users.json")

    def get(self, uwiId: str) -> Optional[dict]:
        return next((u for u in self.store.read() if u["uwiId"] == uwiId), None)

    def byRole(self, role: str) -> List[dict]:
        return [u for u in self.store.read() if u.get("role") == role]

    def saveMany(self, users: List[dict]) -> None:
        with self.store.lock:
            ids = {u["uwiId"] for u in users}
            self.store.write([u for u in self.store.read() if u["uwiId"] not in ids] + list(users))


class TimeSlotRepository:
    """Trainers' available times. Feature 2 (Manage Availability) writes these; Book Trainers reads them."""

    def __init__(self, dataDir: str):
        self.store = JsonStore(dataDir, "timeSlots.json")

    def add(self, *slots: TimeSlot) -> None:
        self.store.append(*(s.toDict() for s in slots))

    def get(self, slotId: str) -> Optional[TimeSlot]:
        record = next((r for r in self.store.read() if r["slotId"] == slotId), None)
        return TimeSlot.fromDict(record) if record else None

    def forTrainer(self, trainerId: str) -> List[TimeSlot]:
        return [TimeSlot.fromDict(r) for r in self.store.read() if r["trainerId"] == trainerId]


class BookingRepository:
    def __init__(self, dataDir: str):
        self.store = JsonStore(dataDir, "bookings.json")

    def listAll(self) -> List[Booking]:
        return [Booking.fromDict(r) for r in self.store.read()]

    def get(self, bookingId: str) -> Optional[Booking]:
        return next((b for b in self.listAll() if b.bookingId == bookingId), None)

    def add(self, booking: Booking) -> None:
        self.store.append(booking.toDict())

    def save(self, *bookings: Booking) -> None:
        """Replace these bookings' records, keeping every other record exactly as it was."""
        with self.store.lock:
            changed = {b.bookingId: b.toDict() for b in bookings}
            records = [changed.pop(r["bookingId"], r) for r in self.store.read()]
            self.store.write(records + list(changed.values()))


class NotificationRepository:
    """In-app notifications (SRS 2.1.3.2), same file and format as the other features."""

    def __init__(self, dataDir: str):
        self.store = JsonStore(dataDir, "notifications.json")

    def add(self, uwiId: str, message: str, now: datetime) -> None:
        self.store.append({"uwiId": uwiId, "message": message,
                           "createdAt": now.isoformat(timespec="seconds"), "read": False})

    def listForUser(self, uwiId: str) -> List[dict]:
        """Newest first; messages from the same second keep the order they were saved in."""
        mine = [(n["createdAt"], i, n) for i, n in enumerate(self.store.read()) if n["uwiId"] == uwiId]
        return [n for _, _, n in sorted(mine, key=lambda t: t[:2], reverse=True)]
