"""开发期工具：提取 NCBI FASTA 中的标记上下文，输出 tools/marker_contexts.txt。

每个原始文件为 NCBI efetch 输出，头部形如：
  >NC_000022.11:19963600-19963900 Homo sapiens ...
在 TARGETS 中标注 accession 与 NCBI dbSNP 坐标，脚本从序列里取该坐标碱基作为 ref。
"""

from __future__ import annotations

import os
import re
import sys

TARGETS = [
    ("rs4680", "COMT", "NC_000022.11", 19963747, "A", "认知风格", "Met/Val 决定多巴胺清除速度",
     "AA 慢速清除：思考更深、对噪音与压力更敏感；GG 快速清除：反应快、抗压好。"),
    ("rs6265", "BDNF", "NC_000011.10", 27658369, "A", "学习与情绪", "Val66Met 影响神经营养因子分泌",
     "携带 A 与情景记忆和情绪弹性差异相关；效应很小，且受运动与睡眠强烈调节。"),
    ("rs53576", "OXTR", "NC_000003.12", 8762690, "A", "社会亲和", "催产素受体启动子区变异",
     "G 型在部分研究中与更高的共情与信任倾向相关；重复研究结果并不一致。"),
    ("rs1800955", "DRD4", "NC_000011.10", 637269, "T", "探索欲", "多巴胺 D4 受体启动子变异",
     "T 型常与更强的探索动机相关，也更容易厌倦重复；不是好或坏。"),
    ("rs6323", "MAOA", "NC_000023.11", 43726509, "T", "冲动控制", "单胺氧化酶 A 功能位点",
     "与多巴胺/去甲肾上腺素分解速率相关。请勿用它给任何人的行为下结论。"),
    ("rs1800497", "DRD2", "NC_000011.10", 113400106, "T", "奖赏敏感", "多巴胺 D2 受体 Taq1A",
     "A1 型在部分研究中与奖赏学习差异相关；个体差异主要由经验塑造。"),
    ("rs1801133", "MTHFR", "NC_000001.11", 11796321, "T", "代谢", "叶酸代谢酶 C677T",
     "T 型酶活性较低，与同型半胱氨酸水平相关；属营养代谢范畴，不是性格。"),
    ("rs429358", "APOE", "NC_000019.10", 44908684, "C", "脂质代谢", "APOE ε4 决定位点之一",
     "只做脂质代谢说明，不做疾病预测。本系统不提供任何健康结论。"),
    ("rs7412", "APOE", "NC_000019.10", 44908822, "T", "脂质代谢", "APOE ε2 决定位点",
     "与 ε4 位点共同决定 APOE 等位型；同样仅作代谢说明。"),
    ("rs1801260", "CLOCK", "NC_000004.12", 55434534, "C", "昼夜节律", "生物钟基因 3111T/C",
     "C 型在部分研究中与夜猫子倾向相关；光照与作息习惯的影响远大于基因。"),
    ("rs1799971", "OPRM1", "NC_000006.12", 154360797, "G", "痛觉与依恋", "μ 阿片受体 A118G",
     "G 型与部分镇痛/依恋反应差异相关；效应小且情境依赖。"),
    ("rs1042713", "ADRB2", "NC_000005.10", 148826878, "A", "应激反应", "β2 肾上腺素受体",
     "与心率与支气管反应性相关；属于生理反应性，不是情绪性格。"),
    ("rs1815739", "ACTN3", "NC_000011.10", 66560624, "T", "体能类型", "α-辅肌动蛋白 3 R577X",
     "CC 快肌倾向，TT 耐力倾向；这是肌肉蛋白，不是意志力。"),
    ("rs4988235", "LCT", "NC_000002.12", 135851076, "A", "乳糖耐受", "乳糖酶持续表达",
     "A 型在东亚人群中很常见，成年后乳糖酶活性下降；与能不能喝牛奶直接相关。"),
    ("rs671", "ALDH2", "NC_000012.12", 111803962, "A", "酒精代谢", "乙醛脱氢酶 2 Glu504Lys",
     "A 型乙醛清除慢，饮酒容易脸红心悸；这是保护性变异。"),
    ("rs17822931", "ABCC11", "NC_000016.10", 48258198, "A", "体味类型", "耵聍/腋汗类型",
     "A 型为干性耵聍、体味较轻，在东亚人群中比例很高。"),
    ("rs762551", "CYP1A2", "NC_000015.10", 74749576, "C", "咖啡因代谢", "CYP1A2 快/慢代谢",
     "AA 快代谢，咖啡因清除较快；C 型慢代谢，下午喝咖啡更影响睡眠。"),
    ("rs1805007", "MC1R", "NC_000016.10", 89919709, "T", "色素与痛觉", "红发/浅色皮肤相关",
     "T 型与红发、浅色皮肤及痛觉敏感性相关；在东亚人群中罕见。"),
    ("rs1799983", "NOS3", "NC_000007.14", 150999023, "T", "血管反应", "内皮型一氧化氮合酶",
     "与血管舒张能力相关；属于生理指标，需结合运动与饮食。"),
    ("rs1800629", "TNF", "NC_000006.12", 31575254, "A", "炎症基调", "TNF-α 启动子 -308",
     "与炎症反应强度相关；睡眠、压力与运动的影响同样显著。"),
]


def parse_fasta(path: str) -> tuple[str, str]:
    header = ""
    chunks: list[str] = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            if s.startswith(">"):
                if not header:
                    header = s
                continue
            if s.startswith("#"):
                continue
            if re.fullmatch(r"[ACGTNacgtn]+", s):
                chunks.append(s.upper())
    return header, "".join(chunks)


def main(directory: str) -> None:
    spans: dict[str, tuple[int, int, str]] = {}
    for name in sorted(os.listdir(directory)):
        if not name.lower().endswith((".txt", ".fasta", ".fa")):
            continue
        header, seq = parse_fasta(os.path.join(directory, name))
        m = re.search(r">(\S+?):(\d+)-(\d+)", header)
        if not m:
            print(f"skip {name}: header {header[:60]}")
            continue
        spans[m.group(1)] = (int(m.group(2)), int(m.group(3)), seq)
    if not spans:
        print("no sequences parsed")
        sys.exit(1)

    out: list[str] = []
    for rsid, gene, acc, pos, risk, trait, effect, note in TARGETS:
        if acc not in spans:
            print(f"MISSING ACC {acc} for {rsid}")
            continue
        start, end, seq = spans[acc]
        idx = pos - start
        if not (30 <= idx < len(seq) - 30):
            print(f"OUT OF RANGE {rsid}: idx={idx} len={len(seq)} span={start}-{end}")
            continue
        ctx = seq[idx - 30 : idx + 31]
        ref = ctx[30]
        if ref not in "ACGT":
            print(f"BAD REF {rsid}: {ref}")
            continue
        chrom = acc.split(".")[0].replace("NC_", "")
        out.append(
            f'    Marker("{rsid}", "{gene}", "{chrom}", {pos}, "{ref}", "{risk}",\n'
            f'           "{ctx}",\n'
            f'           "{trait}", "{effect}",\n'
            f'           "{note}"),'
        )
        print(f"OK {rsid:12s} {gene:7s} {acc}:{pos} ref={ref} ctx={ctx[:10]}..{ctx[50:]}")
    dest = os.path.join(os.path.dirname(__file__), "marker_contexts.txt")
    with open(dest, "w", encoding="utf-8") as f:
        f.write("# 由 tools/build_markers.py 从 NCBI 参考序列提取（GRCh38，正链，变异位点前后各 30 bp）\n")
        f.write("# 把这些 61bp 上下文抄进 suoling/genome.py 的 MARKER_SPECS；请勿手改单碱基。\n\n")
        f.write("\n".join(out))
        f.write("\n")
    print(f"wrote {len(out)} markers")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "raw")
