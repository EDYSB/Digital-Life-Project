import io

p = r"D:\EDY_POWERQ\Digital Life Project\web\style.css"
s = io.open(p, encoding="utf-8").read()

rule = (
    "\n/* An <img> with an empty src renders a broken-image glyph; hide it. */\n"
    'img[src=""], img:not([src]){display:none!important}\n'
)
if 'img[src=""]' not in s:
    s = s + rule
    io.open(p, "w", encoding="utf-8").write(s)

print("css ok:", 'img[src=""]' in s)
