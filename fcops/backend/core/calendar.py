"""Working calendar (WP3): deadlines count working minutes, not wall time.

Workdays, hours and timezone come from settings (placeholders until the PRD
decision); holidays are rows in ``core.Holiday``. Both functions accept an
explicit ``holidays`` set so they can be tested without a database.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings


def _config():
    start_h, end_h = settings.WORKING_HOURS
    return (ZoneInfo(settings.WORKING_TIMEZONE), set(settings.WORKING_DAYS),
            time(start_h), time(end_h))


def _holidays(holidays):
    if holidays is not None:
        return set(holidays)
    from .models import Holiday
    return set(Holiday.objects.values_list("date", flat=True))


def _window(day, tz, workdays, opens, closes, holidays):
    """The working window on a calendar day, or None."""
    if day.weekday() not in workdays or day in holidays:
        return None
    return (datetime.combine(day, opens, tzinfo=tz),
            datetime.combine(day, closes, tzinfo=tz))


def add_working_minutes(start, minutes, holidays=None):
    """The instant ``minutes`` working minutes after ``start``. A start
    outside working hours counts from the next opening."""
    tz, workdays, opens, closes = _config()
    holidays = _holidays(holidays)
    cursor = start.astimezone(tz)
    remaining = timedelta(minutes=minutes)
    day = cursor.date()
    for _ in range(3660):  # ten years of days: a guard against bad config
        window = _window(day, tz, workdays, opens, closes, holidays)
        if window:
            begin = max(cursor, window[0])
            if begin < window[1]:
                available = window[1] - begin
                if remaining <= available:
                    return begin + remaining
                remaining -= available
        day += timedelta(days=1)
    raise ValueError("No working time found; check WORKING_DAYS and holidays.")


def working_minutes_between(a, b, holidays=None):
    """Working minutes from ``a`` to ``b`` (0 if ``b`` is not after ``a``)."""
    if b <= a:
        return 0
    tz, workdays, opens, closes = _config()
    holidays = _holidays(holidays)
    a, b = a.astimezone(tz), b.astimezone(tz)
    total = timedelta()
    day = a.date()
    while day <= b.date():
        window = _window(day, tz, workdays, opens, closes, holidays)
        if window:
            begin, end = max(a, window[0]), min(b, window[1])
            if end > begin:
                total += end - begin
        day += timedelta(days=1)
    return int(total.total_seconds() // 60)


def is_working_time(at, holidays=None):
    tz, workdays, opens, closes = _config()
    local = at.astimezone(tz)
    window = _window(local.date(), tz, workdays, opens, closes, _holidays(holidays))
    return bool(window and window[0] <= local < window[1])
