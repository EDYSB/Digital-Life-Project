"""本地账户：一个人一个账户，一个人一份档案。

- 没有账户时，一切照旧：档案放在 `minds/` 下，谁都能看。
- 建立账户后，每个人只看到自己的 `minds/<账户>/`，互不覆盖。
- 口令用 PBKDF2-HMAC-SHA256 + 随机盐，存在 `minds/.users.json`。
- 当前登录的人存在 `minds/.session`（一行用户名）。

`minds/` 已在 .gitignore 里，账户和档案都不会进仓库。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DIR = os.path.join(_ROOT, "minds")
_USERS = os.path.join(_DIR, ".users.json")
_SESSION = os.path.join(_DIR, ".session")
_ITER = 120_000


def _ensure() -> None:
    os.makedirs(_DIR, exist_ok=True)


def _read_users() -> dict:
    try:
        with open(_USERS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _write_users(d: dict) -> None:
    _ensure()
    with open(_USERS, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


def _hash(pw: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), bytes.fromhex(salt), _ITER).hex()


def has_accounts() -> bool:
    return bool(_read_users())


def users() -> list[str]:
    return sorted(_read_users().keys())


def add_user(name: str, pw: str) -> None:
    name = (name or "").strip()
    if not name or not pw:
        raise ValueError("账户名和口令都要有。")
    d = _read_users()
    salt = os.urandom(16).hex()
    d[name] = {"salt": salt, "hash": _hash(pw, salt), "iter": _ITER}
    _write_users(d)


def verify(name: str, pw: str) -> bool:
    d = _read_users()
    rec = d.get((name or "").strip())
    if not rec:
        return False
    try:
        return hmac.compare_digest(_hash(pw, rec["salt"]), rec.get("hash", ""))
    except (KeyError, ValueError):
        return False


def current_user() -> str:
    try:
        with open(_SESSION, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def set_current(name: str) -> None:
    _ensure()
    if not name:
        try:
            os.remove(_SESSION)
        except OSError:
            pass
        return
    with open(_SESSION, "w", encoding="utf-8") as f:
        f.write(name)


def login(name: str | None = None) -> bool:
    """保证当前有登录者；没有账户体系时直接放行。"""
    if not has_accounts():
        return True
    if name:
        return bool(current_user()) and current_user() == name
    if current_user() in _read_users():
        return True
    import getpass

    for _ in range(3):
        try:
            u = input("  账户：").strip()
            pw = getpass.getpass("  口令：")
        except (EOFError, KeyboardInterrupt):
            print("\n  已取消。")
            return False
        if verify(u, pw):
            set_current(u)
            print("  你好，%s。" % u)
            return True
        print("  不对。")
    return False


def clear() -> None:
    """取消整个账户体系，回到公共目录。"""
    for f in (_USERS, _SESSION):
        try:
            os.remove(f)
        except OSError:
            pass


def owner() -> str:
    """当前档案目录的归属者；没人登录时为空（= 公共目录）。"""
    if not has_accounts():
        return ""
    u = current_user()
    return u if u in _read_users() else ""
