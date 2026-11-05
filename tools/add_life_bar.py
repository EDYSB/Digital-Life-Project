import io

ROOT = r"D:\EDY_POWERQ\Digital Life Project"
SU = ROOT + r"\suoling"
WEB = ROOT + r"\web"

# ---------- 1) life_state: skills, journal review, proactive letter ----------
p = SU + r"\life_state.py"
s = io.open(p, encoding="utf-8").read()
if "def skills(" not in s:
    s += '''

# ---------------------------------------------------------------- growth

# Skills grow with accumulated turns, weighted by the matching trait.
SKILLS = [
    ("listening", "倾听", "empathy"),
    ("noticing", "观察", "sensory"),
    ("keeping", "记事", "order"),
    ("talking", "说话", "creativity"),
    ("steadying", "定心", "stability"),
]


def skills(profile: dict) -> list:
    """Skill levels 0..5 derived from turns and traits; no separate storage."""
    n = turns(profile)
    traits = {t.get("key"): float(t.get("value") or 0) for t in (profile.get("traits") or [])}
    out = []
    for key, zh, trait in SKILLS:
        base = min(5.0, (n / 120.0) * (0.6 + traits.get(trait, 0.5)))
        out.append({"key": key, "name": zh, "level": round(base, 1)})
    return out


def journal_review(profile: dict, days: int = 7) -> dict:
    """Look back at the recent entries instead of only appending new ones."""
    entries = ((profile.get("mind") or {}).get("journal") or [])[-days:]
    if not entries:
        return {"days": 0, "line": "还没有写过日记。", "entries": []}
    moods = [e.get("text", "") for e in entries]
    return {
        "days": len(entries),
        "line": "最近 %d 天，记下了 %d 条。" % (len(entries), len(entries)),
        "entries": entries,
        "first": moods[0][:40] if moods else "",
    }


def letter(profile: dict, now=None) -> str:
    """A short proactive note, written from state rather than a template."""
    now = now or _dt.datetime.now()
    st = rhythm.state(now)
    d = summary(profile, now)
    who = (profile.get("persona") or {}).get("name") or "我"
    parts = []
    parts.append("%s。%s" % (d["calendar"]["name"] + "了。" if d["calendar"].get("today") else st["line"], ""))
    if d["presence"]["state"] in ("有一会儿了", "很久没见"):
        parts.append("你%s没来。" % d["presence"]["gap"])
    if d["stage"]["stage"] not in ("初次见面",):
        parts.append("我们现在算%s。" % d["stage"]["stage"])
    parts.append("我是%s。" % who)
    return "".join(parts).strip()
'''
    io.open(p, "w", encoding="utf-8").write(s)
print("life_state extended:", "def skills(" in s)

# ---------- 2) server: /api/life ----------
p = SU + r"\server.py"
s = io.open(p, encoding="utf-8").read()
if "/api/life" not in s:
    block = '''            if path == "/api/life":
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                mid = (qs.get("id") or [""])[0]
                prof = pipeline.load(mid) if mid else None
                if prof is None:
                    items = pipeline.list_minds()
                    prof = pipeline.load(items[0]["id"]) if items else None
                if prof is None:
                    return self._send_error(HTTPStatus.NOT_FOUND, "还没有档案。")
                from . import life_state

                data = life_state.summary(prof)
                data["skills"] = life_state.skills(prof)
                data["review"] = life_state.journal_review(prof)
                data["letter"] = life_state.letter(prof)
                return self._send_json(data)

'''
    s = s.replace("            return self._serve_static(path)", block + "            return self._serve_static(path)", 1)
    io.open(p, "w", encoding="utf-8").write(s)
print("api:", "/api/life" in s)

# ---------- 3) web: status bar ----------
p = WEB + r"\index.html"
h = io.open(p, encoding="utf-8").read()
if 'id="life-bar"' not in h:
    h = h.replace('<div class="avatar-bubble" id="avatar-bubble"></div>',
                  '<div class="life-bar" id="life-bar"></div>\n      <div class="avatar-bubble" id="avatar-bubble"></div>', 1)
    io.open(p, "w", encoding="utf-8").write(h)
print("html:", 'id="life-bar"' in h)

p = WEB + r"\style.css"
c = io.open(p, encoding="utf-8").read()
if ".life-bar" not in c:
    c += """
.life-bar{display:flex;gap:14px;justify-content:center;flex-wrap:wrap;
  font-size:11.5px;color:#7b8f9a;letter-spacing:.04em;margin:0 auto 8px;opacity:0;
  transition:opacity .3s}
.life-bar.on{opacity:1}
.life-bar b{color:#3d5560;font-weight:500}
.life-bar i{font-style:normal;color:#c3d2d9}
"""
    io.open(p, "w", encoding="utf-8").write(c)
print("css:", ".life-bar" in c)

p = WEB + r"\app.js"
j = io.open(p, encoding="utf-8").read()
if "renderLifeBar" not in j:
    j = j.replace("function startAvatarGif() {", '''async function renderLifeBar() {
  const bar = $('#life-bar');
  if (!bar) return;
  try {
    const r = await fetch('/api/life', { cache: 'no-store' });
    if (!r.ok) return;
    const d = await r.json();
    const bits = [];
    bits.push('作息 <b>' + (d.rhythm ? d.rhythm.phase : '—') + '</b>');
    if (d.presence) bits.push('在场 <b>' + d.presence.state + '</b>');
    if (d.stage) bits.push('关系 <b>' + d.stage.stage + '</b>');
    if (d.mood && d.mood.label) bits.push('心情 <b>' + d.mood.label + '</b>');
    if (d.calendar && d.calendar.name) bits.push('日子 <b>' + d.calendar.name + '</b>');
    if (d.skills) {
      const top = d.skills.slice().sort((a, b) => b.level - a.level)[0];
      if (top) bits.push('最熟 <b>' + top.name + '</b>');
    }
    bar.innerHTML = bits.join('<i>·</i>');
    bar.classList.add('on');
  } catch (e) { /* the bar is optional */ }
}

function startAvatarGif() {''', 1)
    j = j.replace("  idleIntent();\n  randomAction();", "  idleIntent();\n  randomAction();\n  renderLifeBar();\n  setInterval(renderLifeBar, 60000);", 1)
    io.open(p, "w", encoding="utf-8").write(j)
print("js:", "renderLifeBar" in j)
