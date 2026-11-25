from datetime import datetime
from trainer import Trainer

class AvailabilityManager:
    def __init__(self):
        self.__trainers = []

    def add_trainer(self, trainer:Trainer) -> bool:
        if trainer in self.__trainers:
            print("Error: Trainer is already in the system.")
            return False
        self.__trainers.append(trainer)
        return True

    def add_time_slot(self, trainer: Trainer, start_time: datetime, end_time: datetime) -> bool:
        if trainer not in self.__trainers:
            print("Error: Trainer not found in the system.")
            return False

        if end_time <= start_time:
            print("Error: End time must be after start time.")
            return False

        current_availability = trainer.getAvailability()

        # Check for overlapping slots
        for existing_slot in current_availability:
            existing_start = existing_slot['start']
            existing_end = existing_slot['end']
            
            if (start_time < existing_end) and (end_time > existing_start):
                print("Error: Time slot overlaps with existing availability.")
                return False

        current_availability.append({'start': start_time, 'end': end_time})
        trainer.setAvailability(current_availability)
        return True

    def edit_time_slot(self, trainer, old_start: datetime, new_start: datetime, new_end: datetime) -> bool:
        if trainer not in self.__trainers:
            print("Error: Trainer not found in the system.")
            return False

        current_availability = trainer.getAvailability()
        slot_found = False

        # Find the slot to edit
        for slot in current_availability:
            if slot['start'] == old_start:
                slot_found = True
                current_availability.remove(slot) 
                trainer.setAvailability(current_availability)
                
                # Try to add the new time
                success = self.add_time_slot(trainer, new_start, new_end)
                
                # If fail, put old one back
                if not success:
                    current_availability.append(slot)
                    trainer.setAvailability(current_availability)
                    print("Error: Could not edit slot due to overlap or invalid times.")
                    return False
                return True
                
        if not slot_found:
            print("Error: Original time slot not found.")
            return False

    def remove_time_slot(self, trainer, start_time: datetime) -> bool:
        if trainer not in self.__trainers:
            print("Error: Trainer not found in the system.")
            return False

        current_availability = trainer.getAvailability()
        
        for slot in current_availability:
            if slot['start'] == start_time:
                current_availability.remove(slot)
                trainer.setAvailability(current_availability)
                return True
                
        print("Error: Time slot not found.")
        return False

    def block_time(self, trainer: Trainer, start_time: datetime, end_time: datetime) -> bool:
        if trainer not in self.__trainers:
            print("Error: Trainer not found in the system.")
            return False

        if end_time <= start_time:
            print("Error: End time must be after start time.")
            return False

        current_availability = trainer.getAvailability()
        new_availability = []
        slots_removed = 0

        for slot in current_availability:
            if (slot['start'] < end_time) and (slot['end'] > start_time):
                slots_removed += 1
            else:
                new_availability.append(slot)

        if slots_removed == 0:
            print("No time slots were removed. The block time does not overlap with any available slots.")

        trainer.setAvailability(new_availability)
        print(f"Block successful. {slots_removed} available slots were removed.")
        return True

    def get_all_available_trainers(self) -> list:
        if len(self.__trainers) == 0:
            print("Error: No trainers currently in the system.")
            return []

        directory = []
        for trainer in self.__trainers:
            directory.append({
                "trainer_name": trainer._ActiveUser__username, 
                "specialisations": trainer.getSpecialisations(),
                "available_times": trainer.getAvailability()
            })
        return directory



