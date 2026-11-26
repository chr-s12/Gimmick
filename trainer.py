from ActiveUser import ActiveUser
from datetime import datetime, timedelta


def _clientName(booking):
    """The booked student's username (Student objects keep it in getUsername())."""
    student = getattr(booking, 'student', None)
    if student is None:
        return None
    return student.getUsername() if hasattr(student, 'getUsername') else getattr(student, 'username', None)


def _bookingTime(booking):
    """Booking/booking.py keeps the time behind getBookingDateTime()."""
    if hasattr(booking, 'getBookingDateTime'):
        return booking.getBookingDateTime()
    return getattr(booking, 'bookingDateTime', None)


class Trainer(ActiveUser):
    def __init__(self, username: str, idNum: int):
        super().__init__(username, idNum)

        self.__availabilityTimes = []
        self.__specialisations = []
        self.__clientList = {}
        

    def viewClientele(self) -> list:
        return list(self.__clientList.keys())
        #to view names and booking times
        # return self.__clientList
    
    def setAvailability(self, availabilityTimes) -> bool:
        if availabilityTimes is not None:
            self.__availabilityTimes = availabilityTimes
            return True
        return False

    def getAvailability(self):
        return self.__availabilityTimes


    def setSpecialisations(self, specialisations) -> bool:
        if specialisations is None:
            print("Error: Specialisations cannot be empty.")
            return False
            
        if isinstance(specialisations, str):
            clean_list = []
            for item in specialisations.split(","):
                clean_list.append(item.strip())
            specialisations = clean_list

        if not isinstance(specialisations, list):
            print("Error: Invalid format. Please provide a list or a comma-separated statament.")
            return False
            
        self.__specialisations = specialisations
        return True    

    def getSpecialisations(self):
        return self.__specialisations

    ##booking related methods##

    def acceptBooking(self, booking) -> bool:
        if booking is None:
            return False

        booking.setStatus("Accepted")

        username = _clientName(booking)
        booking_time = _bookingTime(booking)

        if username is not None and booking_time is not None:
            if username not in self.__clientList:
                self.__clientList[username] = []
            self.__clientList[username].append(booking_time)
        return True

    def rejectBooking(self, booking) -> bool:
        if booking is None:
            return False
        
        booking.setStatus("Declined")
                  
        return True

    def cancelBooking(self, booking) -> bool:
        if booking is None:
            return False
        booking.setStatus("Cancelled")

        username = _clientName(booking)
        booking_time = _bookingTime(booking)

        if username is not None and booking_time is not None:
            if username in self.__clientList:
                if booking_time in self.__clientList[username]:
                    self.__clientList[username].remove(booking_time)
                
                if len(self.__clientList[username]) == 0:
                    del self.__clientList[username]

        return True

    def editBooking(self, booking, new_booking_time) -> bool:
        if booking is None:
            return False

        username = _clientName(booking)
        old_time = _bookingTime(booking)

        if username is not None and old_time is not None:
            if username in self.__clientList and old_time in self.__clientList[username]:
                self.__clientList[username].remove(old_time)
                
            if username not in self.__clientList:
                self.__clientList[username] = []
            self.__clientList[username].append(new_booking_time)

        booking.setStatus("Accepted")
        booking.setBookingDateTime(new_booking_time) 

        return True

    def assignRoutine(self, routine, stu) -> bool:
        if routine is None or stu is None:
            return False

        # Ensure the student is in this trainer's client list
        if stu.getUsername() not in self.__clientList:
            return False

        # Prevent assigning a duplicate routine the student already has
        if any(str(r.getRoutineId()) == str(routine.getRoutineId()) for r in stu._routine_list):
            return False

        return stu.adoptRoutine(routine)

    def get_upcoming_reminders(self, current_time: datetime) -> list:
        """Scenario 2.11 / AC-02.5: confirmed sessions starting within the next hour."""
        reminders = []
        for username, times in self.__clientList.items():
            for session_time in times:
                if current_time < session_time <= current_time + timedelta(hours=1):
                    reminders.append({"student": username, "session_time": session_time})
        return sorted(reminders, key=lambda r: r["session_time"])

