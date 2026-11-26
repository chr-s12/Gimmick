"""Resolve dashboard period selections to inclusive Jamaica calendar dates."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


PERIOD_LABELS = {
    "all": "All time",
    "last30": "Last 30 days",
    "last7": "Last 7 days",
    "custom": "Custom date range",
}
_RELATIVE_DAYS = {"last30": 30, "last7": 7}
_JAMAICA = ZoneInfo("America/Jamaica")


class PeriodFilterError(ValueError):
    """A period selection the student can correct."""


def _calendar_date(value: str, label: str) -> date | None:
    if not value:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        parsed = None
    if parsed is None or parsed.isoformat() != value:
        raise PeriodFilterError(f"Enter a valid {label} date in YYYY-MM-DD format.")
    return parsed


def resolve_period(
    period: str, start: str, end: str, as_of: datetime,
) -> tuple[date | None, date | None]:
    """Return the bounds to pass to ProgressService for this request."""
    if period == "all":
        return None, None
    if period in _RELATIVE_DAYS:
        today = as_of.astimezone(_JAMAICA).date()
        return today - timedelta(days=_RELATIVE_DAYS[period] - 1), today
    if period != "custom":
        raise PeriodFilterError("Choose an available period or reset to All time.")

    start_date = _calendar_date(start, "start")
    end_date = _calendar_date(end, "end")
    if start_date is None and end_date is None:
        raise PeriodFilterError("Enter a start date, an end date, or both.")
    if start_date is not None and end_date is not None and start_date > end_date:
        raise PeriodFilterError("The start date must be on or before the end date.")
    return start_date, end_date
