"""自主学习（规则型的自我监督，不是训练神经网络）。

它做三件真实的事：
  1. 从自己的记忆里找模式（来的时间、反复出现的词、情绪与睡眠的共现）
  2. 把模式写成一条"自学笔记"，作为新的记忆存下来（source=study）
  3. 下次对话时，这条笔记和普通记忆一样会被召回、被复述、被遗忘

没有外部知识库，没有权重更新；它学到的是"关于你的统计"，不是世界知识。
"""

from __future__ import annotations

import datetime
import re

from . import memory as mem_mod

STOP = set("我的 你的 我们 就是 还是 真的 有点 最近 今天 一个 没有 觉得 知道 时候".split())


def _parse(ts):
    try:
        return datetime.datetime.fromisoformat(ts) if ts else None
    except ValueError:
        return None


def _grams(text: str) -> list[str]:
    s = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", text or "")
    return [s[i:i + 2] for i in range(len(s) - 1)]


def study(profile: dict, now: datetime.datetime | None = None) -> dict | None:
    now = now or datetime.datetime.now().astimezone()
    mind = profile.setdefault("mind", {})
    memories = [m for m in mind.get("memories", []) if m.get("kind") != "birth"]
    if len(memories) < 3:
        return None
    # 冷却：每 6 小时最多学一条
    learn_state = mind.setdefault("learn", {"last": None, "lessons": 0})
    last = _parse(learn_state.get("last"))
    if last and (now - last).total_seconds() < 6 * 3600:
        return None

    candidates = []
    # 1) 来的时间
    hours = [(_parse(m.get("created")) or now).hour for m in memories]
    night = sum(1 for h in hours if h >= 22 or h < 5) / len(hours)
    if night >= 0.55:
        candidates.append(("你大多在深夜来。", "time", min(0.9, night)))
    # 2) 反复出现的词
    counts = {}
    for m in memories:
        for g in set(_grams(m.get("text", ""))):
            if g in STOP or len(g) < 2:
                continue
            counts[g] = counts.get(g, 0) + 1
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:3]
    if top and top[0][1] >= 3:
        g, n = top[0]
        candidates.append(("你最近常提到「%s」。" % g, "topic", min(0.9, n / max(3, len(memories)))))
    # 3) 情绪与睡眠共现
    texts = [m.get("text", "") for m in memories]
    neg = sum(1 for t in texts if any(w in t for w in ("累", "焦虑", "压力", "难过", "睡不着")))
    sleep = sum(1 for t in texts if ("睡" in t or "凌晨" in t))
    if neg >= 2 and sleep >= 1:
        candidates.append(("你说累的时候，常常也睡不好。", "mood", 0.6))

    if not candidates:
        learn_state["last"] = now.isoformat(timespec="seconds")
        return None
    text, kind, conf = max(candidates, key=lambda c: c[2])
    # 去重
    if any(text[:8] in m.get("text", "") for m in memories):
        learn_state["last"] = now.isoformat(timespec="seconds")
        return None

    note = "我自己发现的：" + text
    mem = {
        "id": "m_" + str(abs(hash(note)))[:10],
        "text": note,
        "kind": "insight",
        "created": now.isoformat(timespec="seconds"),
        "last": now.isoformat(timespec="seconds"),
        "rehearsals": 0,
        "valence": 0.1,
        "keywords": sorted(set(_grams(note))),
        "source": "study",
        "faded": False,
        "confidence": round(conf, 2),
        "basis": kind,
    }
    mem["retention"] = mem_mod.retention(mem, now)
    mind.setdefault("memories", []).append(mem)
    learn_state["last"] = now.isoformat(timespec="seconds")
    learn_state["lessons"] = int(learn_state.get("lessons", 0)) + 1
    return mem


def summary(profile: dict) -> dict:
    learn = ((profile.get("mind") or {}).get("learn") or {})
    notes = [m for m in ((profile.get("mind") or {}).get("memories") or []) if m.get("source") == "study"]
    return {"lessons": int(learn.get("lessons", 0)), "notes": len(notes),
            "recent": [{"text": m.get("text"), "confidence": m.get("confidence")} for m in notes[-3:]]}
