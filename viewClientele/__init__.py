"""Gymmick - View Clientele (US-06).

Business Logic and Data Access layers only (SDS 2.3); the team's Flask
Blueprint calls this service.

    from viewClientele import buildClienteleService
    clientele = buildClienteleService("data")
    clientele.listClients("T1")
"""
from datetime import datetime

from .clienteleService import AccessDeniedError, ClienteleError, ClienteleService, SharingDisabledError
from .repositories import (AssignedRoutineRepository, BookingRepository, NotificationRepository,
                           UserRepository, WorkoutLogRepository)


def buildClienteleService(dataDir: str, clock=datetime.now) -> ClienteleService:
    return ClienteleService(UserRepository(dataDir), BookingRepository(dataDir), WorkoutLogRepository(dataDir),
                            AssignedRoutineRepository(dataDir), NotificationRepository(dataDir), clock)
