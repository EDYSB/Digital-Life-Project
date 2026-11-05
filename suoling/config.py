"""本地配置。config.json 不入库，留空就是不用。"""
from __future__ import annotations

import json
import os

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")
_DEFAULT = {
    "deepseek_api_key": "",
    "deepseek_base": "https://api.deepseek.com",
    "deepseek_model": "deepseek-chat",
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
