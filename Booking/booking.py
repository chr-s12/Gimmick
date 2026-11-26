from enum import Enum
from datetime import datetime
from Student import Student
from trainer import Trainer

class BookingStatus(Enum):
    Declined = "Declined"
    Accepted = "Accepted"
    Pending = "Pending"
    Cancelled = "Cancelled"

class Booking:
    def __init__(self, bookingDateTime: datetime, bookingStatus: BookingStatus, student: "Student", trainer: "Trainer"):
        self._bookingDateTime: datetime = bookingDateTime
        self._bookingStatus: BookingStatus = BookingStatus(bookingStatus)
        self.student: "Student" = student
        self.trainer: "Trainer" = trainer

    @staticmethod
    def _availableStarts(tr: "Trainer") -> list:
        # Trainer.getAvailability() holds {'start', 'end'} slots (availability_manager.py)
        return [slot['start'] if isinstance(slot, dict) else slot for slot in tr.getAvailability()]

    def checkAvail(self, tr: "Trainer") -> bool:
        return self._bookingDateTime in self._availableStarts(tr)

    def setBookingDateTime(self, bookingDateTime: datetime) -> bool:
        if bookingDateTime in self._availableStarts(self.trainer):
            self._bookingDateTime = bookingDateTime
            return True
        print("Choose an available booking date and time!")
        return False

    def setStatus(self, bookingStatus: BookingStatus) -> None:
        # Trainer passes plain strings such as "Accepted"
        self._bookingStatus = BookingStatus(bookingStatus)

    def getBookingStatus(self) -> BookingStatus:
        return self._bookingStatus

    def getBookingDateTime(self) -> datetime:
        return self._bookingDateTime

    def sendSessionReminder(self, tr: "Trainer", st: "Student") -> None:
        if self.getBookingStatus() == BookingStatus.Accepted:
            session_time = self.getBookingDateTime()
            if self.student == st:
                print(f"Reminder: You have a session at {session_time} with {tr.getUsername()}")
            if self.trainer == tr:
                print(f"Reminder: You have a session at {session_time} with {st.getUsername()}")
