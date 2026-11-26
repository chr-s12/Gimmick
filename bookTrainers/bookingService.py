"""Business Logic Layer for Book Trainers (SRS Feature 5, US-05).

Students see the trainers and their free times, ask for a session, move a
confirmed session to another time, cancel one, and get a reminder an hour
before it starts. Every change is saved straight away and the other person is
told through notifications.json.

Trainers' free times come from timeSlots.json (written by Manage
Availability, Feature 2). respondToRequest is the hook Feature 2 calls when a
trainer accepts or declines a request (SRS 3.1.2).
"""
from datetime import datetime, timedelta
from typing import Callable, List, Optional

from occupancyTrends.gymHours import OPENING_HOURS

from .models import Booking, BookingStatus, TimeSlot
from .repositories import BookingRepository, NotificationRepository, TimeSlotRepository, UserRepository

REMINDER_LEAD = timedelta(hours=1)   # scenario 6: remind the student one hour before


class BookingError(Exception):
    """Shown to the user as-is; nothing is saved when one is raised."""


class AccessDeniedError(BookingError):
    pass


def withinOpeningHours(start: datetime, end: datetime) -> bool:
    """True if the whole session fits inside one of the gym's opening windows that day (SRS 1.6.8)."""
    if start.date() != end.date():
        return False
    return any(opens <= start.time() and end.time() <= closes
               for opens, closes in OPENING_HOURS[start.weekday()])


def describeTime(moment: datetime) -> str:
    return moment.strftime("%a %d %b, %H:%M")


class BookingService:
    def __init__(self, users: UserRepository, slots: TimeSlotRepository, bookings: BookingRepository,
                 notifications: NotificationRepository, clock: Callable[[], datetime] = datetime.now):
        self.users = users
        self.slots = slots
        self.bookings = bookings
        self.notifications = notifications
        self.clock = clock

    # ---- checks -------------------------------------------------------------------------------

    def _user(self, uwiId: str, role: str) -> dict:
        user = self.users.get(uwiId)
        if not user or user.get("role") != role:
            raise AccessDeniedError(f"Only a {role} can do this.")
        return user

    def _student(self, studentId: str) -> dict:
        user = self._user(studentId, "student")
        self.sendDueReminders()
        return user

    def _trainer(self, trainerId: str) -> dict:
        trainer = self.users.get(trainerId)
        if not trainer or trainer.get("role") != "trainer":
            raise BookingError("That trainer could not be found.")
        return trainer

    def _ownBooking(self, studentId: str, bookingId: str) -> Booking:
        booking = self.bookings.get(bookingId)
        if not booking or booking.studentId != studentId:
            raise BookingError("That booking could not be found.")
        return booking

    def _slotTaken(self, slot: TimeSlot, allBookings: List[Booking], ignoreId: Optional[str] = None) -> bool:
        """A slot is taken once the trainer has accepted a session that overlaps it."""
        return any(b.trainerId == slot.trainerId and b.status == BookingStatus.ACCEPTED
                   and b.bookingId != ignoreId and slot.overlaps(b.start, b.end) for b in allBookings)

    def _isFree(self, slot: TimeSlot, now: datetime, allBookings: List[Booking],
                ignoreId: Optional[str] = None) -> bool:
        return slot.start > now and withinOpeningHours(slot.start, slot.end) \
            and not self._slotTaken(slot, allBookings, ignoreId)

    def _checkSlotForStudent(self, studentId: str, slotId: str, now: datetime, allBookings: List[Booking],
                             ignoreId: Optional[str] = None) -> TimeSlot:
        """Scenario 3: an unavailable time is refused and no request is sent."""
        slot = self.slots.get(slotId)
        if not slot or not self._isFree(slot, now, allBookings, ignoreId):
            raise BookingError("That time is not available. Please pick another.")
        clash = next((b for b in allBookings if b.studentId == studentId and b.isActive()
                      and (ignoreId is None or ignoreId not in (b.bookingId, b.replacesBookingId))
                      and slot.overlaps(b.start, b.end)), None)
        if clash:
            raise BookingError("You already have a session or request at that time.")
        return slot

    # ---- AC-05.0 / scenario 1: trainers and their free times -------------------------------------

    def listTrainers(self, studentId: str) -> List[dict]:
        self._student(studentId)
        return sorted(({"uwiId": t["uwiId"], "name": t["name"], "specialisations": t.get("specialisations", [])}
                       for t in self.users.byRole("trainer")), key=lambda t: t["name"])

    def getTrainerProfile(self, studentId: str, trainerId: str) -> dict:
        self._student(studentId)
        trainer = self._trainer(trainerId)
        now, allBookings = self.clock(), self.bookings.listAll()
        upcoming = sorted((s for s in self.slots.forTrainer(trainerId)
                           if s.start > now and withinOpeningHours(s.start, s.end)), key=lambda s: s.start)
        view = lambda s: {"slotId": s.slotId, "start": s.start, "end": s.end, "label": describeTime(s.start),
                          "endLabel": s.end.strftime("%H:%M")}
        return {"uwiId": trainer["uwiId"], "name": trainer["name"],
                "specialisations": trainer.get("specialisations", []),
                "bio": trainer.get("bio", ""),
                "availableSlots": [view(s) for s in upcoming if self._isFree(s, now, allBookings)],
                "takenSlots": [view(s) for s in upcoming if not self._isFree(s, now, allBookings)]}

    # ---- AC-05.1 / scenarios 2 and 3: ask for a session ----------------------------------------

    def requestBooking(self, studentId: str, slotId: str) -> Booking:
        student = self._student(studentId)
        now, allBookings = self.clock(), self.bookings.listAll()
        slot = self._checkSlotForStudent(studentId, slotId, now, allBookings)
        trainer = self._trainer(slot.trainerId)
        booking = Booking(studentId, slot.trainerId, slot.start, slot.end, slotId=slot.slotId)
        self.bookings.add(booking)
        when = describeTime(slot.start)
        self.notifications.add(trainer["uwiId"], f"{student['name']} asked to book a session on {when}.", now)
        self.notifications.add(studentId, f"Your request for {when} was sent to {trainer['name']} "
                                          f"for confirmation.", now)
        return booking

    # ---- AC-05.2 / scenario 4 (TC-05.4): move a confirmed session ------------------------------

    def editBooking(self, studentId: str, bookingId: str, newSlotId: str) -> Booking:
        """The saved booking moves to the new time and goes from Accepted back to Pending,
        so the trainer confirms the new time like any other request."""
        student = self._student(studentId)
        now = self.clock()
        current = self._ownBooking(studentId, bookingId)
        if current.status != BookingStatus.ACCEPTED or current.start <= now:
            raise BookingError("Only a confirmed session that hasn't started yet can be changed.")
        slot = self._checkSlotForStudent(studentId, newSlotId, now, self.bookings.listAll(), ignoreId=bookingId)
        if slot.trainerId != current.trainerId:
            raise BookingError("Pick another time with the same trainer, or cancel and book someone else.")
        trainer = self._trainer(current.trainerId)
        old, new = describeTime(current.start), describeTime(slot.start)
        current.start, current.end, current.slotId = slot.start, slot.end, slot.slotId
        current.status = BookingStatus.PENDING
        current.studentReminded = current.trainerReminded = False
        self.bookings.save(current)
        self.notifications.add(trainer["uwiId"], f"{student['name']} asked to move their session on {old} "
                                                 f"to {new}.", now)
        self.notifications.add(studentId, f"Your session on {old} was changed to {new} and sent to "
                                          f"{trainer['name']} for confirmation.", now)
        return current

    # ---- AC-05.3 / scenario 5: cancel ------------------------------------------------------------

    def cancelBooking(self, studentId: str, bookingId: str) -> Booking:
        student = self._student(studentId)
        now = self.clock()
        booking = self._ownBooking(studentId, bookingId)
        if not booking.isActive() or booking.end <= now:
            raise BookingError("This session can no longer be cancelled.")
        booking.status = BookingStatus.CANCELLED
        changed = [booking]
        for other in self.bookings.listAll():   # a waiting change to this session goes too
            if other.replacesBookingId == bookingId and other.status == BookingStatus.PENDING:
                other.status = BookingStatus.CANCELLED
                changed.append(other)
        self.bookings.save(*changed)
        trainer = self.users.get(booking.trainerId) or {"name": "the trainer"}
        what = "session" if booking.replacesBookingId is None else "change request for the session"
        self.notifications.add(booking.trainerId, f"{student['name']} cancelled their {what} on "
                                                  f"{describeTime(booking.start)}.", now)
        self.notifications.add(studentId, f"Your {what} with {trainer['name']} on "
                                          f"{describeTime(booking.start)} was cancelled.", now)
        return booking

    # ---- schedule, reminders, notifications ----------------------------------------------------

    def getStudentSchedule(self, studentId: str) -> List[dict]:
        """The student's confirmed sessions and waiting requests that haven't finished yet."""
        self._student(studentId)
        now = self.clock()
        names = {}
        rows = []
        for b in sorted(self.bookings.listAll(), key=lambda b: b.start):
            if b.studentId != studentId or not b.isActive() or b.end <= now:
                continue
            if b.trainerId not in names:
                names[b.trainerId] = (self.users.get(b.trainerId) or {}).get("name", b.trainerId)
            rows.append({"bookingId": b.bookingId, "trainerId": b.trainerId, "trainerName": names[b.trainerId],
                         "start": b.start, "end": b.end, "label": describeTime(b.start),
                         "status": b.status.value, "isChangeRequest": b.replacesBookingId is not None})
        return rows

    def sendDueReminders(self) -> int:
        """Scenario 6 / AC-05.4: remind each student once, an hour before a confirmed session."""
        now = self.clock()
        due = [b for b in self.bookings.listAll() if b.status == BookingStatus.ACCEPTED
               and not b.studentReminded and now < b.start <= now + REMINDER_LEAD]
        for b in due:
            trainer = self.users.get(b.trainerId) or {"name": "your trainer"}
            self.notifications.add(b.studentId, f"Reminder: your session with {trainer['name']} starts at "
                                                f"{b.start.strftime('%H:%M')} ({describeTime(b.start)}).", now)
            b.studentReminded = True
        if due:
            self.bookings.save(*due)
        return len(due)

    def getNotifications(self, uwiId: str) -> List[dict]:
        if not self.users.get(uwiId):
            raise AccessDeniedError("Unknown user.")
        self.sendDueReminders()
        return self.notifications.listForUser(uwiId)

    # ---- SRS 3.1.2: the trainer's answer (called by Manage Availability, Feature 2) -------------

    def respondToRequest(self, trainerId: str, bookingId: str, accept: bool) -> Booking:
        trainer = self._user(trainerId, "trainer")
        now = self.clock()
        booking = self.bookings.get(bookingId)
        if not booking or booking.trainerId != trainerId:
            raise BookingError("That request could not be found.")
        if booking.status != BookingStatus.PENDING or booking.start <= now:
            raise BookingError("This request has already been answered or has expired.")
        changed = [booking]
        when = describeTime(booking.start)
        if accept:
            allBookings = self.bookings.listAll()
            slot = TimeSlot(trainerId, booking.start, booking.end)
            if self._slotTaken(slot, allBookings, ignoreId=booking.replacesBookingId):
                raise BookingError("You already have a confirmed session at that time.")
            booking.status = BookingStatus.ACCEPTED
            if booking.replacesBookingId:   # the old time is freed once the move is accepted
                old = next(b for b in allBookings if b.bookingId == booking.replacesBookingId)
                old.status = BookingStatus.CANCELLED
                changed.append(old)
            # Feature 2: other requests for the same time are declined automatically
            for other in allBookings:
                if (other.trainerId == trainerId and other.status == BookingStatus.PENDING
                        and other.bookingId != booking.bookingId and slot.overlaps(other.start, other.end)):
                    other.status = BookingStatus.DECLINED
                    changed.append(other)
                    self.notifications.add(other.studentId, f"{trainer['name']} declined your request for "
                                                            f"{describeTime(other.start)}: the time was booked "
                                                            f"by someone else.", now)
            message = f"{trainer['name']} confirmed your session on {when}."
        else:
            booking.status = BookingStatus.DECLINED
            message = f"{trainer['name']} declined your request for {when}."
            if booking.replacesBookingId:
                message += " Your original session is unchanged."
        self.bookings.save(*changed)
        self.notifications.add(booking.studentId, message, now)
        return booking
