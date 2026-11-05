import io
import os
import re

ROOT = r"D:\EDY_POWERQ\Digital Life Project"

# ---------- README: drop the credits section (it was the last one) ----------
p = os.path.join(ROOT, "README.md")
s = io.open(p, encoding="utf-8").read()
idx = s.find("## 形象署名 / Credits")
if idx > 0:
    s = s[:idx].rstrip() + "\n"
    io.open(p, "w", encoding="utf-8").write(s)
print("readme credits removed:", "Credits" not in s)

# ---------- index.html: drop live2d scripts and the credit footer ----------
p = os.path.join(ROOT, "web", "index.html")
h = io.open(p, encoding="utf-8").read()
before = h
h = re.sub(r'\s*<script src="/(vendor/(live2dcubismcore\.min|pixi\.min|cubism4\.min)\.js|live2d-view\.js)"></script>', '', h)
h = re.sub(r'\s*<footer class="?site-credit"?[^>]*>.*?</footer>', '', h, flags=re.S)
io.open(p, "w", encoding="utf-8").write(h)
print("scripts left:", h.count("live2d"), "| footer left:", "site-credit" in h)

# ---------- style.css: drop the credit rule ----------
p = os.path.join(ROOT, "web", "style.css")
c = io.open(p, encoding="utf-8").read()
c = re.sub(r'\n\.site-credit\{[^}]*\}\n?', '\n', c)
io.open(p, "w", encoding="utf-8").write(c)
print("css cleaned:", ".site-credit" not in c)

# ---------- .gitignore: live2d dir no longer exists ----------
p = os.path.join(ROOT, ".gitignore")
g = io.open(p, encoding="utf-8").read()
g = g.replace("web/live2d/\n", "")
io.open(p, "w", encoding="utf-8").write(g)
print("gitignore cleaned:", "live2d" not in g)

# ---------- 检查是否还有引用 ----------
hits = []
for dirpath, _, files in os.walk(os.path.join(ROOT, "web")):
    for f in files:
        if f.endswith((".html", ".js", ".css")):
            fp = os.path.join(dirpath, f)
            t = io.open(fp, encoding="utf-8", errors="ignore").read()
            if "live2d" in t.lower():
                hits.append(os.path.relpath(fp, ROOT))
print("remaining refs:", hits)
