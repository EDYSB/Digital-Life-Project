"""rhythm: a daily life state, so the character is not always "on".

Borrowed from private-companion style bots: the persona has a rhythm derived
from local time (awake / busy / winding down / asleep), and every line it says
is shaded by that state. No scheduling daemon, no background loop: the state is
computed from the clock whenever it is needed.
"""

from __future__ import annotations

import datetime as _dt

# phase -> (wakefulness 0..1, tone hints)
PHASES = {
    "deep_night": (0.15, ["太晚了，你怎么还没睡。", "我有点困了，说话会慢。"]),
    "dawn": (0.45, ["天刚亮。现在很安静。", "早上好。今天想做什么？"]),
    "morning": (0.9, ["上午。脑子最清醒的时候。", "早。今天有一堆事吧。"]),
    "noon": (0.65, ["中午了，吃了吗。", "这个点容易犯困。"]),
    "afternoon": (0.8, ["下午。撑住。", "还有半天。"]),
    "evening": (0.7, ["晚上了。今天过得怎么样？", "天黑了，慢一点。"]),
    "late": (0.4, ["很晚了。", "该收尾了。"]),
}


def _bucket(hour: int) -> str:
    if 0 <= hour < 5:
        return "deep_night"
    if 5 <= hour < 7:
        return "dawn"
    if 7 <= hour < 11:
        return "morning"
    if 11 <= hour < 14:
        return "noon"
    if 14 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 22:
        return "evening"
    return "late"


def state(now: _dt.datetime | None = None) -> dict:
    """Current rhythm state, derived from the clock alone."""
    now = now or _dt.datetime.now()
    phase = _bucket(now.hour)
    wake, lines = PHASES[phase]
    # A slow breathing cycle on top of the phase, so two visits are not identical.
    wave = (now.minute % 10) / 10.0
    return {
        "phase": phase,
        "wakefulness": round(min(1.0, wake * (0.9 + wave * 0.2)), 2),
        "hour": now.hour,
        "minute": now.minute,
        "line": lines[now.minute % len(lines)],
        "should_rest": phase in ("deep_night", "late"),
    }


def greeting(now: _dt.datetime | None = None) -> str:
    s = state(now)
    return "%s。" % s["line"]


def is_working_hours(now: _dt.datetime | None = None) -> bool:
    now = now or _dt.datetime.now()
    return now.weekday() < 5 and 9 <= now.hour < 18
