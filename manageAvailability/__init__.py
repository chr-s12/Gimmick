"""Gymmick - Manage Availability (US-02).

    from manageAvailability import buildAvailabilityService
    availability = buildAvailabilityService("data")
    availability.addSlot("T1", "2026-11-30", "10:00", "11:00")
"""
from datetime import datetime

from bookTrainers import buildBookingService
from bookTrainers.repositories import BookingRepository, NotificationRepository, TimeSlotRepository, UserRepository

from .availabilityService import AccessDeniedError, AvailabilityError, AvailabilityService, parseSlotTimes


def buildAvailabilityService(dataDir: str, clock=datetime.now) -> AvailabilityService:
    return AvailabilityService(UserRepository(dataDir), TimeSlotRepository(dataDir), BookingRepository(dataDir),
                               NotificationRepository(dataDir), buildBookingService(dataDir, clock), clock)
