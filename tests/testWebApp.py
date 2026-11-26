"""End-to-end tests of the whole app through its pages (Flask test client, temporary data folder)."""
import json
import re
from datetime import datetime, timedelta

import pytest

from accounts import buildAccountService
from app import create_app
from occupancyTrends.models import Direction, EntryExitEvent
from occupancyTrends.repositories import EntryExitRepository

MONDAY_9AM = datetime(2026, 11, 30, 9, 0)
STUDENT, STUDENT2, TRAINER, STAFF, OPERATOR = "620100001", "620100002", "700000001", "100000001", "100000002"
PASSWORD = "secret123"


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def site(tmp_path):
    clock = Clock(MONDAY_9AM)
    accounts = buildAccountService(str(tmp_path / "data"), clock)
    accounts.createAccount(STUDENT, "Sam Student", "student", PASSWORD, workoutSharing=False)
    accounts.createAccount(STUDENT2, "Tia Student", "student", PASSWORD, workoutSharing=False)
    accounts.createAccount(TRAINER, "Jo Trainer", "trainer", PASSWORD, specialisations=["Strength"], bio="Coach")
    accounts.createAccount(STAFF, "Front Desk", "staff", PASSWORD)
    accounts.createAccount(OPERATOR, "Gym Operator", "operator", PASSWORD)
    app = create_app({"TESTING": True, "DATA_DIR": str(tmp_path / "data"), "LOG_DIR": str(tmp_path / "logs"),
                      "CLOCK": clock, "SECRET_KEY": "test"})
    return app, clock, tmp_path / "data"


def login(app, uwiId):
    client = app.test_client()
    response = client.post("/login", data={"uwiId": uwiId, "password": PASSWORD})
    assert response.status_code == 302, response.data
    return client


def page(client, url, **kwargs):
    response = client.get(url, **kwargs)
    assert response.status_code == 200, (url, response.status_code)
    return response.get_data(as_text=True)


def follow(client, url, data=None):
    response = client.post(url, data=data or {}, follow_redirects=True)
    assert response.status_code == 200, (url, response.status_code)
    return response.get_data(as_text=True)


# ---- login, roles, timeout (SRS 3.2.2) ----------------------------------------------------------------

def test_pagesNeedLogin(site):
    app, _, _ = site
    client = app.test_client()
    response = client.get("/routines/")
    assert response.status_code == 302 and response.location.startswith("/login?next=/routines/")
    assert "UWI ID number" in page(client, "/login")


def test_signUpLogsTheNewStudentIn(site):
    app, _, _ = site
    client = app.test_client()
    html = follow(client, "/signup", {"name": "New Person", "uwiId": "620100099", "role": "student",
                                      "password": "fresh1234", "confirm": "fresh1234"})
    assert "Hi, New" in html and "Your account is ready" in html


def test_wrongPasswordShowsAnError(site):
    app, _, _ = site
    response = app.test_client().post("/login", data={"uwiId": STUDENT, "password": "nope"})
    assert response.status_code == 401 and b"attempts left" in response.data


@pytest.mark.parametrize("uwiId, url", [
    (STUDENT, "/schedule/"), (STUDENT, "/clients/"), (STUDENT, "/reports/"), (STUDENT, "/desk"),
    (TRAINER, "/progress/"), (TRAINER, "/trainers"), (TRAINER, "/reports/"),
    (STAFF, "/routines/"), (STAFF, "/reports/"), (STAFF, "/occupancy"),
    (OPERATOR, "/desk"), (OPERATOR, "/clients/"),
])
def test_eachRoleOnlyReachesItsOwnPages(site, uwiId, url):
    app, _, _ = site
    assert login(app, uwiId).get(url).status_code == 403


def test_homeSendsEachRoleToItsMainPage(site):
    app, _, _ = site
    for uwiId, target in ((TRAINER, "/schedule/"), (STAFF, "/desk"), (OPERATOR, "/reports/")):
        assert login(app, uwiId).get("/").location == target


def test_logoutAfter15MinutesWithoutActivity(site):
    app, clock, _ = site
    client = login(app, STUDENT)
    page(client, "/")
    clock.now += timedelta(minutes=14)
    page(client, "/")
    clock.now += timedelta(minutes=16)
    response = client.get("/")
    assert response.status_code == 302 and response.location.startswith("/login")


def test_occupancyRefreshesDontCountAsActivity(site):
    app, clock, _ = site
    client = login(app, STUDENT)
    page(client, "/occupancy")
    for _ in range(4):   # the page refreshes itself; nobody touches it for 16 minutes
        clock.now += timedelta(minutes=4)
        client.get("/occupancy/status.json")
    assert client.get("/occupancy").status_code == 302


def test_staffResetsAPassword(site):
    app, _, _ = site
    html = follow(login(app, STAFF), "/staff/reset-password", {"uwiId": STUDENT, "password": "brandnew12"})
    assert "Password reset for Sam Student" in html
    assert app.test_client().post("/login", data={"uwiId": STUDENT, "password": "brandnew12"}).status_code == 302


# ---- Feature 1: routines ------------------------------------------------------------------------------

ROUTINE = {"routine_name": "Push day", "excer_name": ["Bench Press", "Dips", ""], "num_sets": ["3", "3", ""],
           "num_reps": ["8", "10", ""], "rest_time": ["90", "60", ""], "weight_kg": ["40", "", ""]}


def routineIds(dataDir, uwiId):
    users = json.loads((dataDir / "users.json").read_text())
    return next(u for u in users if u["uwiId"] == uwiId)["routineIds"]


def test_buildEditAndDeleteARoutineWithConfirmation(site):
    app, _, dataDir = site
    client = login(app, STUDENT)
    html = follow(client, "/routines/new", ROUTINE)
    assert "Saved Push day" in html and "Bench Press: 3 &times; 8 @ 40 kg" in html
    routineId = routineIds(dataDir, STUDENT)[0]
    assert 'value="Bench Press"' in page(client, f"/routines/{routineId}/edit")
    halfCleared = dict(ROUTINE, excer_name=["Bench Press", "", ""])   # Dips' numbers left without a name
    assert client.post(f"/routines/{routineId}/edit", data=halfCleared).status_code == 400
    edited = dict(ROUTINE, routine_name="Push day v2", excer_name=["Bench Press", "", ""],
                  num_sets=["3", "", ""], num_reps=["8", "", ""], rest_time=["90", "", ""])
    html = follow(client, f"/routines/{routineId}/edit", edited)
    assert "Push day v2" in html and "Dips" not in html
    assert "Yes, delete it" in page(client, f"/routines/{routineId}/delete")
    assert routineIds(dataDir, STUDENT) == [routineId]      # nothing deleted until confirmed
    assert "Deleted Push day v2" in follow(client, f"/routines/{routineId}/delete")
    assert routineIds(dataDir, STUDENT) == []


def test_invalidRoutineIsNotSavedAndKeepsTheInput(site):
    app, _, dataDir = site
    client = login(app, STUDENT)
    response = client.post("/routines/new", data=dict(ROUTINE, num_sets=["-2", "3", ""]))
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert "Sets for Bench Press must be at least 1" in html and 'value="Push day"' in html
    assert routineIds(dataDir, STUDENT) == []


def test_studentAdoptsATrainerTemplate(site):
    app, _, dataDir = site
    follow(login(app, TRAINER), "/routines/new", dict(ROUTINE, routine_name="Starter plan", is_public="on"))
    client = login(app, STUDENT)
    templateId = routineIds(dataDir, TRAINER)[0]
    assert "Starter plan" in page(client, "/routines/templates")
    assert "Added Starter plan" in follow(client, f"/routines/templates/{templateId}/adopt")
    assert len(routineIds(dataDir, STUDENT)) == 1 and routineIds(dataDir, STUDENT)[0] != templateId


def test_studentCannotOpenAnotherStudentsRoutine(site):
    app, _, dataDir = site
    follow(login(app, STUDENT), "/routines/new", ROUTINE)
    routineId = routineIds(dataDir, STUDENT)[0]
    other = login(app, STUDENT2)
    assert "That routine isn&#39;t on your profile" in follow(other, f"/routines/{routineId}/delete")
    assert routineIds(dataDir, STUDENT) == [routineId]


# ---- Features 2, 4, 5 and 6 together --------------------------------------------------------------------

def test_bookingToClienteleJourney(site):
    app, clock, dataDir = site
    trainer, student = login(app, TRAINER), login(app, STUDENT)

    # Feature 2: trainer advertises a time
    assert "Students can now book it" in follow(trainer, "/schedule/slots",
                                               {"date": "2026-11-30", "start": "14:00", "end": "15:00"})
    assert "conflicts with your existing slot" in follow(trainer, "/schedule/slots",
                                                         {"date": "2026-11-30", "start": "14:30", "end": "15:30"})

    # Feature 5: student sees the trainer and requests the time
    assert "Jo Trainer" in page(student, "/trainers") and "Strength" in page(student, "/trainers")
    profile = page(student, f"/trainers/{TRAINER}")
    slotId = re.search(r'name="slotId" value="([0-9a-f]+)"', profile).group(1)
    assert "sent to the trainer for confirmation" in follow(student, f"/trainers/{TRAINER}/book", {"slotId": slotId})
    assert "Waiting for trainer" in page(student, "/sessions")

    # Feature 2: trainer accepts
    schedule = page(trainer, "/schedule/")
    assert "Booking requests" in schedule and "Sam Student" in schedule
    bookingId = re.search(r'/schedule/requests/([0-9a-f]+)/accept', schedule).group(1)
    assert "Session confirmed" in follow(trainer, f"/schedule/requests/{bookingId}/accept")
    assert "Confirmed" in page(student, "/sessions")
    assert "Jo Trainer confirmed your session" in page(student, "/notifications")

    # Feature 6: the student is now an active client, but isn't sharing workouts yet
    assert "Sam Student" in page(trainer, "/clients/")
    denied = page(trainer, f"/clients/{STUDENT}")
    assert "has not enabled workout sharing" in denied and "must enable workout sharing" in denied
    follow(student, "/settings", {"workoutSharing": "on"})

    # Feature 4: student logs a workout from their own routine
    follow(student, "/routines/new", ROUTINE)
    routineId = routineIds(dataDir, STUDENT)[0]
    assert 'name="weight_0"' in page(student, f"/progress/log/{routineId}")
    response = student.post(f"/progress/log/{routineId}", data={
        "sets_0": "3", "reps_0": "8", "weight_0": "42.5", "sets_1": "3", "reps_1": "10", "weight_1": "0"})
    assert response.status_code == 303
    assert "Push day" in page(student, "/progress/history")

    # Feature 6: trainer sees the workout and assigns a routine
    profile = page(trainer, f"/clients/{STUDENT}")
    assert "Push day" in profile and "42.5" in profile
    assigned = follow(trainer, f"/clients/{STUDENT}/assign", {
        "routine_name": "Legs", "excer_name": ["Squat"], "num_sets": ["5"], "num_reps": ["5"],
        "rest_time": ["120"], "weight_kg": ["60"]})
    assert "Assigned Legs" in assigned
    home = page(student, "/")
    assert "Trainer-added" in home and "Added by your trainer Jo Trainer" in home
    assert "assigned you a workout: Legs" in page(student, "/notifications")
    assert "Legs (from Jo Trainer)" in page(student, "/progress/")

    # Reminders an hour before (AC-02.5, AC-05.4). Hours later, so both have to log in again.
    clock.now = datetime(2026, 11, 30, 13, 5)
    assert student.get("/notifications").status_code == 302
    trainer, student = login(app, TRAINER), login(app, STUDENT)
    assert "Reminder: your session with Jo Trainer starts at 14:00" in page(student, "/notifications")
    assert "Reminder: your session with Sam Student starts at 14:00" in page(trainer, "/notifications")

    # Feature 5: student cancels with confirmation; trainer is told
    assert "Yes, cancel it" in page(student, f"/sessions/{bookingId}/cancel")
    assert "Cancelled. Your trainer has been told." in follow(student, f"/sessions/{bookingId}/cancel")
    assert "Sam Student cancelled their session" in page(trainer, "/notifications")
    assert "You have no active clients" in page(trainer, "/clients/")


def test_trainerCancelNeedsConfirmation(site):
    app, _, dataDir = site
    trainer, student = login(app, TRAINER), login(app, STUDENT)
    follow(trainer, "/schedule/slots", {"date": "2026-11-30", "start": "14:00", "end": "15:00"})
    slotId = re.search(r'name="slotId" value="([0-9a-f]+)"', page(student, f"/trainers/{TRAINER}")).group(1)
    follow(student, f"/trainers/{TRAINER}/book", {"slotId": slotId})
    bookingId = re.search(r'/schedule/requests/([0-9a-f]+)/accept', page(trainer, "/schedule/")).group(1)
    follow(trainer, f"/schedule/requests/{bookingId}/accept")
    assert "Yes, cancel it" in page(trainer, f"/schedule/sessions/{bookingId}/cancel")
    assert "Confirmed" in page(student, "/sessions")   # only looking at the page changes nothing
    follow(trainer, f"/schedule/sessions/{bookingId}/cancel")
    assert "Jo Trainer cancelled your session" in page(student, "/notifications")


# ---- Feature 3: occupancy -------------------------------------------------------------------------------

def test_frontDeskAndMemberOccupancy(site):
    app, _, _ = site
    staff, student = login(app, STAFF), login(app, STUDENT)
    assert "Checked in. Occupancy: 1/20" in follow(staff, "/desk/check-in", {"uwiId": STUDENT2})
    status = json.loads(page(student, "/occupancy/status.json"))
    assert status["occupancy"] == 1 and status["level"] == "Space available"
    assert STUDENT2 not in json.dumps(status) and "Tia" not in json.dumps(status)   # counts only
    assert "has space" in follow(student, "/occupancy/request")
    desk = json.loads(page(staff, "/desk/status.json"))
    assert desk["inside"][0]["name"] == "Tia Student"
    assert "Checked out" in follow(staff, "/desk/check-out", {"uwiId": STUDENT2})


# ---- Feature 7: reports -----------------------------------------------------------------------------------

def test_operatorReportChartsAndCsv(site):
    app, _, dataDir = site
    events = EntryExitRepository(str(dataDir))
    for day in (16, 17, 23, 24):
        for i in range(3):
            t = datetime(2026, 11, day, 17, 10 * i)
            events.add(EntryExitEvent(f"6201{i:05d}", Direction.IN, t, STAFF),
                       EntryExitEvent(f"6201{i:05d}", Direction.OUT, t + timedelta(minutes=50), STAFF))
    operator = login(app, OPERATOR)
    html = page(operator, "/reports/?start=2026-11-16&end=2026-11-29")
    assert "Total visits" in html and "<svg" in html and "17:00-18:00" in html
    assert "6201" not in html                     # no member IDs in the report
    csv = operator.get("/reports/export.csv?start=2026-11-16&end=2026-11-29")
    assert csv.mimetype == "text/csv" and b"Total visits,12" in csv.data
    chart = operator.get("/reports/chart/hourly.svg?start=2026-11-16&end=2026-11-29")
    assert chart.mimetype == "image/svg+xml" and "attachment" in chart.headers["Content-Disposition"]
    assert "the end date is before the start date" in page(operator, "/reports/?start=2026-11-29&end=2026-11-16")
    assert "no attendance data" in page(operator, "/reports/?start=2026-10-01&end=2026-10-07")


def test_operatorDownloadsABackup(site):
    app, _, _ = site
    response = login(app, OPERATOR).get("/admin/backup")
    assert response.mimetype == "application/zip" and response.data[:2] == b"PK"
