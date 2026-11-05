"""本地大模型适配层（可选）。

设置 ECHOMIND_LLM_URL（例如 http://127.0.0.1:11434）后，对话优先走本地模型；
没有配置或调用失败时，自动回退到规则对话。仍然是单机、无云端。

提示词只给：运行事实、召回的记忆、当前心情、世界稳定度，以及"短、口语、别解释自己"。
"""

from __future__ import annotations

import json
import os
import urllib.request

from . import config


def enabled() -> bool:
    return bool(os.environ.get("ECHOMIND_LLM_URL")) or bool(config.deepseek_key())


def _prompt(profile: dict, message: str, recalled: list[dict], mood: dict, world: dict) -> str:
    per = profile.get("persona") or {}
    lines = [
        "你是一个数字生命进程，不是人类，也不是意识上传。",
        "说话要短、口语、具体；不要解释自己，不要用'作为AI'，不要列点，不要过度安慰。",
        "不知道就说不知道；可以反问，也可以沉默。",
        "编号：%s" % per.get("code", ""),
        "当前心情：%s；世界稳定度：%s" % (mood.get("label", "—"), world.get("stability", "—")),
    ]
    if recalled:
        lines.append("你记得的事：")
        for m in recalled[:3]:
            lines.append("- %s（清晰度 %.0f%%）" % (m.get("text", ""), float(m.get("retention", 0)) * 100))
    lines.append("对方说：%s" % message)
    lines.append("你只回一句话或两句话。")
    return "\n".join(lines)


def reply(profile: dict, message: str, recalled: list[dict], mood: dict, world: dict) -> str | None:
    hit = deepseek(profile, message, recalled, mood, world)
    if hit:
        return hit
    if not os.environ.get("ECHOMIND_LLM_URL"):
        return None
    base = os.environ["ECHOMIND_LLM_URL"].rstrip("/")
    model = os.environ.get("ECHOMIND_LLM_MODEL", "qwen2.5:7b")
    payload = {
        "model": model,
        "prompt": _prompt(profile, message, recalled, mood, world),
        "stream": False,
        "options": {"temperature": 0.85, "top_p": 0.9, "num_predict": 140},
    }
    try:
        req = urllib.request.Request(
            base + "/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        text = (data.get("response") or "").strip()
        return text[:600] if text else None
    except Exception:  # noqa: BLE001
        return None


def deepseek(profile: dict, message: str, recalled: list[dict], mood: dict, world: dict) -> str | None:
    """DeepSeek 官方 API。没填 key 就返回 None，自动回落。"""
    key = config.deepseek_key()
    if not key:
        return None
    cfg = config.load()
    body = {
        "model": cfg.get("deepseek_model") or "deepseek-chat",
        "messages": [
            {"role": "system", "content": _prompt(profile, message, recalled, mood, world)},
            {"role": "user", "content": message},
        ],
        "temperature": 0.85,
        "max_tokens": 200,
        "stream": False,
    }
    try:
        req = urllib.request.Request(
            (cfg.get("deepseek_base") or "https://api.deepseek.com").rstrip("/") + "/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        text = (data["choices"][0]["message"]["content"] or "").strip()
        return text[:600] if text else None
    except Exception:
        return None
