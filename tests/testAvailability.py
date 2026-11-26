"""Tests for Manage Availability (US-02). Each test has its own data folder and a fake clock."""
from datetime import datetime, timedelta

import pytest

from bookTrainers import BookingStatus, buildBookingService
from bookTrainers.repositories import BookingRepository, NotificationRepository, UserRepository
from manageAvailability import AccessDeniedError, AvailabilityError, buildAvailabilityService

MONDAY = "2026-11-30"   # gym open 05:00-22:00; the clock starts the Sunday before


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def world(tmp_path):
    clock = Clock(datetime(2026, 11, 29, 12, 0))
    UserRepository(tmp_path).saveMany([
        {"uwiId": "S1", "name": "Sam Student", "role": "student"},
        {"uwiId": "S2", "name": "Tia Student", "role": "student"},
        {"uwiId": "T1", "name": "Jo Trainer", "role": "trainer", "specialisations": ["Strength"]},
    ])
    return tmp_path, clock, buildAvailabilityService(tmp_path, clock), buildBookingService(tmp_path, clock)


def messages(dataDir, uwiId):
    return [n["message"] for n in NotificationRepository(dataDir).listForUser(uwiId)]


def freeIds(booking, studentId="S1"):
    return [s["slotId"] for s in booking.getTrainerProfile(studentId, "T1")["availableSlots"]]


# AC-02.1: advertise a time
def test_addedSlotIsShownToStudents(world):
    _, _, availability, booking = world
    slot = availability.addSlot("T1", MONDAY, "10:00", "11:00")
    assert freeIds(booking) == [slot.slotId]
    assert availability.getSchedule("T1")["slots"][0]["status"] == "Free"


@pytest.mark.parametrize("start, end, message", [
    ("11:00", "10:00", "end time must be after"),
    ("04:00", "05:00", "gym is open"),
    ("10:00", "10:15", "between 30 minutes and 3 hours"),
])
def test_invalidSlotTimesAreRefused(world, start, end, message):
    _, _, availability, _ = world
    with pytest.raises(AvailabilityError, match=message):
        availability.addSlot("T1", MONDAY, start, end)


def test_pastAndSundaySlotsAreRefused(world):
    _, _, availability, _ = world
    with pytest.raises(AvailabilityError, match="future"):
        availability.addSlot("T1", "2026-11-28", "10:00", "11:00")
    with pytest.raises(AvailabilityError, match="gym is open"):
        availability.addSlot("T1", "2026-12-06", "10:00", "11:00")


def test_overlappingSlotIsRefused(world):
    _, _, availability, _ = world
    availability.addSlot("T1", MONDAY, "10:00", "11:00")
    with pytest.raises(AvailabilityError, match="conflicts with your existing slot"):
        availability.addSlot("T1", MONDAY, "10:30", "11:30")
    assert len(availability.getSchedule("T1")["slots"]) == 1


def test_onlyTrainersCanManageAvailability(world):
    _, _, availability, _ = world
    for action in (lambda: availability.addSlot("S1", MONDAY, "10:00", "11:00"),
                   lambda: availability.getSchedule("S1"),
                   lambda: availability.cancelSession("S1", "x")):
        with pytest.raises(AccessDeniedError):
            action()


# AC-02.2: edit and remove
def test_freeSlotCanBeEditedAndRemoved(world):
    _, _, availability, booking = world
    slot = availability.addSlot("T1", MONDAY, "10:00", "11:00")
    moved = availability.editSlot("T1", slot.slotId, MONDAY, "14:00", "15:00")
    assert booking.getTrainerProfile("S1", "T1")["availableSlots"][0]["start"] == moved.start
    availability.removeSlot("T1", slot.slotId)
    assert freeIds(booking) == []


def test_slotWithARequestCannotBeEditedOrRemoved(world):
    _, _, availability, booking = world
    slot = availability.addSlot("T1", MONDAY, "10:00", "11:00")
    booking.requestBooking("S1", slot.slotId)
    with pytest.raises(AvailabilityError, match="has a booking"):
        availability.editSlot("T1", slot.slotId, MONDAY, "14:00", "15:00")
    with pytest.raises(AvailabilityError, match="has a booking"):
        availability.removeSlot("T1", slot.slotId)


# AC-02.3: accept or decline
def test_acceptingOneRequestDeclinesTheOthersForThatTime(world):
    dataDir, _, availability, booking = world
    slot = availability.addSlot("T1", MONDAY, "10:00", "11:00")
    first = booking.requestBooking("S1", slot.slotId)
    second = booking.requestBooking("S2", slot.slotId)
    assert availability.getSchedule("T1")["slots"][0]["status"] == "2 requests"
    availability.respondToRequest("T1", first.bookingId, accept=True)
    saved = BookingRepository(dataDir)
    assert saved.get(first.bookingId).status == BookingStatus.ACCEPTED
    assert saved.get(second.bookingId).status == BookingStatus.DECLINED
    assert "confirmed your session" in messages(dataDir, "S1")[0]
    assert "booked by someone else" in messages(dataDir, "S2")[0]
    assert availability.getSchedule("T1")["slots"][0]["bookedBy"] == "Sam Student"


def test_declineIsRecordedAndStudentTold(world):
    dataDir, _, availability, booking = world
    slot = availability.addSlot("T1", MONDAY, "10:00", "11:00")
    request = booking.requestBooking("S1", slot.slotId)
    availability.respondToRequest("T1", request.bookingId, accept=False)
    assert BookingRepository(dataDir).get(request.bookingId).status == BookingStatus.DECLINED
    assert "declined" in messages(dataDir, "S1")[0]


# AC-02.4: cancel
def test_trainerCancelsAConfirmedSession(world):
    dataDir, _, availability, booking = world
    slot = availability.addSlot("T1", MONDAY, "10:00", "11:00")
    request = booking.requestBooking("S1", slot.slotId)
    availability.respondToRequest("T1", request.bookingId, accept=True)
    availability.cancelSession("T1", request.bookingId)
    assert BookingRepository(dataDir).get(request.bookingId).status == BookingStatus.CANCELLED
    assert "Jo Trainer cancelled your session" in messages(dataDir, "S1")[0]
    assert booking.getStudentSchedule("S1") == []
    assert freeIds(booking, "S2") == [slot.slotId]


# AC-02.0: move a confirmed session
def test_trainerMovesASessionAndStudentIsTold(world):
    dataDir, _, availability, booking = world
    first = availability.addSlot("T1", MONDAY, "10:00", "11:00")
    second = availability.addSlot("T1", MONDAY, "14:00", "15:00")
    request = booking.requestBooking("S1", first.slotId)
    availability.respondToRequest("T1", request.bookingId, accept=True)
    assert [o["slotId"] for o in availability.freeSlotsForMove("T1", request.bookingId)] == [second.slotId]
    availability.moveSession("T1", request.bookingId, second.slotId)
    schedule = booking.getStudentSchedule("S1")
    assert [(s["label"], s["status"]) for s in schedule] == [("Mon 30 Nov, 14:00", "Accepted")]
    assert "moved your session" in messages(dataDir, "S1")[0]
    assert freeIds(booking, "S2") == [first.slotId]


def test_cannotMoveOntoABookedTime(world):
    _, _, availability, booking = world
    first = availability.addSlot("T1", MONDAY, "10:00", "11:00")
    second = availability.addSlot("T1", MONDAY, "14:00", "15:00")
    mine = booking.requestBooking("S1", first.slotId)
    theirs = booking.requestBooking("S2", second.slotId)
    availability.respondToRequest("T1", mine.bookingId, accept=True)
    availability.respondToRequest("T1", theirs.bookingId, accept=True)
    with pytest.raises(AvailabilityError, match="already booked"):
        availability.moveSession("T1", mine.bookingId, second.slotId)


# AC-02.5: reminder
def test_trainerIsRemindedOnceAnHourBefore(world):
    dataDir, clock, availability, booking = world
    slot = availability.addSlot("T1", MONDAY, "10:00", "11:00")
    request = booking.requestBooking("S1", slot.slotId)
    availability.respondToRequest("T1", request.bookingId, accept=True)
    clock.now = datetime(2026, 11, 30, 9, 0)
    assert availability.sendDueReminders() == 1
    assert availability.sendDueReminders() == 0
    reminder = messages(dataDir, "T1")[0]
    assert "Sam Student" in reminder and "10:00" in reminder
