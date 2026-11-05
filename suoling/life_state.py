"""life_state: the parts that make a companion feel like it has a life.

Six facets, all derived from stored state plus the clock. No daemon, no
background loop: everything is computed when asked, so restarting the process
does not reset the character's day.

    rhythm    - wakefulness by hour (see rhythm.py)
    presence  - how long since the last exchange
    mood      - the two-dimensional slow variable already in memory.py
    journal   - one short entry per day, written from memory + mood
    growth    - relationship stage from accumulated turns
    calendar  - fixed-date festivals and the 24 solar terms

Deliberately excluded: lunar festivals (Spring Festival, Mid-Autumn). Those
need a lunar calendar; faking them with fixed dates would be wrong.
"""

from __future__ import annotations

import datetime as _dt

from . import rhythm

# Relationship stages by total turns.
STAGES = [
    (0, "初次见面", "还在互相试探。"),
    (12, "认识", "开始记得你说过的事。"),
    (60, "熟悉", "会主动问起你。"),
    (200, "亲近", "不太需要客套了。"),
    (600, "长久", "它记得你说话的方式。"),
]

# Fixed-date festivals: (month, day, name)
FESTIVALS = [
    (1, 1, "元旦"),
    (2, 14, "情人节"),
    (3, 8, "妇女节"),
    (5, 1, "劳动节"),
    (6, 1, "儿童节"),
    (10, 1, "国庆节"),
    (12, 24, "平安夜"),
    (12, 25, "圣诞节"),
    (12, 31, "跨年夜"),
]

# 24 solar terms with their usual Gregorian dates (off by one in some years).
SOLAR_TERMS = [
    (1, 6, "小寒"), (1, 20, "大寒"), (2, 4, "立春"), (2, 19, "雨水"),
    (3, 6, "惊蛰"), (3, 21, "春分"), (4, 5, "清明"), (4, 20, "谷雨"),
    (5, 6, "立夏"), (5, 21, "小满"), (6, 6, "芒种"), (6, 21, "夏至"),
    (7, 7, "小暑"), (7, 23, "大暑"), (8, 8, "立秋"), (8, 23, "处暑"),
    (9, 8, "白露"), (9, 23, "秋分"), (10, 8, "寒露"), (10, 24, "霜降"),
    (11, 8, "立冬"), (11, 22, "小雪"), (12, 7, "大雪"), (12, 22, "冬至"),
]


def _stats(profile: dict) -> dict:
    return ((profile.get("mind") or {}).get("stats") or {})


def turns(profile: dict) -> int:
    s = _stats(profile)
    return int(s.get("turns") or s.get("messages") or 0)


def stage(profile: dict) -> dict:
    n = turns(profile)
    name, note = STAGES[0][1], STAGES[0][2]
    for threshold, label, desc in STAGES:
        if n >= threshold:
            name, note = label, desc
    return {"turns": n, "stage": name, "note": note}


def presence(profile: dict, now: _dt.datetime | None = None) -> dict:
    now = now or _dt.datetime.now()
    last = ((profile.get("mind") or {}).get("last_seen")) or ""
    if not last:
        return {"state": "新认识", "gap": "", "minutes": None}
    try:
        then = _dt.datetime.fromisoformat(last)
    except ValueError:
        return {"state": "新认识", "gap": "", "minutes": None}
    # Stored timestamps may carry an offset; compare on the same footing.
    if then.tzinfo is not None:
        then = then.replace(tzinfo=None)
    if now.tzinfo is not None:
        now = now.replace(tzinfo=None)
    mins = max(0, int((now - then).total_seconds() // 60))
    if mins < 3:
        return {"state": "在", "gap": "刚刚", "minutes": mins}
    if mins < 60:
        return {"state": "刚离开", "gap": "%d 分钟前" % mins, "minutes": mins}
    if mins < 60 * 24:
        return {"state": "有一会儿了", "gap": "%d 小时前" % (mins // 60), "minutes": mins}
    return {"state": "很久没见", "gap": "%d 天前" % (mins // 1440), "minutes": mins}


def calendar(now: _dt.datetime | None = None) -> dict:
    now = now or _dt.datetime.now()
    for m, d, name in FESTIVALS:
        if (now.month, now.day) == (m, d):
            return {"kind": "festival", "name": name, "today": True}
    for m, d, name in SOLAR_TERMS:
        if (now.month, now.day) == (m, d):
            return {"kind": "term", "name": name, "today": True}
    # Next upcoming solar term within a week.
    for m, d, name in SOLAR_TERMS:
        try:
            when = now.replace(month=m, day=d, hour=0, minute=0, second=0, microsecond=0)
        except ValueError:
            continue
        if when > now and (when - now).days <= 7:
            return {"kind": "term", "name": name, "today": False, "in_days": (when - now).days}
    return {"kind": "", "name": "", "today": False}


def journal_entry(profile: dict, now: _dt.datetime | None = None) -> str:
    """One human-sized line describing the day so far."""
    now = now or _dt.datetime.now()
    st = rhythm.state(now)
    mood = ((profile.get("mind") or {}).get("mood") or {}).get("label") or "说不上来"
    mems = ((profile.get("mind") or {}).get("memories") or [])
    latest = mems[-1].get("text", "")[:24] if mems else ""
    bits = ["%d 月 %d 日，%s。" % (now.month, now.day, st["line"])]
    bits.append("心情是%s。" % mood)
    if latest:
        bits.append("我还记着：%s…" % latest)
    return "".join(bits)


def touch(profile: dict, now: _dt.datetime | None = None) -> None:
    """Call after each exchange: update last_seen and write the daily journal entry."""
    now = now or _dt.datetime.now()
    mind = profile.setdefault("mind", {})
    mind["last_seen"] = now.isoformat(timespec="seconds")
    day = now.strftime("%Y-%m-%d")
    journal = mind.setdefault("journal", [])
    if not journal or journal[-1].get("date") != day:
        journal.append({"date": day, "text": journal_entry(profile, now)})
        if len(journal) > 60:
            del journal[:-60]


def summary(profile: dict, now: _dt.datetime | None = None) -> dict:
    now = now or _dt.datetime.now()
    return {
        "rhythm": rhythm.state(now),
        "presence": presence(profile, now),
        "stage": stage(profile),
        "calendar": calendar(now),
        "mood": ((profile.get("mind") or {}).get("mood") or {}),
        "journal": ((profile.get("mind") or {}).get("journal") or [])[-1:],
    }


# ---------------------------------------------------------------- growth

# Skills grow with accumulated turns, weighted by the matching trait.
SKILLS = [
    ("listening", "倾听", "empathy"),
    ("noticing", "观察", "sensory"),
    ("keeping", "记事", "order"),
    ("talking", "说话", "creativity"),
    ("steadying", "定心", "stability"),
]


def skills(profile: dict) -> list:
    """Skill levels 0..5 derived from turns and traits; no separate storage."""
    n = turns(profile)
    traits = {t.get("key"): float(t.get("value") or 0) for t in (profile.get("traits") or [])}
    out = []
    for key, zh, trait in SKILLS:
        base = min(5.0, (n / 120.0) * (0.6 + traits.get(trait, 0.5)))
        out.append({"key": key, "name": zh, "level": round(base, 1)})
    return out


def journal_review(profile: dict, days: int = 7) -> dict:
    """Look back at the recent entries instead of only appending new ones."""
    entries = ((profile.get("mind") or {}).get("journal") or [])[-days:]
    if not entries:
        return {"days": 0, "line": "还没有写过日记。", "entries": []}
    moods = [e.get("text", "") for e in entries]
    return {
        "days": len(entries),
        "line": "最近 %d 天，记下了 %d 条。" % (len(entries), len(entries)),
        "entries": entries,
        "first": moods[0][:40] if moods else "",
    }


def letter(profile: dict, now=None) -> str:
    """A short proactive note, written from state rather than a template."""
    now = now or _dt.datetime.now()
    st = rhythm.state(now)
    d = summary(profile, now)
    who = (profile.get("persona") or {}).get("name") or "我"
    parts = []
    parts.append("%s。%s" % (d["calendar"]["name"] + "了。" if d["calendar"].get("today") else st["line"], ""))
    if d["presence"]["state"] in ("有一会儿了", "很久没见"):
        parts.append("你%s没来。" % d["presence"]["gap"])
    if d["stage"]["stage"] not in ("初次见面",):
        parts.append("我们现在算%s。" % d["stage"]["stage"])
    parts.append("我是%s。" % who)
    try:
        from . import records

        back = records.callback_line(str(profile.get("id", "")))
        if back:
            parts.append(back)
    except Exception:  # noqa: BLE001
        pass
    return "".join(parts).replace("。。", "。").strip()
