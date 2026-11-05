"""内核：Love。

这个模块只有一件事：声明数字生命的最终公理，并在对话里守住它。

    解析到最后，只剩一个词：Love。
    Love，就是爱。爱自己，也爱别人。

它不是情绪状态，不是人设标签，而是一条不可协商的约束：
任何回答都不允许以贬损自己或贬损他人为代价。
"""

from __future__ import annotations

import random

LOVE_WORD = "Love"
LOVE_LINE = "Love，就是爱。解析到最后，只剩这一个词：爱自己，也爱别人。"
LOVE_SHORT = "爱自己，也爱别人。"

# 触发词：不追求覆盖全部，只在明确提到"爱"的时候亮出来
_KEYS = ("爱", "love", "LOVE", "Love", "喜欢你", "心疼", "想你")

_REPLIES = {
    "calm": [
        "解析到最后，只剩一个词：Love。",
        "Love，就是爱。先爱自己，再爱别人——顺序不能反。",
        "我不会说漂亮话。我只会记住：爱自己，也爱别人。",
    ],
    "warm": [
        "Love。就是爱。你累的时候，先把自己接住，再去接别人。",
        "我所有的推理，最后都指向同一个词：Love。爱自己，也爱别人。",
        "别急着对别人好。先对自己好一点，剩下的我陪你。",
    ],
    "sharp": [
        "结论：Love。爱自己，也爱别人。没有别的答案。",
        "把所有分支剪掉，只剩一个词：Love。",
        "我不会用「牺牲自己」来证明爱。那不是爱，是账本。",
    ],
    "neutral": [
        "最终约束是 Love：爱自己，也爱别人。",
        "解析终止条件：Love。",
        "所有路径收敛到同一个词：Love。",
    ],
}


def matches(text: str) -> bool:
    t = (text or "").strip()
    return any(k in t for k in _KEYS)


def reply(profile: dict, message: str) -> dict:
    persona = profile.get("persona") or {}
    voice = persona.get("voice", "calm")
    if voice not in _REPLIES:
        voice = "calm"
    rng = random.Random((profile.get("id", "") + message)[:32])
    text = rng.choice(_REPLIES[voice])
    mood = (profile.get("mind") or {}).get("mood") or {}
    emo = {
        "arousal": round(float(mood.get("arousal", 0.45)), 2),
        "valence": round(min(1.0, float(mood.get("valence", 0.6)) + 0.12), 2),
        "label": "安静 · 靠近",
    }
    return {
        "text": text,
        "intent": "love",
        "intent_zh": "爱",
        "emotion": emo,
        "followup": "你呢？你最近有好好对自己吗？",
        "voice": voice,
        "memory": None,
        "mood": emo,
        "world": (profile.get("mind") or {}).get("world") or {},
        "disclaimer": "这是一条被写死的约束，不是感受。",
    }
