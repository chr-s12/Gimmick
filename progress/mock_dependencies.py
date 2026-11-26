
import json
from pathlib import Path


FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def load_fixture(filename):
    file_path = FIXTURES_DIR / filename

    with file_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def get_student(student_id):
    students = load_fixture("students.json")

    for student in students:
        if student["student_id"] == student_id:
            return student

    return None


def get_student_routines(student_id):
    routines = load_fixture("routines.json")

    return [
        routine
        for routine in routines
        if routine["student_id"] == student_id
    ]


def get_student_routine(student_id, routine_id):
    routines = get_student_routines(student_id)

    for routine in routines:
        if routine["routine_id"] == routine_id:
            return routine

    return None
