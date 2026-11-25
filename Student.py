from ActiveUser import *
import copy
class Student(ActiveUser):
    # ... existing booking and analytics methods ...

    def adoptRoutine(self, routine: Routine) -> bool:
        if routine is None or not routine.getIsPublic() or routine in self._routine_list:
            return False

        exer_copy = copy.deepcopy(routine.getExerciseList())
        adoptedRout = Routine(routine.getRoutineName(), exer_copy, is_public=False)

        if not adoptedRout.saveRoutine():
            return False

        self._routine_list.append(adoptedRout)
        return self.userSave()