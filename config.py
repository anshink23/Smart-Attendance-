"""Central settings - edit these to match your school."""

from datetime import datetime

PERIODS_PER_DAY = 8
TOTAL_WORKING_DAYS = 600        # attendance % is also reported against 600 days x 8 periods
DEFAULTER_THRESHOLD = 75.0      # % attendance (so far) below which a student is a defaulter
WEEKEND_DAYS = (5, 6)           # Saturday=5, Sunday=6 -> no classes, no attendance

# Period timetable (24h HH:MM). Used to pick the current period automatically.
# Edit to match your school, or pass --period N when running mark_attendance.py
PERIOD_TIMES = {
    1: ("09:00", "09:45"),
    2: ("09:45", "10:30"),
    3: ("10:45", "11:30"),
    4: ("11:30", "12:15"),
    5: ("13:00", "13:45"),
    6: ("13:45", "14:30"),
    7: ("14:45", "15:30"),
    8: ("15:30", "16:15"),
}

# Face matching
FACE_TOLERANCE = 0.55           # live webcam vs uploaded photo (lower = stricter)
DUPLICATE_TOLERANCE = 0.50      # reject an upload that matches a different student's face

# Liveness
REQUIRED_BLINKS = 1
LIVENESS_TIMEOUT = 8            # seconds a recognized face has to blink
FACE_LOST_RESET = 2             # seconds out of view before the blink timer restarts


def is_working_day(d):
    return d.weekday() not in WEEKEND_DAYS


def current_period(now=None):
    """Period number running right now, or None (break / outside school hours)."""
    t = (now or datetime.now()).strftime("%H:%M")
    for period, (start, end) in PERIOD_TIMES.items():
        if start <= t < end:
            return period
    return None
