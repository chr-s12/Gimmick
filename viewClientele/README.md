# View Clientele (US-06)

The logic for Feature 6: trainers can see their active clients and the sessions coming up with each one. When a client has turned on workout sharing, the trainer can also see the client's completed workouts and assign them routines. This package has no web pages or login. The Flask Blueprint calls `ClienteleService`, following the SDS layers: Blueprint → Service → Repository → JSON.

```python
from viewClientele import buildClienteleService, ClienteleError

clientele = buildClienteleService("data")

clientele.listClients("T1")                    # {"clients": [...], "message": None or the empty-state message}
clientele.getClientProfile("T1", "620200001")  # sessions, plus workouts only if the client shares them
clientele.getUpcomingSessions("T1", "620200001")
clientele.assignRoutine("T1", "620200001", "Strength Block",
                        [{"excerName": "Squat", "numSets": 3, "numReps": 8, "restTime": 90, "weightKG": 60}])

clientele.setWorkoutSharing("620200001", True) # the student turns permission on or off
clientele.getClientRoutines("620200001")       # the student's trainer-added routines
clientele.getNotifications("620200001")
```

Every method raises `ClienteleError` with a message that is safe to show on the page:
- `AccessDeniedError` when the user isn't a trainer, or the student isn't one of their active clients.
- `SharingDisabledError` when the trainer tries to assign a routine to a client who doesn't share workouts.

## Rules
- **Active client:** a student with at least one Accepted booking with this trainer that hasn't ended. Pending, declined, cancelled and past sessions don't count. A client whose session is happening now is listed first (SRS 3.2.2, Priority View).
- **Role check on every call:** the service checks the trainer's role itself on every call, as well as the Blueprint (SRS 3.2.2). A trainer can never open another trainer's client.
- **Workout sharing:** the `workoutSharing` flag on the student's record in `users.json`. When it is off, the trainer sees no workouts and can't assign routines (AC-06.1, AC-06.3, SRS 4.2).
- **Assigned routines:**
  - Each one is validated (name, at least one exercise, sets/reps ≥ 1, rest ≥ 0, weight ≥ 0).
  - They are saved to `assignedRoutines.json` in the same shape as `Routine.to_dict()`, marked `trainerAdded`.
  - The client gets an in-app notification.

## Data files (in the shared `data/` folder)
| File | Written by | Record |
|---|---|---|
| `users.json` | shared | `uwiId`, `name`, `role`, `workoutSharing` |
| `bookings.json` | Book Trainers (Feature 5) | `bookingId`, `studentId`, `trainerId`, `start`, `end`, `status` (Pending/Accepted/Declined/Cancelled) |
| `workoutLogs.json` | Workout logging (Feature 4) | the progress feature's `WorkoutLog.to_dict()` |
| `assignedRoutines.json` | this feature | `Routine.to_dict()` + `ownerId`, `trainerAdded`, `addedBy`, `addedByName`, `assignedAt` |
| `notifications.json` | shared | `uwiId`, `message`, `createdAt`, `read` |

Run the tests with `python -m pytest tests/testClientele.py`.
