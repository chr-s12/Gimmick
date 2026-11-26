# Gymmick 8-minute demo: run sheet

Every feature in 8 minutes. Times are cumulative. Screenshots of each step are in the
[user guide](userGuide.md). Where the demo uses test plan data, the test case ID is in brackets.

## Before you present (about 10 minutes beforehand)

1. Reset the demo data and fill the gym to 19 people (one short of full):

   ```powershell
   python seedData.py --reset
   python seedData.py --fill-gym
   ```

2. Start the app with gym hours switched off, so the front desk works whatever the time:

   ```powershell
   $env:GYMMICK_IGNORE_HOURS="1"; python app.py
   ```

3. Open four separate windows. Each browser window type keeps its own login:

   | Window | Log in as | UWI ID |
   |---|---|---|
   | Edge | Student (Alex Brown) | `620200001` |
   | Edge InPrivate (Ctrl+Shift+N) | Trainer (Devon Clarke) | `700000001` |
   | Chrome | Gym staff | `100000001` |
   | Chrome Incognito (Ctrl+Shift+N) | Gym operator | `100000002` |

   Every password is `gymmick123`. Go to http://127.0.0.1:5000 in each.

4. Log in no more than 15 minutes before you start; the app logs out after 15 minutes of inactivity.
5. Keep a fifth tab on http://127.0.0.1:5000/login, logged out, for the opening and the security step.

If anything goes wrong mid-demo, stop the app, repeat steps 1 and 2, and log in again.

## The demo

### 0:00 to 0:30: Introduction (login tab)

- "Gymmick runs locally on Python and Flask with JSON files, and works offline."
- Show the login page: "Four roles. Each one only sees its own pages, and passwords are stored as salted
  hashes."

### 0:30 to 2:45: Student (Edge)

1. **Home:** occupancy, upcoming session with Devon Clarke, routines and notifications.
2. **F1, routines:** **My routines** → **New routine**.
   - Type the name `Chest Day` and select **Save routine** with no exercises: "A routine needs at least one
     exercise." (TC-0.1.1)
   - Fill in one row: `Bench Press`, 3 sets, 8 reps, 90 s rest, 100 kg. Tick **Make public** → **Save
     routine**. (TC-0.1.0)
   - **Browse templates** → **Add to my routines** on *Beginner full body*. "Students get their own copy."
3. **F4, progress:** **Log workout** → **My push day**. Change Bench Press weight to `45` → **Save Completed
   Workout**. Then **My Progress** (top bar): weekly consistency, exercise progression, personal records.
   Select a chart's download button to save it as SVG. Select **← Gymmick home** to return.
4. **F5, booking:** **Book a trainer** → **Devon Clarke** → **Request this time** on the first free time.
   It shows **Waiting for trainer**. (TC-05.2)
   - On the confirmed session, **Change time** → pick another time → it goes back to Waiting for trainer.
     (TC-05.4)

### 2:45 to 4:45: Trainer (Edge InPrivate)

1. **F2, availability:** **My schedule** shows the two requests from Alex.
   - Under **Add an available time**, enter the date of one of the **Free** rows with a start and end 30
     minutes later than that row's (for example 06:30 to 07:30 for a 06:00 to 07:00 row) → **Add time**:
     refused for overlapping. (TC-2.4)
   - Enter a free hour on a day with gym hours → **Add time**: added. (TC-2.1)
   - **Accept** Alex's first request: "Session confirmed." Other requests for that time are declined
     automatically. (TC-2.5, TC-2.7)
2. **F6, clients:** **My clients** → **Alex Brown**: the workout Alex logged a minute ago. (TC-0.6.2)
   - Open **Build a new routine for Alex Brown**: name `Strength Block`, row `Squat` 3 × 8, 90 s, 60 kg →
     **Assign routine**. "Alex is notified and it shows on their routines as added by their trainer."
     (TC-0.6.5)

### 4:45 to 6:30: Gym staff (Chrome), with the student window

1. **F3, front desk:** 19 of 20 inside, with names and time inside.
2. Check in `620200050` → **Check in**: the gym is **Full**. (TC-03.03)
3. Switch to the **student** window → **Gym occupancy** → **Request entry**: "Added to the queue at
   position 1" with an estimated wait. Members see counts only, never names. (TC-03.04)
4. Back on the **front desk**, the queue shows Alex. Select **Check out** beside the first person.
5. **Student** window (it updates within 5 seconds; refresh if needed): "It's your turn!" with a countdown
   from 60 seconds to check in. (TC-03.07)
6. Mention: if Alex doesn't check in within a minute, the next person is called (TC-03.08). While people
   are waiting, anyone inside over an hour is marked **Time up** (TC-03.09).

### 6:30 to 7:30: Gym operator (Chrome Incognito)

1. **F7, reports:** **Usage reports**. Set **From** to 4 weeks ago and **To** to yesterday → **Generate
   report**: total visits, peak hours, busiest days, times full and for how long, average queue wait,
   rising or falling trend, charts. "Totals only; no names or IDs." (TC-07.01, TC-07.10)
2. **Save chart** on one chart and **Export CSV**. (TC-07.09)
3. Swap the dates so **To** is before **From** → **Generate report**: refused with a message. (TC-07.11)

### 7:30 to 8:00: Security and close (student window, login tab)

1. In the student window, go to http://127.0.0.1:5000/clients/: "Only personal trainers can view clients.
   This is outside what your account can do." (TC-0.6.7)
2. In the login tab, log in as `620200002` with a wrong password: "4 attempts left before the account is
   locked."
3. Close: "All seven features, role-based access, 15-minute logout, lockout after 5 tries, and 291
   automated tests."

## Mention rather than show

These take real time to happen, so describe them. All are covered by the automated tests.

- Session reminders an hour before, for students and trainers.
- The 1-minute window to check in after being called.
- The 1-hour limit while people are waiting.
- The 15-minute lockout after 5 wrong passwords, and staff password resets.
- The operator's **Download backup**.
