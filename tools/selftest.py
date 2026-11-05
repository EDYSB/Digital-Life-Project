"""单元级自测：不依赖网络、不依赖浏览器。

python tools/selftest.py
"""

from __future__ import annotations

import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from suoling import analysis, dialogue, eeg as E, genome as G, persona as P, pipeline as PL, signal as S

FAIL = []
PASS = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL.append(name)
        print("  FAIL %s %s" % (name, detail))


def test_signal() -> None:
    print("\n[signal]")
    fs = 128
    n = 1024
    x = [math.sin(2 * math.pi * 10 * i / fs) for i in range(n)]
    spec = S.welch(x, fs, nfft=1024)
    peak, _ = S.peak_in_band(spec, 8, 13)
    check("10Hz 正弦的 α 峰频", abs(peak - 10) < 0.3, "got %.3f" % peak)
    p_alpha = spec.band_power(8, 13)
    p_beta = spec.band_power(13, 30)
    check("α 功率远大于 β", p_alpha > p_beta * 20, "a=%.3f b=%.3f" % (p_alpha, p_beta))
    check("谱熵在 0..1", 0 <= S.spectral_entropy(spec) <= 1)

    # 逆变换一致性
    rnd = random.Random(1)
    data = [complex(rnd.random(), rnd.random()) for _ in range(256)]
    spec2 = S._fft(data)
    inv = [v.conjugate() for v in S._fft([v.conjugate() for v in spec2])]
    err = max(abs(inv[i].real / 256 - data[i].real) for i in range(256))
    check("FFT 逆变换", err < 1e-9, "err=%g" % err)

    x2 = [math.sin(2 * math.pi * 6 * i / fs) + rnd.random() * .2 for i in range(2048)]
    check("样本熵有限且非负", 0 <= S.sample_entropy(x2) <= 3)
    check("Hurst 在 0..1", 0 < S.hurst_exponent(S.detrend(x2)) <= 1)


def test_eeg() -> None:
    print("\n[eeg]")
    leads, names = S.synthesize_eeg("meditation", fs=128, seconds=10, seed=3)
    e = E.prepare(E.EEGData(leads, names, 128, 10, source="synth"))
    check("合成 EEG 通道/采样率", e.n_channels == 4 and abs(e.fs - 128) < 1e-9)
    f, summ = analysis.analyze_eeg(e)
    traits, sources, amp = analysis.eeg_traits(f)
    check("七个维度齐全", set(traits) == set(analysis.TRAITS))
    check("维度在 0..1", all(0 <= v <= 1 for v in traits.values()))
    check("每个维度有来源", all(sources[k] for k in traits))
    check("α 为静息态主导", summ["dominant"] == "alpha", summ["dominant"])
    check("质量分在 0..1", 0 <= f.quality["score"] <= 1)

    # CSV 往返
    csv = S.synthetic_csv("focus", fs=128, seconds=6, seed=9)
    e2 = E.parse_bytes(csv.encode(), "t.csv")
    check("CSV 往返：4 导联", e2.n_channels == 4)
    check("CSV 往返：采样率", abs(e2.fs - 128) < 1e-6)
    e3 = E.parse_bytes(csv.encode(), "t.txt")
    check("TXT 同样可解析", e3.n_channels == 4)


def test_genome() -> None:
    print("\n[genome]")
    check("标记数 = 20", len(G.MARKERS) == 20)
    bad = [m.rsid for m in G.MARKERS if len(m.context) != 61 or m.context[30] != m.ref_allele]
    check("参考上下文 61bp 且中心为 ref", not bad, str(bad))
    check("功能等位与 ref 不同", all(m.functional != m.ref_allele for m in G.MARKERS))

    gt = {"rs4680": "TT", "rs53576": "TT", "rs671": "AA", "rs762551": "CC"}
    d = G.parse_bytes(G.demo_fasta(gt, seed=7).encode(), "demo.fasta")
    a = G.analyze(d)
    check("FASTA 判定 20/20", a["coverage"]["markers_hit"] == 20, str(a["coverage"]))
    got = {m["rsid"]: m["genotype"] for m in a["markers"]}
    check("rs4680 读到 T", "T" in got.get("rs4680", ""), got.get("rs4680", ""))
    check("序列扫描标注 zygosity 未知",
          all(not m["zygosity_known"] for m in a["markers"] if m["method"] == "context-scan"))
    check("倾向在 0.15..0.85", all(0.15 <= v <= 0.85 for v in a["tendencies"].values()))
    check("有可读的基因洞察", len(a["insights"]) >= 1)

    g = G.parse_bytes(G.demo_genotype_file(gt).encode(), "raw.txt")
    ag = G.analyze(g)
    check("23andMe 四列判定 20/20", ag["coverage"]["markers_hit"] == 20)
    check("四列文件 zygosity 已知", all(m["zygosity_known"] for m in ag["markers"]))

    v = G.parse_bytes(G.demo_vcf(gt).encode(), "demo.vcf")
    check("VCF 判定 20/20", G.analyze(v)["coverage"]["markers_hit"] == 20)

    j = G.parse_bytes(b'{"markers": {"rs4680": "TT"}}', "x.json")
    check("JSON 基因型", G.analyze(j)["coverage"]["markers_hit"] == 1)


def test_pipeline() -> None:
    print("\n[pipeline]")
    e = E.load_path("samples/eeg_flow.csv")
    d = G.load_path("samples/dna_explorer.fasta")
    p = PL.build(e, d, subject="自测", voice="warm")
    check("档案 id 格式", p["id"].startswith("mind_") and len(p["id"]) == 17, p["id"])
    check("七个维度", len(p["traits"]) == 7)
    per = p["persona"]
    for key in ("name", "code", "title", "summary", "memories", "greeting",
                "voice_label", "limits"):
        check("persona.%s" % key, bool(per.get(key)), repr(per.get(key))[:40])
    check("编号与 id 对得上",
          per["code"] == "DL-" + p["id"].replace("mind_", "")[-6:].upper(), per["code"])
    check("记忆片段 ≥ 2", len(per["memories"]) >= 2)
    check("演示对话 4 组", len(p["conversation"]) == 4)
    check("波形点 > 0", len(p["eeg"]["waveform"]["channels"][0]) > 0)
    check("频谱点 > 100", len(p["eeg"]["spectrum"]["freqs"]) > 100)
    check("基因预览 480bp", len(p["dna"]["preview"]["bases"]) == 480)
    check("JSON 可序列化", len(json.dumps(p, ensure_ascii=False)) > 20000)
    check("脑波+基因权重合计 1", abs(p["fusion"]["eeg_weight"] + p["fusion"]["gene_weight"] - 1) < 1e-9)

    r = dialogue.reply(p, "我最近睡不着，脑子里很吵。", [])
    check("睡眠意图", r["intent"] == "sleep", r["intent"])
    check("回复非空", len(r["text"]) > 5)
    check("情绪二维", set(r["emotion"]) >= {"arousal", "valence", "label"})
    q = dialogue.classify("你觉得自己是真的吗？")
    check("真实性意图", q == "real", q)
    check("致谢意图", dialogue.classify("谢谢你") == "thanks")
    check("告别意图", dialogue.classify("晚安") == "bye")

    p2 = PL.build(E.load_path("samples/eeg_focus.csv"), G.load_path("samples/dna_steady.vcf"))
    cmp = PL.compare(p, p2)
    check("对比：7 项差值", len(cmp["diffs"]) == 7)
    check("对比：共鸣度 0..100", 0 <= cmp["resonance"] <= 100)
    md = PL.export_markdown(p)
    check("Markdown 导出", len(md) > 500 and p["persona"]["name"] in md)

    # 同一输入 → 同一档案
    p3 = PL.build(E.load_path("samples/eeg_flow.csv"), G.load_path("samples/dna_explorer.fasta"),
                  subject="自测", voice="warm")
    check("可复现（相同输入相同编号）", p3["id"] == p["id"] and p3["persona"]["name"] == per["name"])


def test_persona() -> None:
    print("\n[persona]")
    cases = {
        "meditation": {"curiosity": 0.20, "empathy": 0.74, "order": 0.73, "alertness": 0.18,
                       "creativity": 0.37, "stability": 0.83, "sensory": 0.60},
        "focus": {"curiosity": 0.68, "empathy": 0.25, "order": 0.69, "alertness": 0.73,
                  "creativity": 0.45, "stability": 0.52, "sensory": 0.42},
    }
    picks = [P.pick_archetype(v)[0][1] for v in cases.values()]
    check("不同状态映射不同原型", picks[0] != picks[1], str(picks))
    check("原型表 12 个", len(P.ARCHETYPES) == 12)
    check("声音 4 种", len(P.VOICE_STYLE) == 4)
    check("原型表可序列化", all("line" in x for x in P.archetype_table()))


def main() -> None:
    print("数字生命初级 · 自测")
    test_signal()
    test_eeg()
    test_genome()
    test_pipeline()
    test_persona()
    print("\n%d passed, %d failed" % (PASS, len(FAIL)))
    if FAIL:
        print("失败项：", ", ".join(FAIL))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
