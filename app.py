"""Gymmick - UWI Gym Routine Planner/Tracker.

Run the prototype (SRS 1.4.1):
    python seedData.py --reset     # demo accounts and data (first time only)
    python app.py                  # then open http://127.0.0.1:5000

Every page goes through the same path (SDS 2.3.1): a Blueprint in controllers/
checks the login and role, then calls one service, which reads and writes the
JSON files in DATA_DIR through its repositories.
"""
import logging
import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for

from accounts import ROLE_LABELS, buildAccountService
from bookTrainers import buildBookingService
from controllers.auth import auth
from controllers.availability import availability
from controllers.booking import booking
from controllers.clients import clients
from controllers.home import home
from controllers.occupancy import occupancy
from controllers.reports import reports
from controllers.routines import routines
from manageAvailability import buildAvailabilityService
from occupancyTrends import buildServices
from occupancyTrends.repositories import NotificationRepository
from progress.repository import WorkoutLogRepository
from progress.routes import progress_bp
from progress.service import ProgressService
from routineBuilder import buildRoutineService
from viewClientele import buildClienteleService

BASE_DIR = Path(__file__).resolve().parent
SESSION_TIMEOUT = timedelta(minutes=15)   # SRS 3.2.2: log out after 15 minutes of inactivity
OPEN_ENDPOINTS = {"auth.login", "auth.signup", "static"}
BLUEPRINT_ROLES = {   # checked on every request (SRS 3.2.2); the services check again
    "routines": ("student", "trainer"), "progress": ("student",), "booking": ("student",),
    "availability": ("trainer",), "clients": ("trainer",), "reports": ("operator",),
}
NAVIGATION = {
    "student": [("home.index", "Home"), ("routines.myRoutines", "My routines"), ("progress.dashboard", "Log workout"),
                ("progress.analytics_dashboard", "My progress"), ("booking.trainers", "Book a trainer"),
                ("booking.sessions", "My sessions"), ("occupancy.member", "Gym occupancy"),
                ("home.settings", "Settings")],
    "trainer": [("availability.schedule", "My schedule"), ("clients.clientList", "My clients"),
                ("routines.myRoutines", "Routines"), ("home.settings", "Trainer profile")],
    "staff": [("occupancy.desk", "Front desk"), ("home.resetPassword", "Reset a password")],
    "operator": [("reports.report", "Usage reports"), ("home.backup", "Download backup")],
}


NAV_PARENT = {"booking.trainer": "booking.trainers", "booking.change": "booking.sessions",
              "booking.cancel": "booking.sessions", "progress.log_workout": "progress.dashboard",
              "progress.workout_summary": "progress.dashboard", "progress.workout_history": "progress.dashboard"}


def _activeNav(endpoint: str, endpoints: list):
    """The one sidebar link to highlight for this page."""
    if endpoint in endpoints:
        return endpoint
    if endpoint in NAV_PARENT:
        return NAV_PARENT[endpoint]
    sameArea = [e for e in endpoints if e.split(".")[0] == endpoint.split(".")[0]]
    return sameArea[0] if len(sameArea) == 1 else None


class ProgressAccounts:
    """Gives Track Progress (progress/) the logged-in student and their real routines."""

    def __init__(self, accounts, routineService):
        self.accounts, self.routines = accounts, routineService

    def current_student_id(self):
        return g.user["uwiId"]

    def get_student(self, student_id):
        user = self.accounts.get(student_id)
        return {"student_id": student_id, "username": user["name"], "role": user["role"]} if user else None

    def get_student_routines(self, student_id):
        return self.routines.progressRoutines(student_id)

    def get_student_routine(self, student_id, routine_id):
        return self.routines.progressRoutine(student_id, routine_id)


def _setUpErrorLog(logDir: str) -> None:
    """System errors and failed logins go to a local text file (SRS 4.3)."""
    os.makedirs(logDir, exist_ok=True)
    path = os.path.abspath(os.path.join(logDir, "gymmick.log"))
    logger = logging.getLogger("gymmick")
    if not any(getattr(h, "baseFilename", None) == path for h in logger.handlers):
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        DATA_DIR=str(BASE_DIR / "data"),
        LOG_DIR=str(BASE_DIR / "logs"),
        CLOCK=datetime.now,
        ENFORCE_GYM_HOURS=os.environ.get("GYMMICK_IGNORE_HOURS") != "1",
        PERMANENT_SESSION_LIFETIME=SESSION_TIMEOUT,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PROGRESS_FIXTURES=False,   # True runs Track Progress on its demo fixtures (used by its own tests)
    )
    if config is not None:
        app.config.update(config)
    dataDir, clock = str(app.config["DATA_DIR"]), app.config["CLOCK"]
    _setUpErrorLog(str(app.config["LOG_DIR"]))

    # ---- services (Business Logic Layer) ----------------------------------------------------------
    accounts = buildAccountService(dataDir, clock)
    occupancyServices = buildServices(dataDir, clock=clock, enforceGymHours=app.config["ENFORCE_GYM_HOURS"])
    routineService = buildRoutineService(dataDir)
    app.extensions["gymmick"] = {
        "accounts": accounts, "routines": routineService,
        "booking": buildBookingService(dataDir, clock), "availability": buildAvailabilityService(dataDir, clock),
        "clientele": buildClienteleService(dataDir, clock),
        "occupancy": occupancyServices["occupancy"], "reports": occupancyServices["reports"],
        "notifications": NotificationRepository(dataDir), "clock": clock,
    }

    # Track Progress (Feature 4) keeps its own service and Blueprint
    storagePath = app.config.get("WORKOUT_STORAGE_PATH") or os.path.join(dataDir, "workoutLogs.json")
    app.extensions["progress_service"] = ProgressService(WorkoutLogRepository(storagePath))
    if not app.config["PROGRESS_FIXTURES"]:
        app.extensions["progress_dependencies"] = ProgressAccounts(accounts, routineService)

    for blueprint in (auth, home, routines, availability, booking, clients, occupancy, reports):
        app.register_blueprint(blueprint)
    app.register_blueprint(progress_bp, url_prefix="/progress")

    # ---- every request: login, inactivity timeout, role, reminders ---------------------------------
    @app.before_request
    def checkLogin():
        g.user = None
        endpoint = request.endpoint or ""
        if endpoint in OPEN_ENDPOINTS or endpoint.endswith(".static"):
            return None
        if app.config["PROGRESS_FIXTURES"] and request.blueprint == "progress":
            return None
        uwiId = session.get("uwiId")
        if not uwiId:
            nextPage = request.full_path if request.method == "GET" and request.path != "/" else ""
            return redirect(url_for("auth.login", next=nextPage.rstrip("?") or None))
        now = clock().timestamp()
        if now - session.get("lastSeen", now) > SESSION_TIMEOUT.total_seconds():
            session.clear()
            flash("You were logged out after 15 minutes without activity. Please log in again.", "info")
            return redirect(url_for("auth.login"))
        user = accounts.get(uwiId)
        if user is None:
            session.clear()
            return redirect(url_for("auth.login"))
        g.user = user
        if not endpoint.endswith("Status"):   # the pages' 5-second refreshes aren't user activity
            session["lastSeen"] = now
        allowed = BLUEPRINT_ROLES.get(request.blueprint)
        if allowed and user["role"] not in allowed:
            abort(403)
        try:   # session reminders are due an hour before (AC-02.5, AC-05.4)
            app.extensions["gymmick"]["booking"].sendDueReminders()
            app.extensions["gymmick"]["availability"].sendDueReminders()
        except Exception:
            logging.getLogger("gymmick").exception("Could not send session reminders")
        return None

    @app.context_processor
    def layout():
        user = g.get("user")
        if not user:
            return {"currentUser": None}
        unread = sum(not n.get("read") for n in app.extensions["gymmick"]["notifications"].listForUser(user["uwiId"]))
        navigation = NAVIGATION.get(user["role"], [])
        return {"currentUser": user, "roleLabel": ROLE_LABELS.get(user["role"], user["role"]),
                "navigation": navigation, "unreadCount": unread,
                "activeNav": _activeNav(request.endpoint or "", [e for e, _ in navigation])}

    @app.template_filter("when")
    def when(value):
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        return value.strftime("%a %d %b %Y, %H:%M")

    @app.errorhandler(403)
    def forbidden(_):
        return render_template("error.html", title="Not allowed",
                               message="Your account doesn't have access to this page."), 403

    @app.errorhandler(404)
    def notFound(_):
        return render_template("error.html", title="Page not found",
                               message="That page doesn't exist."), 404

    @app.errorhandler(500)
    def serverError(error):
        logging.getLogger("gymmick").error("Server error on %s", request.path,
                                           exc_info=getattr(error, "original_exception", None))
        return render_template("error.html", title="Something went wrong",
                               message="The error has been logged. Please try again."), 500

    return app


if __name__ == "__main__":
    create_app().run(debug=os.environ.get("FLASK_DEBUG") == "1")
