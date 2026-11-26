"""Data Access Layer: one repository per JSON file (SDS 2.3.1).

Only this module touches storage, so moving to the UWI database means
changing this file and nothing else.
"""
import json
import os
import threading
from datetime import datetime
from typing import List, Optional

from .models import EntryExitEvent, QueueEntry


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


def _between(value: datetime, since: Optional[datetime], until: Optional[datetime]) -> bool:
    return (since is None or value >= since) and (until is None or value < until)


class EntryExitRepository:
    def __init__(self, dataDir: str):
        self.store = JsonStore(dataDir, "entryExitEvents.json")

    def add(self, *events: EntryExitEvent) -> None:
        self.store.append(*(e.toDict() for e in events))

    def listEvents(self, since: datetime = None, until: datetime = None) -> List[EntryExitEvent]:
        events = (EntryExitEvent.fromDict(r) for r in self.store.read())
        return sorted((e for e in events if _between(e.timestamp, since, until)), key=lambda e: e.timestamp)


class QueueRepository:
    """Keeps every queue record, past and present, for wait-time reports."""

    def __init__(self, dataDir: str):
        self.store = JsonStore(dataDir, "queue.json")

    def listEntries(self, since: datetime = None, until: datetime = None) -> List[QueueEntry]:
        entries = (QueueEntry.fromDict(r) for r in self.store.read())
        return [e for e in entries if _between(e.joinTime, since, until)]

    def saveEntries(self, entries: List[QueueEntry]) -> None:
        self.store.write([e.toDict() for e in entries])

    def add(self, *entries: QueueEntry) -> None:
        self.store.append(*(e.toDict() for e in entries))


class NotificationRepository:
    """In-app notifications (SRS 2.1.3.2)."""

    def __init__(self, dataDir: str):
        self.store = JsonStore(dataDir, "notifications.json")

    def add(self, uwiId: str, message: str, now: datetime) -> None:
        self.store.append({"uwiId": uwiId, "message": message,
                           "createdAt": now.isoformat(timespec="seconds"), "read": False})

    def listForUser(self, uwiId: str) -> List[dict]:
        return sorted((n for n in self.store.read() if n["uwiId"] == uwiId),
                      key=lambda n: n["createdAt"], reverse=True)

    def markAllRead(self, uwiId: str) -> None:
        with self.store.lock:
            records = self.store.read()
            for n in records:
                if n["uwiId"] == uwiId:
                    n["read"] = True
            self.store.write(records)


class UserRepository:
    """Shared users file: {"uwiId", "name", "role", ...}; role is student/trainer/staff/operator."""

    def __init__(self, dataDir: str):
        self.store = JsonStore(dataDir, "users.json")

    def get(self, uwiId: str) -> Optional[dict]:
        return next((u for u in self.store.read() if u["uwiId"] == uwiId), None)

    def saveMany(self, users: List[dict]) -> None:
        with self.store.lock:
            ids = {u["uwiId"] for u in users}
            self.store.write([u for u in self.store.read() if u["uwiId"] not in ids] + list(users))
