"""Data Access Layer for accounts: the shared users.json file (SDS 2.3.1).

One record per person, used by every feature:
    {"uwiId", "name", "role", "passwordHash", "createdAt", "failedLogins", "lockedUntil",
     "workoutSharing", "specialisations", "bio", "routineIds"}
role is one of student, trainer, staff, operator (SRS 3.2.2).
"""
import json
import os
import threading
from typing import List, Optional


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


def recordId(record: dict) -> Optional[str]:
    """Older records written by ActiveUser used "ID Number"; newer ones use "uwiId"."""
    return record.get("uwiId", record.get("ID Number"))


class UserRepository:
    def __init__(self, dataDir: str):
        self.store = JsonStore(dataDir, "users.json")

    def get(self, uwiId: str) -> Optional[dict]:
        return next((u for u in self.store.read() if recordId(u) == uwiId), None)

    def listAll(self) -> List[dict]:
        return self.store.read()

    def add(self, user: dict) -> None:
        with self.store.lock:
            self.store.write(self.store.read() + [user])

    def update(self, uwiId: str, **fields) -> None:
        """Change only these fields, keeping everything else other features saved on the record."""
        with self.store.lock:
            records = self.store.read()
            for u in records:
                if recordId(u) == uwiId:
                    u.update(fields)
            self.store.write(records)
