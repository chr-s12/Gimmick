"""Test plan TC-2.1 to TC-2.12 (Feature 2, US-02), run on Rahmone's AvailabilityManager and Trainer
with the same data as the test plan."""
from datetime import datetime

import pytest

from Booking.booking import Booking, BookingStatus
from Student import Student
from availability_manager import AvailabilityManager
from trainer import Trainer

START, END = datetime(2026, 11, 24, 14, 0), datetime(2026, 11, 24, 16, 0)


@pytest.fixture
def setup():
    manager, bob = AvailabilityManager(), Trainer("coach_bob", 700000001)
    assert manager.add_trainer(bob)
    return manager, bob


def booking(trainer, student="john_doe", studentId="123456789", when=START, status="Pending"):
    return Booking(when, status, Student(student, studentId), trainer)


def test_tc21_addTimeSlot(setup):
    manager, bob = setup
    assert manager.add_time_slot(bob, START, END)
    assert bob.getAvailability() == [{"start": START, "end": END}]


def test_tc22_editTimeSlot(setup):
    manager, bob = setup
    manager.add_time_slot(bob, START, END)
    assert manager.edit_time_slot(bob, START, datetime(2026, 11, 24, 18), datetime(2026, 11, 24, 20))
    assert bob.getAvailability() == [{"start": datetime(2026, 11, 24, 18), "end": datetime(2026, 11, 24, 20)}]


def test_tc23_removeTimeSlot(setup):
    manager, bob = setup
    manager.add_time_slot(bob, START, END)
    assert manager.remove_time_slot(bob, START)
    assert bob.getAvailability() == []


def test_tc24_overlappingSlotIsNotSaved(setup):
    manager, bob = setup
    manager.add_time_slot(bob, START, END)
    assert manager.add_time_slot(bob, datetime(2026, 11, 24, 15), datetime(2026, 11, 24, 17)) is False
    assert bob.getAvailability() == [{"start": START, "end": END}]


def test_endBeforeStartIsNotSaved(setup):
    manager, bob = setup
    assert manager.add_time_slot(bob, END, START) is False


def test_tc25_acceptAddsStudentToClientList(setup):
    _, bob = setup
    request = booking(bob)
    assert bob.acceptBooking(request)
    assert request.getBookingStatus() == BookingStatus.Accepted
    assert bob.viewClientele() == ["john_doe"]


def test_tc26_declineDoesNotAddStudent(setup):
    _, bob = setup
    request = booking(bob)
    assert bob.rejectBooking(request)
    assert request.getBookingStatus() == BookingStatus.Declined
    assert bob.viewClientele() == []


def test_tc27_acceptOneDeclineTheOther(setup):
    _, bob = setup
    a, b = booking(bob), booking(bob, "jane_doe", "123456780")
    bob.acceptBooking(a)
    bob.rejectBooking(b)
    assert (a.getBookingStatus(), b.getBookingStatus()) == (BookingStatus.Accepted, BookingStatus.Declined)
    assert bob.viewClientele() == ["john_doe"]


def test_tc28_cancelConfirmedSession(setup):
    _, bob = setup
    session = booking(bob)
    bob.acceptBooking(session)
    assert bob.cancelBooking(session)
    assert session.getBookingStatus() == BookingStatus.Cancelled
    assert bob.viewClientele() == []


def test_tc29_sessionStaysConfirmedWithoutCancel(setup):
    _, bob = setup
    session = booking(bob)
    bob.acceptBooking(session)
    assert session.getBookingStatus() == BookingStatus.Accepted
    assert bob.viewClientele() == ["john_doe"]


def test_tc210_moveConfirmedSession(setup):
    manager, bob = setup
    newTime = datetime(2026, 11, 24, 18)
    manager.add_time_slot(bob, START, END)
    manager.add_time_slot(bob, newTime, datetime(2026, 11, 24, 19))
    session = booking(bob)
    bob.acceptBooking(session)
    assert bob.editBooking(session, newTime)
    assert session.getBookingDateTime() == newTime
    assert bob.get_upcoming_reminders(datetime(2026, 11, 24, 17, 30)) == [
        {"student": "john_doe", "session_time": newTime}]


def test_tc211_reminderAnHourBefore(setup):
    _, bob = setup
    sessionTime = datetime(2026, 11, 25, 15)
    bob.acceptBooking(booking(bob, when=sessionTime))
    assert bob.get_upcoming_reminders(datetime(2026, 11, 25, 14)) == [
        {"student": "john_doe", "session_time": sessionTime}]
    assert bob.get_upcoming_reminders(datetime(2026, 11, 25, 13)) == []   # more than an hour away


def test_tc212_unauthorisedUserCannotEditAvailability(setup):
    manager, _ = setup
    hacker = Trainer("hacker", 999999999)   # never added to the manager
    assert manager.add_time_slot(hacker, START, END) is False
    assert hacker.getAvailability() == []
    assert manager.add_trainer(Student("hacker", 999999999)) is False   # not a Trainer object
