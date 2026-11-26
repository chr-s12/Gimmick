"""AccountService: sign-up, login and password resets (SRS 3.2.2).

- Everyone signs in with their UWI ID number and a password.
- Passwords are only ever stored as salted hashes.
- 5 failed logins in a row lock the account for 15 minutes.
- Forgotten passwords are reset by gym staff after checking the person's UWI ID.
- Failed logins are written to the error log (SRS 4.3).
"""
import logging
import re
from datetime import datetime, timedelta
from typing import Callable, List, Optional

from werkzeug.security import check_password_hash, generate_password_hash

from .repositories import UserRepository, recordId

ROLES = ("student", "trainer", "staff", "operator")
SELF_SIGNUP_ROLES = ("student", "trainer")   # staff and operator accounts are set up by the gym
MAX_FAILED_LOGINS = 5
LOCK_TIME = timedelta(minutes=15)
ROLE_LABELS = {"student": "Student", "trainer": "Personal Trainer", "staff": "Gym Staff", "operator": "Gym Operator"}

securityLog = logging.getLogger("gymmick.security")


class AccountError(Exception):
    """Shown to the user as-is."""


class LoginError(AccountError):
    pass


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


def checkPassword(password: str) -> Optional[str]:
    if len(password or "") < 8:
        return "Your password must be at least 8 characters long."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Your password must contain at least one letter and one number."
    return None


def cleanUwiId(uwiId: str) -> str:
    uwiId = (uwiId or "").strip()
    if not re.fullmatch(r"\d{6,12}", uwiId):
        raise AccountError("Enter your UWI ID number (6 to 12 digits, numbers only).")
    return uwiId


def splitList(text: str) -> List[str]:
    return [part.strip() for part in (text or "").split(",") if part.strip()]


class AccountService:
    def __init__(self, users: UserRepository, clock: Callable[[], datetime] = datetime.now):
        self.users, self.clock = users, clock

    def get(self, uwiId: str) -> Optional[dict]:
        user = self.users.get(uwiId)
        if user and "uwiId" not in user:   # a record ActiveUser wrote before the shared format
            user = dict(user, uwiId=recordId(user), name=user.get("Username", ""), role=user.get("role", "student"))
        return user

    # ---- sign-up -----------------------------------------------------------------------------------

    def register(self, uwiId: str, name: str, password: str, confirm: str, role: str,
                 specialisations: str = "", bio: str = "") -> dict:
        uwiId = cleanUwiId(uwiId)
        name = " ".join((name or "").split())
        if not name:
            raise AccountError("Enter your name.")
        if len(name) > 60:
            raise AccountError("Your name must be 60 characters or fewer.")
        if role not in SELF_SIGNUP_ROLES:
            raise AccountError("Choose whether you are a student or a personal trainer.")
        problem = checkPassword(password)
        if problem:
            raise AccountError(problem)
        if password != confirm:
            raise AccountError("The two passwords don't match.")
        if self.users.get(uwiId):
            raise AccountError("An account with this UWI ID already exists. Log in instead, or ask gym staff "
                               "to reset your password.")
        user = {"uwiId": uwiId, "name": name, "role": role, "passwordHash": generate_password_hash(password),
                "createdAt": _iso(self.clock()), "failedLogins": 0, "lockedUntil": None, "routineIds": []}
        if role == "student":
            user["workoutSharing"] = False
        else:
            user["specialisations"] = splitList(specialisations)
            user["bio"] = (bio or "").strip()
        self.users.add(user)
        return user

    def createAccount(self, uwiId: str, name: str, role: str, password: str, **extra) -> dict:
        """For setting up staff and operator accounts (used by seedData.py), and demo accounts."""
        if role not in ROLES:
            raise AccountError(f"Unknown role {role}.")
        user = {"uwiId": uwiId, "name": name, "role": role, "passwordHash": generate_password_hash(password),
                "createdAt": _iso(self.clock()), "failedLogins": 0, "lockedUntil": None, "routineIds": []}
        user.update(extra)
        if self.users.get(uwiId):
            self.users.update(uwiId, **user)
        else:
            self.users.add(user)
        return user

    # ---- login -------------------------------------------------------------------------------------

    def login(self, uwiId: str, password: str) -> dict:
        now = self.clock()
        uwiId = (uwiId or "").strip()
        user = self.users.get(uwiId)
        if not user or not user.get("passwordHash"):
            securityLog.warning("Failed login for unknown UWI ID %s", uwiId or "(blank)")
            raise LoginError("That UWI ID and password don't match an account.")
        locked = user.get("lockedUntil")
        if locked and datetime.fromisoformat(locked) > now:
            minutes = max(1, int((datetime.fromisoformat(locked) - now).total_seconds() // 60) + 1)
            securityLog.warning("Login attempt on locked account %s", uwiId)
            raise LoginError(f"This account is locked after too many failed attempts. Try again in {minutes} "
                             f"minute{'s' if minutes != 1 else ''}.")
        if not check_password_hash(user["passwordHash"], password or ""):
            failed = (0 if locked else user.get("failedLogins", 0)) + 1
            if failed >= MAX_FAILED_LOGINS:
                self.users.update(uwiId, failedLogins=0, lockedUntil=_iso(now + LOCK_TIME))
                securityLog.warning("Account %s locked after %d failed logins", uwiId, failed)
                raise LoginError("Too many failed attempts. This account is locked for 15 minutes.")
            self.users.update(uwiId, failedLogins=failed, lockedUntil=None)
            securityLog.warning("Failed login for %s (%d in a row)", uwiId, failed)
            left = MAX_FAILED_LOGINS - failed
            raise LoginError(f"That UWI ID and password don't match an account. {left} attempt"
                             f"{'s' if left != 1 else ''} left before the account is locked.")
        self.users.update(uwiId, failedLogins=0, lockedUntil=None)
        return self.get(uwiId)

    # ---- staff and profile -------------------------------------------------------------------------

    def resetPassword(self, staffId: str, uwiId: str, newPassword: str) -> str:
        staff = self.users.get(staffId)
        if not staff or staff.get("role") != "staff":
            raise AccountError("Only gym staff can reset passwords.")
        uwiId = (uwiId or "").strip()
        user = self.users.get(uwiId)
        if not user:
            raise AccountError(f"No account has UWI ID {uwiId}.")
        problem = checkPassword(newPassword)
        if problem:
            raise AccountError(problem)
        self.users.update(uwiId, passwordHash=generate_password_hash(newPassword), failedLogins=0, lockedUntil=None)
        securityLog.info("Password for %s reset by staff %s", uwiId, staffId)
        return f"Password reset for {user.get('name', uwiId)}. Their account is unlocked."

    def updateTrainerProfile(self, trainerId: str, specialisations: str, bio: str) -> str:
        user = self.users.get(trainerId)
        if not user or user.get("role") != "trainer":
            raise AccountError("Only personal trainers have a trainer profile.")
        items = splitList(specialisations)
        if not items:
            raise AccountError("List at least one speciality, separated by commas.")
        self.users.update(trainerId, specialisations=items, bio=(bio or "").strip()[:500])
        return "Your trainer profile was updated."
