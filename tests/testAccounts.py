"""Tests for accounts (SRS 3.2.2): sign-up checks, hashed passwords, lockout and staff resets."""
import json
from datetime import datetime, timedelta

import pytest

from accounts import AccountError, LoginError, buildAccountService
from routineBuilder import buildRoutineService, parseExercises


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def setup(tmp_path):
    clock = Clock(datetime(2026, 11, 30, 9, 0))
    service = buildAccountService(str(tmp_path), clock)
    service.register("620100001", "Sam Student", "secret123", "secret123", "student")
    service.createAccount("100000001", "Front Desk", "staff", "staffpass1")
    return tmp_path, clock, service


def test_passwordIsStoredOnlyAsASaltedHash(setup):
    dataDir, _, service = setup
    raw = (dataDir / "users.json").read_text()
    assert "secret123" not in raw
    record = service.get("620100001")
    assert record["passwordHash"] and record["role"] == "student" and record["workoutSharing"] is False


@pytest.mark.parametrize("uwiId, password, confirm, role, message", [
    ("12ab", "secret123", "secret123", "student", "UWI ID"),
    ("620100002", "short1", "short1", "student", "at least 8"),
    ("620100002", "lettersonly", "lettersonly", "student", "letter and one number"),
    ("620100002", "secret123", "secret124", "student", "don't match"),
    ("620100002", "secret123", "secret123", "staff", "student or a personal trainer"),
    ("620100001", "secret123", "secret123", "student", "already exists"),
])
def test_signUpRejectsBadDetails(setup, uwiId, password, confirm, role, message):
    _, _, service = setup
    with pytest.raises(AccountError, match=message):
        service.register(uwiId, "New Person", password, confirm, role)


def test_trainerSignUpKeepsSpecialities(setup):
    _, _, service = setup
    trainer = service.register("700000001", "Jo Trainer", "coach1234", "coach1234", "trainer", "Strength, Mobility")
    assert trainer["specialisations"] == ["Strength", "Mobility"]


def test_loginWorksWithRightPasswordOnly(setup):
    _, _, service = setup
    assert service.login("620100001", "secret123")["name"] == "Sam Student"
    with pytest.raises(LoginError, match="4 attempts left"):
        service.login("620100001", "wrong")
    with pytest.raises(LoginError, match="don't match"):
        service.login("999999999", "secret123")


def test_fiveFailedLoginsLockTheAccountFor15Minutes(setup):
    _, clock, service = setup
    for _ in range(4):
        with pytest.raises(LoginError):
            service.login("620100001", "wrong")
    with pytest.raises(LoginError, match="locked for 15 minutes"):
        service.login("620100001", "wrong")
    with pytest.raises(LoginError, match="locked"):
        service.login("620100001", "secret123")   # even the right password is refused while locked
    clock.now += timedelta(minutes=15, seconds=1)
    assert service.login("620100001", "secret123")["uwiId"] == "620100001"


def test_failedLoginsAreLogged(setup, caplog):
    _, _, service = setup
    with caplog.at_level("WARNING", logger="gymmick.security"):
        with pytest.raises(LoginError):
            service.login("620100001", "wrong")
    assert "Failed login for 620100001" in caplog.text


def test_onlyStaffCanResetPasswordsAndItUnlocks(setup):
    _, _, service = setup
    for _ in range(5):
        with pytest.raises(LoginError):
            service.login("620100001", "wrong")
    with pytest.raises(AccountError, match="Only gym staff"):
        service.resetPassword("620100001", "620100001", "newpass123")
    assert "unlocked" in service.resetPassword("100000001", "620100001", "newpass123")
    assert service.login("620100001", "newpass123")


def test_savingRoutinesKeepsTheAccountFields(setup):
    """ActiveUser.userSave shares users.json, so it must not wipe the password or role."""
    dataDir, _, service = setup
    routines = buildRoutineService(str(dataDir))
    routines.create("620100001", "Push day", parseExercises(["Bench Press"], ["3"], ["8"], ["90"], ["40"]))
    record = next(u for u in json.loads((dataDir / "users.json").read_text()) if u["uwiId"] == "620100001")
    assert record["passwordHash"] and record["role"] == "student" and len(record["routineIds"]) == 1
    assert service.login("620100001", "secret123")
