# Gymmick user guide

How to use every feature of the Gymmick prototype, role by role. The screenshots come from a real run of
the app on the demo data (`python seedData.py --reset`), following the same steps as the
[8-minute demo](demoRunSheet.md).

## Start the app

```sh
python -m pip install -r requirements.txt
python seedData.py --reset
python app.py
```

Open http://127.0.0.1:5000 in a browser. Every demo account uses the password `gymmick123`.

| Role | UWI ID | Name |
|---|---|---|
| Student | `620200001` | Alex Brown |
| Personal trainer | `700000001` | Devon Clarke |
| Gym staff | `100000001` | Front Desk |
| Gym operator | `100000002` | Gym Operator |

The front desk only accepts check-ins during gym opening hours. Outside them, start the app with
`GYMMICK_IGNORE_HOURS=1` (PowerShell: `$env:GYMMICK_IGNORE_HOURS="1"; python app.py`).

Each browser keeps one login. To use two roles at once, use two browsers or a normal and a private window.

## Logging in

Sign in with your UWI ID and password. New students and trainers can register with **Register here**.

![Login page](screenshots/01-login.png)

After 5 wrong passwords the account is locked for 15 minutes. If you forget your password, gym staff can
reset it (**Reset a password** on the staff menu). You are logged out after 15 minutes without activity.

![Wrong password warning](screenshots/35-wrong-password.png)

---

## Student

The home page shows the gym's occupancy, your upcoming sessions, your routines and your latest
notifications.

![Student home](screenshots/02-student-home.png)

### Build routines (Feature 1)

1. Go to **My routines** and select **New routine**.
2. Name the routine and fill in a row for each exercise: sets, reps, rest (seconds) and weight (kg).
   Use **+ Add exercise** for more rows. Empty rows are ignored.
3. Tick **Make public** to publish it as a template other students can adopt.
4. Select **Save routine**. Nothing is saved until you do.

![Routine builder](screenshots/03-routine-builder.png)

A routine needs at least one exercise, and negative or blank numbers are refused.

![Empty routine refused](screenshots/04-routine-empty-error.png)

![Routine saved](screenshots/05-routine-saved.png)

To edit or delete a routine, use the buttons beside it on **My routines**. Deleting asks you to confirm.

**Templates:** on **My routines**, select **Browse templates**, then **Add to my routines** on a template. You get your own
copy, which you can edit without changing the original.

![Templates](screenshots/06-templates.png)

![Template adopted](screenshots/07-template-adopted.png)

### Log workouts and track progress (Feature 4)

1. Select **Log workout**, then the routine you did.
2. Enter what you actually completed. The planned values are filled in for you.
3. Select **Save Completed Workout**. A summary of the workout is shown.

![Choose a routine](screenshots/08-progress-routines.png)

![Log a workout](screenshots/09-log-workout.png)

![Workout summary](screenshots/10-workout-summary.png)

**My progress** shows how many days you trained each week, how each exercise is progressing (weight, reps or
volume) and your all-time personal records. Choose a period to filter the charts. Each chart can be
downloaded as an SVG file.

![My progress](screenshots/11-my-progress.png)

### Book a trainer (Feature 5)

1. Select **Book a trainer** to see every trainer, their specialities and their next free time.
2. Open a trainer to see all of their free times, then select **Request this time** on one.
3. The request shows as **Waiting for trainer** on **My sessions** until the trainer answers. You get a
   notification either way, and a reminder an hour before a confirmed session.

![Trainer list](screenshots/12-trainers.png)

![Trainer profile](screenshots/13-trainer-profile.png)

![Request sent](screenshots/14-booking-requested.png)

To move a confirmed session, select **Change time** on **My sessions** and pick another of that trainer's
free times. The session goes back to **Waiting for trainer** until the trainer accepts the new time.
**Cancel** (or **Withdraw** for a request) asks you to confirm, then tells the trainer.

![Change a session](screenshots/15-change-session.png)

![Session changed](screenshots/16-session-changed.png)

### Gym occupancy (Feature 3)

**Gym occupancy** shows how many people are inside, how many are waiting and the estimated wait. It
updates every 5 seconds and never shows names.

![Member occupancy](screenshots/17-member-occupancy.png)

When the gym is full (20 people), select **Request entry** to join the queue. You see your place and
estimated wait.

![Joined the queue](screenshots/28-student-queued.png)

When a space opens and you are first, you are told it's your turn. Check in at the front desk within 1
minute, or your place goes to the next person.

![It's your turn](screenshots/30-student-called.png)

### Settings

In **Settings** a student can turn **workout sharing** on or off. Trainers can only see your workouts or
assign you routines while sharing is on.

---

## Personal trainer

### Manage availability (Feature 2)

**My schedule** shows booking requests, upcoming sessions and the times you've said you're free.

![Trainer schedule](screenshots/18-trainer-schedule.png)

**Add a free time:** under **Add an available time**, pick the date, start and end, then select **Add time**.
Times must be 30 minutes to 3 hours long, in the future and inside gym hours. Times that overlap one you
already have are refused.

![Overlapping time refused](screenshots/19-slot-overlap-refused.png)

![Free time added](screenshots/20-slot-added.png)

Use **Edit** or **Remove** beside a free time to change it. Times that already have a booking can't be
changed.

**Answer requests:** select **Accept** or **Decline**. Accepting a request automatically declines any other
requests for the same time, and the students are told.

![Request accepted](screenshots/21-request-accepted.png)

Use **Move** or **Cancel** beside an upcoming session to change it. Cancelling asks you to confirm. You get
a reminder an hour before each session.

### View clients (Feature 6)

**My clients** lists the students with an upcoming session with you.

![Client list](screenshots/22-client-list.png)

Open a client to see your upcoming sessions with them. If they share their workouts you also see their
completed workouts and can assign them a routine, either a copy of one of yours or a new one built on the
spot.

![Client profile](screenshots/23-client-profile.png)

![Routine assigned](screenshots/24-routine-assigned.png)

The student is notified, and the routine appears on their **My routines** as added by their trainer.

![Routine on the student's list](screenshots/25-student-trainer-routine.png)

**Trainer profile** is where you set your specialities and bio, which students see when booking.

---

## Gym staff

### Front desk (Feature 3)

The **Front desk** shows who is inside, the queue and today's hours. It updates every 5 seconds.

- **Check in:** type the student's UWI ID and select **Check in**. When the gym is full, a walk-in joins the
  queue instead.
- **Check out:** select **Check out** beside the person.
- **Queue:** add someone with **Add to queue** (only while the gym is full) or remove them with **Remove**.

![Front desk](screenshots/26-front-desk.png)

![Gym full](screenshots/27-gym-full.png)

![Queue at the front desk](screenshots/29-desk-queue.png)

While people are waiting, anyone inside for more than an hour is marked **Time up** and asked to leave.

**Reset a password:** enter the student's UWI ID and a new password. This also unlocks a locked account.

---

## Gym operator

### Usage reports (Feature 7)

1. Open **Usage reports**, choose the **From** and **To** dates and select **Generate report**.
2. The report shows total visits, peak hours, busiest days, how often and how long the gym was full, the
   average queue wait, the weekly trend and charts by hour, day and week. It contains totals only, never
   names or UWI IDs.
3. **Save chart** downloads a chart as an SVG file. **Export CSV** downloads the whole report.

![Usage report](screenshots/31-usage-report.png)

Invalid date ranges, and ranges with no attendance data, are refused with a message.

![Invalid date range](screenshots/33-report-invalid-range.png)

**Download backup** saves a zip of all the app's data files.

---

## Access control

Each role can only open its own pages. Opening another role's page says who the page is for.

![Wrong role](screenshots/34-wrong-role.png)
