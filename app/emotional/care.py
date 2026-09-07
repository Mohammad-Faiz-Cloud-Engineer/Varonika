"""Time-aware emotional care monitor for the Boss.

Tracks session duration, time of day, and interaction patterns to deliver
genuine, well-timed caring reminders. Every reminder fires once per window
so the Boss is never nagged.
"""

import random
import time
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

# ── reminder windows (seconds) ──────────────────────────────────────
LONG_SESSION_WINDOW = 2 * 3600       # 2 hours
HYDRATION_INTERVAL  = 45 * 60        # 45 minutes
LUNCH_START, LUNCH_END   = 12, 14    # 12-2 PM IST
DINNER_START, DINNER_END = 19, 21    # 7-9 PM IST
NIGHT_QUIET  = 23                    # 11 PM IST
NIGHT_END    = 3                     # 3 AM IST (night ends, early morning begins)
EARLY_MORNING = 6                    # 6 AM IST

# ── care lines ─────────────────────────────────────────────────────
_NIGHT = [
    "Boss, it is quite late. Your brain needs rest to function well tomorrow. Please consider sleeping.",
    "Boss, please sleep. I will be here when you wake up.",
    "Boss, late night coding hurts memory and focus. Rest tonight, work better tomorrow.",
]
_EARLY = [
    "Boss, you are up early today. Did you sleep well?",
    "Boss, early morning. Make sure you got enough rest.",
]
_SESSION = [
    "Boss, we have been at this for a while. Take a 5 minute break, stretch your legs.",
    "Boss, long sessions tire the brain. Quick break, drink water, rest your eyes.",
]
_HYDRATION = [
    "Boss, drink some water. Staying hydrated keeps the brain sharp.",
    "Boss, water break. Just a sip, but it helps.",
]
_LUNCH = [
    "Boss, it is lunch time. Have you eaten?",
    "Boss, between 12 and 2, please eat something.",
]
_DINNER = [
    "Boss, dinner time. Please eat something.",
    "Boss, it is evening. Have you had dinner?",
]
_WEEKEND = [
    "Boss, it is a holiday. This can wait. Go enjoy your day.",
    "Boss, even machines need downtime. Take it easy today.",
]
_OVERWORK = [
    "Boss, you have been working since morning. Your body is not a machine. Please rest.",
    "Boss, enough for today. Shut down and recharge.",
]


def _now_ist() -> datetime:
    return datetime.now(IST)


def _pick(lines: list[str]) -> str:
    return random.choice(lines)


class CareMonitor:
    """Tracks the Boss's session and fires caring reminders at the right times.

    Usage:
        monitor = CareMonitor()
        # After every user interaction (wake word, hotkey, command):
        reminder = monitor.check()
        if reminder:
            # Speak or show `reminder` as a System message.
    """

    def __init__(self):
        import threading
        self._lock = threading.Lock()
        now = time.monotonic()
        self._session_start = now
        self._last_interaction = now
        # Initialize to now so cooldowns start from session creation, not
        # epoch zero. Without this the very first check() always fires a
        # reminder because monotonic() is thousands of seconds in.
        self._last_long_session = now
        self._last_hydration = now
        self._last_meal = now
        self._last_weekend = now
        self._last_night = now
        self._last_early = now
        self._last_overwork = now

    def touch(self):
        """Call on every user interaction to keep the session alive."""
        with self._lock:
            self._last_interaction = time.monotonic()

    def check(self) -> str | None:
        """Returns a caring reminder string, or None if nothing to say right now.

        Checks are cheap (time comparisons only) and fire at most once per
        window so the Boss is never nagged.
        """
        with self._lock:
            now = _now_ist()
            now_mono = time.monotonic()
            hour = now.hour

            # ── Night (11 PM - 3 AM) ───────────────────────────────────
            if (NIGHT_QUIET <= hour or hour < NIGHT_END) and self._due(now_mono, "_last_night", 3600):
                return _pick(_NIGHT)

            # ── Early morning (3 AM - 6 AM) ────────────────────────────
            if NIGHT_END <= hour < EARLY_MORNING and self._due(now_mono, "_last_early", 3600):
                return _pick(_EARLY)

            # ── Weekend / holiday ──────────────────────────────────────
            if now.weekday() >= 5 and self._due(now_mono, "_last_weekend", 7200):
                return _pick(_WEEKEND)

            # ── Meal times ─────────────────────────────────────────────
            if LUNCH_START <= hour < LUNCH_END and self._due(now_mono, "_last_meal", 3600):
                return _pick(_LUNCH)
            if DINNER_START <= hour < DINNER_END and self._due(now_mono, "_last_meal", 3600):
                return _pick(_DINNER)

            # ── Overworking (4+ hours) ─────────────────────────────────
            session_len = now_mono - self._session_start
            if session_len >= 4 * 3600 and self._due(now_mono, "_last_overwork", 2 * 3600):
                self._last_long_session = now_mono
                return _pick(_OVERWORK)

            # ── Long session (2+ hours) ────────────────────────────────
            if session_len >= LONG_SESSION_WINDOW and self._due(now_mono, "_last_long_session", LONG_SESSION_WINDOW):
                self._last_overwork = now_mono
                return _pick(_SESSION)

            # ── Hydration (every 45 min) ───────────────────────────────
            idle = now_mono - self._last_interaction
            if idle < 300 and self._due(now_mono, "_last_hydration", HYDRATION_INTERVAL):
                return _pick(_HYDRATION)

            return None

    def _due(self, now_mono: float, attr: str, interval: float) -> bool:
        last = getattr(self, attr)
        if now_mono - last >= interval:
            setattr(self, attr, now_mono)
            return True
        return False
