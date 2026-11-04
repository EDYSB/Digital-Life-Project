"""记忆与心情：艾宾浩斯遗忘曲线、情景记忆召回、心情漂移。

设计原则
--------
* 记忆不是数据库：每条记忆有"强度 S"，随时间指数衰减 R = exp(-Δt / S)。
  被想起一次，S 变大（间隔重复），于是忘得更慢；情绪强烈的记忆衰减更慢。
* 遗忘不是删除：R 很低的记忆仍保留，只是"想不起来细节"，并会以感觉的形式残留。
* 心情是慢变量：唤醒度/愉悦度在对话中漂移，之后按半衰期回落到人格基线，
  并留下一条可回看的心情轨迹。

所有函数只操作 profile["mind"]，不依赖全局状态，便于测试与回放。
"""

from __future__ import annotations

import datetime
import hashlib
import math
import re

from . import signal as sig

# ---------------------------------------------------------------- 基础
STOP_BIGRAMS = {
    "我们", "你们", "他们", "自己", "这个", "那个", "什么", "怎么", "因为", "所以",
    "但是", "如果", "就是", "可以", "没有", "知道", "觉得", "感觉", "现在", "时候",
    "一个", "一下", "一点", "还是", "已经", "真的", "不是", "我的", "你的", "然后",
    "可能", "应该", "需要", "想要", "比较", "非常", "有点", "一直", "总是", "最近",
}

EMOTION_WORDS = {
    "累": -0.6, "疲惫": -0.6, "难过": -0.8, "伤心": -0.8, "焦虑": -0.7, "压力": -0.6,
    "孤独": -0.7, "寂寞": -0.6, "害怕": -0.7, "恐惧": -0.8, "失眠": -0.6, "睡不着": -0.6,
    "烦": -0.5, "崩溃": -0.9, "委屈": -0.6, "空": -0.4, "麻木": -0.5, "后悔": -0.6,
    "开心": 0.7, "高兴": 0.7, "喜欢": 0.6, "爱": 0.8, "幸福": 0.8, "平静": 0.4,
    "放松": 0.5, "期待": 0.5, "希望": 0.4, "谢谢": 0.4, "温暖": 0.6, "安心": 0.6,
}

INTENT_VALENCE = {
    "feeling": -0.15, "sleep": -0.1, "love": 0.15, "thanks": 0.2, "bye": 0.05,
    "memory": 0.05, "identity": 0.0, "real": -0.05, "death": -0.2, "future": 0.05,
}

FACT_PATTERNS = [
    (r"我(?:叫|的名字是)(.{1,12})", "identity"),
    (r"我(?:是|在|住在|来自)(.{2,18})", "fact"),
    (r"我(?:的)?(猫|狗|妈妈|爸爸|母亲|父亲|孩子|女儿|儿子|伴侣|爱人)(.{0,16})", "fact"),
    (r"我(?:喜欢|爱|讨厌|不喜欢|害怕|怕|想要|希望|打算|准备)(.{2,22})", "preference"),
    (r"我(?:每天|每周|常常|经常|总是|一般)(.{2,22})", "habit"),
    (r"我(?:最近|今天|昨晚|昨天|这几天)(.{2,26})", "event"),
]


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


def _days_between(a: datetime.datetime | None, b: datetime.datetime) -> float:
    if a is None:
        return 0.0
    return max(0.0, (b - a).total_seconds() / 86400.0)


# ---------------------------------------------------------------- 记忆条目
def bigrams(text: str) -> set[str]:
    s = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", text or "")
    grams = set()
    for i in range(len(s) - 1):
        g = s[i : i + 2]
        if g not in STOP_BIGRAMS:
            grams.add(g)
    if len(s) == 1:
        grams.add(s)
    return grams


def _overlap(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / math.sqrt(len(a) * len(b))


def stability(mem: dict) -> float:
    """记忆强度 S（天）。出生记忆与高情绪记忆更耐久，复述会显著延长。"""
    base = 7.0 if (mem.get("source") == "birth" or mem.get("pinned")) else 1.0
    rehearsals = int(mem.get("rehearsals", 0))
    s = base * (1.0 + 0.75 * rehearsals) * (1.0 + 0.9 * abs(float(mem.get("valence", 0))))
    return max(0.15, min(120.0, s))


def retention(mem: dict, now: datetime.datetime | None = None) -> float:
    """艾宾浩斯遗忘曲线：R = exp(-Δt / S)，S 随复述与情绪强度增长。"""
    now = now or _now()
    last = _parse(mem.get("last")) or _parse(mem.get("created")) or now
    dt = _days_between(last, now)
    r = math.exp(-dt / stability(mem))
    return round(max(0.0, min(1.0, r)), 4)


def _mem_id(text: str, kind: str) -> str:
    return "m_" + hashlib.sha256((kind + "|" + text).encode("utf-8")).hexdigest()[:10]


def _clean_clause(text: str) -> str:
    t = re.sub(r"\s+", "", text or "")
    t = t.strip("，。！？、；：,.!?;:")
    return t[:80]


def extract(message: str) -> list[dict]:
    """从一句话里提取"值得记住"的片段（规则驱动，不假装理解）。"""
    msg = _clean_clause(message)
    if len(msg) < 4 or msg.endswith(("吗", "呢", "？", "?")):
        return []
    found: list[dict] = []
    for pattern, kind in FACT_PATTERNS:
        m = re.search(pattern, msg)
        if m:
            frag = _clean_clause(m.group(0))
            if len(frag) >= 4:
                found.append({"text": frag, "kind": kind})
    # 情绪陈述也记，但归为 emotion
    for w, v in EMOTION_WORDS.items():
        if w in msg and len(msg) >= 5:
            kind = "emotion" if abs(v) >= 0.6 else "feeling"
            found.append({"text": msg, "kind": kind, "valence": v})
            break
    # 去掉包含关系里的重复
    uniq = []
    for f in found:
        if not any(f["text"] in u["text"] and f["text"] != u["text"] for u in found):
            uniq.append(f)
    return uniq[:3]


def _merge(profile: dict, cand: dict, now: datetime.datetime) -> dict:
    mind = profile.setdefault("mind", {})
    memories = mind.setdefault("memories", [])
    grams = bigrams(cand["text"])
    for mem in memories:
        if mem.get("faded"):
            continue
        if _overlap(grams, set(mem.get("keywords", []))) >= 0.62:
            # 同一件事又提了一次：复述强化，更新措辞
            mem["rehearsals"] = int(mem.get("rehearsals", 0)) + 1
            mem["last"] = _iso(now)
            mem["text"] = cand["text"]
            mem["keywords"] = sorted(grams)
            mem["kind"] = cand["kind"]
            mem["retention"] = retention(mem, now)
            return {"memory": mem, "strengthened": True}
    mem = {
        "id": _mem_id(cand["text"], cand["kind"]),
        "text": cand["text"],
        "kind": cand["kind"],
        "created": _iso(now),
        "last": _iso(now),
        "rehearsals": 0,
        "valence": float(cand.get("valence", 0.0)),
        "keywords": sorted(grams),
        "source": cand.get("source", "chat"),
        "faded": False,
    }
    mem["retention"] = retention(mem, now)
    memories.append(mem)
    return {"memory": mem, "strengthened": False}


def decay(profile: dict, now: datetime.datetime | None = None) -> dict:
    """推进一步遗忘：更新每条记忆的留存率，标记长期未被想起的为"模糊"。"""
    now = now or _now()
    mind = profile.setdefault("mind", {})
    memories = mind.setdefault("memories", [])
    events = mind.setdefault("events", [])
    faded_now = 0
    for mem in memories:
        r = retention(mem, now)
        mem["retention"] = r
        if r < 0.06:
            if not mem.get("faded"):
                mem["faded"] = True
                events.append({"t": _iso(now), "type": "forgot", "text": mem.get("text", ""),
                               "kind": mem.get("kind", ""), "retention": r})
            faded_now += 1
        elif mem.get("faded") and r > 0.6:
            mem["faded"] = False
    if len(events) > 80:
        mind["events"] = events[-80:]
    # 上限保护：超出 160 条时，先丢最模糊、且不是出生记忆的
    if len(memories) > 160:
        ranked = sorted(enumerate(memories),
                        key=lambda iv: (iv[1].get("source") == "birth", iv[1].get("retention", 0)))
        drop = {i for i, _ in ranked[: len(memories) - 160]}
        memories[:] = [m for i, m in enumerate(memories) if i not in drop]
    stats = mind.setdefault("stats", {})
    stats["last_tick"] = _iso(now)
    stats["faded"] = faded_now
    return {"count": len(memories), "faded": faded_now}


def recall(profile: dict, query: str, now: datetime.datetime | None = None, limit: int = 3) -> list[dict]:
    now = now or _now()
    mind = profile.get("mind") or {}
    memories = mind.get("memories") or []
    grams = bigrams(query)
    scored = []
    for mem in memories:
        r = retention(mem, now)
        if r < 0.035:
            continue
        sim = _overlap(grams, set(mem.get("keywords", [])))
        # 与当前话题无关时，只允许高留存 + 高情绪的记忆"浮上来"
        score = 0.55 * sim + 0.35 * r + 0.10 * abs(float(mem.get("valence", 0)))
        # 与当前话题必须有最低限度的语义重叠；否则再清晰也不该被"想起"
        if sim < 0.07:
            continue
        if score < 0.16:
            continue
        scored.append((score, mem, r, sim))
    scored.sort(key=lambda x: -x[0])
    out = []
    for score, mem, r, sim in scored[:limit]:
        out.append({
            "id": mem["id"],
            "text": mem["text"],
            "kind": mem.get("kind", "fact"),
            "retention": r,
            "score": round(score, 3),
            "recollect": r >= 0.5,
            "created": mem.get("created"),
            "rehearsals": mem.get("rehearsals", 0),
        })
    return out


def reinforce(profile: dict, ids: list[str], now: datetime.datetime | None = None) -> None:
    now = now or _now()
    mind = profile.get("mind") or {}
    for mem in mind.get("memories") or []:
        if mem.get("id") in ids:
            mem["rehearsals"] = int(mem.get("rehearsals", 0)) + 1
            mem["last"] = _iso(now)
            mem["retention"] = retention(mem, now)


# ---------------------------------------------------------------- 心情
MOOD_POINTS = {
    (0.78, 0.75): "明亮 · 上扬",
    (0.55, 0.78): "温和 · 靠近",
    (0.80, 0.55): "紧绷 · 锋利",
    (0.50, 0.55): "平静 · 中性",
    (0.28, 0.72): "安静 · 柔软",
    (0.62, 0.30): "不安 · 内耗",
    (0.30, 0.35): "低电量 · 内收",
    (0.70, 0.20): "烦躁 · 易碎",
}


def mood_label(valence: float, arousal: float) -> str:
    best = 9.0
    label = "平静 · 中性"
    for (a, v), lab in MOOD_POINTS.items():
        d = (a - arousal) ** 2 + (v - valence) ** 2
        if d < best:
            best = d
            label = lab
    return label


def baseline_mood(traits: dict[str, float]) -> dict[str, float]:
    a = 0.22 + 0.42 * traits.get("alertness", 0.5) + 0.14 * traits.get("curiosity", 0.5)
    v = 0.30 + 0.38 * traits.get("empathy", 0.5) + 0.24 * traits.get("stability", 0.5)
    return {"arousal": round(sig.clamp(a, 0.1, 0.9), 3), "valence": round(sig.clamp(v, 0.1, 0.9), 3)}


def ensure(profile: dict, traits: dict[str, float] | None = None, birth: list[str] | None = None) -> dict:
    """确保 profile 里有 mind 结构；首次创建时写入"出生记忆"。"""
    traits = traits or {}
    now = _now()
    mind = profile.setdefault("mind", {})
    mind.setdefault("stats", {"sessions": 0, "messages": 0, "born": _iso(now)})
    if "mood" not in mind:
        base = baseline_mood(traits)
        mind["mood"] = {
            **base,
            "label": mood_label(base["valence"], base["arousal"]),
            "baseline": base,
            "updated": _iso(now),
            "history": [{"t": _iso(now), "v": base["valence"], "a": base["arousal"]}],
        }
    if "memories" not in mind:
        mind["memories"] = []
    if birth:
        for text in birth:
            if any(m.get("text") == text for m in mind["memories"]):
                continue
            mem = {
                "id": _mem_id(text, "birth"),
                "text": text,
                "kind": "birth",
                "created": _iso(now),
                "last": _iso(now),
                "rehearsals": 3,
                "valence": 0.3,
                "keywords": sorted(bigrams(text)),
                "source": "birth",
                "faded": False,
            }
            mem["retention"] = retention(mem, now)
            mind["memories"].append(mem)
    return mind


def update_mood(profile: dict, message: str, intent: str = "", now: datetime.datetime | None = None) -> dict:
    """在当前心情上叠加这句话的影响，并让心情向基线回落。"""
    now = now or _now()
    mind = profile.setdefault("mind", {})
    mood = mind.get("mood")
    if not mood:
        return {}
    baseline = mood.get("baseline") or {"valence": 0.5, "arousal": 0.5}
    last = _parse(mood.get("updated")) or now
    hours = max(0.0, (now - last).total_seconds() / 3600.0)
    # 半衰期 5 小时回落到基线
    k = 1 - math.pow(0.5, hours / 5.0)
    v = mood.get("valence", 0.5) + (baseline["valence"] - mood.get("valence", 0.5)) * k
    a = mood.get("arousal", 0.5) + (baseline["arousal"] - mood.get("arousal", 0.5)) * k

    txt = message or ""
    delta_v = 0.0
    for w, dv in EMOTION_WORDS.items():
        if w in txt:
            delta_v += dv * 0.5
    delta_v += INTENT_VALENCE.get(intent, 0.0)
    delta_a = 0.02
    if any(w in txt for w in ("?", "？", "吗", "呢")):
        delta_a += 0.02
    if any(w in txt for w in ("睡不着", "焦虑", "压力", "烦", "吵", "崩溃")):
        delta_a += 0.05
    if any(w in txt for w in ("累", "疲惫", "空", "麻木")):
        delta_a -= 0.03

    v = sig.clamp(v + sig.clamp(delta_v, -0.2, 0.2), 0.08, 0.95)
    a = sig.clamp(a + sig.clamp(delta_a, -0.06, 0.06), 0.08, 0.95)
    mood["valence"] = round(v, 3)
    mood["arousal"] = round(a, 3)
    mood["label"] = mood_label(v, a)
    mood["updated"] = _iso(now)
    history = mood.setdefault("history", [])
    history.append({"t": _iso(now), "v": round(v, 3), "a": round(a, 3)})
    if len(history) > 120:
        del history[: len(history) - 120]
    return {"valence": mood["valence"], "arousal": mood["arousal"], "label": mood["label"]}


# ---------------------------------------------------------------- 对外接口
def observe(profile: dict, message: str, reply_text: str = "", intent: str = "",
            now: datetime.datetime | None = None) -> dict:
    """一次对话结束后：提取新记忆、强化被召回的记忆、推进遗忘与心情。"""
    now = now or _now()
    ensure(profile, birth=None)
    learned = []
    for cand in extract(message):
        res = _merge(profile, cand, now)
        if not res["strengthened"]:
            learned.append(res["memory"]["text"])
    decay(profile, now)
    mood = update_mood(profile, message, intent, now)
    stats = profile["mind"].setdefault("stats", {})
    stats["messages"] = int(stats.get("messages", 0)) + 1
    stats["last_seen"] = _iso(now)
    return {"learned": learned, "mood": mood, "count": len(profile["mind"].get("memories", []))}


def start_session(profile: dict, now: datetime.datetime | None = None) -> dict:
    now = now or _now()
    ensure(profile)
    decay(profile, now)
    stats = profile["mind"].setdefault("stats", {})
    stats["sessions"] = int(stats.get("sessions", 0)) + 1
    stats["last_seen"] = _iso(now)
    last = _parse(stats.get("last_session"))
    stats["last_session"] = _iso(now)
    memories = profile["mind"].get("memories", [])
    strong = [m for m in memories if retention(m, now) >= 0.35 and m.get("kind") != "birth"]
    return {
        "sessions": stats["sessions"],
        "since_last": round(_days_between(last, now), 2),
        "memories": len(memories),
        "strong": len(strong),
        "mood": profile["mind"].get("mood", {}),
    }


def recall_context(profile: dict, message: str, now: datetime.datetime | None = None) -> dict:
    now = now or _now()
    recalled = recall(profile, message, now)
    mind = profile.get("mind") or {}
    faded = [m for m in mind.get("memories", []) if m.get("faded")][:3]
    return {
        "recalled": recalled,
        "faded_count": len(faded),
        "faded": [{"text": m.get("text", ""), "kind": m.get("kind", "")} for m in faded],
        "mood": mind.get("mood") or {},
        "count": len(mind.get("memories", [])),
    }


def timeline(profile: dict, days: int = 30, now: datetime.datetime | None = None) -> list[dict]:
    """给 UI 用的"未来 days 天留存预览"（不修改档案）。"""
    now = now or _now()
    memories = (profile.get("mind") or {}).get("memories", [])
    focus = sorted(memories, key=lambda m: -retention(m, now))[:6]
    out = []
    for mem in focus:
        row = {"id": mem.get("id"), "text": mem.get("text"), "kind": mem.get("kind"),
               "curve": []}
        for d in range(days + 1):
            fake = dict(mem)
            fake["last"] = _iso(now - datetime.timedelta(days=d) + datetime.timedelta(days=d))  # 保持 now 为基准
            # 直接按当前留存率做指数外推
            r0 = retention(mem, now)
            last = _parse(mem.get("last")) or now
            stability = 1.0 * (1 + 0.75 * int(mem.get("rehearsals", 0))) * (1 + 0.9 * abs(float(mem.get("valence", 0))))
            stability = max(0.15, min(60.0, stability))
            row["curve"].append(round(r0 * math.exp(-d / stability), 4))
        out.append(row)
    return out


def summary(profile: dict) -> dict:
    mind = profile.get("mind") or {}
    memories = mind.get("memories", [])
    now = _now()
    live = [m for m in memories if not m.get("faded")]
    mood = mind.get("mood") or {}
    return {
        "count": len(memories),
        "live": len(live),
        "faded": len(memories) - len(live),
        "mood": mood,
        "sessions": mind.get("stats", {}).get("sessions", 0),
        "messages": mind.get("stats", {}).get("messages", 0),
        "strong": len([m for m in live if retention(m, now) >= 0.5]),
    }
