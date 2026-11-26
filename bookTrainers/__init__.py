"""Gymmick - Book Trainers (US-05).

Business Logic and Data Access layers only (SDS 2.3); the team's Flask
Blueprint calls this service.

    from bookTrainers import buildBookingService
    booking = buildBookingService("data")
    booking.listTrainers("S1")
"""
from datetime import datetime

from .bookingService import AccessDeniedError, BookingError, BookingService, withinOpeningHours
from .models import Booking, BookingStatus, TimeSlot
from .repositories import BookingRepository, NotificationRepository, TimeSlotRepository, UserRepository


def buildBookingService(dataDir: str, clock=datetime.now) -> BookingService:
    return BookingService(UserRepository(dataDir), TimeSlotRepository(dataDir), BookingRepository(dataDir),
                          NotificationRepository(dataDir), clock)
