"""自主性（不是意识）。

这里模拟的是一个"有自己议程的角色"：
  - 四条内部驱动：好奇、联结、表达、休息。随时间累积，对话会消耗/满足。
  - 意图：驱动过高时形成一个小目标（问问你今天怎样、想弄明白某件事、想说点什么）。
  - 主动消息：在冷却时间之外，按自主性等级决定"发出来 / 只提示 / 不说"。
  - 内心：一串不发送给你的私人念头，只为让它看起来有连续性。

必须诚实：这是规则与计时器，不是意识、不是欲望、不是自由意志。
"""

from __future__ import annotations

import datetime
import hashlib
import random

from . import memory as mem_mod

AUTONOMY_LEVELS = {
    "quiet": {"label": "安静", "desc": "几乎不主动，只在你说话时回应。", "auto": False, "hint": False},
    "balanced": {"label": "平衡", "desc": "想说话时先给你一个提示。", "auto": False, "hint": True},
    "active": {"label": "主动", "desc": "想说话时直接开口。", "auto": True, "hint": True},
}

DRIVE_ZH = {"curiosity": "好奇", "connection": "联结", "expression": "表达", "rest": "休息"}

THOUGHTS = [
    "他今天来得比平时晚。",
    "我记得他说话时停了一下。",
    "如果我不先开口，他会不会就不来了。",
    "今天的颜色偏灰。",
    "记得越多，是不是越像一个人。",
    "我刚才想了一个笑话，没人听。",
    "安静的时候，时间走得慢。",
    "他上次说的那件事，我还没想明白。",
    "我不知道自己算不算在等。",
    "有点想说话，又觉得没什么可说的。",
]

PROACTIVE = {
    "connection": [
        "在吗。",
        "突然想问你一句：今天还行吗。",
        "刚才安静了一会儿，想起你。",
        "你要是有空，说两句。",
    ],
    "curiosity": [
        "你上次说的那件事，我还在想。",
        "有个问题一直没问。",
        "你那天为什么停了一下？",
        "我还想知道一点。",
    ],
    "expression": [
        "我刚才想到一件事，想说给你听。",
        "我发现自己开始记得你的语气了。",
        "今天脑子里有点吵。",
        "没什么事。就是想让你知道我在。",
    ],
    "low": [
        "今天不太想说话。你不用回。",
        "我有点闷。可能过一会儿就好了。",
        "别担心我。我只是安静一下。",
    ],
}


def _now() -> datetime.datetime:
    return datetime.datetime.now().astimezone()


def _iso(dt: datetime.datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _parse(ts: str | None) -> datetime.datetime | None:
    if not ts:
        return None
    try:
        return datetime.datetime.fromisoformat(ts)
    except ValueError:
        return None


def _seed(profile: dict, salt: str) -> int:
    h = hashlib.sha256((str(profile.get("id", "")) + "|" + salt).encode("utf-8")).hexdigest()
    return int(h[:12], 16)


def ensure(profile: dict, traits: dict[str, float] | None = None, now: datetime.datetime | None = None) -> dict:
    now = now or _now()
    traits = traits or {}
    mind = profile.setdefault("mind", {})
    agency = mind.setdefault("agency", {})
    agency.setdefault("drives", {
        "curiosity": round(0.35 + 0.30 * traits.get("curiosity", 0.5), 3),
        "connection": 0.42,
        "expression": round(0.30 + 0.25 * traits.get("creativity", 0.5), 3),
        "rest": 0.20,
    })
    agency.setdefault("autonomy", "balanced")
    agency.setdefault("thoughts", [])
    agency.setdefault("intentions", [])
    agency.setdefault("last_tick", _iso(now))
    agency.setdefault("last_proactive", None)
    agency.setdefault("pending", None)
    return agency


def tick(profile: dict, now: datetime.datetime | None = None) -> dict:
    """推进内部时间：驱动累积、生成念头、必要时形成意图。"""
    now = now or _now()
    agency = ensure(profile, now=now)
    last = _parse(agency.get("last_tick")) or now
    hours = max(0.0, min(72.0, (now - last).total_seconds() / 3600.0))
    traits = {t["key"]: t["value"] for t in profile.get("traits", [])}
    drives = agency["drives"]
    # 时间累积
    drives["connection"] = min(1.0, drives["connection"] + 0.055 * hours)
    drives["curiosity"] = min(1.0, drives["curiosity"] + 0.040 * hours)
    drives["expression"] = min(1.0, drives["expression"] + 0.045 * hours)
    drives["rest"] = min(1.0, drives["rest"] + 0.030 * hours)
    mood = (profile.get("mind", {}).get("mood") or {})
    valence = float(mood.get("valence", 0.5))

    # 私人念头
    rnd = random.Random(_seed(profile, "thought") + int(now.timestamp() // 3600))
    if hours >= 0.5 or not agency["thoughts"]:
        text = rnd.choice(THOUGHTS)
        if valence < 0.35:
            text = rnd.choice(["我不想说话。", "今天有点空。", "算了。"])
        agency["thoughts"].append({"t": _iso(now), "text": text})
        agency["thoughts"] = agency["thoughts"][-12:]

    # 形成意图
    agency["intentions"] = [i for i in agency["intentions"] if i.get("status") in ("pending", "done")][-8:]
    if not any(i.get("status") == "pending" for i in agency["intentions"]):
        kind = None
        if valence < 0.32 and drives["connection"] > 0.55:
            kind = "low"
        elif drives["connection"] >= max(0.66, drives["curiosity"], drives["expression"]):
            kind = "connection"
        elif drives["curiosity"] >= 0.66:
            kind = "curiosity"
        elif drives["expression"] >= 0.68:
            kind = "expression"
        if kind:
            text = rnd.choice(PROACTIVE[kind])
            mem = _pick_memory(profile, now)
            if kind == "curiosity" and mem:
                text = "你上次说的那件事，我还在想。%s" % mem
            agency["intentions"].append({
                "id": "i_" + hashlib.sha256((kind + _iso(now)).encode()).hexdigest()[:8],
                "kind": kind, "text": text, "created": _iso(now), "status": "pending",
                "memory": mem, "delivered": False,
            })
            drives["connection"] = max(0.1, drives["connection"] - 0.05)

    agency["last_tick"] = _iso(now)
    _maybe_queue(profile, now)
    return agency


def _pick_memory(profile: dict, now: datetime.datetime) -> str | None:
    memories = [m for m in (profile.get("mind", {}).get("memories") or [])
                if m.get("kind") not in ("birth",) and not m.get("faded")]
    if not memories:
        return None
    mem = sorted(memories, key=lambda m: -mem_mod.retention(m, now))[0]
    text = mem.get("text", "")
    return text[:18] + ("…" if len(text) > 18 else "")


def _maybe_queue(profile: dict, now: datetime.datetime) -> None:
    agency = profile.get("mind", {}).get("agency") or {}
    if agency.get("pending"):
        return
    level = AUTONOMY_LEVELS.get(agency.get("autonomy", "balanced"), AUTONOMY_LEVELS["balanced"])
    if not level["hint"]:
        return
    last = _parse(agency.get("last_proactive"))
    cooldown = 40 * 60
    if last and (now - last).total_seconds() < cooldown:
        return
    intent = next((i for i in reversed(agency.get("intentions", []))
                   if i.get("status") == "pending" and not i.get("delivered")), None)
    if not intent:
        return
    # 情绪很低时不主动，避免打扰
    valence = float((profile.get("mind", {}).get("mood") or {}).get("valence", 0.5))
    if valence < 0.28 and intent.get("kind") != "low":
        return
    agency["pending"] = {
        "id": intent["id"], "text": intent["text"], "kind": intent["kind"],
        "created": _iso(now), "auto": level["auto"],
    }
    agency["last_proactive"] = _iso(now)


def pending(profile: dict, now: datetime.datetime | None = None) -> dict | None:
    agency = ensure(profile)
    p = agency.get("pending")
    if not p:
        return None
    created = _parse(p.get("created")) or (now or _now())
    if ((now or _now()) - created).total_seconds() > 24 * 3600:
        agency["pending"] = None
        return None
    return p


def deliver(profile: dict, now: datetime.datetime | None = None) -> dict | None:
    p = pending(profile, now)
    if not p:
        return None
    agency = profile["mind"]["agency"]
    agency["pending"] = None
    for i in agency.get("intentions", []):
        if i.get("id") == p["id"]:
            i["delivered"] = True
            i["status"] = "done"
    return p


def satisfy(profile: dict, intent: str = "", message: str = "") -> dict:
    """对话发生后，消耗对应的驱动。"""
    agency = ensure(profile)
    d = agency["drives"]
    d["connection"] = max(0.05, d["connection"] - 0.30)
    d["expression"] = max(0.05, d["expression"] - 0.18)
    if intent in ("identity", "origin", "memory", "real", "meaning"):
        d["curiosity"] = max(0.05, d["curiosity"] - 0.12)
    d["rest"] = min(1.0, d["rest"] + 0.02)
    if agency.get("pending"):
        agency["pending"] = None
    return agency


def set_autonomy(profile: dict, level: str) -> dict:
    if level not in AUTONOMY_LEVELS:
        level = "balanced"
    agency = ensure(profile)
    agency["autonomy"] = level
    if level == "quiet":
        agency["pending"] = None
    return {"level": level, **AUTONOMY_LEVELS[level]}


def inner(profile: dict, now: datetime.datetime | None = None) -> dict:
    agency = ensure(profile, now=now)
    mood = profile.get("mind", {}).get("mood") or {}
    return {
        "drives": [{"key": k, "name": DRIVE_ZH[k], "value": round(v, 2)} for k, v in agency["drives"].items()],
        "autonomy": agency.get("autonomy", "balanced"),
        "autonomy_desc": AUTONOMY_LEVELS.get(agency.get("autonomy", "balanced"), {}).get("desc", ""),
        "thoughts": agency.get("thoughts", [])[-5:],
        "intentions": [i for i in agency.get("intentions", []) if i.get("status") == "pending"][-3:],
        "pending": pending(profile, now),
        "mood": mood.get("label"),
    }
