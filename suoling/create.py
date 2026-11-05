"""create: hand-build a digital life from the command line.

This is the only way to create a dossier without uploading biosignals.
The skeleton comes from the bundled samples (so every field the web needs
exists), then the seven traits, the name and the voice are overwritten by
hand. The result is deterministic: same answers -> same mind id.

    dl create
    dl create --name 小满 --voice warm --traits 好奇=70,共情=80
"""

from __future__ import annotations

import hashlib
import os

from . import eeg as eeg_mod, genome as genome_mod, pipeline

KEYS = [
    ("curiosity", "好奇"),
    ("empathy", "共情"),
    ("order", "秩序"),
    ("alertness", "警觉"),
    ("creativity", "创造"),
    ("stability", "定力"),
    ("sensory", "感受力"),
]

VOICES = {"1": "calm", "2": "warm", "3": "sharp", "4": "neutral"}


def _ask(prompt: str, default: str = "") -> str:
    try:
        val = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit("已取消。")
    return val or default


def _parse_traits(text: str) -> dict:
    out = {}
    if not text:
        return out
    for part in text.replace("，", ",").split(","):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        k = k.strip()
        for key, zh in KEYS:
            if k in (key, zh):
                try:
                    out[key] = max(0.0, min(1.0, float(v) / 100.0))
                except ValueError:
                    pass
    return out


def run(name: str = "", voice: str = "", traits_text: str = "") -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    eeg_path = os.path.join(root, "samples", "eeg_meditation.csv")
    dna_path = os.path.join(root, "samples", "dna_sensitive.fasta")
    if not (os.path.isfile(eeg_path) and os.path.isfile(dna_path)):
        raise SystemExit("示例数据不存在，请先运行：python tools/make_samples.py")

    print("")
    print("  手工创造一个数字生命")
    print("  " + "─" * 40)
    name = name or _ask("  名字：", "无名")
    if not voice:
        print("  说话方式：1 静水  2 暖流  3 刃口  4 素面")
        voice = VOICES.get(_ask("  选择（默认 1）：", "1"), "calm")
    if not traits_text:
        print("  七维数值 0-100，直接回车用默认 50，格式 好奇=70,共情=80")
        traits_text = _ask("  数值：", "")

    override = _parse_traits(traits_text)

    with open(eeg_path, "rb") as f:
        eeg = eeg_mod.parse_bytes(f.read(), os.path.basename(eeg_path))
    with open(dna_path, "rb") as f:
        dna = genome_mod.parse_bytes(f.read(), os.path.basename(dna_path))

    profile = pipeline.build(eeg, dna, subject=name, voice=voice)

    # 覆盖七维：来源标成手工指定，权重 1.0
    for row in profile.get("traits", []):
        key = row["key"]
        row["value"] = round(override.get(key, 0.5), 3)
        row["sources"] = [{"source": "手工指定", "weight": 1.0}]
        row["fuse"] = {"eeg": 0.0, "gene": 0.0}

    # 名字与语气
    per = profile.setdefault("persona", {})
    per["name"] = name
    per["voice"] = voice
    per["summary"] = "%s。由手工指定的七维构成；此刻的心情是 %s。" % (
        name, (profile.get("eeg") or {}).get("mood") or "—")

    # 编号由输入决定：同样参数 = 同样编号
    sig = "|".join([name, voice] + ["%s=%.2f" % (k, override.get(k, 0.5)) for k, _ in KEYS])
    profile["id"] = "mind_" + hashlib.sha256(sig.encode("utf-8")).hexdigest()[:12]
    per["code"] = "DL-" + profile["id"].replace("mind_", "")[-6:].upper()
    profile["subject"] = name
    profile["origin"] = {
        "eeg_source": "手工创造（无上传）",
        "dna_source": "手工创造（无上传）",
        "eeg_kind": "manual",
        "dna_kind": "manual",
        "notes": ["手工指定七维，未经生物信号测量"],
    }

    path = pipeline.save(profile)
    print("")
    print("  已创造：%s" % per["code"])
    print("  名字：%s　语气：%s" % (name, voice))
    print("  编号：%s" % profile["id"])
    print("  保存：%s" % path)
    print("")
    print("  网页会同步：dl serve 之后在档案库里就能看到。")
    print("")
