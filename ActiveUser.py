from Routine import Routine
from Exercise import Exercise
from pathlib import Path
import json
import os

users_file_path = Path("users.json")


class ActiveUser:
    def __init__(self, username: str, idnum: str):
        self._username = username
        self._idnum = idnum
        self._routine_list: list[Routine] = []

    def getUserId(self):
        return self._idnum

    def getIdNum(self):
        return self._idnum

    def getUsername(self):
        return self._username
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
        # Same keys as the shared users.json record that every feature reads (accounts/repositories.py)
        return {
            "uwiId": self._idnum,
            "name": self._username,
            "routineIds": [routine.getRoutineId() for routine in self._routine_list]
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

    def getRoutineById(self, routine_id: str) -> Routine | None:
        for r in self._routine_list:
            if r.getRoutineId() == routine_id:
                return r  
        return None       

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

        for existing in users:
            if _recordId(existing) == user_data["uwiId"]:
                # Keep the fields other features store on the same record (password, role, sharing...)
                for old_key in ("ID Number", "Username", "Routine List"):
                    existing.pop(old_key, None)
                existing.update(user_data)
                break
        else:
            users.append(user_data)

        users_file_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = users_file_path.with_name(users_file_path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2)
        os.replace(tmp, users_file_path)
        return True

    @classmethod
    def loadUser(cls, idnum: str) -> 'ActiveUser | None':
        if not users_file_path.exists():
            return None
        with open(users_file_path, "r", encoding="utf-8") as f:
            try:
                users = json.load(f)
            except json.JSONDecodeError:
                return None

        record = next((u for u in users if _recordId(u) == idnum), None)
        if record is None:
            return None

        user = cls(record.get("name", record.get("Username", "")), _recordId(record))
        all_routines = {r.getRoutineId(): r for r in Routine.loadAllRoutines()}
        for r_id in record.get("routineIds", record.get("Routine List", [])):
            if r_id in all_routines:
                user._routine_list.append(all_routines[r_id])
        return user


def _recordId(record: dict):
    """Records use "uwiId"; ones saved before the shared format used "ID Number"."""
    return record.get("uwiId", record.get("ID Number"))


def setDataDir(data_dir) -> None:
    """Keep users.json in the app's data folder with every other feature's files."""
    global users_file_path
    users_file_path = Path(data_dir) / "users.json"