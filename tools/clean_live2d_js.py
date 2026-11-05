import io
import re

p = r"D:\EDY_POWERQ\Digital Life Project\web\app.js"
s = io.open(p, encoding="utf-8").read()

# 1) 删掉 tryLive2D helper
s = re.sub(r'/\*[^*]*Live2D[^*]*\*/\s*\n?async function tryLive2D\(host, setter\) \{.*?\n\}\n', '', s, flags=re.S)

# 2) 删掉两处调用
s = re.sub(r'\n\s*tryLive2D\([^;]*\);', '', s)

# 3) 欢迎页里的 Live2D 分支
s = re.sub(r'\n\s*if \(window\.Live2DView && !welcomePersona\) \{.*?\n\s{2}\}\n', '\n', s, flags=re.S)

io.open(p, "w", encoding="utf-8").write(s)
print("live2d refs left:", s.lower().count("live2d"))
