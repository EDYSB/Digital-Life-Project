"""一键生成自包含的记忆档案（单文件 HTML，无外部依赖）。

包含：身份契约、七维、记忆星图（SVG）、遗忘曲线、心情轨迹、情景记忆清单。
"""

from __future__ import annotations

import html
import math
import random

from . import admin, memory


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _hash(s: str) -> int:
    h = 2166136261
    for ch in s:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def _star_map(profile: dict, report: dict, W: int = 760, H: int = 360) -> str:
    memories = (profile.get("mind") or {}).get("memories") or []
    if not memories:
        return '<p class="empty">还没有情景记忆。</p>'
    cx, cy, rx, ry = W / 2, H / 2 + 6, W * 0.4, H * 0.38
    now = memory._now()
    pts = []
    rnd = random.Random(_hash(profile.get("id", "")))
    for m in memories:
        a = rnd.random() * math.tau
        r = 0.18 + rnd.random() * 0.72
        x = cx + math.cos(a) * rx * r
        y = cy + math.sin(a) * ry * r
        ret = memory.retention(m, now)
        pts.append({"m": m, "x": x, "y": y, "r": ret})
    edges = []
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            ka = set(pts[i]["m"].get("keywords", []))
            kb = set(pts[j]["m"].get("keywords", []))
            if ka and kb and len(ka & kb) >= 2:
                edges.append((i, j))
    out = ['<svg viewBox="0 0 %d %d" class="starmap" role="img" aria-label="记忆星图">' % (W, H)]
    out.append('<defs><radialGradient id="glow"><stop offset="0" stop-color="#38e8ff" stop-opacity=".35"/>'
               '<stop offset="1" stop-color="#38e8ff" stop-opacity="0"/></radialGradient></defs>')
    out.append('<ellipse cx="%.1f" cy="%.1f" rx="%.1f" ry="%.1f" fill="none" stroke="#2a4a58" stroke-width="1" stroke-dasharray="4 6"/>' % (cx, cy, rx, ry))
    for i, j in edges:
        a, b = pts[i], pts[j]
        out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#2e6b7d" stroke-opacity="%.2f" stroke-width="1"/>'
                   % (a["x"], a["y"], b["x"], b["y"], 0.15 + 0.35 * min(a["r"], b["r"])))
    for p in pts:
        r = 2.5 + p["r"] * 5
        op = 0.18 + p["r"] * 0.82
        color = {"emotion": "#ff5fa2", "feeling": "#ff8bbd", "identity": "#9b6bff",
                 "fact": "#b79bff", "preference": "#ffb057", "habit": "#ffc98a",
                 "event": "#38e8ff", "birth": "#e8f6ff"}.get(p["m"].get("kind"), "#9fb4c0")
        out.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s" fill-opacity="%.2f"/>'
                   % (p["x"], p["y"], r * 2.4, "#38e8ff", 0.04 * p["r"]))
        out.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s" fill-opacity="%.2f"/>'
                   % (p["x"], p["y"], r, color, op))
        if p["r"] >= 0.5:
            out.append('<text x="%.1f" y="%.1f" font-size="8" fill="#9fc3cf" text-anchor="middle">%s</text>'
                       % (p["x"], p["y"] - r - 6, _esc(p["m"].get("text", "")[:10])))
    out.append('</svg>')
    return "".join(out)


def _curve(report: dict) -> str:
    proj = report.get("projection") or []
    if not proj:
        return ""
    W, H = 760, 180
    pad = 30
    x = lambda d: pad + d / 60 * (W - pad * 2)
    y = lambda v: H - pad - v * (H - pad * 2)
    pts = " ".join("%.1f,%.1f" % (x(p["day"]), y(p["retention"])) for p in proj)
    area = "%.1f,%.1f " % (x(0), H - pad) + pts + " %.1f,%.1f" % (x(60), H - pad)
    labels = "".join('<text x="%.1f" y="%d" font-size="9" fill="#6f8b98" text-anchor="middle">%dd</text>'
                     % (x(p["day"]), H - 8, p["day"]) for p in proj if p["day"] in (0, 7, 30, 60))
    return ('<svg viewBox="0 0 %d %d" class="curve">'
            '<polygon points="%s" fill="#38e8ff" fill-opacity=".08"/>'
            '<polyline points="%s" fill="none" stroke="#38e8ff" stroke-width="2"/>%s</svg>'
            % (W, H, area, pts, labels))


def _mood(profile: dict) -> str:
    hist = ((profile.get("mind") or {}).get("mood") or {}).get("history") or []
    hist = hist[-40:]
    if len(hist) < 2:
        return '<p class="empty">心情轨迹还不够长。</p>'
    W, H = 760, 120
    def pt(i, v):
        return (20 + i / (len(hist) - 1) * (W - 40), H - 14 - v * (H - 28))
    vline = " ".join("%.1f,%.1f" % pt(i, h.get("v", .5)) for i, h in enumerate(hist))
    aline = " ".join("%.1f,%.1f" % pt(i, h.get("a", .5)) for i, h in enumerate(hist))
    return ('<svg viewBox="0 0 %d %d" class="curve">'
            '<polyline points="%s" fill="none" stroke="#38e8ff" stroke-width="1.6"/>'
            '<polyline points="%s" fill="none" stroke="#ff5fa2" stroke-opacity=".7" stroke-width="1.2"/></svg>'
            % (W, H, vline, aline))


def build(profile: dict) -> str:
    report = admin.mind_report(profile)
    p = profile.get("persona") or {}
    traits = profile.get("traits") or []
    memories = ((profile.get("mind") or {}).get("memories") or [])
    memories = sorted(memories, key=lambda m: -(m.get("retention") or 0))
    mind = profile.get("mind") or {}
    world = mind.get("world") or {}
    rows = []
    for m in memories[:40]:
        r = round(float(m.get("retention", 0)) * 100)
        rows.append(
            "<tr><td>%s</td><td>%s</td><td><div class='bar'><i style='width:%d%%'></i></div></td><td>%d%%</td></tr>"
            % (_esc({ "birth": "出生", "emotion": "情绪", "feeling": "感受", "identity": "身份",
                      "fact": "事实", "preference": "偏好", "habit": "习惯", "event": "事件"}.get(m.get("kind"), m.get("kind"))),
               _esc(m.get("text", "")), r, r))
    trait_html = "".join("<div class='trait'><span>%s</span><div class='bar'><i style='width:%d%%'></i></div><em>%d</em></div>"
                         % (_esc(t["name"]), round(t["value"] * 100), round(t["value"] * 100)) for t in traits)
    css = """
    :root{--bg:#070b10;--panel:#0d151d;--line:#1c2f3a;--text:#e6f0f4;--muted:#8ba3af;--cyan:#38e8ff}
    *{box-sizing:border-box}body{margin:0;background:radial-gradient(900px 500px at 50% -10%,#0e2230,#070b10 60%);color:var(--text);font-family:"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.7}
    .wrap{max-width:900px;margin:0 auto;padding:48px 28px 80px}
    h1{font-size:42px;margin:8px 0 4px;letter-spacing:.04em}h2{font-size:18px;margin:36px 0 12px;letter-spacing:.08em;font-weight:500}
    .eyebrow{font-family:Consolas,monospace;font-size:10px;letter-spacing:.3em;color:var(--cyan)}
    .title{font-family:Consolas,monospace;font-size:11px;letter-spacing:.24em;color:var(--muted)}
    .lede{font-size:15px;color:#cfe3ea;max-width:680px;margin:16px 0}
    .meta{font-family:Consolas,monospace;font-size:10.5px;color:var(--muted);line-height:2}
    .panel{border:1px solid var(--line);border-radius:14px;background:var(--panel);padding:18px 20px}
    .starmap{width:100%;height:auto;display:block;background:radial-gradient(60% 70% at 50% 50%,#0e2230,#070b10);border-radius:12px}
    .curve{width:100%;height:auto;display:block}
    .trait{display:grid;grid-template-columns:54px 1fr 32px;gap:10px;align-items:center;font-size:11.5px;margin:7px 0;color:var(--muted)}
    .bar{height:3px;background:#1a2732;border-radius:3px;overflow:hidden}.bar i{display:block;height:100%;background:linear-gradient(90deg,#19c2d6,#38e8ff)}
    table{width:100%;border-collapse:collapse;font-size:12px}th,td{text-align:left;padding:7px 6px;border-bottom:1px solid #14232c;vertical-align:top}
    th{font-size:10px;letter-spacing:.1em;color:#6f8b98;font-weight:400}td:nth-child(3){width:22%}td:last-child{font-family:Consolas,monospace;color:#8ba3af;text-align:right;width:42px}
    .badge{display:inline-block;font-size:10px;border:1px solid var(--line);border-radius:999px;padding:3px 9px;color:var(--muted);margin-right:6px}
    .empty{color:#6f8b98;font-size:12px}
    .foot{margin-top:40px;padding-top:16px;border-top:1px solid var(--line);font-size:10.5px;color:#6f8b98;line-height:1.9}
    @media print{body{background:#fff;color:#111}.panel{background:#fff;border-color:#ddd}.starmap{background:#f7fbfd}}
    """
    return """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>%(name)s · 记忆档案</title><style>%(css)s</style></head><body><div class="wrap">
<div class="eyebrow">MEMORY ARCHIVE · 记忆档案</div>
<h1>%(name)s</h1><div class="title">%(title)s</div>
<p class="lede">%(one)s</p>
<div class="meta">编号 %(id)s · 生于 %(created)s<br>
心情 %(mood)s · 会话 %(sessions)s 次 · 消息 %(messages)s 条<br>
记忆 %(count)s 条（清晰 %(live)s / 模糊 %(faded)s）· 平均留存 %(avg)s%% · 半衰期约 %(half)s 天<br>
世界稳定度 %(stability)s%% · %(world)s</div>

<h2>七维</h2><div class="panel">%(traits)s</div>

<h2>记忆星图</h2><div class="panel">%(starmap)s</div>

<h2>遗忘曲线</h2><div class="panel">%(curve)s</div>

<h2>心情轨迹</h2><div class="panel">%(mood)s</div>

<h2>遗忘记录</h2><div class="panel"><table><thead><tr><th>时间</th><th>被忘掉的</th></tr></thead><tbody>%(forgot)s</tbody></table></div>

<h2>情景记忆</h2><div class="panel"><table><thead><tr><th>类型</th><th>内容</th><th>留存</th><th>&#37;</th></tr></thead><tbody>%(rows)s</tbody></table></div>

<div class="foot">
它不是 XXX 的复活，而是一个由脑波、基因、面孔与对话生成的新个体。<br>
记忆按艾宾浩斯曲线衰减，复述会延缓遗忘；出生记忆更耐久。<br>
本档案由「数字生命初级」生成 · 数据只在本机。
</div></div></body></html>""" % {
        "name": _esc(p.get("name", "未命名")), "title": _esc(p.get("title", "")),
        "one": _esc(p.get("one_line", "")), "id": _esc(profile.get("id", "")),
        "created": _esc(profile.get("created_at", "")),
        "mood": _esc((mind.get("mood") or {}).get("label", "—")),
        "sessions": report.get("sessions", 0), "messages": report.get("messages", 0),
        "count": len(memories), "live": report["memories"]["live"], "faded": report["memories"]["faded"],
        "avg": round(report["memories"]["avg_retention"] * 100),
        "half": report.get("half_life_days") if report.get("half_life_days") is not None else "—",
        "stability": round(float(world.get("stability", 1)) * 100), "world": _esc(world.get("label", "稳定")),
        "traits": trait_html, "starmap": _star_map(profile, report), "curve": _curve(report),
        "mood": _mood(profile), "rows": "".join(rows),
        "forgot": "".join("<tr><td>%s</td><td>%s</td></tr>" % (_esc(e.get("t", "")[:16]), _esc(e.get("text", "")))
                          for e in [x for x in (mind.get("events") or []) if x.get("type") == "forgot"][-12:]) or "<tr><td>—</td><td>还没有彻底忘掉的事。</td></tr>",
        "css": css,
    }
