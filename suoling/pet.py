"""桌宠：把立绘放进一个小窗，能拖、能点、会说一句话。

    dl pet
    dl pet --test     1.2 秒后自动关闭
"""

from __future__ import annotations

import os
import random
import sys

import tkinter as tk

from . import core as core_mod

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDLE = os.path.join(ROOT, "web", "assets", "df-pet.png")
TALK = os.path.join(ROOT, "web", "assets", "df-pet-talk.png")
BG = "#0a1018"

LINES = [
    "我在。",
    "你今天还好吗？",
    "不用一直看着我，忙你的。",
    "记得喝水。",
    core_mod.LOVE_SHORT,
]


def main(duration_ms: int | None = None) -> None:
    if not os.path.isfile(IDLE):
        print("  找不到立绘：%s" % IDLE)
        return

    root = tk.Tk()
    root.title("Digital Life")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.configure(bg=BG)

    idle = tk.PhotoImage(file=IDLE)
    talk = tk.PhotoImage(file=TALK) if os.path.isfile(TALK) else idle
    w = idle.width()
    h = idle.height() + 34

    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    root.geometry("%dx%d+%d+%d" % (w, h, sw - w - 60, sh - h - 90))

    bubble = tk.Label(root, text="", bg="#ffffff", fg="#243038",
                      font=("Microsoft YaHei", 9), wraplength=w - 16, pady=4)
    bubble.pack(pady=(4, 0))
    pic = tk.Label(root, image=idle, bg=BG, bd=0)
    pic.pack()

    drag = {"x": 0, "y": 0}

    def say(text):
        bubble.config(text=text)
        pic.config(image=talk)
        root.after(1200, lambda: pic.config(image=idle))
        root.after(2600, lambda: bubble.config(text=""))

    def press(e):
        drag["x"] = e.x_root - root.winfo_x()
        drag["y"] = e.y_root - root.winfo_y()
        say(random.choice(LINES))

    def move(e):
        root.geometry("+%d+%d" % (e.x_root - drag["x"], e.y_root - drag["y"]))

    for wdg in (pic, bubble):
        wdg.bind("<Button-1>", press)
        wdg.bind("<B1-Motion>", move)
        wdg.bind("<Button-3>", lambda e: root.destroy())

    if duration_ms:
        root.after(duration_ms, root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
