"""Tests for Book Trainers (US-05). Each test runs on its own empty data folder with a fake clock."""
from datetime import datetime, timedelta

import pytest

from bookTrainers import BookingError, BookingStatus, TimeSlot, buildBookingService
from bookTrainers.bookingService import AccessDeniedError
from bookTrainers.repositories import BookingRepository, NotificationRepository, TimeSlotRepository, UserRepository
from viewClientele import buildClienteleService

MONDAY = datetime(2026, 11, 30)   # gym open 05:00-22:00


def at(day: datetime, hour: int, minute: int = 0) -> datetime:
    return day.replace(hour=hour, minute=minute)


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def world(tmp_path):
    clock = Clock(at(MONDAY, 8))
    UserRepository(tmp_path).saveMany([
        {"uwiId": "S1", "name": "Sam Student", "role": "student", "workoutSharing": True},
        {"uwiId": "S2", "name": "Tia Student", "role": "student", "workoutSharing": True},
        {"uwiId": "T1", "name": "Jo Trainer", "role": "trainer", "specialisations": ["Strength", "Mobility"]},
        {"uwiId": "T2", "name": "Al Trainer", "role": "trainer", "specialisations": ["Cardio"]},
    ])
    slots = {
        "mon10": TimeSlot("T1", at(MONDAY, 10), at(MONDAY, 11), "mon10"),
        "mon12": TimeSlot("T1", at(MONDAY, 12), at(MONDAY, 13), "mon12"),
        "mon06": TimeSlot("T1", at(MONDAY, 6), at(MONDAY, 7), "mon06"),                  # already past
        "tue1030": TimeSlot("T1", at(MONDAY + timedelta(1), 10, 30),
                            at(MONDAY + timedelta(1), 11, 30), "tue1030"),              # gym shut 10:00-12:30
        "sun10": TimeSlot("T1", at(MONDAY + timedelta(6), 10), at(MONDAY + timedelta(6), 11), "sun10"),
        "t2mon10": TimeSlot("T2", at(MONDAY, 10), at(MONDAY, 11), "t2mon10"),
    }
    TimeSlotRepository(tmp_path).add(*slots.values())
    return tmp_path, clock, buildBookingService(tmp_path, clock)


def messages(dataDir, uwiId):
    return [n["message"] for n in NotificationRepository(dataDir).listForUser(uwiId)]


def confirmed(service, slotId, student="S1"):
    request = service.requestBooking(student, slotId)
    return service.respondToRequest(request.trainerId, request.bookingId, accept=True)


# AC-05.0 / scenario 1
def test_listTrainersShowsEveryTrainerWithSpecialisations(world):
    _, _, service = world
    trainers = service.listTrainers("S1")
    assert [t["name"] for t in trainers] == ["Al Trainer", "Jo Trainer"]
    assert trainers[1]["specialisations"] == ["Strength", "Mobility"]


def test_profileShowsOnlyFreeTimesInsideGymHours(world):
    _, _, service = world
    profile = service.getTrainerProfile("S1", "T1")
    assert profile["name"] == "Jo Trainer"
    assert [s["slotId"] for s in profile["availableSlots"]] == ["mon10", "mon12"]


def test_onlyStudentsCanBook(world):
    _, _, service = world
    with pytest.raises(AccessDeniedError):
        service.listTrainers("T1")
    with pytest.raises(AccessDeniedError):
        service.requestBooking("nobody", "mon10")


# AC-05.1 / scenario 2
def test_requestIsForwardedToTrainerAndStudentIsTold(world):
    dataDir, _, service = world
    booking = service.requestBooking("S1", "mon10")
    assert booking.status == BookingStatus.PENDING
    assert BookingRepository(dataDir).get(booking.bookingId).start == at(MONDAY, 10)
    assert "Sam Student asked to book" in messages(dataDir, "T1")[0]
    assert "sent to Jo Trainer for confirmation" in messages(dataDir, "S1")[0]


def test_pendingRequestDoesNotBlockOtherStudentsUntilAccepted(world):
    _, _, service = world
    service.requestBooking("S1", "mon10")
    assert "mon10" in [s["slotId"] for s in service.getTrainerProfile("S2", "T1")["availableSlots"]]
    other = service.requestBooking("S2", "mon10")
    service.respondToRequest("T1", other.bookingId, accept=True)
    assert "mon10" not in [s["slotId"] for s in service.getTrainerProfile("S1", "T1")["availableSlots"]]


# AC-05.1 / scenario 3
@pytest.mark.parametrize("slotId", ["mon06", "tue1030", "sun10", "missing"])
def test_unavailableTimeIsRefusedAndNothingIsSent(world, slotId):
    dataDir, _, service = world
    with pytest.raises(BookingError, match="not available"):
        service.requestBooking("S1", slotId)
    assert BookingRepository(dataDir).listAll() == []
    assert messages(dataDir, "T1") == []


def test_takenTimeIsRefused(world):
    dataDir, _, service = world
    confirmed(service, "mon10", student="S2")
    before = len(BookingRepository(dataDir).listAll())
    with pytest.raises(BookingError, match="not available"):
        service.requestBooking("S1", "mon10")
    assert len(BookingRepository(dataDir).listAll()) == before


def test_studentCannotDoubleBookTheSameTime(world):
    _, _, service = world
    service.requestBooking("S1", "mon10")
    with pytest.raises(BookingError, match="already have"):
        service.requestBooking("S1", "mon10")
    with pytest.raises(BookingError, match="already have"):
        service.requestBooking("S1", "t2mon10")


# SRS 3.1.2: trainer's answer
def test_trainerDeclineTellsTheStudent(world):
    dataDir, _, service = world
    request = service.requestBooking("S1", "mon10")
    service.respondToRequest("T1", request.bookingId, accept=False)
    assert BookingRepository(dataDir).get(request.bookingId).status == BookingStatus.DECLINED
    assert "declined" in messages(dataDir, "S1")[0]
    assert service.getStudentSchedule("S1") == []


# AC-05.2 / scenario 4
def test_editMovesTheSavedBookingFromAcceptedToPending(world):
    """TC-05.4: Accepted -> Pending at the new time, trainer asked to confirm, student informed."""
    dataDir, _, service = world
    session = confirmed(service, "mon10")
    change = service.editBooking("S1", session.bookingId, "mon12")
    assert change.bookingId == session.bookingId
    saved = BookingRepository(dataDir).get(session.bookingId)
    assert saved.status == BookingStatus.PENDING and saved.slotId == "mon12"
    assert len(BookingRepository(dataDir).listAll()) == 1
    assert "asked to move" in messages(dataDir, "T1")[0]
    assert "sent to" in messages(dataDir, "S1")[0]

    service.respondToRequest("T1", session.bookingId, accept=True)
    schedule = service.getStudentSchedule("S1")
    assert [(row["label"], row["status"]) for row in schedule] == [("Mon 30 Nov, 12:00", "Accepted")]


def test_editToUnavailableTimeIsRefused(world):
    dataDir, _, service = world
    session = confirmed(service, "mon10")
    for slotId in ("tue1030", "t2mon10"):
        with pytest.raises(BookingError):
            service.editBooking("S1", session.bookingId, slotId)
    assert len(BookingRepository(dataDir).listAll()) == 1


def test_onlyConfirmedSessionsCanBeEdited(world):
    _, _, service = world
    request = service.requestBooking("S1", "mon10")
    with pytest.raises(BookingError, match="confirmed"):
        service.editBooking("S1", request.bookingId, "mon12")
    with pytest.raises(BookingError, match="could not be found"):
        service.editBooking("S2", request.bookingId, "mon12")


# AC-05.3 / scenario 5
def test_cancelRemovesSessionFromBothSchedulesAndTellsTrainer(world):
    dataDir, clock, service = world
    session = confirmed(service, "mon10")
    service.editBooking("S1", session.bookingId, "mon12")
    service.cancelBooking("S1", session.bookingId)

    assert service.getStudentSchedule("S1") == []
    assert all(b.status == BookingStatus.CANCELLED for b in BookingRepository(dataDir).listAll())
    assert "Sam Student cancelled their session" in messages(dataDir, "T1")[0]
    assert "mon10" in [s["slotId"] for s in service.getTrainerProfile("S2", "T1")["availableSlots"]]
    clientele = buildClienteleService(dataDir, clock)
    assert clientele.listClients("T1")["clients"] == []


def test_finishedSessionCannotBeCancelled(world):
    _, clock, service = world
    session = confirmed(service, "mon10")
    clock.now = at(MONDAY, 11, 30)
    with pytest.raises(BookingError, match="no longer"):
        service.cancelBooking("S1", session.bookingId)


# AC-05.4 / scenario 6
def test_reminderIsSentOnceAnHourBefore(world):
    dataDir, clock, service = world
    confirmed(service, "mon10")
    clock.now = at(MONDAY, 8, 59)
    assert service.sendDueReminders() == 0
    clock.now = at(MONDAY, 9)
    reminder = service.getNotifications("S1")[0]["message"]
    assert "Jo Trainer" in reminder and "10:00" in reminder
    clock.now = at(MONDAY, 9, 30)
    assert service.sendDueReminders() == 0
    assert sum("Reminder" in m for m in messages(dataDir, "S1")) == 1


def test_noReminderForPendingOrCancelledSessions(world):
    _, clock, service = world
    service.requestBooking("S1", "mon10")
    session = confirmed(service, "mon12", student="S2")
    service.cancelBooking("S2", session.bookingId)
    clock.now = at(MONDAY, 11, 30)
    assert service.sendDueReminders() == 0


# Shared data: View Clientele (Feature 6) reads the bookings this feature saves
def test_viewClienteleSeesConfirmedBookings(world):
    dataDir, clock, service = world
    confirmed(service, "mon10")
    clientele = buildClienteleService(dataDir, clock)
    assert [c["uwiId"] for c in clientele.listClients("T1")["clients"]] == ["S1"]
    assert clientele.getUpcomingSessions("T1", "S1")[0]["start"] == "2026-11-30T10:00"
