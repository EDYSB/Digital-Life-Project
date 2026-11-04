"""生成几份内置示例档案，让档案库第一次打开就不是空的。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from suoling import eeg as E, genome as G, pipeline as P

COMBOS = [
    ("eeg_meditation.csv", "dna_sensitive.fasta", "warm", "内置示例 · 静息 × 高敏"),
    ("eeg_focus.csv", "dna_explorer.fasta", "sharp", "内置示例 · 专注 × 探索"),
    ("eeg_flow.csv", "dna_steady.vcf", "calm", "内置示例 · 心流 × 稳态"),
]


def main() -> None:
    os.makedirs(P.MIND_DIR, exist_ok=True)
    for eeg_name, dna_name, voice, subject in COMBOS:
        e = E.load_path(os.path.join("samples", eeg_name))
        d = G.load_path(os.path.join("samples", dna_name))
        profile = P.build(e, d, subject=subject, voice=voice)
        path = P.save(profile)
        print("seeded %-10s %-14s -> %s" % (profile["persona"]["name"], profile["persona"]["title"], path))


if __name__ == "__main__":
    main()
