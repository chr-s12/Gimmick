"""GymUsageAnalytics (SDS class diagram) - figures for Feature 7, Analyze Usage Trends.

Totals and averages only: never names or ID numbers (AC-07.4).
"""
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional

from .gymHours import FIRST_OPEN_HOUR, LAST_CLOSE_HOUR, OPENING_HOURS, isOpen
from .models import Direction, EntryExitEvent, EntryStatus, Queue, QueueEntry

# One person out and the next queued student in makes the count dip for a few
# seconds; dips this short are part of the same "full" period.
MERGE_GAP = timedelta(minutes=2)


class GymUsageAnalytics:
    def __init__(self, startDate: date, endDate: date, maxCapacity: int = Queue.MAX_CAPACITY):
        self.startDate, self.endDate, self.maxCapacity = startDate, endDate, maxCapacity
        self.totalVisits = 0
        self.averageWait: Optional[int] = None            # seconds
        self.averageWaitAtCapacity: Optional[int] = None
        self.peakHours: List[int] = []
        self.busiestDays: List[date] = []
        self.visitsPerHour: Dict[int, int] = {}
        self.visitsPerDay: Dict[date, int] = {}
        self.weekly: Dict[date, int] = {}                   # week start (Monday) -> visits
        self.trend: Optional[str] = None                    # rising / falling / steady
        self.capacityPeriods: List[tuple] = []             # (start, end)

    def generateUsageAnalytics(self, events: Iterable[EntryExitEvent],
                                 queueEntries: Iterable[QueueEntry]) -> "GymUsageAnalytics":
        events = sorted((e for e in events if self.startDate <= e.timestamp.date() <= self.endDate),
                        key=lambda e: e.timestamp)
        # A visit is a check-in during opening hours (AC-07.4).
        visits = [e.timestamp for e in events if e.direction == Direction.IN and isOpen(e.timestamp)]
        self.totalVisits = len(visits)
        self.visitsPerHour = {h: 0 for h in range(FIRST_OPEN_HOUR, LAST_CLOSE_HOUR)}
        self.visitsPerDay = {d: 0 for d in self._openDays()}
        for t in visits:
            self.visitsPerHour[t.hour] += 1
            self.visitsPerDay[t.date()] += 1
        self.peakHours = self.calculatePeakHours()
        self.busiestDays = _top(self.visitsPerDay)
        self._weeklyTrend()
        self._capacityPeriods(events)
        self._waits(queueEntries)
        return self

    def calculatePeakHours(self) -> List[int]:
        """The three busiest hours of the day (AC-07.1)."""
        return _top(self.visitsPerHour)

    def getTotalVisits(self) -> int:
        return self.totalVisits

    def getAverageWait(self) -> Optional[int]:
        return self.averageWait

    @property
    def secondsAtCapacity(self) -> int:
        return int(sum((end - start).total_seconds() for start, end in self.capacityPeriods))

    def summary(self) -> dict:
        return {
            "startDate": self.startDate.isoformat(), "endDate": self.endDate.isoformat(),
            "totalVisits": self.totalVisits,
            "peakHours": [hourLabel(h) for h in self.peakHours],
            "busiestDays": [d.isoformat() for d in self.busiestDays],
            "timesAtCapacity": len(self.capacityPeriods),
            "timeAtCapacity": formatDuration(self.secondsAtCapacity),
            "averageWaitAtCapacity": formatDuration(self.averageWaitAtCapacity),
            "averageWait": formatDuration(self.averageWait),
            "trend": self.trend or "Needs at least 2 weeks",
        }

    # ------------------------------------------------------------------
    def _openDays(self) -> List[date]:
        days = (self.startDate + timedelta(days=i) for i in range((self.endDate - self.startDate).days + 1))
        return [d for d in days if OPENING_HOURS[d.weekday()]]

    def _weeklyTrend(self) -> None:
        """Weekly attendance and whether it is rising or falling (needs 2+ weeks)."""
        perDay: Dict[date, List[int]] = {}
        for day, n in self.visitsPerDay.items():
            perDay.setdefault(day - timedelta(days=day.weekday()), []).append(n)
        self.weekly = {week: sum(days) for week, days in sorted(perDay.items())}
        if len(perDay) < 2:
            return
        # Compare visits per open day, so a part-week at either end doesn't skew it.
        averages = [sum(days) / len(days) for _, days in sorted(perDay.items())]
        first, last = averages[0], averages[-1]
        change = (last - first) / first if first else (1 if last else 0)
        self.trend = "rising" if change > 0.05 else "falling" if change < -0.05 else "steady"

    def _capacityPeriods(self, events: List[EntryExitEvent]) -> None:
        """When the gym was at maximum capacity, replaying each day's entries and exits (AC-07.2)."""
        periods, count, day, start, last = [], 0, None, None, None
        for e in events:
            if e.timestamp.date() != day:  # the gym empties overnight
                if start:
                    periods.append([start, last])
                count, day, start = 0, e.timestamp.date(), None
            count = count + 1 if e.direction == Direction.IN else max(0, count - 1)
            if count >= self.maxCapacity and start is None:
                start = e.timestamp
            elif count < self.maxCapacity and start is not None:
                periods.append([start, e.timestamp])
                start = None
            last = e.timestamp
        if start:
            periods.append([start, last])

        merged = []
        for p in periods:
            if merged and p[0].date() == merged[-1][1].date() and p[0] - merged[-1][1] <= MERGE_GAP:
                merged[-1][1] = max(merged[-1][1], p[1])
            else:
                merged.append(p)
        self.capacityPeriods = [tuple(p) for p in merged]

    def _waits(self, queueEntries: Iterable[QueueEntry]) -> None:
        """Average queue wait overall, and while the gym was full (AC-07.2)."""
        waits = [(e.joinTime, e.getTotalWaitTime()) for e in queueEntries
                 if e.status == EntryStatus.ADMITTED and self.startDate <= e.joinTime.date() <= self.endDate]
        self.averageWait = _mean(w for _, w in waits)
        self.averageWaitAtCapacity = _mean(
            w for t, w in waits if any(start <= t <= end for start, end in self.capacityPeriods))


def _top(counts: dict, n: int = 3) -> list:
    return [k for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])) if v > 0][:n]


def _mean(values) -> Optional[int]:
    values = list(values)
    return int(sum(values) / len(values)) if values else None


def hourLabel(hour: int) -> str:
    return f"{hour:02d}:00-{hour + 1:02d}:00"


def formatDuration(seconds: Optional[int]) -> str:
    if seconds is None:
        return "No data"
    hours, minutes = divmod(int(seconds) // 60, 60)
    return f"{hours} h {minutes} min" if hours else f"{minutes} min"
