"""后台观测台：跨档案的记忆/心情汇总。

只读聚合，不改档案；所有"遗忘曲线"都是按当前强度外推，不会写入。
"""

from __future__ import annotations

import datetime
import math

from . import memory


def _now() -> datetime.datetime:
    return datetime.datetime.now().astimezone()


def project_retention(mem: dict, days: float, now: datetime.datetime | None = None) -> float:
    """从"现在"起再过 days 天的留存率（不修改记忆）。"""
    now = now or _now()
    last = memory._parse(mem.get("last")) or memory._parse(mem.get("created")) or now
    dt = memory._days_between(last, now) + max(0.0, days)
    return round(max(0.0, min(1.0, math.exp(-dt / memory.stability(mem)))), 4)


def mind_report(profile: dict, now: datetime.datetime | None = None) -> dict:
    now = now or _now()
    mind = profile.get("mind") or {}
    memories = mind.get("memories") or []
    mood = mind.get("mood") or {}
    stats = mind.get("stats") or {}
    live = [m for m in memories if not m.get("faded")]
    rets = [memory.retention(m, now) for m in memories]
    live_rets = [memory.retention(m, now) for m in live]

    buckets = []
    for lo in range(0, 100, 20):
        hi = lo + 20
        n = sum(1 for r in rets if lo / 100 <= r < hi / 100 or (hi == 100 and r >= 0.8))
        buckets.append({"label": "%d–%d%%" % (lo, hi), "count": n})

    days = [0, 1, 3, 7, 14, 30, 60]
    projection = []
    for d in days:
        if live:
            avg = sum(project_retention(m, d, now) for m in live) / len(live)
        else:
            avg = 0.0
        projection.append({"day": d, "retention": round(avg, 4)})

    ranked = sorted(live, key=lambda m: memory.retention(m, now))
    fragile = [{"text": m.get("text", "")[:48], "retention": memory.retention(m, now),
                "kind": m.get("kind"), "last": m.get("last")} for m in ranked[:4]]
    stable = [{"text": m.get("text", "")[:48], "retention": memory.retention(m, now),
               "kind": m.get("kind"), "rehearsals": m.get("rehearsals", 0)}
              for m in reversed(ranked[-4:]) if m not in fragile]

    # 半衰期：平均留存降到 50% 所需天数（从前 30 天曲线插值）
    half_life = None
    if live:
        prev_d, prev_r = 0, projection[0]["retention"]
        for p in projection[1:]:
            if prev_r >= 0.5 >= p["retention"]:
                span = max(1e-6, prev_r - p["retention"])
                half_life = round(prev_d + (prev_r - 0.5) / span * (p["day"] - prev_d), 1)
                break
            prev_d, prev_r = p["day"], p["retention"]

    return {
        "id": profile.get("id"),
        "name": (profile.get("persona") or {}).get("name"),
        "title": (profile.get("persona") or {}).get("title"),
        "archetype": (profile.get("persona") or {}).get("archetype_name"),
        "color": (profile.get("persona") or {}).get("color", "#38e8ff"),
        "created_at": profile.get("created_at"),
        "last_seen": stats.get("last_seen") or stats.get("last_session"),
        "mood": {"label": mood.get("label"), "valence": mood.get("valence"),
                 "arousal": mood.get("arousal"), "baseline": mood.get("baseline")},
        "memories": {
            "count": len(memories),
            "live": len(live),
            "faded": len(memories) - len(live),
            "avg_retention": round(sum(rets) / len(rets), 3) if rets else 0.0,
            "live_retention": round(sum(live_rets) / len(live_rets), 3) if live_rets else 0.0,
            "strong": sum(1 for r in live_rets if r >= 0.5),
        },
        "sessions": int(stats.get("sessions", 0)),
        "messages": int(stats.get("messages", 0)),
        "buckets": buckets,
        "projection": projection,
        "half_life_days": half_life,
        "fragile": fragile,
        "stable": stable,
        "recent_forgotten": [e for e in (mind.get("events") or []) if e.get("type") == "forgot"][-5:],
        "has_face": bool((profile.get("avatar") or {}).get("views")),
        "has_voice": bool((profile.get("voice") or {}).get("metrics")),
    }


def overview(profiles: list[dict], now: datetime.datetime | None = None) -> dict:
    now = now or _now()
    items = [mind_report(p, now) for p in profiles]
    totals = {
        "minds": len(items),
        "memories": sum(i["memories"]["count"] for i in items),
        "live": sum(i["memories"]["live"] for i in items),
        "faded": sum(i["memories"]["faded"] for i in items),
        "sessions": sum(i["sessions"] for i in items),
        "messages": sum(i["messages"] for i in items),
        "avg_retention": round(sum(i["memories"]["avg_retention"] for i in items) / max(1, len(items)), 3),
    }
    return {"ok": True, "generated_at": now.isoformat(timespec="seconds"), "totals": totals, "items": items}
