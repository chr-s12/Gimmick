# Book Trainers (Feature 5, US-05)

Logic and storage for students booking sessions with trainers. There are no pages yet: a Flask Blueprint can call `BookingService` directly.

```python
from bookTrainers import buildBookingService
booking = buildBookingService("data")
```

| SRS | Method | What it does |
|---|---|---|
| AC-05.0, scenario 1 | `listTrainers(studentId)`, `getTrainerProfile(studentId, trainerId)` | Trainers with their specialisations; a trainer's free upcoming times inside gym hours |
| AC-05.1, scenarios 2–3 | `requestBooking(studentId, slotId)` | Sends a Pending request to the trainer and tells the student it was forwarded. A time that is taken, past, outside gym hours or clashes with the student's own sessions is refused and nothing is sent |
| AC-05.2, scenario 4 | `editBooking(studentId, bookingId, newSlotId)` | Asks the trainer to move a confirmed session; the old session stays until the trainer accepts |
| AC-05.3, scenario 5 | `cancelBooking(studentId, bookingId)` | Cancels the session (and any waiting change to it) and notifies the trainer |
| AC-05.4, scenario 6 | `sendDueReminders()` | Reminds the student once, an hour before a confirmed session, with the trainer's name and time. Runs on every student call and on `getNotifications` |
| SRS 3.1.2 | `respondToRequest(trainerId, bookingId, accept)` | For Manage Availability (Feature 2) to call when a trainer accepts or declines |

## Data files

All in the shared data folder:

- `users.json`: trainers may have `specialisations` (list) and `bio`.
- `timeSlots.json`: `{slotId, trainerId, start, end}`, the trainer's free times. Feature 2 writes these.
- `bookings.json`: `{bookingId, studentId, trainerId, start, end, status, slotId, replacesBookingId, studentReminded}`. View Clientele reads the same file.
- `notifications.json`: same format as the other features.

Gym hours come from `occupancyTrends/gymHours.py`.

## Tests

```
python -m pytest tests/testBookTrainers.py
```
