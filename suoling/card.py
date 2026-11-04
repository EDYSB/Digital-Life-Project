"""Digital Life Card：一张可打印/保存的数字生命卡。"""

from __future__ import annotations

import html


def _e(s):
    return html.escape(str(s if s is not None else ""))


def build(profile: dict) -> str:
    p = profile.get("persona") or {}
    mind = profile.get("mind") or {}
    world = mind.get("world") or {}
    traits = profile.get("traits") or []
    code = p.get("code") or ("DL-" + profile.get("id", "")[-6:].upper())
    name = p.get("name") or code
    dna = profile.get("dna") or {}
    eeg = profile.get("eeg") or {}
    mem = len(mind.get("memories") or [])
    sessions = (mind.get("stats") or {}).get("sessions", 0)
    bars = "".join(
        "<div class='tr'><span>%s</span><div class='bar'><i style='width:%d%%'></i></div><em>%d</em></div>"
        % (_e(t["name"]), round(t["value"] * 100), round(t["value"] * 100)) for t in traits)
    return """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>%(code)s · Digital Life Card</title><style>
*{box-sizing:border-box}body{margin:0;background:#fff;color:#111;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
.card{width:720px;margin:40px auto;border:1px solid #111;padding:28px 30px 22px}
.top{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:1px solid #111;padding-bottom:14px}
.brand{font-size:11px;letter-spacing:.24em;color:#666}
.code{font-family:Consolas,monospace;font-size:28px;letter-spacing:.04em;margin-top:6px}
.level{font-size:10px;border:1px solid #111;padding:2px 8px;border-radius:2px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:22px;margin-top:20px}
h3{font-size:11px;letter-spacing:.14em;color:#666;font-weight:400;margin:0 0 8px}
.row{font-size:12px;line-height:1.9;color:#333}
.row b{font-family:Consolas,monospace;font-weight:400;color:#111}
.tr{display:grid;grid-template-columns:52px 1fr 30px;gap:8px;align-items:center;font-size:11px;color:#555;margin:5px 0}
.bar{height:3px;background:#e8e8e8;border-radius:2px;overflow:hidden}.bar i{display:block;height:100%%;background:#111}
.tr em{font-style:normal;font-family:Consolas,monospace;font-size:10px;text-align:right;color:#666}
.codebar{display:flex;gap:2px;height:34px;margin-top:18px;align-items:flex-end}
.codebar i{display:block;background:#111}
.foot{display:flex;justify-content:space-between;margin-top:18px;padding-top:12px;border-top:1px solid #ddd;font-size:10px;color:#777}
@media print{body{margin:0}.card{margin:0;border:0}}
</style></head><body><div class="card">
  <div class="top"><div><div class="brand">DIGITAL LIFE PROJECT</div><div class="code">%(code)s</div></div><div class="level">LEVEL 1</div></div>
  <div class="grid">
    <div>
      <h3>IDENTITY</h3>
      <div class="row">名称 <b>%(name)s</b><br>生于 <b>%(born)s</b><br>会话 <b>%(sessions)s</b> · 记忆 <b>%(mem)s</b><br>世界稳定度 <b>%(stab)s%%</b></div>
    </div>
    <div>
      <h3>SOURCE</h3>
      <div class="row">脑波 <b>%(eeg_s)s</b> 秒 · <b>%(eeg_ch)s</b> 导联<br>基因 <b>%(markers)s</b> 个位点<br>声音 <b>%(voice)s</b> · 面孔 <b>%(face)s</b></div>
    </div>
    <div>
      <h3>SEVEN DIMENSIONS</h3>
      %(bars)s
    </div>
    <div>
      <h3>NOTES</h3>
      <div class="row">由脑波、基因、面孔与对话生成的模拟进程。<br>记忆会衰减，心情会漂移，驱动会累积。<br>不是意识复制，不是诊断。</div>
    </div>
  </div>
  <div class="codebar">%(codebar)s</div>
  <div class="foot"><span>%(id)s</span><span>Digital Life Project · L1</span></div>
</div></body></html>""" % {
        "code": _e(code), "name": _e(name), "born": _e((profile.get("created_at") or "")[:16].replace("T", " ")),
        "sessions": sessions, "mem": mem, "stab": round(float(world.get("stability", 1)) * 100),
        "eeg_s": round(float(eeg.get("seconds", 0))), "eeg_ch": eeg.get("n_channels", 4),
        "markers": (dna.get("coverage") or {}).get("markers_hit", 0),
        "voice": "有" if (profile.get("voice") or {}).get("metrics") else "无",
        "face": "有" if (profile.get("avatar") or {}).get("views") or (profile.get("avatar") or {}).get("sprite") else "无",
        "bars": bars,
        "codebar": "".join("<i style='width:%dpx;height:%dpx'></i>" % (2 + (i * 7) % 6, 12 + (i * 13) % 22) for i in range(46)),
        "id": _e(profile.get("id", "")),
    }
