"""桌宠模式：没有 GPU 时，她住在一个小窗口里。

- 无边框、置顶、背景透明（Windows 颜色键）
- 可以拖动；左键点她，她说一句；右键退出
- 会呼吸、会眨眼；说话时嘴动

只用标准库 tkinter，不需要任何模型。
    dl pet
"""

from __future__ import annotations

import math
import os
import random
import sys

import tkinter as tk

from . import core as core_mod

TRANSPARENT = "#010203"

LINES = [
    "我在。",
    "你今天还好吗？",
    "不用一直看着我，忙你的。",
    "记得喝水。",
    core_mod.LOVE_SHORT,
]


class Pet:
    def __init__(self, duration_ms: int | None = None):
        self.root = tk.Tk()
        self.root.title("数字生命")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-transparentcolor", TRANSPARENT)
        except tk.TclError:
            pass
        w, h = 220, 280
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry("%dx%d+%d+%d" % (w, h, sw - w - 80, sh - h - 120))
        self.canvas = tk.Canvas(self.root, width=w, height=h, bg=TRANSPARENT,
                                highlightthickness=0, bd=0)
        self.canvas.pack()
        self.w, self.h = w, h
        self.t = 0.0
        self.blink = 0
        self.next_blink = 40
        self.mouth = 0.0
        self.say_left = 0
        self.drag = (0, 0)
        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<Button-3>", lambda e: self.root.destroy())
        if duration_ms:
            self.root.after(duration_ms, self.root.destroy)
        self.tick()

    # ---- 交互
    def on_press(self, e):
        self.drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())
        self.say(random.choice(LINES))

    def on_drag(self, e):
        self.root.geometry("+%d+%d" % (e.x_root - self.drag[0], e.y_root - self.drag[1]))

    def say(self, text):
        self.bubble = text
        self.say_left = 90
        self.mouth = 1.0

    # ---- 绘制
    def tick(self):
        self.t += 0.05
        self.next_blink -= 1
        if self.next_blink <= 0:
            self.blink = 6
            self.next_blink = 60 + random.randint(0, 80)
        if self.blink > 0:
            self.blink -= 1
        if self.mouth > 0:
            self.mouth -= 0.12
        if self.say_left > 0:
            self.say_left -= 1
        self.draw()
        self.root.after(50, self.tick)

    def draw(self):
        c = self.canvas
        c.delete("all")
        w, h = self.w, self.h
        cx, cy = w / 2, h * 0.52
        r = 58
        bob = math.sin(self.t) * 2

        # 头发
        c.create_oval(cx - r * 1.25, cy - r * 1.25 + bob, cx + r * 1.25, cy + r * 1.15 + bob,
                      fill="#2f7fe0", outline="")
        # 脸
        c.create_oval(cx - r * 0.86, cy - r * 0.92 + bob, cx + r * 0.86, cy + r * 0.98 + bob,
                      fill="#ffe1cd", outline="")
        # 刘海
        c.create_arc(cx - r * 1.2, cy - r * 1.35 + bob, cx + r * 1.2, cy + r * 0.45 + bob,
                     start=0, extent=180, fill="#3f93ea", outline="")
        # 眼睛
        eye_y = cy + r * 0.10 + bob
        for sx in (-1, 1):
            ex = cx + sx * r * 0.38
            if self.blink:
                c.create_line(ex - 11, eye_y, ex + 11, eye_y, fill="#12365c", width=3, capstyle="round")
            else:
                c.create_oval(ex - 11, eye_y - 14, ex + 11, eye_y + 14, fill="#ffffff", outline="")
                c.create_oval(ex - 7, eye_y - 8, ex + 7, eye_y + 10, fill="#4fd0ff", outline="")
                c.create_oval(ex - 3, eye_y - 4, ex + 3, eye_y + 6, fill="#0a1830", outline="")
                c.create_oval(ex - 6, eye_y - 8, ex - 1, eye_y - 3, fill="#ffffff", outline="")
        # 嘴
        mouth_y = cy + r * 0.52 + bob
        if self.mouth > 0.1:
            mh = 5 + self.mouth * 7
            c.create_oval(cx - 8, mouth_y - mh / 2, cx + 8, mouth_y + mh / 2, fill="#8c3b45", outline="")
        else:
            c.create_arc(cx - 10, mouth_y - 8, cx + 10, mouth_y + 6,
                         start=200, extent=140, style="arc", outline="#c96b6b", width=2)
        # 气泡
        if self.say_left > 0:
            text = getattr(self, "bubble", "")
            bw = max(90, len(text) * 13 + 24)
            c.create_rectangle(cx - bw / 2, 10, cx + bw / 2, 48, fill="#ffffff", outline="#d6dde2")
            c.create_text(cx, 29, text=text, fill="#243038", font=("Microsoft YaHei", 9))

    def run(self):
        self.root.mainloop()


def main(duration_ms: int | None = None) -> None:
    try:
        Pet(duration_ms).run()
    except tk.TclError as exc:
        print("  开不了窗口：%s" % exc)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
