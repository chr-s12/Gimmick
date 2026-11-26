"""ReportService - Feature 7, Analyze Usage Trends (AC-07.0 - AC-07.5)."""
import csv
import io
import re
from datetime import date, datetime, time, timedelta
from typing import Tuple

from .analytics import GymUsageAnalytics, formatDuration, hourLabel


class ReportError(Exception):
    """A report that cannot be produced; the message is shown to the operator."""


class InvalidDateRangeError(ReportError):
    pass


class NoDataError(ReportError):
    pass


class ReportService:
    def __init__(self, events, queueRepo):
        self.events, self.queueRepo = events, queueRepo

    @staticmethod
    def parseDateRange(startText: str, endText: str) -> Tuple[date, date]:
        """Validate the operator's date range (AC-07.5)."""
        try:
            start, end = date.fromisoformat(startText.strip()), date.fromisoformat(endText.strip())
        except (AttributeError, ValueError):
            raise InvalidDateRangeError("Enter both dates as YYYY-MM-DD.")
        if end < start:
            raise InvalidDateRangeError("The date range is invalid: the end date is before the start date.")
        return start, end

    def generateReport(self, start: date, end: date) -> GymUsageAnalytics:
        """Attendance report for a date range (AC-07.0); fails if there is no data (AC-07.5)."""
        if end < start:
            raise InvalidDateRangeError("The date range is invalid: the end date is before the start date.")
        since, until = datetime.combine(start, time.min), datetime.combine(end + timedelta(days=1), time.min)
        analytics = GymUsageAnalytics(start, end).generateUsageAnalytics(
            self.events.listEvents(since, until), self.queueRepo.listEntries(since, until))
        if analytics.totalVisits == 0:
            raise NoDataError(f"There is no attendance data from {start} to {end}.")
        return analytics

    @staticmethod
    def exportCsv(a: GymUsageAnalytics) -> str:
        """CSV of the same figures shown on screen - no names or IDs (AC-07.3, AC-07.4)."""
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["Metric", "Value"])
        for key, value in a.summary().items():
            w.writerow([re.sub(r"(?<!^)([A-Z])", r" \1", key).capitalize(),"; ".join(value) if isinstance(value, list) else value])
        w.writerow([])
        w.writerow(["Hour", "Visits"])
        w.writerows([hourLabel(h), n] for h, n in a.visitsPerHour.items())
        w.writerow([])
        w.writerow(["Date", "Visits"])
        w.writerows([d.isoformat(), n] for d, n in a.visitsPerDay.items())
        w.writerow([])
        w.writerow(["Week starting", "Visits"])
        w.writerows([d.isoformat(), n] for d, n in a.weekly.items())
        w.writerow([])
        w.writerow(["Full from", "Until", "Duration"])
        w.writerows([s.isoformat(sep=" ", timespec="minutes"), e.isoformat(sep=" ", timespec="minutes"),
                     formatDuration((e - s).total_seconds())] for s, e in a.capacityPeriods)
        return out.getvalue()
