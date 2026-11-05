import io
import re

W = r"D:\EDY_POWERQ\Digital Life Project\web"
p = W + r"\app.js"
s = io.open(p, encoding="utf-8").read()

if "function setAvatar(" not in s:
    s = s.replace("let avatarFallback = 0;", '''let avatarFallback = 0;

/* 只有确认加载成功才换图，失败就保留当前帧——不会出现裂图占位 */
const _avatarCache = {};
function setAvatar(src) {
  const img = document.querySelector('#avatar-gif');
  if (!img || !src) return;
  const key = src.split('?')[0];
  if (_avatarCache[key]) { img.src = src; return; }
  const probe = new Image();
  probe.onload = function () { _avatarCache[key] = true; img.src = src; };
  probe.onerror = function () { /* keep the previous frame */ };
  probe.src = src;
}''', 1)

    # 替换所有直接赋值
    s = re.sub(r"img\.src = '([^']+)' \+ Date\.now\(\);", r"setAvatar('\1?' + Date.now());", s)
    s = re.sub(r"img\.src = '([^']+)';", r"setAvatar('\1');", s)
    s = re.sub(r"av\.src = '([^']+)' \+ Date\.now\(\);", r"setAvatar('\1?' + Date.now());", s)
    s = re.sub(r"av2\.src = '([^']+)' \+ Date\.now\(\);", r"setAvatar('\1?' + Date.now());", s)
    s = re.sub(r"av3\.src = '([^']+)' \+ Date\.now\(\);", r"setAvatar('\1?' + Date.now());", s)

    io.open(p, "w", encoding="utf-8").write(s)

print("setAvatar:", "function setAvatar(" in s)
print("direct assignments left:", len(re.findall(r"\.src = '/assets/", s)))
