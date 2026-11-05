"""records: a small SQLite log of everything that was said.

The .mind file stays human-readable config; this is the raw ledger, so the
journal and the timeline can be rebuilt from facts rather than from memory.

    minds/records.db
      turns(id, mind_id, at, role, text, intent)
      days(mind_id, day, summary)
"""

from __future__ import annotations

import datetime as _dt
import os
import sqlite3
import threading

_LOCK = threading.Lock()
_DB = {"path": ""}

SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mind_id TEXT NOT NULL,
    at TEXT NOT NULL,
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    intent TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_turns_mind ON turns(mind_id, at);
CREATE TABLE IF NOT EXISTS days (
    mind_id TEXT NOT NULL,
    day TEXT NOT NULL,
    summary TEXT DEFAULT '',
    PRIMARY KEY (mind_id, day)
);
"""


def path(root: str | None = None) -> str:
    if _DB["path"]:
        return _DB["path"]
    root = root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    d = os.path.join(root, "minds")
    os.makedirs(d, exist_ok=True)
    _DB["path"] = os.path.join(d, "records.db")
    return _DB["path"]


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(path(), timeout=5)
    c.executescript(SCHEMA)
    return c


def add_turn(mind_id: str, role: str, text: str, intent: str = "") -> None:
    if not mind_id or not text:
        return
    now = _dt.datetime.now().isoformat(timespec="seconds")
    with _LOCK:
        c = _conn()
        with c:
            c.execute(
                "INSERT INTO turns(mind_id, at, role, text, intent) VALUES (?,?,?,?,?)",
                (mind_id, now, role, text[:2000], intent or ""),
            )
        c.close()


def recent(mind_id: str, limit: int = 40) -> list:
    c = _conn()
    rows = c.execute(
        "SELECT at, role, text FROM turns WHERE mind_id=? ORDER BY id DESC LIMIT ?",
        (mind_id, limit),
    ).fetchall()
    c.close()
    return [{"at": r[0], "role": r[1], "text": r[2]} for r in reversed(rows)]


def days(mind_id: str, limit: int = 14) -> list:
    c = _conn()
    rows = c.execute(
        "SELECT substr(at,1,10) AS d, COUNT(*) FROM turns WHERE mind_id=? "
        "GROUP BY d ORDER BY d DESC LIMIT ?",
        (mind_id, limit),
    ).fetchall()
    c.close()
    return [{"day": r[0], "turns": r[1]} for r in rows]


def digest(mind_id: str, day: str | None = None) -> str:
    """Rebuild a day's summary from the ledger."""
    day = day or _dt.date.today().isoformat()
    c = _conn()
    rows = c.execute(
        "SELECT role, text FROM turns WHERE mind_id=? AND substr(at,1,10)=? ORDER BY id",
        (mind_id, day),
    ).fetchall()
    c.close()
    if not rows:
        return ""
    mine = [r[1] for r in rows if r[0] == "me"]
    hers = [r[1] for r in rows if r[0] == "her"]
    bits = ["%s：说了 %d 句，回了 %d 句。" % (day, len(mine), len(hers))]
    if mine:
        bits.append("最开头是「%s」。" % mine[0][:20])
    if hers:
        bits.append("我记得我说过「%s」。" % hers[-1][:20])
    text = "".join(bits)
    with _LOCK:
        c = _conn()
        with c:
            c.execute(
                "INSERT OR REPLACE INTO days(mind_id, day, summary) VALUES (?,?,?)",
                (mind_id, day, text),
            )
        c.close()
    return text
