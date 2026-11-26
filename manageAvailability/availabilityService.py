"""AvailabilityService (SDS 2.3.1): Manage Availability, US-02 (SRS 2.3.2).

Trainers advertise the times they are free, change or remove those times while
nobody has booked them, answer booking requests, cancel or move sessions, and
get a reminder an hour before each session. Students see the times through
Book Trainers (Feature 5), which reads the same timeSlots.json and bookings.json.
"""
from datetime import date, datetime, time, timedelta
from typing import Callable, List, Optional, Tuple

from bookTrainers.bookingService import BookingError, BookingService, describeTime, withinOpeningHours
from bookTrainers.models import Booking, BookingStatus, TimeSlot
from bookTrainers.repositories import BookingRepository, NotificationRepository, TimeSlotRepository, UserRepository
from occupancyTrends.gymHours import hoursText

REMINDER_LEAD = timedelta(hours=1)
MIN_SLOT = timedelta(minutes=30)
MAX_SLOT = timedelta(hours=3)


class AvailabilityError(BookingError):
    """Shown to the trainer as-is; nothing is saved when one is raised."""


class AccessDeniedError(AvailabilityError):
    pass


def parseSlotTimes(dateText: str, startText: str, endText: str) -> Tuple[datetime, datetime]:
    try:
        day = date.fromisoformat((dateText or "").strip())
        start = datetime.combine(day, time.fromisoformat((startText or "").strip()))
        end = datetime.combine(day, time.fromisoformat((endText or "").strip()))
    except ValueError:
        raise AvailabilityError("Enter a date and a start and end time.") from None
    return start, end


class AvailabilityService:
    def __init__(self, users: UserRepository, slots: TimeSlotRepository, bookings: BookingRepository,
                 notifications: NotificationRepository, bookingService: BookingService,
                 clock: Callable[[], datetime] = datetime.now):
        self.users, self.slots, self.bookings = users, slots, bookings
        self.notifications, self.bookingService, self.clock = notifications, bookingService, clock

    # ---- checks -------------------------------------------------------------------------------------

    def _trainer(self, trainerId: str) -> dict:
        """Checked on every call (SRS 3.2.2; scenario "User is not an authorised personal trainer")."""
        user = self.users.get(trainerId)
        if not user or user.get("role") != "trainer":
            raise AccessDeniedError("Only personal trainers can manage availability.")
        self.sendDueReminders()
        return user

    def _ownSlot(self, trainerId: str, slotId: str) -> TimeSlot:
        slot = self.slots.get(slotId)
        if not slot or slot.trainerId != trainerId:
            raise AvailabilityError("That time slot could not be found.")
        return slot

    def _ownBooking(self, trainerId: str, bookingId: str) -> Booking:
        booking = self.bookings.get(bookingId)
        if not booking or booking.trainerId != trainerId:
            raise AvailabilityError("That session could not be found.")
        return booking

    def _bookingsOn(self, slot: TimeSlot, allBookings: List[Booking]) -> List[Booking]:
        """Pending requests and confirmed sessions that use this slot's time."""
        return [b for b in allBookings if b.trainerId == slot.trainerId and b.isActive()
                and (b.slotId == slot.slotId or (b.status == BookingStatus.ACCEPTED
                                                 and slot.overlaps(b.start, b.end)))]

    def _checkTimes(self, trainerId: str, start: datetime, end: datetime, ignoreSlotId: Optional[str] = None):
        """SRS 3.3.2: an end before the start, a past time, a time outside gym hours or an overlap is refused."""
        if end <= start:
            raise AvailabilityError("The end time must be after the start time.")
        if end - start < MIN_SLOT or end - start > MAX_SLOT:
            raise AvailabilityError("A time slot must be between 30 minutes and 3 hours long.")
        if start <= self.clock():
            raise AvailabilityError("Pick a time in the future.")
        if not withinOpeningHours(start, end):
            raise AvailabilityError(f"Sessions can only be held while the gym is open. Hours that day: "
                                    f"{hoursText(start.date())}.")
        clash = next((s for s in self.slots.forTrainer(trainerId)
                      if s.slotId != ignoreSlotId and s.overlaps(start, end)), None)
        if clash:
            raise AvailabilityError(f"This conflicts with your existing slot on {describeTime(clash.start)}-"
                                    f"{clash.end.strftime('%H:%M')}.")

    # ---- AC-02.1 / AC-02.2: advertise and edit times ----------------------------------------------

    def addSlot(self, trainerId: str, dateText: str, startText: str, endText: str) -> TimeSlot:
        self._trainer(trainerId)
        start, end = parseSlotTimes(dateText, startText, endText)
        self._checkTimes(trainerId, start, end)
        slot = TimeSlot(trainerId, start, end)
        self.slots.add(slot)
        return slot

    def editSlot(self, trainerId: str, slotId: str, dateText: str, startText: str, endText: str) -> TimeSlot:
        self._trainer(trainerId)
        slot = self._ownSlot(trainerId, slotId)
        if self._bookingsOn(slot, self.bookings.listAll()):
            raise AvailabilityError("This slot has a booking or a request, so it can't be changed. Move or "
                                    "cancel the session instead.")
        start, end = parseSlotTimes(dateText, startText, endText)
        self._checkTimes(trainerId, start, end, ignoreSlotId=slotId)
        slot.start, slot.end = start, end
        self.slots.save(slot)
        return slot

    def removeSlot(self, trainerId: str, slotId: str) -> None:
        self._trainer(trainerId)
        slot = self._ownSlot(trainerId, slotId)
        if self._bookingsOn(slot, self.bookings.listAll()):
            raise AvailabilityError("This slot has a booking or a request, so it can't be removed. Answer or "
                                    "cancel those first.")
        self.slots.remove(slotId)

    def getSlot(self, trainerId: str, slotId: str) -> TimeSlot:
        self._trainer(trainerId)
        return self._ownSlot(trainerId, slotId)

    # ---- the trainer's schedule ---------------------------------------------------------------------

    def getSchedule(self, trainerId: str) -> dict:
        self._trainer(trainerId)
        now, allBookings = self.clock(), self.bookings.listAll()
        names = {}

        def studentName(uwiId):
            if uwiId not in names:
                names[uwiId] = (self.users.get(uwiId) or {}).get("name", uwiId)
            return names[uwiId]

        def row(b: Booking) -> dict:
            replaced = self.bookings.get(b.replacesBookingId) if b.replacesBookingId else None
            return {"bookingId": b.bookingId, "studentId": b.studentId, "studentName": studentName(b.studentId),
                    "start": b.start, "end": b.end, "label": describeTime(b.start), "endLabel": b.end.strftime("%H:%M"),
                    "isChangeRequest": replaced is not None,
                    "replacesLabel": describeTime(replaced.start) if replaced else None,
                    "inProgress": b.start <= now < b.end}

        mine = sorted((b for b in allBookings if b.trainerId == trainerId and b.end > now), key=lambda b: b.start)
        slots = []
        for s in sorted(self.slots.forTrainer(trainerId), key=lambda s: s.start):
            if s.end <= now:
                continue
            on = self._bookingsOn(s, allBookings)
            confirmed = [b for b in on if b.status == BookingStatus.ACCEPTED]
            pending = [b for b in on if b.status == BookingStatus.PENDING]
            status = "Booked" if confirmed else f"{len(pending)} request{'s' if len(pending) != 1 else ''}" \
                if pending else "Free"
            slots.append({"slotId": s.slotId, "start": s.start, "end": s.end, "label": describeTime(s.start),
                          "endLabel": s.end.strftime("%H:%M"), "status": status, "canChange": not on,
                          "dateValue": s.start.date().isoformat(), "startValue": s.start.strftime("%H:%M"),
                          "endValue": s.end.strftime("%H:%M"),
                          "bookedBy": studentName(confirmed[0].studentId) if confirmed else None})
        return {"slots": slots,
                "requests": [row(b) for b in mine if b.status == BookingStatus.PENDING],
                "sessions": [row(b) for b in mine if b.status == BookingStatus.ACCEPTED]}

    def freeSlotsForMove(self, trainerId: str, bookingId: str) -> List[dict]:
        """Other free times a confirmed session could move to."""
        self._trainer(trainerId)
        booking = self._ownBooking(trainerId, bookingId)
        now, allBookings = self.clock(), self.bookings.listAll()
        free = []
        for s in sorted(self.slots.forTrainer(trainerId), key=lambda s: s.start):
            others = [b for b in self._bookingsOn(s, allBookings)
                      if b.bookingId != bookingId and b.status == BookingStatus.ACCEPTED]
            if s.start > now and not others and s.slotId != booking.slotId:
                free.append({"slotId": s.slotId, "label": f"{describeTime(s.start)}-{s.end.strftime('%H:%M')}"})
        return free

    # ---- AC-02.3: accept or decline ------------------------------------------------------------------

    def respondToRequest(self, trainerId: str, bookingId: str, accept: bool) -> Booking:
        self._trainer(trainerId)
        return self.bookingService.respondToRequest(trainerId, bookingId, accept)

    # ---- AC-02.4: cancel ------------------------------------------------------------------------------

    def cancelSession(self, trainerId: str, bookingId: str) -> Booking:
        trainer = self._trainer(trainerId)
        now = self.clock()
        booking = self._ownBooking(trainerId, bookingId)
        if not booking.isActive() or booking.end <= now:
            raise AvailabilityError("This session can no longer be cancelled.")
        wasConfirmed = booking.status == BookingStatus.ACCEPTED
        booking.status = BookingStatus.CANCELLED
        changed = [booking]
        for other in self.bookings.listAll():
            if other.replacesBookingId == bookingId and other.status == BookingStatus.PENDING:
                other.status = BookingStatus.CANCELLED
                changed.append(other)
        self.bookings.save(*changed)
        what = "session" if wasConfirmed else "session request"
        self.notifications.add(booking.studentId, f"{trainer['name']} cancelled your {what} on "
                                                  f"{describeTime(booking.start)}.", now)
        return booking

    # ---- AC-02.0: move a confirmed session -----------------------------------------------------------

    def moveSession(self, trainerId: str, bookingId: str, slotId: str) -> Booking:
        trainer = self._trainer(trainerId)
        now = self.clock()
        booking = self._ownBooking(trainerId, bookingId)
        if booking.status != BookingStatus.ACCEPTED or booking.start <= now:
            raise AvailabilityError("Only a confirmed session that hasn't started yet can be moved.")
        slot = self._ownSlot(trainerId, slotId)
        allBookings = self.bookings.listAll()
        if slot.start <= now or not withinOpeningHours(slot.start, slot.end):
            raise AvailabilityError("That time is not available.")
        if any(b.bookingId != bookingId and b.status == BookingStatus.ACCEPTED
               for b in self._bookingsOn(slot, allBookings)):
            raise AvailabilityError("That time is already booked.")
        if any(b.studentId == booking.studentId and b.isActive() and b.bookingId != bookingId
               and b.replacesBookingId != bookingId and slot.overlaps(b.start, b.end) for b in allBookings):
            raise AvailabilityError("The student already has another session or request at that time.")
        old = describeTime(booking.start)
        booking.start, booking.end, booking.slotId = slot.start, slot.end, slot.slotId
        booking.studentReminded = booking.trainerReminded = False
        changed = [booking]
        for other in allBookings:   # a waiting change request from the student is no longer needed
            if other.replacesBookingId == bookingId and other.status == BookingStatus.PENDING:
                other.status = BookingStatus.CANCELLED
                changed.append(other)
        self.bookings.save(*changed)
        self.notifications.add(booking.studentId, f"{trainer['name']} moved your session on {old} to "
                                                  f"{describeTime(slot.start)}.", now)
        return booking

    # ---- AC-02.5: reminders ----------------------------------------------------------------------------

    def sendDueReminders(self) -> int:
        """Remind each trainer once, an hour before a confirmed session, with the student's name and time."""
        now = self.clock()
        due = [b for b in self.bookings.listAll() if b.status == BookingStatus.ACCEPTED
               and not b.trainerReminded and now < b.start <= now + REMINDER_LEAD]
        for b in due:
            student = self.users.get(b.studentId) or {"name": "your client"}
            self.notifications.add(b.trainerId, f"Reminder: your session with {student['name']} starts at "
                                                f"{b.start.strftime('%H:%M')} ({describeTime(b.start)}).", now)
            b.trainerReminded = True
        if due:
            self.bookings.save(*due)
        return len(due)
