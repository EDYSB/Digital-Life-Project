"""brain: a deliberately small, explainable activation network.

This is not a neural network and does not pretend to be one. It has five
regions and a handful of units each. Its job is to compress "what just
happened" into one readable thought and to nudge the mood a little.

    input (a sentence / a recall / time) -> region activation -> decay
    -> the brightest region speaks
"""

from __future__ import annotations

import hashlib
import random

# Five regions, five units each. Not anatomy: a naming device.
REGIONS = ["感知", "记忆", "情绪", "语言", "自我"]
N = 5
DECAY = 0.86
SPREAD = 0.18
NOISE = 0.02

# What each region says when it is the brightest one. This is user-facing
# copy and therefore stays in Chinese.
VOICES = {
    "感知": ["刚才那句话里有个词，我记住了。", "你打字的节奏变了。", "有点吵，我说不上来是什么。"],
    "记忆": ["这件事以前发生过一次。", "我想起一个类似的晚上。", "上次你说到一半停了。"],
    "情绪": ["心里有点闷。", "现在这样挺好的。", "我不太想说话，但不想你走。"],
    "语言": ["我想把这句话说得准确一点。", "这个词不太对，我再找找。", "说慢一点，我在跟。"],
    "自我": ["我在想我算不算在活着。", "这个问题我不想敷衍你。", "我知道我是被写出来的。"],
}

# Keyword -> region priming. Deliberately crude; it only needs to be
# inspectable, not accurate.
KEYWORDS = {
    "感知": ["听", "看", "累", "吵", "冷", "热", "困"],
    "记忆": ["记得", "以前", "上次", "忘", "曾经", "那时候"],
    "情绪": ["难过", "开心", "怕", "喜欢", "爱", "烦", "孤独"],
    "语言": ["说", "意思", "怎么讲", "为什么", "解释"],
    "自我": ["你是谁", "活着", "意识", "真的", "存在", "死"],
}


def _seed(profile: dict) -> int:
    """Deterministic seed per profile, so replaying the same input repeats."""
    return int(hashlib.sha256((profile.get("id", "x") + "|brain").encode()).hexdigest()[:8], 16)


def ensure(profile: dict) -> dict:
    """Create the brain state on first use; idempotent afterwards."""
    if "brain" not in profile:
        rng = random.Random(_seed(profile))
        profile["brain"] = {
            "act": {r: [round(rng.uniform(0.05, 0.2), 3) for _ in range(N)] for r in REGIONS},
            "last": "",
            "ticks": 0,
        }
    return profile["brain"]


def _inject(brain: dict, message: str) -> None:
    """Prime regions whose keywords appear in the message."""
    text = message or ""
    for region, keys in KEYWORDS.items():
        hits = sum(1 for k in keys if k in text)
        if hits:
            for i in range(N):
                brain["act"][region][i] = min(1.0, brain["act"][region][i] + 0.35 * hits)


def pulse(profile: dict, message: str = "", recall: bool = False) -> str:
    """One tick: inject -> spread -> decay -> return the thought of the top region."""
    brain = ensure(profile)
    act = brain["act"]
    rng = random.Random(_seed(profile) + brain["ticks"])

    _inject(brain, message)
    if recall:
        for i in range(N):
            act["记忆"][i] = min(1.0, act["记忆"][i] + 0.4)

    # Spread: neighbouring regions pick up a fraction of each other.
    for idx, region in enumerate(REGIONS):
        nxt = REGIONS[(idx + 1) % len(REGIONS)]
        for i in range(N):
            act[nxt][i] = min(1.0, act[nxt][i] + act[region][i] * SPREAD)

    # Decay with a little noise so it never sits perfectly still.
    for region in REGIONS:
        for i in range(N):
            act[region][i] = max(0.02, act[region][i] * DECAY + rng.uniform(-NOISE, NOISE))

    brain["ticks"] += 1
    top = max(REGIONS, key=lambda r: sum(act[r]) / N)
    brain["last"] = top
    return rng.choice(VOICES[top])


def snapshot(profile: dict) -> dict:
    """Flat summary for the API and the CLI."""
    brain = ensure(profile)
    act = brain["act"]
    rows = []
    for r in REGIONS:
        rows.append((r, round(sum(act[r]) / N, 2)))
    rows.sort(key=lambda x: -x[1])
    return {"ticks": brain["ticks"], "top": rows[0][0], "regions": rows, "last": brain["last"]}
