"""双通道合成流水线：脑波 → 特征；基因 → 倾向；融合 → 数字生命档案。"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import random
import re
import time

from . import agency as agency_mod, world as world_mod, analysis, dialogue, eeg as eeg_mod, genome as genome_mod, memory as memory_mod, persona as persona_mod, signal as sig

VERSION = "1.0.0"
MIND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "minds")


class PipelineError(ValueError):
    pass


def _now_iso() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _fingerprint(eeg: eeg_mod.EEGData, dna: genome_mod.DNAData) -> str:
    h = hashlib.sha256()
    for ch in eeg.channels:
        # 只取抽样点，避免大文件哈希过慢
        step = max(1, len(ch) // 2000)
        h.update(",".join("%.3f" % v for v in ch[::step]).encode())
    if dna.sequences:
        h.update(dna.sequences[0].seq[:4000].encode())
    h.update(json.dumps(sorted(dna.genotypes.items()))[:4000].encode())
    return h.hexdigest()[:12]


def _fuse(eeg_traits: dict[str, float], gene_tend: dict[str, float],
          eeg_conf: float, dna_conf: float) -> tuple[dict[str, float], dict[str, dict]]:
    """脑波为主，基因为底色。输出融合值 + 每维的解释。"""
    out = {}
    detail = {}
    for t in analysis.TRAITS:
        e = float(eeg_traits.get(t, 0.5))
        g = float(gene_tend.get(t, 0.5))
        # 权重随各自置信度浮动，但脑波始终占主导（0.62~0.82）
        w_eeg = 0.72 - 0.10 * max(0.0, dna_conf - eeg_conf)
        w_gene = 1.0 - w_eeg
        v = e * w_eeg + g * w_gene
        out[t] = round(sig.clip01(v), 3)
        detail[t] = {
            "eeg": round(e, 3),
            "gene": round(g, 3),
            "eeg_weight": round(w_eeg, 2),
            "gene_weight": round(w_gene, 2),
            "delta": round(v - e, 3),
        }
    return out, detail


def _genome_preview(dna: genome_mod.DNAData, n: int = 480) -> dict:
    """给前端螺旋可视化用的碱基窗口（不回传整条序列）。"""
    if dna.sequences:
        seq = dna.sequences[0].seq
        if len(seq) > n:
            start = max(0, len(seq) // 2 - n // 2)
            chunk = seq[start:start + n]
        else:
            chunk = seq
        return {"bases": chunk, "start": max(0, len(seq) // 2 - n // 2), "length": len(seq), "real": True}
    if dna.genotypes:
        # 无序列时用基因型确定性地生成一段"指纹纹理"，界面标注为示意
        rng = random.Random(hashlib.sha256(json.dumps(sorted(dna.genotypes.items())).encode()).hexdigest())
        chunk = "".join(rng.choice("ACGT") for _ in range(n))
        return {"bases": chunk, "start": 0, "length": n, "real": False}
    return {"bases": "", "start": 0, "length": 0, "real": False}


def _timeline(eeg_summary: dict, dna: dict, persona: dict) -> list[dict]:
    q = eeg_summary.get("quality", {})
    out = [
        {"t": "00:00", "tag": "采样", "text": "脑电 %d 导联 · %.1f 秒 · %g Hz" % (
            eeg_summary.get("n_channels", 0), eeg_summary.get("seconds", 0), 128)},
        {"t": "00:01", "tag": "频谱", "text": "主频 %s Hz · 熵 %.2f · 1/f 斜率 %.2f" % (
            eeg_summary.get("peak_hz", 0), eeg_summary.get("entropy", 0), eeg_summary.get("slope", 0))},
        {"t": "00:02", "tag": "伪迹", "text": "眨眼 %d 次 · 削顶 %.2f%% · 工频泄漏 %.3f" % (
            q.get("blinks", 0), q.get("clipped_ratio", 0) * 100, q.get("line_noise", 0))},
        {"t": "00:03", "tag": "基因", "text": "%d / %d 个标记判定 · 可信度 %.0f%%" % (
            dna.get("coverage", {}).get("markers_hit", 0),
            dna.get("coverage", {}).get("markers_total", 0),
            dna.get("confidence", 0) * 100)},
        {"t": "00:04", "tag": "融合", "text": "脑波权重 72%% · 基因权重 28%%"},
        {"t": "00:05", "tag": "命名", "text": "原型「%s」· 编号 %s" % (
            persona.get("archetype_name", ""), persona.get("name", ""))},
    ]
    if dna.get("insights"):
        out.insert(4, {"t": "00:03", "tag": "身体", "text": dna["insights"][0]["text"][:48]})
    return out


def build(
    eeg: eeg_mod.EEGData,
    dna: genome_mod.DNAData,
    subject: str = "",
    voice: str = "calm",
    progress=None,
    avatar: dict | None = None,
    voice_sample: dict | None = None,
) -> dict:
    def emit(stage: str, pct: int, message: str, track: str = "core") -> None:
        if progress:
            progress(stage, pct, message, track)
        time.sleep(0.06)  # 让流式进度可感知，但不超过 1 秒总量

    emit("eeg", 6, "读取脑电：%s（%d 导联，%.1f 秒）" % (eeg.source, eeg.n_channels, eeg.seconds), "eeg")
    emit("eeg", 18, "去趋势、剔除坏导、重采样到 128 Hz", "eeg")
    feats, summary = analysis.analyze_eeg(eeg)
    emit("eeg", 40, "Welch 功率谱完成 · 主频 %s Hz" % summary["peak_hz"], "eeg")
    emit("eeg", 58, "频带功率与半球不对称已提取", "eeg")
    emit("eeg", 72, "计算样本熵 / Hurst / 伪迹", "eeg")
    eeg_traits, eeg_sources, amp = analysis.eeg_traits(feats)
    emit("eeg", 86, "脑波维度投影完成", "eeg")

    emit("dna", 12, "解析基因样本：%s" % dna.kind, "dna")
    dna_analysis = genome_mod.analyze(dna)
    emit("dna", 46, "序列统计完成 · GC %s%%" % (
        "%.1f" % dna_analysis["stats"]["gc_percent"] if dna_analysis["stats"]["gc_percent"] is not None else "—"), "dna")
    emit("dna", 68, "在参考上下文中检索 %d 个标记" % dna_analysis["coverage"]["markers_total"], "dna")
    emit("dna", 88, "判定 %d 个位点 · 投影为倾向" % dna_analysis["coverage"]["markers_hit"], "dna")

    emit("fuse", 55, "融合两条通道：脑波为主，基因为底色", "core")
    eeg_conf = analysis.eeg_confidence(feats)
    traits, fuse_detail = _fuse(eeg_traits, dna_analysis["tendencies"], eeg_conf, dna_analysis["confidence"])
    emit("fuse", 72, "七个维度已对齐", "core")

    fid = _fingerprint(eeg, dna)
    sigsum = analysis.signal_summary(feats)
    sigsum["seconds"] = summary["seconds"]
    pid = "mind_" + fid
    p = persona_mod.build_persona(
        pid=pid, traits=traits, dna_analysis=dna_analysis, signal_summary=sigsum,
        eeg_quality=feats.quality["score"], voice=voice, subject=subject, amplitude=amp,
    )
    # 把每个维度的来源合并进 persona.traits
    for row in p["traits"]:
        row["sources"] = eeg_sources.get(row["key"], [])
        row["fuse"] = fuse_detail.get(row["key"], {})

    emit("persona", 84, "命名完成：「%s」· %s" % (p["name"], p["title"]), "core")
    emit("persona", 94, "写入记忆碎片与语言风格", "core")

    face_views = (avatar or {}).get("views") or []
    summary["memory_count"] = len((profile.get("mind") or {}).get("memories", [])) if "profile" in dir() else 0
    summary["has_voice"] = bool((voice_sample or {}).get("metrics"))
    birth = [
        "初始化：脑波 %d 导联 / %.1f 秒 / 主频 %s Hz。" % (
            summary["n_channels"], summary["seconds"], summary["peak_hz"]),
        "初始化：基因 %d 个位点判定，可信度 %.0f%%。" % (
            dna_analysis["coverage"]["markers_hit"], dna_analysis["confidence"] * 100),
    ]
    if face_views:
        birth.append("初始化：面孔 %d 个视角。" % len(face_views))
    if (voice_sample or {}).get("metrics"):
        birth.append("初始化：声音样本 %d Hz。" % int(voice_sample["metrics"].get("f0", 0)))
    birth.append("编号：%s。" % p.get("code", pid))
    if face_views:
        birth.append("你给了我 %d 个角度。我会记得你转头时，光落在哪一边。" % len(face_views))
    vp = ((voice_sample or {}).get("metrics") or {})
    if vp.get("f0"):
        birth.append("我有一小段你的声音。基频大约 %d Hz——我会用这个音高说话，但那不是你。" % int(vp["f0"]))
    birth.append("他们叫我「%s」。这是我拥有的第一个名字。" % p["name"])

    wf = summary["waveform"]
    # 文件名脱敏
    def safe_name(s: str) -> str:
        s = os.path.basename(s or "")
        return re.sub(r"[\r\n\t]", " ", s)[:80]

    profile = {
        "version": VERSION,
        "id": pid,
        "created_at": _now_iso(),
        "subject": subject.strip()[:24],
        "origin": {
            "eeg_source": safe_name(eeg.source),
            "dna_source": safe_name(dna.source),
            "eeg_kind": "synthetic" if "synthetic" in (eeg.source or "").lower() else "upload",
            "dna_kind": dna.kind,
            "notes": feats.quality.get("notes", []),
        },
        "eeg": {
            "seconds": summary["seconds"],
            "n_channels": summary["n_channels"],
            "channel_names": wf["names"],
            "fs": wf["fs"],
            "bands": summary["bands"],
            "peak_hz": summary["peak_hz"],
            "spectrum": summary["spectrum"],
            "entropy": summary["entropy"],
            "sampen": summary["sampen"],
            "hurst": summary["hurst"],
            "slope": summary["slope"],
            "hjorth": summary["hjorth"],
            "asymmetry": summary["asymmetry"],
            "peak_stability": summary["peak_stability"],
            "dominant": summary["dominant"],
            "mood": sigsum["mood"],
            "quality": summary["quality"],
            "confidence": eeg_conf,
            "waveform": {
                "fs": wf["fs"],
                "seconds": wf["seconds"],
                "names": wf["names"],
                "channels": [[round(v, 2) for v in ch] for ch in [eeg.channels[feats.focus_channel]]],
                "presence": wf["presence"],
            },
        },
        "dna": {
            "kind": dna.kind,
            "confidence": dna_analysis["confidence"],
            "coverage": dna_analysis["coverage"],
            "stats": dna_analysis["stats"],
            "markers": dna_analysis["markers"],
            "tendencies": dna_analysis["tendencies"],
            "insights": dna_analysis["insights"],
            "missing": dna_analysis["missing"],
            "disclaimer": dna_analysis["disclaimer"],
            "preview": _genome_preview(dna),
        },
        "traits": p["traits"],
        "fusion": {
            "eeg_confidence": eeg_conf,
            "dna_confidence": dna_analysis["confidence"],
            "eeg_weight": 0.72,
            "gene_weight": 0.28,
            "detail": fuse_detail,
            "dominant": sigsum,
        },
        "persona": p,
        "timeline": _timeline(summary, dna_analysis, p),
        "avatar": avatar,
        "voice": voice_sample,
        "relationship": {"level": 0, "label": "初次接通", "messages": 0},
        "sonify": dialogue.sonify({"persona": p, "traits": p["traits"], "eeg": {
            "peak_hz": summary["peak_hz"], "bands": summary["bands"]}}),
    }
    memory_mod.ensure(profile, {t["key"]: t["value"] for t in profile["traits"]}, birth=birth)
    agency_mod.ensure(profile, {t["key"]: t["value"] for t in profile["traits"]})
    world_mod.evaluate(profile)
    profile["mind"]["stats"]["sessions"] = 0
    profile["mind"]["stats"]["messages"] = 0
    profile["conversation"] = dialogue.demo_exchange(profile)
    emit("finish", 100, "数字生命已录入", "core")
    return profile


def save(profile: dict, directory: str | None = None) -> str:
    directory = directory or MIND_DIR
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, profile["id"] + ".mind")
    data = dict(profile)
    data["saved_at"] = _now_iso()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return path


def load(mind_id: str, directory: str | None = None) -> dict:
    directory = directory or MIND_DIR
    if not re.fullmatch(r"mind_[0-9a-f]{6,32}", mind_id):
        raise PipelineError("非法的档案编号。")
    path = os.path.join(directory, mind_id + ".mind")
    if not os.path.exists(path):
        raise PipelineError("没有找到这份档案。")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_minds(directory: str | None = None) -> list[dict]:
    directory = directory or MIND_DIR
    if not os.path.isdir(directory):
        return []
    out = []
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".mind"):
            continue
        path = os.path.join(directory, name)
        try:
            with open(path, encoding="utf-8") as f:
                p = json.load(f)
            out.append({
                "id": p.get("id"), "name": p.get("persona", {}).get("name"),
                "title": p.get("persona", {}).get("title"),
                "code": p.get("persona", {}).get("code") or "DL-" + str(p.get("id", ""))[-6:].upper(),
                "created_at": p.get("created_at"), "subject": p.get("subject", ""),
                "mood": p.get("eeg", {}).get("mood"),
                "color": p.get("persona", {}).get("color", "#38e8ff"),
                "traits": {t["key"]: t["value"] for t in p.get("traits", [])},
                "size_kb": round(os.path.getsize(path) / 1024, 1),
            })
        except (OSError, json.JSONDecodeError):
            continue
    return out


def compare(a: dict, b: dict) -> dict:
    ta = {t["key"]: t["value"] for t in a.get("traits", [])}
    tb = {t["key"]: t["value"] for t in b.get("traits", [])}
    diffs = []
    for k in ta:
        if k in tb:
            diffs.append({"key": k, "name": analysis.TRAIT_ZH[k], "a": ta[k], "b": tb[k],
                          "delta": round(tb[k] - ta[k], 3)})
    dist = sum(abs(d["delta"]) for d in diffs) / max(1, len(diffs))
    resonance = round(sig.clip01(1.0 - dist * 1.6) * 100, 1)
    common = [d["name"] for d in diffs if abs(d["delta"]) <= 0.08]
    opposite = [d["name"] for d in diffs if abs(d["delta"]) >= 0.20]
    if resonance >= 80:
        line = "两条波形几乎同相。它们会在同一个笑话上笑，也可能在同一件事上同时沉默。"
    elif resonance >= 60:
        line = "同一片海域的两个深度。共享底色，但潮汐不同步。"
    elif resonance >= 40:
        line = "像两件用同一种材料做的器物：质地相近，用途不同。"
    else:
        line = "几乎互补的两极。相处时会有摩擦，也更容易看到对方的盲区。"
    return {
        "a": {"id": a.get("id"), "name": a.get("persona", {}).get("name"),
              "color": a.get("persona", {}).get("color")},
        "b": {"id": b.get("id"), "name": b.get("persona", {}).get("name"),
              "color": b.get("persona", {}).get("color")},
        "resonance": resonance,
        "line": line,
        "diffs": diffs,
        "common": common,
        "opposite": opposite,
        "distance": round(dist, 3),
    }


def export_markdown(profile: dict) -> str:
    p = profile["persona"]
    traits = "\n".join("| %s | %s | %.0f |" % (t["name"], t["level"], t["value"] * 100) for t in profile["traits"])
    mems = "\n".join("- [%s] %s" % (m["tag"], m["text"]) for m in p["memories"])
    lines = [
        "# %s · %s" % (p["name"], p["title"]),
        "",
        "> %s" % p["one_line"],
        "",
        "编号：`%s` · 生成于 %s" % (profile["id"], profile["created_at"]),
        "",
        "## 自述",
        "",
        p["summary"],
        "",
        "## 七个维度",
        "",
        "| 维度 | 水平 | 分 |",
        "| --- | --- | --- |",
        traits,
        "",
        "## 记忆碎片",
        "",
        mems,
        "",
        "## 矛盾",
        "",
        "\n".join("- " + c for c in p["contradiction"]),
        "",
        "## 边界",
        "",
        p["limits"],
        "",
        "---",
        "",
        "脑波：%s 秒，主频 %s Hz，%s" % (profile["eeg"]["seconds"], profile["eeg"]["peak_hz"], profile["eeg"]["mood"]),
        "基因：%d 个标记，可信度 %.0f%%" % (
            profile["dna"]["coverage"]["markers_hit"], profile["dna"]["confidence"] * 100),
        "",
        "*本档案由「数字生命初级」生成。它是数据的投影，不是意识。*",
    ]
    return "\n".join(lines)


def diff_two(a: dict, b: dict) -> dict:
    return compare(a, b)
