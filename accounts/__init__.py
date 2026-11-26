"""Gymmick accounts: sign-up, login, roles and password resets (SRS 3.2.2)."""
from datetime import datetime

from .accountService import ROLE_LABELS, ROLES, AccountError, AccountService, LoginError
from .repositories import UserRepository


def buildAccountService(dataDir: str, clock=datetime.now) -> AccountService:
    return AccountService(UserRepository(dataDir), clock)
