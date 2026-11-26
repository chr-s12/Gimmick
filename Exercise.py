class Exercise:
    COMMON_EXERCISES = [
        "Bench Press",
        "Incline Dumbbell Press",
        "Overhead Press",
        "Dips",
        "Pull-Ups",
        "Lat Pulldown",
        "Barbell Row",
        "Chest-Supported Row",
        "Squat",
        "Romanian Deadlift",
        "Deadlift",
        "Leg Press",
        "Lunges",
        "Bicep Curl",
        "Tricep Pushdown",
        "Plank",
    ]

    def __init__(
        self,
        excer_name: str,
        num_sets: int,
        num_reps: int,
        rest_time: int,
        weight_kg: float,
        is_complete: bool = False,
        is_custom: bool | None = None,
    ):
        clean_name = excer_name.strip()
        if not clean_name:
            raise ValueError("Exercise name cannot be empty.")

        # Private attributes
        self._excerName = clean_name
        self._numSets = num_sets
        self._numReps = num_reps
        self._restTime = rest_time
        self._isComplete = is_complete
        self._weightKG = weight_kg
        self._isCustom = (
            is_custom
            if is_custom is not None
            else clean_name.lower() not in {e.lower() for e in self.COMMON_EXERCISES}
        )

    @classmethod
    def getCommonExercises(cls) -> list[str]:
        return list(cls.COMMON_EXERCISES)

    @classmethod
    def createCustom(
        cls,
        excer_name: str,
        num_sets: int,
        num_reps: int,
        rest_time: int,
        weight_kg: float,
        is_complete: bool = False,
    ) -> "Exercise":
        return cls(
            excer_name=excer_name,
            num_sets=num_sets,
            num_reps=num_reps,
            rest_time=rest_time,
            weight_kg=weight_kg,
            is_complete=is_complete,
            is_custom=True,
        )

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

    def getWeightKG(self) -> float:
        return self._weightKG

    def getIsCustom(self) -> bool:
        return self._isCustom

    # Setters
    def setExcerName(self, excer_name: str) -> None:
        clean_name = excer_name.strip()
        if not clean_name:
            raise ValueError("Exercise name cannot be empty.")
        self._excerName = clean_name
        self._isCustom = clean_name.lower() not in {e.lower() for e in self.COMMON_EXERCISES}

    def setNumSets(self, num_sets: int) -> None:
        self._numSets = num_sets

    def setNumReps(self, num_reps: int) -> None:
        self._numReps = num_reps

    def setRestTime(self, rest_time: int) -> None:
        self._restTime = rest_time

    def setIsComplete(self, is_complete: bool) -> None:
        self._isComplete = is_complete

    def setWeightKG(self, weight_kg: float) -> None:
        self._weightKG = weight_kg

    def to_dict(self) -> dict:
        return {
            "excerName": self._excerName,
            "numSets": self._numSets,
            "numReps": self._numReps,
            "restTime": self._restTime,
            "isComplete": self._isComplete,
            "weightKG": self._weightKG,
            "isCustom": self._isCustom,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Exercise":
        return cls(
            excer_name=data["excerName"],
            num_sets=data["numSets"],
            num_reps=data["numReps"],
            rest_time=data["restTime"],
            weight_kg=data["weightKG"],
            is_complete=data.get("isComplete", False),
            is_custom=data.get("isCustom"),
        )
