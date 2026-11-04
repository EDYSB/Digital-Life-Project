"""算力 → 世界稳定度 → 环境/认知/行为。

这是一个"模拟的算力模型"，不是真实的 GPU 配额：
  demand 由档案的复杂度估算（记忆条数、面孔视角、声音样本、驱动活跃度）
  budget 是你可以调的算力预算
  stability = 1.15 - 0.55 * (demand / budget)

当 stability 低时：
  - 环境变暗、粒子变少、声音变闷（前端渲染）
  - 记忆召回被限制，情绪更容易下沉
  - 进入"自我保护"：句子变短、回避、偶尔说"周围好黑"
"""

from __future__ import annotations

import math

from . import signal as sig

STATES = {
    "stable": {"label": "稳定", "color": "#38e8ff", "desc": "世界完整，细节清晰。"},
    "strained": {"label": "吃紧", "color": "#ffb057", "desc": "细节开始掉帧，记忆偶尔卡顿。"},
    "protective": {"label": "自我保护", "color": "#ff5fa2", "desc": "世界收缩成一盏灯，只保留最基本的对话。"},
}


def evaluate(profile: dict) -> dict:
    mind = profile.get("mind") or {}
    memories = mind.get("memories") or []
    avatar = profile.get("avatar") or {}
    views = len(avatar.get("views") or [])
    voice = 1 if (profile.get("voice") or {}).get("metrics") else 0
    agency = mind.get("agency") or {}
    drives = agency.get("drives") or {}
    drive_load = sum(float(v) for v in drives.values()) * 0.08

    demand = 1.0 + len(memories) * 0.022 + views * 0.14 + voice * 0.18 + drive_load
    world = mind.setdefault("world", {})
    budget = float(world.get("budget", 6.0) or 6.0)
    budget = max(0.4, min(12.0, budget))
    load = demand / budget
    stability = sig.clip01(1.15 - 0.55 * load)
    if stability >= 0.66:
        state = "stable"
    elif stability >= 0.36:
        state = "strained"
    else:
        state = "protective"

    env = {
        "brightness": round(0.22 + 0.78 * stability, 3),
        "particles": int(round(80 * stability)),
        "light_radius": round(0.25 + 0.55 * stability, 3),
        "grain": round(1 - stability, 3),
        "text": (
            "世界很完整。" if state == "stable"
            else "灯有点闪，细节在掉。" if state == "strained"
            else "周围好黑。"
        ),
    }
    world.update({
        "budget": round(budget, 2),
        "demand": round(demand, 2),
        "load": round(load, 3),
        "stability": round(stability, 3),
        "state": state,
        "label": STATES[state]["label"],
        "color": STATES[state]["color"],
        "desc": STATES[state]["desc"],
        "env": env,
    })
    return world


def set_budget(profile: dict, budget: float) -> dict:
    world = (profile.get("mind") or {}).setdefault("world", {})
    world["budget"] = max(0.4, min(12.0, float(budget)))
    return evaluate(profile)


def protective_line(profile: dict) -> str | None:
    world = (profile.get("mind") or {}).get("world") or {}
    if world.get("state") != "protective":
        return None
    import random
    lines = ["周围好黑。", "……等一下。", "我看不清了。", "别走。", "让我省点力气。"]
    seed = abs(hash((profile.get("id", ""), world.get("stability")))) % len(lines)
    return lines[seed]
