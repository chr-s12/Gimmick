"""ClienteleService (SDS 2.3): View Clientele, US-06 (SRS 2.3.6).

A trainer's active clients are students with at least one confirmed session
with that trainer that hasn't finished yet. Trainers only ever see their own
active clients, and only see a client's workouts or assign them routines when
the client has turned on workout sharing (SRS 3.2.2, 4.2).
"""
from collections import defaultdict
from datetime import datetime
from typing import Callable, List

from .models import AssignedExercise, AssignedRoutine
from .repositories import (AssignedRoutineRepository, BookingRepository, NotificationRepository,
                           UserRepository, WorkoutLogRepository)

NO_CLIENTS_MESSAGE = ("You have no active clients. Students appear here once they have an upcoming "
                      "session with you.")


class ClienteleError(Exception):
    """A request that can't be carried out; the message is safe to show the user."""


class AccessDeniedError(ClienteleError):
    pass


class SharingDisabledError(ClienteleError):
    pass


def _sortTime(value: str) -> datetime:
    t = datetime.fromisoformat(value)
    return t.astimezone().replace(tzinfo=None) if t.tzinfo else t


class ClienteleService:
    def __init__(self, users: UserRepository, bookings: BookingRepository, workouts: WorkoutLogRepository,
                 routines: AssignedRoutineRepository, notifications: NotificationRepository,
                 clock: Callable[[], datetime] = datetime.now):
        self.users, self.bookings, self.workouts = users, bookings, workouts
        self.routines, self.notifications, self.clock = routines, notifications, clock

    # ------------------------------------------------------------ access checks
    def _trainer(self, trainerId: str) -> dict:
        """Checked on every call, not just when the page loads (SRS 3.2.2)."""
        user = self.users.get(trainerId)
        if not user or user.get("role") != "trainer":
            raise AccessDeniedError("Only personal trainers can view clients.")
        return user

    def _activeSessions(self, trainerId: str):
        now = self.clock()
        byStudent = defaultdict(list)
        for b in sorted(self.bookings.forTrainer(trainerId), key=lambda b: b.start):
            if b.isUpcoming(now):
                byStudent[b.studentId].append(b)
        return now, byStudent

    def _client(self, trainerId: str, clientId: str):
        trainer = self._trainer(trainerId)
        now, byStudent = self._activeSessions(trainerId)
        client = self.users.get(clientId)
        if clientId not in byStudent or not client or client.get("role") != "student":
            raise AccessDeniedError("This student is not one of your active clients.")
        return trainer, client, byStudent[clientId], now

    # ------------------------------------------------------------ AC-06.0
    def listClients(self, trainerId: str) -> dict:
        """The trainer's active clients. A client in a session right now is listed first (SRS 3.2.2 Priority View)."""
        self._trainer(trainerId)
        now, byStudent = self._activeSessions(trainerId)
        clients = []
        for studentId, sessions in byStudent.items():
            user = self.users.get(studentId)
            if not user or user.get("role") != "student":
                continue
            clients.append({"uwiId": studentId, "name": user["name"],
                            "nextSession": sessions[0].start.isoformat(timespec="minutes"),
                            "upcomingSessions": len(sessions),
                            "inSessionNow": any(s.isInProgress(now) for s in sessions),
                            "workoutSharing": bool(user.get("workoutSharing"))})
        clients.sort(key=lambda c: (not c["inSessionNow"], c["nextSession"], c["name"]))
        return {"clients": clients, "message": None if clients else NO_CLIENTS_MESSAGE}

    # ------------------------------------------------------------ AC-06.2
    def getUpcomingSessions(self, trainerId: str, clientId: str) -> List[dict]:
        """This client's upcoming sessions with this trainer, soonest first."""
        _, _, sessions, now = self._client(trainerId, clientId)
        return [{"start": s.start.isoformat(timespec="minutes"), "end": s.end.isoformat(timespec="minutes"),
                 "inProgress": s.isInProgress(now)} for s in sessions]

    # ------------------------------------------------------------ AC-06.1
    def getClientProfile(self, trainerId: str, clientId: str) -> dict:
        """Client profile. Workouts are only included when the client shares them."""
        trainer, client, _, _ = self._client(trainerId, clientId)
        sharing = bool(client.get("workoutSharing"))
        profile = {"uwiId": clientId, "name": client["name"], "workoutSharing": sharing,
                   "upcomingSessions": self.getUpcomingSessions(trainerId, clientId),
                   "workouts": None, "workoutMessage": None, "assignedRoutines": []}
        if not sharing:
            profile["workoutMessage"] = (f"{client['name']} has not enabled workout sharing, so their "
                                         "workouts can't be shown.")
            return profile
        logs = sorted(self.workouts.forStudent(clientId), key=lambda w: _sortTime(w["completed_at"]), reverse=True)
        profile["workouts"] = [{"routineName": w["routine_name"], "completedAt": w["completed_at"],
                                "exercises": [{"name": e["exercise_name"], "sets": e["sets"], "reps": e["reps"],
                                               "weightKg": e["weight_kg"]} for e in w["exercises"]]}
                               for w in logs]
        if not logs:
            profile["workoutMessage"] = f"{client['name']} hasn't logged any workouts yet."
        profile["assignedRoutines"] = [r.toDict() for r in self.routines.forStudent(clientId)
                                       if r.addedBy == trainer["uwiId"]]
        return profile

    # ------------------------------------------------------------ AC-06.3
    def assignRoutine(self, trainerId: str, clientId: str, routineName: str, exercises: List[dict]) -> dict:
        """Put a routine on the client's profile as trainer-added and notify them."""
        trainer, client, _, now = self._client(trainerId, clientId)
        if not client.get("workoutSharing"):
            raise SharingDisabledError(f"{client['name']} must enable workout sharing before routines can be "
                                       "assigned.")
        name = (routineName or "").strip()
        if not name:
            raise ClienteleError("Give the routine a name.")
        if not exercises:
            raise ClienteleError("Add at least one exercise to the routine.")
        try:
            items = [AssignedExercise.fromInput(e) for e in exercises]
        except ValueError as x:
            raise ClienteleError(str(x)) from None
        routine = AssignedRoutine(name, items, clientId, trainer["uwiId"], trainer["name"], now)
        self.routines.add(routine)
        self.notifications.add(clientId, f"Your trainer {trainer['name']} has assigned you a workout: {name}.", now)
        return routine.toDict()

    # ------------------------------------------------------------ student side
    def getClientRoutines(self, studentId: str) -> List[dict]:
        """Routines trainers added to this student's profile, newest first, labelled as trainer-added."""
        routines = sorted(self.routines.forStudent(studentId), key=lambda r: r.assignedAt, reverse=True)
        return [dict(r.toDict(), label=f"Added by your trainer {r.addedByName}") for r in routines]

    def setWorkoutSharing(self, studentId: str, enabled: bool) -> str:
        """The student's permission for their trainers to see workouts and assign routines."""
        user = self.users.get(studentId)
        if not user or user.get("role") != "student":
            raise ClienteleError("Only students can change workout sharing.")
        self.users.setField(studentId, "workoutSharing", bool(enabled))
        return ("Workout sharing is on: your trainers can see your workouts and assign you routines."
                if enabled else "Workout sharing is off: your trainers can no longer see your workouts.")

    def getNotifications(self, uwiId: str) -> List[dict]:
        return self.notifications.listForUser(uwiId)
