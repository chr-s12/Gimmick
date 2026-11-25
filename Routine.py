from Exercise import Exercise
import json
import uuid
from pathlib import Path

routine_file_path = Path("routines.json")

class Routine:
    def __init__(self, routine_name: str, exercises: list[Exercise], is_public: bool = False):
        if not exercises:
            raise ValueError("Routines must have at least one exercise present.")
        self._routineId = str(uuid.uuid4())
        self._routineName = routine_name
        self._isPublic = is_public
        self._exerciseList: list[Exercise] = list(exercises)

    def getRoutineId(self) -> str:
        return self._routineId

    def setIspublic(self, isPublic: bool) -> None:
        self._isPublic = isPublic

    def getRoutineName(self) -> str:
        return self._routineName

    def setRoutineName(self, routine_name: str) -> None:
        self._routineName = routine_name

    def addExer(self, exer: Exercise) -> None:
        self._exerciseList.append(exer)

    def remExer(self, exer: Exercise) -> bool:
        if len(self._exerciseList) <= 1:
            return False
        if exer in self._exerciseList:
            self._exerciseList.remove(exer)
            return True
        return False

    def getIsPublic(self) -> bool:
        return self._isPublic

    def getExerciseList(self) -> list[Exercise]:
        return self._exerciseList

    def to_dict(self) -> dict:
        return {
            "routineId": self._routineId,
            "routineName": self._routineName,
            "isPublic": self._isPublic,
            "exercises": [ex.to_dict() for ex in self._exerciseList]
        }

    def saveRoutine(self) -> bool:
        try:
            if routine_file_path.exists():
                with open(routine_file_path, "r") as f:
                    try:
                        routines = json.load(f)
                    except json.JSONDecodeError:
                        routines = []
            else:
                routines = []

            routine_data = self.to_dict()

            for i, existing in enumerate(routines):
                if existing.get("routineId") == self._routineId:
                    routines[i] = routine_data
                    break
            else:
                routines.append(routine_data)

            with open(routine_file_path, "w") as f:
                json.dump(routines, f, indent=4)
            return True
        except OSError:
            return False

    def deleteFromFile(self) -> bool:
        if not routine_file_path.exists():
            return False
        with open(routine_file_path, "r") as f:
            try:
                routines = json.load(f)
            except json.JSONDecodeError:
                return False

        updated_routines = [
            r for r in routines if r.get("routineId") != self._routineId
        ]
        if len(updated_routines) == len(routines):
            return False

        with open(routine_file_path, "w") as f:
            json.dump(updated_routines, f, indent=4)

        return True
    @classmethod
    def from_dict(cls, data: dict) -> 'Routine':
        exercises = [Exercise.from_dict(ex) for ex in data.get("exercises", [])]
        routine = cls(
            routine_name=data["routineName"],
            exercises=exercises,
            is_public=data.get("isPublic", False)
        )
        routine._routineId = data["routineId"]
        return routine

    @classmethod
    def loadAllRoutines(cls) -> list['Routine']:
        if not routine_file_path.exists():
            return []
        with open(routine_file_path, "r") as f:
            try:
                raw = json.load(f)
            except json.JSONDecodeError:
                return []
        return [cls.from_dict(r) for r in raw]

    @classmethod
    def getPublicRoutines(cls) -> list['Routine']:
        return [r for r in cls.loadAllRoutines() if r.getIsPublic()]


            