"""Data Access Layer: one repository per JSON file (SDS 2.3.1).

Only this module touches storage. The file names and record shapes match the
other features (users.json and notifications.json as in occupancyTrends,
workoutLogs.json as in the progress feature), so all features can share one
data folder.
"""
import json
import os
import threading
from datetime import datetime
from typing import List, Optional

from .models import AssignedRoutine, Booking


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
    """Shared users file: {"uwiId", "name", "role", "workoutSharing"}; role is student/trainer/staff/operator."""

    def __init__(self, dataDir: str):
        self.store = JsonStore(dataDir, "users.json")

    def get(self, uwiId: str) -> Optional[dict]:
        return next((u for u in self.store.read() if u["uwiId"] == uwiId), None)

    def saveMany(self, users: List[dict]) -> None:
        with self.store.lock:
            ids = {u["uwiId"] for u in users}
            self.store.write([u for u in self.store.read() if u["uwiId"] not in ids] + list(users))

    def setField(self, uwiId: str, key: str, value) -> None:
        with self.store.lock:
            records = self.store.read()
            for u in records:
                if u["uwiId"] == uwiId:
                    u[key] = value
            self.store.write(records)


class BookingRepository:
    def __init__(self, dataDir: str):
        self.store = JsonStore(dataDir, "bookings.json")

    def add(self, *bookings: Booking) -> None:
        self.store.append(*(b.toDict() for b in bookings))

    def forTrainer(self, trainerId: str) -> List[Booking]:
        return [Booking.fromDict(r) for r in self.store.read() if r["trainerId"] == trainerId]


class WorkoutLogRepository:
    """Completed workouts, in the progress feature's WorkoutLog.to_dict() shape."""

    def __init__(self, dataDir: str):
        self.store = JsonStore(dataDir, "workoutLogs.json")

    def add(self, *logs: dict) -> None:
        self.store.append(*logs)

    def forStudent(self, studentId: str) -> List[dict]:
        return [r for r in self.store.read() if r["student_id"] == studentId]


class AssignedRoutineRepository:
    def __init__(self, dataDir: str):
        self.store = JsonStore(dataDir, "assignedRoutines.json")

    def add(self, routine: AssignedRoutine) -> None:
        self.store.append(routine.toDict())

    def forStudent(self, studentId: str) -> List[AssignedRoutine]:
        return [AssignedRoutine.fromDict(r) for r in self.store.read() if r["ownerId"] == studentId]


class NotificationRepository:
    """In-app notifications (SRS 2.1.3.2), same file and format as occupancyTrends."""

    def __init__(self, dataDir: str):
        self.store = JsonStore(dataDir, "notifications.json")

    def add(self, uwiId: str, message: str, now: datetime) -> None:
        self.store.append({"uwiId": uwiId, "message": message,
                           "createdAt": now.isoformat(timespec="seconds"), "read": False})

    def listForUser(self, uwiId: str) -> List[dict]:
        return sorted((n for n in self.store.read() if n["uwiId"] == uwiId),
                      key=lambda n: n["createdAt"], reverse=True)
