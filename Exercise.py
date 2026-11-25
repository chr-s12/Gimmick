
class Exercise:
    def __init__(self, excer_name: str, num_sets: int, num_reps: int, rest_time: int, weight_kg: int, is_complete: bool = False):
        # Private attributes 
        self._excerName = excer_name
        self._numSets = num_sets
        self._numReps = num_reps
        self._restTime = rest_time
        self._isComplete = is_complete
        self._weightKG = weight_kg

    # Getters 
    def getExcerName(self) -> str:
        return self._excerName

    def getNumSets(self) -> int:
        return self._numSets

    def getNumReps(self) -> int:
        return self._numReps

    def getRestTime(self) -> int:
        return self._restTime

    def getIsComplete(self) -> bool:
        return self._isComplete

    def getWeightKG(self) -> int:
        return self._weightKG

    # Setters 
    def setExcerName(self, excer_name: str) -> None:
        self._excerName = excer_name

    def setNumSets(self, num_sets: int) -> None:
        self._numSets = num_sets

    def setNumReps(self, num_reps: int) -> None:
        self._numReps = num_reps

    def setRestTime(self, rest_time: int) -> None:
        self._restTime = rest_time

    def setIsComplete(self, is_complete: bool) -> None:
        self._isComplete = is_complete

    def setWeightKG(self, weight_kg: int) -> None:
        self._weightKG = weight_kg

    def to_dict(self) -> dict:
        return {
            "excerName": self._excerName,
            "numSets": self._numSets,
            "numReps": self._numReps,
            "restTime": self._restTime,
            "isComplete": self._isComplete,
            "weightKG": self._weightKG
        }
    @classmethod
    def from_dict(cls, data: dict) -> 'Exercise':
        return cls(
            excer_name=data["excerName"],
            num_sets=data["numSets"],
            num_reps=data["numReps"],
            rest_time=data["restTime"],
            weight_kg=data["weightKG"],
            is_complete=data.get("isComplete", False)
        )
