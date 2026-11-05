"""Digital Life - terminal UI (TUI).

在 cmd / PowerShell 里单独开一个界面，不依赖浏览器：
    dl tui
    dl tui --id mind_xxxxxx

左：拟人像（半块字符 + 真彩色，会呼吸、眨眼）
右：对话流
底：状态条（心跳 / 情绪 / 记忆）与输入行

只用标准库：msvcrt 读键，ANSI 转义写屏。
"""

from __future__ import annotations

import math
import os
import shutil
import sys
import time

try:
    import msvcrt
except ImportError:  # 非 Windows 时降级为普通 REPL
    msvcrt = None

from . import dialogue, pipeline

ESC = "\x1b"
ACCENT = (79, 227, 255)
RESET = ESC + "[0m"


# ---------------------------------------------------------------- terminal control
def enable_vt() -> None:
    """Enable ANSI escapes in cmd.exe."""
    if os.name != "nt":
        return
    try:
        import ctypes

        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        k.GetConsoleMode(h, ctypes.byref(mode))
        k.SetConsoleMode(h, mode.value | 0x0004)
    except Exception:
        pass


def term_size() -> tuple[int, int]:
    s = shutil.get_terminal_size((100, 30))
    return max(60, s.columns), max(20, s.lines)


def put(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def goto(row: int, col: int) -> str:
    return "%s[%d;%dH" % (ESC, row, col)


def clear() -> None:
    put(ESC + "[2J" + ESC + "[H")


# ---------------------------------------------------------------- portrait
def pixel_color(u: float, v: float, t: float, glow: float) -> tuple[int, int, int] | None:
    """Colour of one pixel; None means transparent (keep the background)."""
    # Head ellipse.
    hx, hy, hrx, hry = 0.50, 0.40, 0.165, 0.205
    dx = (u - hx) / hrx
    dy = (v - hy) / hry
    in_head = dx * dx + dy * dy <= 1.0

    # Back hair.
    bx, by, brx, bry = 0.50, 0.395, 0.205, 0.235
    bdx = (u - bx) / brx
    bdy = (v - by) / bry
    in_hair_back = bdx * bdx + bdy * bdy <= 1.0

    # Shoulders.
    in_body = v > 0.735 and abs(u - 0.5) < 0.44
    if v > 0.735:
        # Shoulder line widens downwards.
        width = 0.20 + (v - 0.735) * 1.55
        in_body = abs(u - 0.5) < width

    # Eyes.
    eye_y = 0.415
    eye_dx = 0.062
    eye_rx, eye_ry = 0.036, 0.030
    blink = 1.0 - glow * 0.0  # 由外部传入的眨眼系数
    for sx in (-1, 1):
        ex = 0.5 + sx * eye_dx
        edx = (u - ex) / eye_rx
        edy = (v - eye_y) / (eye_ry * max(0.08, blink))
        d2 = edx * edx + edy * edy
        if d2 <= 1.0:
            # Iris: bright centre, cyan edge.
            k = min(1.0, math.sqrt(d2))
            r = int(200 * (1 - k) + 40 * k)
            g = int(250 * (1 - k) + 150 * k)
            b = int(255)
            return (r, g, b)

    if in_head:
        # Skin, very dark: an outline plus a faint highlight.
        shade = 1.0 - min(1.0, abs(u - 0.5) * 3.2)
        return (int(16 + 10 * shade), int(26 + 14 * shade), int(38 + 18 * shade))
    if in_hair_back:
        return (9, 15, 24)
    if in_body:
        return (10, 16, 25)
    return None


def render_portrait(width: int, height: int, t: float, blink_phase: float) -> list[str]:
    """Render the pixel art as text lines using the half-block char."""
    px_w = width
    px_h = height * 2
    rows: list[str] = []
    for cy in range(height):
        line: list[str] = []
        for cx in range(px_w):
            u = (cx + 0.5) / px_w
            v_top = (cy * 2 + 0.5) / px_h
            v_bot = (cy * 2 + 1.5) / px_h
            c_top = pixel_color(u, v_top, t, blink_phase)
            c_bot = pixel_color(u, v_bot, t, blink_phase)
            if c_top is None and c_bot is None:
                line.append(" ")
                continue
            if c_top is None:
                c_top = (4, 8, 12)
            if c_bot is None:
                c_bot = (4, 8, 12)
            line.append(
                "%s[38;2;%d;%d;%dm%s[48;2;%d;%d;%dm▀"
                % (ESC, c_top[0], c_top[1], c_top[2], ESC, c_bot[0], c_bot[1], c_bot[2])
            )
        rows.append("".join(line) + RESET)
    return rows


# ---------------------------------------------------------------- layout
class Tui:
    def __init__(self, profile: dict):
        self.p = profile
        self.per = profile.get("persona") or {}
        self.history: list[dict] = []
        self.lines: list[tuple[str, str]] = []   # (who, text)
        self.input = ""
        self.t0 = time.time()
        self.blink_at = time.time() + 3.0
        self.blink = 0.0
        self.running = True
        self.scroll = 0
        self._greet()

    # -- state
    def mood(self) -> tuple[float, float, str]:
        mind = (self.p.get("mind") or {}).get("mood") or {}
        return (
            float(mind.get("arousal", 0.5)),
            float(mind.get("valence", 0.55)),
            str(mind.get("label") or self.per.get("mood") or "平静 · 中性"),
        )

    def bpm(self) -> int:
        a, _, _ = self.mood()
        return int(58 + a * 34 + math.sin((time.time() - self.t0) * 1.4) * 2)

    def _greet(self) -> None:
        opening = self.per.get("greeting") or "连接已建立。"
        self.lines.append(("sys", "%s · %s" % (self.per.get("name", "—"), self.per.get("title", ""))))
        self.lines.append(("ai", opening))

    # -- drawing
    def draw(self) -> None:
        w, h = term_size()
        left_w = max(26, min(38, w // 3))
        top, bottom = 2, h - 2

        out: list[str] = [ESC + "[?25l"]
        out.append(goto(1, 1) + ESC + "[48;2;6;10;16m" + ESC + "[38;2;200;230;245m")
        title = " 数字生命 · %s " % self.per.get("code", "—")
        head = title + " " * max(0, w - len(title) - 1)
        out.append(goto(1, 1) + head[:w])

        # Left column: portrait.
        pw = left_w - 2
        ph = max(6, top + (bottom - top) // 2 - 2)
        blink_gap = time.time() - self.blink_at
        if 0 <= blink_gap < 0.12:
            self.blink = 1.0
        else:
            self.blink = 0.0
            if blink_gap > 0 and blink_gap < 0.2:
                self.blink = 0.0

        rows = render_portrait(pw, ph, time.time() - self.t0, 1.0 - self.blink)
        for i, r in enumerate(rows):
            out.append(goto(top + i, 2) + r)

        # Vertical divider.
        for y in range(top, bottom + 1):
            out.append(goto(y, left_w) + ESC + "[38;2;40;60;75m│" + RESET)

        # Right column: conversation.
        rw = w - left_w - 2
        body_h = bottom - top
        visible = self._wrap_lines(rw, body_h)
        for i, (who, text, color) in enumerate(visible):
            out.append(goto(top + i, left_w + 2) + color + text + RESET)

        # Status bar.
        a, v_, label = self.mood()
        drives = ((self.p.get("mind") or {}).get("agency") or {}).get("drives") or {}
        mem = len(((self.p.get("mind") or {}).get("memories")) or [])
        bar = " 心跳 %d bpm   %s   记忆 %d   联结 %d%%   ♥ LOVE " % (
            self.bpm(), label, mem, int(float(drives.get("connection", 0)) * 100))
        out.append(goto(h - 1, 1) + ESC + "[48;2;8;14;22m" + ESC + "[38;2;90;150;175m" + bar.ljust(w)[:w])
        out.append(RESET)

        # Input line.
        prompt = " > "
        out.append(goto(h, 1) + ESC + "[38;2;79;227;255m" + prompt + RESET)
        out.append(goto(h, len(prompt) + 1) + ESC + "[38;2;230;245;255m" + self.input[-max(10, w - 8):] + RESET)
        out.append(goto(h, len(prompt) + 1 + len(self.input[-max(10, w - 8):])) + ESC + "[?25h")
        put("".join(out))

    def _wrap_lines(self, width: int, height: int) -> list[tuple[str, str, str]]:
        rows: list[tuple[str, str, str]] = []
        for who, text in self.lines[-60:]:
            if who == "sys":
                rows.append(("", text, ESC + "[38;2;90;120;140m"))
                rows.append(("", "", ""))
                continue
            prefix = "你  " if who == "me" else "%s  " % self.per.get("name", "她")
            color = ESC + "[38;2;120;180;205m" if who == "me" else ESC + "[38;2;225;240;250m"
            head = "%s%s" % (prefix, "")
            avail = max(8, width - len(prefix))
            chunks = []
            cur = ""
            for ch in text:
                if len(cur) >= avail:
                    chunks.append(cur)
                    cur = ""
                cur += ch
            if cur:
                chunks.append(cur)
            for i, c in enumerate(chunks):
                if i == 0:
                    rows.append(("", prefix + c, color))
                else:
                    rows.append(("", " " * len(prefix) + c, color))
            rows.append(("", "", ""))
        # Keep only the last `height` rows.
        return rows[-height:] if len(rows) > height else rows

    # -- interaction
    def read_key(self) -> str:
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):      # 方向键等
            msvcrt.getwch()
            return ""
        return ch

    def submit(self) -> None:
        text = self.input.strip()
        self.input = ""
        if not text:
            return
        if text in ("/quit", "/exit", "exit", "q"):
            self.running = False
            return
        self.lines.append(("me", text))
        self.lines.append(("ai", "…"))
        self.draw()
        try:
            r = dialogue.reply(self.p, text, self.history)
            reply = r.get("text", "")
        except Exception as exc:  # noqa: BLE001
            reply = "（出错了：%s）" % exc
        self.lines[-1] = ("ai", reply)
        self.history.append({"role": "user", "text": text})
        self.history.append({"role": "assistant", "text": reply})
        self.draw()

    def run(self) -> None:
        enable_vt()
        put(ESC + "[?1049h")     # 备用屏幕
        clear()
        self.draw()
        try:
            while self.running:
                ch = self.read_key()
                if ch == "":
                    continue
                if ch == "\x03":     # Ctrl+C
                    break
                if ch == "\r":
                    self.submit()
                elif ch in ("\x08", "\x7f"):
                    self.input = self.input[:-1]
                    self.draw()
                elif ch == "\x1b":
                    break
                elif ch.isprintable():
                    self.input += ch
                    self.draw()
                # Blink.
                if time.time() - self.blink_at > 4.0:
                    self.blink_at = time.time()
        finally:
            put(RESET + ESC + "[?1049l")
            put("已退出。\n")


def main(mind_id: str | None = None) -> None:
    items = pipeline.list_minds()
    if not items:
        print("还没有档案。先运行：dl demo")
        return
    if mind_id:
        profile = pipeline.load(mind_id)
    else:
        profile = pipeline.load(items[0]["id"])
    if msvcrt is None or not sys.stdout.isatty():
        _plain(profile)
        return
    Tui(profile).run()


def _plain(profile: dict) -> None:
    per = profile.get("persona") or {}
    print("\n%s · %s" % (per.get("name"), per.get("title")))
    print("（输入 /quit 退出）\n")
    history: list[dict] = []
    print(per.get("greeting") or "我在。")
    while True:
        try:
            text = input("你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text in ("/quit", "/exit", "exit"):
            break
        r = dialogue.reply(profile, text, history)
        print("%s > %s" % (per.get("name"), r["text"]))
        history.append({"role": "user", "text": text})
        history.append({"role": "assistant", "text": r["text"]})
