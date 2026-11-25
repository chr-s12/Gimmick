"""Demo data: users plus simulated attendance for the past N weeks.

    python seedData.py --reset [--weeks 6] [--data-dir data]

The simulation follows opening hours, the 20-person cap and the queue, so the
usage reports have realistic peaks, full periods and wait times.
"""
import argparse
import heapq
import os
import random
import shutil
from collections import deque
from datetime import date, datetime, timedelta

from occupancyTrends.gymHours import OPENING_HOURS
from occupancyTrends.models import Direction, EntryExitEvent, EntryStatus, Queue, QueueEntry
from occupancyTrends.repositories import EntryExitRepository, QueueRepository, UserRepository

STAFF_ID = "100000001"


def arrivalChance(t: datetime, week: int) -> float:
    """Chance someone arrives in a given minute: busy mornings and evenings, rising slowly."""
    h = t.hour + t.minute / 60
    base = (0.17 if t.weekday() == 5 else 0.26 if 6 <= h < 8.5 else 0.17 if 11.5 <= h < 13.5
            else 0.33 if 17 <= h < 19 else 0.24 if 16 <= h < 20 else 0.08)
    return base * (1 + 0.03 * week)


def simulate(day, openT, closeT, students, rng, week):
    close = datetime.combine(day, closeT)
    events, records, inside, waiting, busy = [], [], [], deque(), set()

    def enter(uid, t):
        events.append(EntryExitEvent(uid, Direction.IN, t, STAFF_ID))
        stay = timedelta(minutes=min(120, max(25, rng.gauss(65, 15))))
        heapq.heappush(inside, (min(t + stay, close), uid))

    def leaveUntil(t):
        while inside and inside[0][0] <= t:
            outT, uid = heapq.heappop(inside)
            events.append(EntryExitEvent(uid, Direction.OUT, outT, STAFF_ID))
            busy.discard(uid)
            while waiting:  # call the next student; 8% miss the 1-minute window
                qid, joined = waiting.popleft()
                entry = QueueEntry(qid, joined, notifiedTime=outT)
                records.append(entry)
                inT = outT + timedelta(seconds=rng.randint(10, 55))
                if rng.random() < 0.08 or inT > close - timedelta(minutes=10):
                    entry.leave(outT + timedelta(seconds=61), EntryStatus.REMOVED, "missedWindow")
                    busy.discard(qid)
                    continue
                entry.leave(inT, EntryStatus.ADMITTED)
                enter(qid, inT)
                break

    t = datetime.combine(day, openT)
    while t < close - timedelta(minutes=30):
        if rng.random() < arrivalChance(t, week):
            leaveUntil(t)
            uid = rng.choice([s for s in students if s not in busy])
            busy.add(uid)
            if len(inside) < Queue.MAX_CAPACITY and not waiting:
                enter(uid, t)
            else:
                waiting.append((uid, t))
        t += timedelta(minutes=1)
    leaveUntil(close)
    for uid, joined in waiting:
        records.append(QueueEntry(uid, joined, status=EntryStatus.REMOVED, leftQueueTime=close,
                                  removalReason="closed"))
    return events, records


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--weeks", type=int, default=6)
    p.add_argument("--data-dir", dest="dataDir", default="data")
    p.add_argument("--reset", action="store_true")
    args = p.parse_args()
    if args.reset:
        shutil.rmtree(args.dataDir, ignore_errors=True)
    if os.path.exists(os.path.join(args.dataDir, "entryExitEvents.json")):
        return print("Data already exists; use --reset to replace it.")

    students = [f"620200{i:03d}" for i in range(1, 121)]
    UserRepository(args.dataDir).saveMany(
        [{"uwiId": STAFF_ID, "name": "Front Desk", "role": "staff"},
         {"uwiId": "100000002", "name": "Gym Operator", "role": "operator"}]
        + [{"uwiId": s, "name": f"Student {s[-3:]}", "role": "student"} for s in students])

    rng, end = random.Random(2140), date.today() - timedelta(days=1)
    start = end - timedelta(weeks=args.weeks) + timedelta(days=1)
    allEvents, allRecords = [], []
    for i in range((end - start).days + 1):
        day = start + timedelta(days=i)
        for openT, closeT in OPENING_HOURS[day.weekday()]:
            ev, rec = simulate(day, openT, closeT, students, rng, i // 7)
            allEvents += ev
            allRecords += rec
    EntryExitRepository(args.dataDir).add(*allEvents)
    QueueRepository(args.dataDir).add(*allRecords)
    print(f"{start} to {end}: {sum(e.direction == Direction.IN for e in allEvents)} visits, "
          f"{len(allRecords)} queue records in {args.dataDir}/")


if __name__ == "__main__":
    main()
