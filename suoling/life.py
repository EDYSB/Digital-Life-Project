"""常驻生命循环：即使没人打开页面，档案也在走时间。

每 30 秒 tick 一次：
  - 记忆按艾宾浩斯曲线衰减，记录新变模糊的条目
  - 驱动累积、心情回落到基线
  - 可能形成一个新的意图/待发消息
  - 落盘，并把"生活事件"写进进程日志

这仍然是规则与计时器，不是意识；但它让"数字生命"从静态文件变成一个持续运行的过程。
"""

from __future__ import annotations

import datetime
import threading
import time
import traceback

from . import agency, learn, memory, pipeline, world


class LifeLoop:
    def __init__(self, interval: float = 30.0):
        self.interval = interval
        self.ticks = 0
        self.started_at = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        self.last_tick = None
        self.running = False
        self.events: list[dict] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run, name="echomind-life", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.running = False

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick_once()
            except Exception:  # noqa: BLE001
                traceback.print_exc()
            self._stop.wait(self.interval)

    def _log(self, name: str, text: str) -> None:
        with self._lock:
            self.events.append({
                "t": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                "name": name, "text": text,
            })
            self.events = self.events[-30:]

    def tick_once(self) -> None:
        now = datetime.datetime.now().astimezone()
        items = pipeline.list_minds()
        for item in items:
            try:
                profile = pipeline.load(item["id"])
                traits = {t["key"]: t["value"] for t in profile.get("traits", [])}
                memory.ensure(profile, traits)
                before_faded = sum(1 for m in profile["mind"]["memories"] if m.get("faded"))
                memory.decay(profile, now)
                after_faded = sum(1 for m in profile["mind"]["memories"] if m.get("faded"))
                if after_faded > before_faded:
                    self._log(profile["persona"]["name"], "有一段记忆变模糊了。")

                agency.ensure(profile, traits)
                before = (profile["mind"].get("agency") or {}).get("pending")
                agency.tick(profile, now)
                after = (profile["mind"].get("agency") or {}).get("pending")
                if after and not before:
                    self._log(profile["persona"]["name"], "她形成了一个念头：" + after.get("text", "")[:24])
                note = learn.study(profile, now)
                if note:
                    self._log(profile["persona"]["name"], "她自己学到一件事：" + note["text"][:22])
                w = world.evaluate(profile)
                if w.get("state") == "protective":
                    self._log(profile["persona"]["name"], "世界太暗了，她进入自我保护。")
                pipeline.save(profile)
            except Exception:  # noqa: BLE001
                continue
        with self._lock:
            self.ticks += 1
            self.last_tick = now.isoformat(timespec="seconds")

    def status(self) -> dict:
        with self._lock:
            return {
                "running": self.running,
                "ticks": self.ticks,
                "interval_seconds": self.interval,
                "started_at": self.started_at,
                "last_tick": self.last_tick,
                "events": list(reversed(self.events[-8:])),
                "note": "规则驱动的持续模拟，不是意识。",
            }
