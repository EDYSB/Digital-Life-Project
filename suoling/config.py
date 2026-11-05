"""本地配置。config.json 不入库，留空就是不用。"""
from __future__ import annotations

import json
import os

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")
_DEFAULT = {
    "deepseek_api_key": "",
    "deepseek_base": "https://api.deepseek.com",
    "deepseek_model": "deepseek-chat",
    "voice_backend": "",
    "voice_ws": "",
    "mode": "auto",
}


def load() -> dict:
    data = dict(_DEFAULT)
    try:
        with open(_PATH, encoding="utf-8") as f:
            data.update(json.load(f) or {})
    except (OSError, ValueError):
        pass
    return data


def deepseek_key() -> str:
    return (os.environ.get("DEEPSEEK_API_KEY") or load().get("deepseek_api_key") or "").strip()


def save(patch: dict) -> dict:
    data = load()
    data.update(patch or {})
    with open(_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return data


def mask(key: str) -> str:
    key = key or ""
    if not key:
        return "（未设置）"
    if len(key) <= 10:
        return key[:2] + "****"
    return key[:5] + "****" + key[-4:]
