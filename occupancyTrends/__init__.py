"""Gymmick - Occupancy Monitoring (US-03) and Analyze Usage Trends (US-07).

Business Logic and Data Access layers only (SDS 2.3); the team's Flask
Blueprints call these services.

    from occupancyTrends import buildServices
    svc = buildServices("data")
    svc["occupancy"].recordEntry("620200001", staffId="100000001")
    report = svc["reports"].generateReport(startDate, endDate)
"""
from datetime import datetime

from .occupancyService import OccupancyError, OccupancyService
from .reportService import InvalidDateRangeError, NoDataError, ReportError, ReportService
from .repositories import EntryExitRepository, NotificationRepository, QueueRepository, UserRepository


def buildServices(dataDir: str, clock=datetime.now, enforceGymHours=True) -> dict:
    events, queueRepo = EntryExitRepository(dataDir), QueueRepository(dataDir)
    occupancy = OccupancyService(events, queueRepo, NotificationRepository(dataDir), UserRepository(dataDir),
                                 clock, enforceGymHours)
    return {"occupancy": occupancy, "reports": ReportService(events, queueRepo)}
