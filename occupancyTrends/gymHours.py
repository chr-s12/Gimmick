"""UWI Gym opening hours (SRS 1.6, Assumption 8). Monday = 0 ... Sunday = 6."""
from datetime import date, datetime, time

OPENING_HOURS = {
    0: [(time(5), time(22))],
    1: [(time(5), time(10)), (time(12, 30), time(22))],
    2: [(time(5), time(22))],
    3: [(time(5), time(22))],
    4: [(time(5), time(10)), (time(12, 30), time(22))],
    5: [(time(10), time(16))],
    6: [],  # closed Sundays
}
FIRST_OPEN_HOUR, LAST_CLOSE_HOUR = 5, 22


def isOpen(moment: datetime) -> bool:
    """True if the gym is open at this date and time."""
    todaysHours = OPENING_HOURS[moment.weekday()]
    for opens, closes in todaysHours:
        if opens <= moment.time() < closes:
            return True
    return False


def hoursText(day: date) -> str:
    """The day's opening hours as text, e.g. "05:00-10:00, 12:30-22:00"."""
    todaysHours = OPENING_HOURS[day.weekday()]
    if not todaysHours:
        return "Closed"
    parts = []
    for opens, closes in todaysHours:
        parts.append(opens.strftime("%H:%M") + "-" + closes.strftime("%H:%M"))
    return ", ".join(parts)
