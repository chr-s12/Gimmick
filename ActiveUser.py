from Routine import Routine
from Exercise import Exercise
from pathlib import Path
import json

users_file_path = Path("users.json")


class ActiveUser:
    def __init__(self, username: str, idnum: str):
        self._username = username
        self._idnum = idnum
        self._routine_list: list[Routine] = []

    def buildRoutine(self,routineName: str,exercises: list[Exercise],isPublic: bool = False) -> Routine:
        if not exercises:
            raise ValueError("Cannot build a routine with no exercises.")
        new_routine = Routine(routineName, exercises, isPublic)
        new_routine.saveRoutine()
        self._routine_list.append(new_routine)
        self.userSave()
        return new_routine

    def editRoutine(self,routine: Routine,routineName: str | None = None,isPublic: bool | None = None,exercises_add: list[Exercise] | None = None,exercises_remove: list[Exercise] | None = None) -> bool:
        if routine is None:
            return False
        if routineName is not None:
            routine.setRoutineName(routineName)
        if isPublic is not None:
            routine.setIspublic(isPublic)
        if exercises_add is not None:
            for exer in exercises_add:
                routine.addExer(exer)
        if exercises_remove is not None:
            for exer in exercises_remove:
                routine.remExer(exer)
        return routine.saveRoutine()

    def toDict(self) -> dict:
        return {
            "ID Number": self._idnum,
            "Username": self._username,
            "Routine List": [routine.getRoutineId() for routine in self._routine_list]
        }

    def deleteRoutine(self, routine: Routine) -> bool:
        if routine is None:
            return False
        if routine in self._routine_list:
            self._routine_list.remove(routine)

        deleted = routine.deleteFromFile()
        if deleted:
            self.userSave()
        return deleted

    def logWorkout(self, routine: Routine) -> None:
        pass

    def userSave(self, user: 'ActiveUser | None' = None) -> bool:
        target_user = user if user is not None else self
        if target_user is None:
            return False

        if users_file_path.exists():
            with open(users_file_path, "r") as f:
                try:
                    users = json.load(f)
                except json.JSONDecodeError:
                    users = []
        else:
            users = []

        user_data = target_user.toDict()

        for i, existing in enumerate(users):
            if existing.get("ID Number") == user_data["ID Number"]:
                users[i] = user_data
                break
        else:
            users.append(user_data)

        with open(users_file_path, "w") as f:
            json.dump(users, f, indent=4)
        return True