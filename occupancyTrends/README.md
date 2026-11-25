# Gymmick: Occupancy Monitoring and Usage Trends

This is the business logic and data access code for two features of the UWI Gym Routine Planner/Tracker:

- Feature 3, Occupancy Monitoring (US-03)
- Feature 7, Analyze Usage Trends (US-07)

It contains no pages or routes. The team's Flask Blueprints call these services, as in SDS 2.3.

```
occupancyTrends/
  models.py             Queue, QueueEntry, EntryStatus, Staff (SDS class diagram) + wait-time maths
  analytics.py          GymUsageAnalytics (SDS class diagram)
  occupancyService.py   OccupancyService: headcount, 20-person cap, queue, 1-minute window, 1-hour limit, ETA
  reportService.py      ReportService: date-range reports, CSV export
  repositories.py       Data Access Layer - one JSON file per repository
  gymHours.py           opening hours
tests/                  pytest acceptance tests from the SRS scenarios
seedData.py             demo users + simulated attendance
```

## Usage

```python
from occupancyTrends import buildServices
svc = buildServices("data")
occ, rep = svc["occupancy"], svc["reports"]

occ.recordEntry("620200001", "100000001")     # staff check-in; if the gym is full, a walk-in is queued instead
occ.recordExit("620200001", "100000001")      # next student in the queue is called
occ.requestEntry("620200021")                 # student joins the queue only if the gym is full
occ.getMemberStatus("620200021")              # counts only + own position / ETA / called / time inside
occ.getStaffStatus()                          # counts + queue + who has been asked to leave (for staff)

start, end = rep.parseDateRange("2026-10-01", "2026-11-22")
analytics = rep.generateReport(start, end)    # NoDataError if empty
rep.exportCsv(analytics)
```

Every action returns a message to show. If it is refused (gym full, closed, already queued, ...) it raises `OccupancyError`; show `str(error)` to the user.

Poll `getMemberStatus` / `getStaffStatus` every few seconds. Each call also passes a missed turn on to the next student (SRS 3.2.1.1) and applies the time limit below.

## 1-hour time limit

- A timer starts when someone checks in (`getMemberStatus(id)["you"]["minutesInside"]`).
- While the gym has room, or nobody is waiting, people can stay as long as they like.
- When the gym is full and a student is waiting, the person who has been inside the longest and is past 1 hour gets a notification asking them to leave. One person is asked per waiting student.
- They appear in `getStaffStatus()["askedToLeave"]` so staff can check them out. The system never checks anyone out by itself, because staff log check-outs by hand.

## Tests and demo data

```bash
pip install -r requirements.txt
python -m pytest
python seedData.py --reset
```
