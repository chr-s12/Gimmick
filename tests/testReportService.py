"""Feature 7 - Analyze Usage Trends acceptance scenarios (SRS 2.3.7)."""
from datetime import date, datetime, timedelta

import pytest

from occupancyTrends import InvalidDateRangeError, NoDataError, ReportService
from occupancyTrends.models import Direction, EntryExitEvent, EntryStatus, QueueEntry

MON = date(2026, 11, 2)


def at(day, hour, minute=0, second=0):
    return datetime(day.year, day.month, day.day, hour, minute, second)


def visit(uid, start):
    return [EntryExitEvent(uid, Direction.IN, start), EntryExitEvent(uid, Direction.OUT, start + timedelta(hours=1))]


def testInvalidRangeAndNoData(reports):
    for start, end in (("2026-11-10", "2026-11-01"), ("bad", "2026-11-01"), ("", "2026-11-01")):
        with pytest.raises(InvalidDateRangeError):
            ReportService.parseDateRange(start, end)
    with pytest.raises(NoDataError):
        reports.generateReport(MON, MON + timedelta(days=6))


def testVisitsPeaksAndOpeningHoursOnly(reports, events):
    for i in range(5):
        events.add(*visit(f"a{i}", at(MON, 17, i)))
    events.add(*visit("b", at(MON, 7)), *visit("c", at(MON + timedelta(days=2), 9)))
    events.add(*visit("x", at(MON, 3)), *visit("y", at(MON + timedelta(days=1), 11)))   # closed times
    a = reports.generateReport(MON, MON + timedelta(days=6))
    assert a.totalVisits == 7
    assert a.peakHours[0] == 17 and a.busiestDays[0] == MON
    assert MON + timedelta(days=6) not in a.visitsPerDay   # Sunday


def testCapacityPeriodsMergeShortDipsAndAverageWait(reports, events, queueRepo):
    start = at(MON, 17)
    evs = [EntryExitEvent(f"p{i}", Direction.IN, start + timedelta(seconds=i)) for i in range(20)]
    t = start + timedelta(minutes=10)
    for i in range(3):   # someone leaves, the queued student enters 40 s later
        evs += [EntryExitEvent(f"p{i}", Direction.OUT, t), EntryExitEvent(f"q{i}", Direction.IN, t + timedelta(seconds=40))]
        t += timedelta(minutes=5)
    evs.append(EntryExitEvent("p10", Direction.OUT, start + timedelta(minutes=60)))
    events.add(*evs)
    q = QueueEntry("w", start + timedelta(minutes=5))
    q.leave(start + timedelta(minutes=10, seconds=40), EntryStatus.ADMITTED)
    queueRepo.add(q)

    a = reports.generateReport(MON, MON)
    assert len(a.capacityPeriods) == 1
    assert a.averageWaitAtCapacity == 340


def testWeeklyTrendRising(reports, events):
    for week, perDay in enumerate([2, 4, 6]):
        for d in range(6):
            day = MON + timedelta(weeks=week, days=d)
            for i in range(perDay):
                events.add(*visit(f"u{week}{d}{i}", at(day, 14, i)))
    a = reports.generateReport(MON, MON + timedelta(days=20))
    assert list(a.weekly.values()) == [12, 24, 36] and a.trend == "rising"


def testCsvHasTotalsAndNoIds(reports, events):
    events.add(*visit("620009999", at(MON, 17)))
    text = ReportService.exportCsv(reports.generateReport(MON, MON))
    assert "Total visits,1" in text and "620009999" not in text
