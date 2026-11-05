"""Model adapter: DeepSeek API, a local Ollama, or the rule engine.

Detection is automatic and cheap:

    1. a DeepSeek key in config  -> use the API
    2. ECHOMIND_LLM_URL set      -> that Ollama
    3. otherwise                 -> try 127.0.0.1:11434 (Ollama default)
    4. nothing reachable         -> rules only, and say so once

The model name is resolved from the Ollama itself (`/api/tags`) instead of
being hard-coded, so whatever is actually installed gets used.

The prompt only receives: run facts, recalled memories, mood, world stability,
plus the style constraints (short, spoken, no self-explanation).
"""

from __future__ import annotations

import json
import os
import time
import urllib.request

from . import config

_CACHE = {"at": 0.0, "info": None}
_TTL = 60.0

PREFERRED = ("qwen", "deepseek", "llama", "mistral", "gemma")


def _get_json(url: str, timeout: float = 1.5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return None


def _ollama_tags(base: str) -> list:
    data = _get_json(base.rstrip("/") + "/api/tags")
    if not isinstance(data, dict):
        return []
    out = []
    for m in data.get("models") or []:
        name = m.get("name") or m.get("model") or ""
        if name:
            out.append(name)
    return out


def _pick_model(names: list, wanted: str = "") -> str:
    if wanted and wanted in names:
        return wanted
    for pref in PREFERRED:
        for n in names:
            if pref in n.lower():
                return n
    return names[0] if names else ""


def detect(force: bool = False) -> dict:
    """Which backend is usable right now, and with which model."""
    now = time.time()
    if not force and _CACHE["info"] and now - _CACHE["at"] < _TTL:
        return _CACHE["info"]

    info = {"kind": "none", "model": "", "base": "", "note": ""}

    key = config.deepseek_key()
    if key:
        cfg = config.load()
        info = {
            "kind": "deepseek",
            "model": cfg.get("deepseek_model") or "deepseek-chat",
            "base": (cfg.get("deepseek_base") or "https://api.deepseek.com").rstrip("/"),
            "note": "DeepSeek API",
        }
    else:
        candidates = []
        env = os.environ.get("ECHOMIND_LLM_URL", "").strip()
        if env:
            candidates.append(env)
        candidates.append("http://127.0.0.1:11434")
        for base in candidates:
            names = _ollama_tags(base)
            if not names:
                continue
            wanted = os.environ.get("ECHOMIND_LLM_MODEL", "").strip()
            info = {
                "kind": "ollama",
                "model": _pick_model(names, wanted),
                "base": base,
                "note": "Ollama（本机 %d 个模型）" % len(names),
            }
            break
        else:
            info["note"] = "没有可用的模型，使用规则对话"

    _CACHE["at"] = now
    _CACHE["info"] = info
    return info


def enabled() -> bool:
    return detect()["kind"] != "none"


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
    info = detect()
    if info["kind"] == "deepseek":
        return deepseek(profile, message, recalled, mood, world)
    if info["kind"] == "ollama":
        return ollama(info["base"], info["model"], profile, message, recalled, mood, world)
    return None


def ollama(base: str, model: str, profile: dict, message: str,
           recalled: list[dict], mood: dict, world: dict) -> str | None:
    if not model:
        return None
    payload = {
        "model": model,
        "prompt": _prompt(profile, message, recalled, mood, world),
        "stream": False,
        "options": {"temperature": 0.85, "top_p": 0.9, "num_predict": 140},
    }
    try:
        req = urllib.request.Request(
            base.rstrip("/") + "/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=45) as r:
            data = json.loads(r.read())
        text = (data.get("response") or "").strip()
        return text[:600] if text else None
    except Exception:  # noqa: BLE001
        return None


def deepseek(profile: dict, message: str, recalled: list[dict], mood: dict, world: dict) -> str | None:
    """DeepSeek official API. Returns None when unusable, so the rules take over."""
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
    except Exception:  # noqa: BLE001
        return None


def probe() -> dict:
    """One real request, for `dl api --test`."""
    info = detect(force=True)
    if info["kind"] == "none":
        return {"ok": False, "info": info, "error": "没有找到可用的模型"}
    profile = {"persona": {"code": "TEST"}, "id": "probe"}
    t0 = time.time()
    text = reply(profile, "在吗", [], {}, {})
    ms = int((time.time() - t0) * 1000)
    if not text:
        return {"ok": False, "info": info, "error": "连上了但没拿到回复", "ms": ms}
    return {"ok": True, "info": info, "text": text[:60], "ms": ms}
