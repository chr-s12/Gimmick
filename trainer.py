from ActiveUser import ActiveUser
from datetime import datetime

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

        student = getattr(booking, 'student', None)
        booking_time = getattr(booking, 'bookingDateTime', None)

        if student is not None and booking_time is not None:
            if student.username not in self.__clientList:
                self.__clientList[student.username] = []
            self.__clientList[student.username].append(booking_time)
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

        student = getattr(booking, 'student', None)
        booking_time = getattr(booking, 'bookingDateTime', None)

        if student is not None and booking_time is not None:
            username = student.username 
            if username in self.__clientList:
                if booking_time in self.__clientList[username]:
                    self.__clientList[username].remove(booking_time)
                
                if len(self.__clientList[username]) == 0:
                    del self.__clientList[username]

        return True

    def editBooking(self, booking, new_booking_time) -> bool:
        if booking is None:
            return False

        student = getattr(booking, 'student', None)
        old_time = getattr(booking, 'bookingDateTime', None)

        if student is not None and old_time is not None:
            username = student.username
            if username in self.__clientList and old_time in self.__clientList[username]:
                self.__clientList[username].remove(old_time)
                
            if username not in self.__clientList:
                self.__clientList[username] = []
            self.__clientList[username].append(new_booking_time)

        booking.setStatus("Accepted")
        booking.setBookingDateTime(new_booking_time) 

        return True
