from enum import Enum
from datetime import datetime
from Student import Student
from Trainer import Trainer

class BookingStatus(Enum):
    Declined = "Declined"
    Accepted = "Accepted"
    Pending = "Pending"

class Booking:
    def __init__(self, bookingDateTime: datetime, bookingStatus: BookingStatus, student: "Student", trainer: "Trainer"):
        self._bookingDateTime: datetime = bookingDateTime
        self._bookingStatus: BookingStatus = bookingStatus
        self.student: "Student" = student
        self.trainer: "Trainer" = trainer

    def checkAvail(self, tr: "Trainer") -> bool:
        return self._bookingDateTime in tr.getAvailabilityTimes()
            
    def setBookingDateTime(self, bookingDateTime: datetime) -> None:
        if bookingDateTime in self.trainer.getAvailabilityTimes():
            self._bookingDateTime = bookingDateTime
        else:
            print("Choose an available booking date and time!")

    def setStatus(self, bookingStatus: BookingStatus) -> None:
        self._bookingStatus = bookingStatus

    def getBookingStatus(self) -> BookingStatus:
        return self._bookingStatus

    def getBookingDateTime(self) -> datetime:
        return self._bookingDateTime

    def sendSessionReminder(self, tr: "Trainer", st: "Student") -> None:
        if self.getBookingStatus == BookingStatus.Accepted:
            session_time = self.getBookingDateTime
            if self.student == st:
                print(f"Reminder: You have a session at {session_time} with {tr}, {st}")
            if self.trainer == tr:
                print(f"Reminder: You have a session at {session_time} with {st}, {tr}")
                