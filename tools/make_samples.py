"""生成内置示例数据：4 份合成脑电 + 4 份演示基因（多种格式）。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from suoling import genome as G
from suoling import signal as S

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples")


def make_eeg() -> None:
    for p in S.SYNTH_PRESETS:
        path = os.path.join(OUT, "eeg_%s.csv" % p.key)
        csv = S.synthetic_csv(p.state, fs=128, seconds=12.0, seed=20261104 + len(p.key))
        header = (
            "# EchoMind synthesized EEG | preset=%s | fs=128 | channels=4 | seconds=12\n"
            "# 合成数据，用于演示溯灵的分析流程；不是真实人类脑电记录。\n"
            "# 状态：%s\n" % (p.key, p.desc)
        )
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(header + csv)
        print("wrote", path, os.path.getsize(path), "bytes")


def make_dna() -> None:
    # 1. 高敏型 FASTA
    gt = G.DEMO_GENOME_PRESETS["sensitive"]["gt"]
    fasta = G.demo_fasta(gt, seed=31)
    with open(os.path.join(OUT, "dna_sensitive.fasta"), "w", encoding="utf-8", newline="\n") as f:
        f.write(fasta)
    # 2. 探索型 FASTA（带更多变异）
    gt2 = G.DEMO_GENOME_PRESETS["explorer"]["gt"]
    with open(os.path.join(OUT, "dna_explorer.fasta"), "w", encoding="utf-8", newline="\n") as f:
        f.write(G.demo_fasta(gt2, seed=47).replace(
            ">EchoMind_demo_subject",
            ">EchoMind_demo_explorer"))
    # 3. 稳态型 VCF
    gt3 = G.DEMO_GENOME_PRESETS["steady"]["gt"]
    with open(os.path.join(OUT, "dna_steady.vcf"), "w", encoding="utf-8", newline="\n") as f:
        f.write(G.demo_vcf(gt3))
    # 4. 均衡型 23andMe 原始格式
    with open(os.path.join(OUT, "dna_balanced.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(G.demo_genotype_file({}))
    for name in ("dna_sensitive.fasta", "dna_explorer.fasta", "dna_steady.vcf", "dna_balanced.txt"):
        p = os.path.join(OUT, name)
        print("wrote", p, os.path.getsize(p), "bytes")


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    make_eeg()
    make_dna()
    print("done")


if __name__ == "__main__":
    main()
