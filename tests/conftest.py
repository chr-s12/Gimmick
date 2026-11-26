from datetime import datetime, timedelta

import pytest

from occupancyTrends import buildServices
from occupancyTrends.repositories import EntryExitRepository, QueueRepository, UserRepository

OPEN_MONDAY = datetime(2026, 11, 23, 10, 0)   # gym open 5 am - 10 pm


class FakeClock:
    def __init__(self, start):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


def student(i):
    return f"62000{i:04d}"


@pytest.fixture
def clock():
    return FakeClock(OPEN_MONDAY)


@pytest.fixture
def dataDir(tmp_path):
    users = [{"uwiId": "S1", "name": "Staff", "role": "staff"},
             {"uwiId": "T1", "name": "Trainer", "role": "trainer"}]
    users += [{"uwiId": student(i), "name": f"Student {i}", "role": "student"} for i in range(1, 31)]
    UserRepository(str(tmp_path)).saveMany(users)
    return str(tmp_path)


@pytest.fixture
def occupancy(dataDir, clock):
    return buildServices(dataDir, clock=clock)["occupancy"]


@pytest.fixture
def reports(dataDir):
    return buildServices(dataDir)["reports"]


@pytest.fixture
def events(dataDir):
    return EntryExitRepository(dataDir)


@pytest.fixture
def queueRepo(dataDir):
    return QueueRepository(dataDir)


def fillGym(occupancy, clock, count=20):
    for i in range(1, count + 1):
        occupancy.recordEntry(student(i), "S1")
        clock.advance(seconds=1)
