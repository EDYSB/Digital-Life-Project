"""基因样本录入与分析。

做三件真实的事：
  1. 解析 FASTA / 23andMe 原始基因型 / VCF / JSON；
  2. 对序列做 GC、碱基组成、ORF、k-mer 等统计；
  3. 在内置标记表（真实 GRCh38 参考上下文）上判定基因型，并投影为"倾向"。

边界（必须诚实）：
  * 参考上下文取自 NCBI 参考基因组，由 tools/build_markers.py 生成；判定只在
    "两侧锚点都命中且仅变异位点不同"时成立，否则报"未检出"，不做插补。
  * 单基因对性格的效应量极小；多基因评分在个体水平上不可靠。
    这里的"倾向"是可解释的艺术化权重，不是医学或心理诊断。
  * 不做疾病风险预测，不做亲缘或族源推断。
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
from dataclasses import dataclass, field

from . import signal as sig

DEMO_25 = "ACTG" * 6 + "AC"
COMPLEMENT = str.maketrans("ACGTNacgtn", "TGCANtgcan")
TRAITS = ("curiosity", "empathy", "order", "alertness", "creativity", "stability", "sensory")

TRAIT_ZH = {
    "curiosity": "好奇",
    "empathy": "共情",
    "order": "秩序",
    "alertness": "警觉",
    "creativity": "创造",
    "stability": "定力",
    "sensory": "感受力",
}


class DNAError(ValueError):
    """输入文件无法被解释为基因数据。"""


# ---------------------------------------------------------------- 标记定义
@dataclass(frozen=True)
class Marker:
    rsid: str
    gene: str
    chromosome: str
    pos: int
    ref_allele: str           # GRCh38 正链参考碱基
    functional: str           # 本表关注的功能等位（GRCh38 正链）
    context: str              # 61 bp 参考上下文，正中间即变异位点
    trait: str                # 中文标签
    effect: str               # 一句话机制
    note: str                 # 诚实的边界说明
    # 功能等位对 7 个倾向的方向（+1 提高 / -1 降低 / 0 仅记录）
    direction: dict[str, float] = field(default_factory=dict)
    confidence: str = "medium"  # high / medium / low

    @property
    def trait_key(self) -> str:
        return self.trait


# 方向表：功能等位携带 1 份时对该倾向的加分方向。
# 说明：这些方向是"读文献时的常见叙事"，不是经过验证的心理测量权重。
DIRECTIONS: dict[str, dict[str, float]] = {
    "rs4680": {"order": 1.0, "sensory": 1.0, "curiosity": 0.4, "alertness": -0.4},
    "rs6265": {"creativity": 1.0, "stability": 0.4, "sensory": 0.3},
    "rs53576": {"empathy": 1.0, "stability": 0.5},
    "rs1800955": {"curiosity": 1.0, "creativity": 0.5, "order": -0.4},
    "rs6323": {"alertness": 0.6, "empathy": -0.5},
    "rs1800497": {"curiosity": 0.6, "creativity": 0.3, "order": -0.3},
    "rs1801133": {"sensory": 0.3},
    "rs429358": {},
    "rs7412": {},
    "rs1801260": {"alertness": 1.0, "order": -0.5},
    "rs1799971": {"empathy": 0.6, "sensory": 0.5},
    "rs1042713": {"alertness": 0.5, "sensory": 0.4},
    "rs1815739": {"stability": 0.5, "alertness": -0.3},
    "rs4988235": {},
    "rs671": {},
    "rs17822931": {},
    "rs762551": {"alertness": 1.0, "stability": -0.4},
    "rs1805007": {"sensory": 0.8},
    "rs1799983": {"stability": 0.2},
    "rs1800629": {"stability": -0.4},
}

MARKER_SPECS = [
    # rsid, gene, chrom, pos, ref, functional, context, 中文特质, 机制, 边界说明, 把握度
    ("rs4680", "COMT", "22", 19963747, "C", "T",
     "CATCACCCAGCGGATGGTGGATTTCGCTGGCGTGAAGGACAAGGTGTGCATGCCTGACCCG",
     "认知风格", "Val158Met：Met 型多巴胺清除慢", "Met 携带者未必“更好”，只是处理深度与压力敏感度不同。", "high"),
    ("rs6265", "BDNF", "11", 27658369, "C", "T",
     "TCTGGTCCTCATCCAACAGCTCTTCTATCACGTGTTCGAAAGTGTCAGCCAATGATGTCAA",
     "学习与情绪", "Val66Met：影响神经营养因子分泌", "效应很小，且被运动、睡眠与社会支持强烈调节。", "high"),
    ("rs53576", "OXTR", "3", 8762690, "C", "T",
     "AAAGGTGTACGGGACATGCCCGAGGATCCTCAGTCCCACAGAAACAGGGAGGGGCTGGGAA",
     "社会亲和", "催产素受体启动子区变异", "重复研究结果并不一致，不能据此断言一个人的亲密能力。", "medium"),
    ("rs1800955", "DRD4", "11", 637269, "G", "A",
     "GGGGAGGGACTCCCCGGCTTGCGACCCGGCGTTGTCCGCGGTGCTCAGCGCCCGCCCGGGC",
     "探索欲", "多巴胺 D4 受体启动子变异", "与探索动机的关联在不同人群中不稳定。", "low"),
    ("rs6323", "MAOA", "X", 43726509, "T", "A",
     "GTGTCTGCTTCACGAAGTTCTTGTGGTGCATTTTTCAGCTCCATCAGGTCATTTATGTTCT",
     "冲动控制", "单胺氧化酶 A 功能位点", "位于 X 染色体，男性为半合子（本系统按 1 份计）。请勿用它给行为下结论。", "medium"),
    ("rs1800497", "DRD2", "11", 113400106, "G", "T",
     "GGCAACACAGCCATCCTCAAAGTGCTGGTCGAGGCAGGCGCCCAGCTGGACGTCCAGGATG",
     "奖赏敏感", "多巴胺 D2 受体 Taq1A", "与奖赏学习的关联被多次重复但也多次未重复。", "medium"),
    ("rs1801133", "MTHFR", "1", 11796321, "G", "A",
     "TCAAAGAAAAGCTGCGTGATGATGAAATCGGCTCCCGCAGACACCTTCTCCTTCAAGTGCT",
     "代谢", "叶酸代谢酶 C677T", "属营养代谢，不是性格；需要时请查同型半胱氨酸。", "high"),
    ("rs429358", "APOE", "19", 44908684, "T", "C",
     "GCCCGGCTGGGCGCGGACATGGAGGACGTGTGCGGCCGCCTGGTGCAGTACCGCGGCGAGG",
     "脂质代谢", "APOE ε4 决定位点之一", "仅作脂质代谢记录。本系统不做任何疾病风险预测。", "high"),
    ("rs7412", "APOE", "19", 44908822, "C", "T",
     "CTCCTCCGCGATGCCGATGACCTGCAGAAGCGCCTGGCAGTGTACCAGGCCGGGGCCCGCG",
     "脂质代谢", "APOE ε2 决定位点", "与 ε4 位点共同决定等位型；同样仅作代谢记录。", "high"),
    ("rs1801260", "CLOCK", "4", 55434534, "T", "C",
     "ATCCTATTTTCAAACATAATTGAAAAATAATGAAATGAGGGATATTTCTGAATAACTTGAA",
     "昼夜节律", "生物钟基因 3111T/C", "与“夜猫子”的关联不稳定；光照与作息习惯影响远大于此位点。", "low"),
    ("rs1799971", "OPRM1", "6", 154360797, "A", "C",
     "ATTACAATTCAAGACGAGGTTTGGGTGGGGACACAAAGCCTAGCCATAGCATTCAGCAAAT",
     "痛觉与依恋", "μ 阿片受体 A118G（正链 C）", "效应小且情境依赖；痛觉体验还受注意、情绪与预期影响。", "medium"),
    ("rs1042713", "ADRB2", "5", 148826878, "G", "A",
     "ACGGCAGCGCCTTCTTGCTGGCACCCAATGGAAGCCATGCGCCGGACCACGACGTCACGCA",
     "应激反应", "β2 肾上腺素受体", "属于生理反应性记录，不构成情绪性格判断。", "medium"),
    ("rs1815739", "ACTN3", "11", 66560624, "C", "T",
     "CAGTTCAAGGCAACACTGCCCGAGGCTGACCGAGAGCGAGGTGCCATCATGGGCATCCAGG",
     "体能类型", "α-辅肌动蛋白 3 R577X", "只说明肌纤维类型倾向，不是意志力或运动能力上限。", "high"),
    ("rs4988235", "LCT", "2", 135851076, "G", "A",
     "CTAAGGAGGAGAGTTCCTTTGAGGCCAGGGGCTACATTATCTTATCTGTATTGCCAGCGCA",
     "乳糖耐受", "乳糖酶持续表达", "东亚人群中该位点解释力有限，乳糖不耐受还与其他调控位点相关。", "medium"),
    ("rs671", "ALDH2", "12", 111803962, "G", "A",
     "TTGGGCGAGTACGGGCTGCAGGCATACACTGAAGTGAAAACTGTGAGTGTGGGACCTGCTG",
     "酒精代谢", "乙醛脱氢酶 2 Glu504Lys", "A 型乙醛清除慢、易脸红心悸，是保护性变异而非缺陷。", "high"),
    ("rs17822931", "ABCC11", "16", 48258198, "T", "C",
     "AAACCCTGTCTCTACTAAAAATACAAAAAATTAGCCGGGCATGGTGTCGGGTGCCTGTAGT",
     "体味类型", "耵聍/腋汗类型", "这是最“无害”的可见性状之一，东亚人群中 A 型（干性）占多数。", "high"),
    ("rs762551", "CYP1A2", "15", 74749576, "C", "A",
     "TGTGATGCTCAAAGGGTGAGCTCTGTGGGCCCAGGACGCATGGTAGATGGAGCTTAGTCTT",
     "咖啡因代谢", "CYP1A2 诱导型", "A 型的“快代谢”只在部分研究中成立；半衰期还受吸烟、口服避孕药影响。", "medium"),
    ("rs1805007", "MC1R", "16", 89919709, "C", "T",
     "GACCGCTACATCTCCATCTTCTACGCACTGCGCTACCACAGCATCGTGACCCTGCCGCGGG",
     "色素与痛觉", "红发/浅色皮肤相关", "T 型在东亚人群中罕见；色素还受许多其他基因控制。", "high"),
    ("rs1799983", "NOS3", "7", 150999023, "T", "G",
     "GCTGCCCCTGCTGCTGCAGGCCCCAGATGATCCCCCAGAACTCTTCCTTCTGCCCCCCGAG",
     "血管反应", "内皮型一氧化氮合酶", "与血管舒张相关；需结合血压、运动与饮食综合看。", "medium"),
    ("rs1800629", "TNF", "6", 31575254, "G", "A",
     "AAATGGAGGCAATAGGTTTTGAGGGGCATGGGGACGGGGTTCAGCCTCCAGGGTCCTACAC",
     "炎症基调", "TNF-α 启动子 -308", "炎症反应受睡眠、压力、感染与运动的综合影响。", "medium"),
]

MARKERS: list[Marker] = [
    Marker(rsid, gene, chrom, pos, ref, func, ctx, trait, effect, note,
           DIRECTIONS.get(rsid, {}), conf)
    for rsid, gene, chrom, pos, ref, func, ctx, trait, effect, note, conf in MARKER_SPECS
]
MARKER_BY_RSID = {m.rsid: m for m in MARKERS}

# 仅用于 "微洞察" 的解读文案（键为 GRCh38 正链基因型）
INSIGHT_RULES = {
    "rs4988235": {"GG": "乳糖酶持续表达，成年后喝牛奶大概率没什么负担。",
                  "AA": "乳糖酶活性可能下降，大量喝奶容易胀气——这是常见体质，不是毛病。",
                  "AG": "乳糖耐受大概在中间档，空腹喝奶时留意一下身体反馈。"},
    "rs671": {"AA": "乙醛清除慢，喝酒容易脸红心悸。这是保护性变异，别硬练酒量。",
              "AG": "乙醛清除偏慢，喝酒后反应会比较明显。",
              "GG": "酒精代谢较快，脸红反应不明显——但耐受不等于无害。"},
    "rs17822931": {"CC": "湿性耵聍，体味相关腺体更活跃。",
                   "TT": "干性耵聍、体味较轻，在东亚人群中很常见。",
                   "TC": "干湿之间的耵聍型。"},
    "rs1815739": {"TT": "α-辅肌动蛋白 3 缺失，肌肉更偏耐力型，长距离可能更合你的身体。",
                  "CC": "快肌倾向更明显，短时高强度更有优势。",
                  "CT": "快慢肌混合型，多数人都在这个位置。"},
    "rs1805007": {"TT": "MC1R 变异纯合：浅色皮肤、痛觉可能更敏感，也更怕晒。",
                  "CC": "色素沉着较深，晒后恢复通常更快。"},
    "rs762551": {"AA": "咖啡因代谢偏快，一杯咖啡大概能撑半天。",
                 "CC": "咖啡因代谢偏慢，下午那杯可能会一直陪到深夜。"},
    "rs4680": {"TT": "COMT 慢速清除：思考更深、细节记得牢，但噪音和压力更容易耗掉你。",
               "CC": "COMT 快速清除：反应快、抗压好，代价是容易对慢节奏不耐烦。"},
    "rs1801260": {"CC": "生物钟偏晚，夜里更像你自己。",
                  "TT": "生物钟偏早，早晨的状态通常比深夜好。"},
}

DEMO_GENOME_PRESETS = {
    "balanced": {
        "label": "均衡型 · 参考纯合",
        "desc": "全部标记为参考型。作为对照样本，展示“没有偏好”的基因底稿。",
        "gt": {},
    },
    "sensitive": {
        "label": "高敏型 · 慢清除",
        "desc": "COMT 慢速、OXTR 敏感、MC1R 变异——感知细腻，恢复较慢，也更容易被细节打动。",
        "gt": {"rs4680": "TT", "rs53576": "TT", "rs6265": "TT",
               "rs1805007": "TT", "rs762551": "CC", "rs1799971": "CC"},
    },
    "explorer": {
        "label": "探索型 · 高多巴胺",
        "desc": "DRD4 探索型、COMT 快速、DRD2 奖赏敏感——容易厌倦，也容易出发。",
        "gt": {"rs4680": "CC", "rs1800955": "AA", "rs1800497": "TT",
               "rs1801260": "CC", "rs762551": "AA", "rs1815739": "CC"},
    },
    "steady": {
        "label": "稳态型 · 慢节奏",
        "desc": "OXTR 参考型、MAOA 参考型、CLOCK 早型——情绪回稳快，作息偏早。",
        "gt": {"rs53576": "CC", "rs6323": "TT", "rs1801260": "TT",
               "rs1799983": "GG", "rs1800629": "GG", "rs1815739": "TT"},
    },
}


# ---------------------------------------------------------------- 解析
@dataclass
class SequenceRecord:
    name: str
    seq: str


@dataclass
class DNAData:
    kind: str
    source: str
    sequences: list[SequenceRecord] = field(default_factory=list)
    genotypes: dict[str, str] = field(default_factory=dict)
    declared: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    total_bases: int = 0
    scan_bases: int = 0


def _norm_seq(s: str) -> str:
    return re.sub(r"[^ACGTN]", "", s.upper())


def parse_fasta(text: str, source: str) -> DNAData:
    recs: list[SequenceRecord] = []
    name = "sequence_1"
    buf: list[str] = []
    declared: dict[str, str] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith(">"):
            if buf:
                recs.append(SequenceRecord(name, "".join(buf)))
                buf = []
            name = s[1:].strip() or f"sequence_{len(recs) + 1}"
            for m in re.finditer(r"(rs\d+)\s*[=:]\s*([ACGT]{1,2})\b", name, re.I):
                declared[m.group(1).lower()] = m.group(2).upper()
        elif not s.startswith(";"):
            buf.append(_norm_seq(s))
    if buf:
        recs.append(SequenceRecord(name, "".join(buf)))
    recs = [r for r in recs if len(r.seq) >= 40]
    if not recs:
        raise DNAError("FASTA 中没有可用的碱基序列（至少 40 bp）。")
    total = sum(len(r.seq) for r in recs)
    d = DNAData(kind="fasta", source=source, sequences=recs, declared=declared, total_bases=total)
    d.notes.append(f"读取 {len(recs)} 条序列，共 {total:,} bp。")
    return d


def parse_genotype(text: str, source: str) -> DNAData:
    """23andMe / AncestryDNA / 通用四列格式：rsid  chrom  pos  genotype。"""
    g: dict[str, str] = {}
    declared: dict[str, str] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            m = re.match(r"#\s*(rs\d+)\s*[=:]\s*([ACGT]{1,2})\b", s, re.I)
            if m:
                declared[m.group(1).lower()] = m.group(2).upper()
            continue
        parts = re.split(r"[\t, ]+", s)
        if len(parts) < 4:
            continue
        rsid = parts[0].strip().lower()
        if not rsid.startswith("rs"):
            continue
        gt = parts[-1].strip().upper()
        if not re.fullmatch(r"[ACGT]{1,2}", gt):
            continue
        # 半数以上格式里字母序不代表相位，统一按字母序存，判定时不区分
        g[rsid] = "".join(sorted(gt))
    if not g and not declared:
        raise DNAError("没有识别到基因型行（格式应为 rsid 染色体 位置 基因型）。")
    d = DNAData(kind="genotype", source=source, genotypes=g, declared=declared)
    d.notes.append(f"读取 {len(g)} 个基因型位点。")
    return d


def parse_vcf(text: str, source: str) -> DNAData:
    g: dict[str, str] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        cols = s.split("\t") if "\t" in s else re.split(r"\s+", s)
        if len(cols) < 8:
            continue
        rsid = cols[2].strip().lower()
        if not rsid.startswith("rs"):
            m = re.search(r"rs\d+", cols[7])
            if not m:
                continue
            rsid = m.group(0).lower()
        ref = cols[3].strip().upper()
        alt = cols[4].strip().upper().split(",")[0]
        if len(cols) < 10:
            continue
        fmt = cols[8]
        sample = cols[9]
        info = dict(zip(fmt.split(":"), sample.split(":")))
        gt = info.get("GT", "")
        if not gt:
            continue
        bases = []
        for i in re.split(r"[/|]", gt):
            if i == "0":
                bases.append(ref)
            elif i.isdigit() and int(i) == 1:
                bases.append(alt[:1])
            elif i in ("", "."):
                continue
        if len(bases) < 2:
            continue
        g[rsid] = "".join(sorted(bases[:2]))
    if not g:
        raise DNAError("VCF 中没有可用的 GT 基因型字段（需要 FORMAT 含 GT 且有样本列）。")
    d = DNAData(kind="vcf", source=source, genotypes=g)
    d.notes.append(f"从 VCF 读取 {len(g)} 个带基因型的位点。")
    return d


def parse_genome_json(text: str, source: str) -> DNAData:
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DNAError(f"JSON 解析失败：{exc.msg}") from exc
    if not isinstance(obj, dict):
        raise DNAError("基因 JSON 应为对象。")
    declared = {
        str(k).lower(): str(v).upper()
        for k, v in (obj.get("markers") or obj.get("genotypes") or {}).items()
    }
    declared = {k: v for k, v in declared.items() if re.fullmatch(r"[ACGT]{1,2}", v)}
    seq = obj.get("sequence") or obj.get("seq")
    if isinstance(seq, str) and len(_norm_seq(seq)) >= 40:
        clean = _norm_seq(seq)
        d = DNAData(kind="json", source=source,
                    sequences=[SequenceRecord(obj.get("name") or "sequence_1", clean)],
                    declared=declared, genotypes=declared, total_bases=len(clean))
    elif declared:
        d = DNAData(kind="json", source=source, declared=declared, genotypes=declared)
    else:
        raise DNAError("JSON 中既没有 sequence，也没有 markers。")
    d.notes.append("JSON 基因样本。")
    return d


def parse_bytes(data: bytes, filename: str = "dna.fasta") -> DNAData:
    if not data:
        raise DNAError("文件为空。")
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    text = data.decode("utf-8-sig", errors="replace")
    head = text[:4000]
    if ext == "vcf" or re.search(r"^##fileformat=VCF", head, re.M):
        return parse_vcf(text, filename)
    if ext == "json" or head.lstrip().startswith("{"):
        return parse_genome_json(text, filename)
    if head.lstrip().startswith(">") or re.search(r"(?m)^>", head):
        return parse_fasta(text, filename)
    if re.search(r"(?mi)^(?:#\s*)?rs\d+\b", head):
        if re.search(r"(?m)^rs\d+", text) or re.search(r"(?mi)^#\s*rs\d+\s*[=:]", text):
            return parse_genotype(text, filename)
    seq = _norm_seq(re.sub(r"[\s\d]", "", text))
    if len(seq) >= 40:
        d = DNAData(kind="text", source=filename,
                    sequences=[SequenceRecord("seq_1", seq)], total_bases=len(seq))
        d.notes.append(f"按纯碱基序列处理，共 {len(seq):,} bp。")
        return d
    raise DNAError("无法识别的基因格式。支持 FASTA / 23andMe / VCF / JSON / 纯序列。")


# ---------------------------------------------------------------- 序列统计
def gc_content(seq: str) -> float:
    s = _norm_seq(seq)
    if not s:
        return 0.0
    return (s.count("G") + s.count("C")) / len(s)


def gc_track(seq: str, windows: int = 72, win: int = 2000) -> list[float]:
    s = _norm_seq(seq)
    if not s:
        return []
    win = min(win, max(20, len(s) // 2))
    step = max(1, (len(s) - win) // max(1, windows - 1))
    out = []
    for i in range(windows):
        start = i * step
        out.append(round(gc_content(s[start : start + win]) * 100, 2))
    return out


def base_composition(seq: str) -> dict[str, float]:
    s = _norm_seq(seq)
    n = len(s) or 1
    return {b: round(s.count(b) / n * 100, 2) for b in "ACGT"}


CODON_TABLE = {
    "TTT": "F", "TTC": "F", "TTA": "L", "TTG": "L", "CTT": "L", "CTC": "L", "CTA": "L", "CTG": "L",
    "ATT": "I", "ATC": "I", "ATA": "I", "ATG": "M", "GTT": "V", "GTC": "V", "GTA": "V", "GTG": "V",
    "TCT": "S", "TCC": "S", "TCA": "S", "TCG": "S", "CCT": "P", "CCC": "P", "CCA": "P", "CCG": "P",
    "ACT": "T", "ACC": "T", "ACA": "T", "ACG": "T", "GCT": "A", "GCC": "A", "GCA": "A", "GCG": "A",
    "TAT": "Y", "TAC": "Y", "TAA": "*", "TAG": "*", "CAT": "H", "CAC": "H", "CAA": "Q", "CAG": "Q",
    "AAT": "N", "AAC": "N", "AAA": "K", "AAG": "K", "GAT": "D", "GAC": "D", "GAA": "E", "GAG": "E",
    "TGT": "C", "TGC": "C", "TGA": "*", "TGG": "W", "CGT": "R", "CGC": "R", "CGA": "R", "CGG": "R",
    "AGT": "S", "AGC": "S", "AGA": "R", "AGG": "R", "GGT": "G", "GGC": "G", "GGA": "G", "GGG": "G",
}


def orfs(seq: str, max_scan: int = 120_000, limit: int = 6) -> list[dict]:
    """三个读框里找最长 ORF（ATG…终止）。用于展示"这段序列像不像编码区"。"""
    s = _norm_seq(seq[:max_scan])
    found: list[dict] = []
    for frame in range(3):
        i = frame
        start = None
        while i + 3 <= len(s):
            codon = s[i : i + 3]
            if codon == "ATG" and start is None:
                start = i
            elif codon in ("TAA", "TAG", "TGA") and start is not None:
                length = i + 3 - start
                if length >= 180:
                    aa = "".join(CODON_TABLE.get(s[j : j + 3], "X") for j in range(start, i + 3, 3))
                    found.append({
                        "frame": frame + 1,
                        "start": start + 1,
                        "end": i + 3,
                        "bp": length,
                        "aa": length // 3,
                        "preview": aa[:26] + ("…" if len(aa) > 26 else ""),
                    })
                start = None
            i += 3
    found.sort(key=lambda x: -x["bp"])
    return found[:limit]


def repeat_summary(seq: str, k: int = 6, top: int = 5) -> list[dict]:
    s = _norm_seq(seq)
    if len(s) < 2000:
        return []
    counts: dict[str, int] = {}
    step = max(1, len(s) // 300_000)
    for i in range(0, len(s) - k, max(1, step // 2)):
        km = s[i : i + k]
        if "N" in km:
            continue
        counts[km] = counts.get(km, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])[:top]
    return [{"kmer": k, "count": c} for k, c in ranked]


def hashes(seq: str) -> dict[str, str]:
    s = _norm_seq(seq)
    if not s:
        return {"sha256_12": "", "sha256_full": ""}
    h = hashlib.sha256(s.encode("ascii", "ignore")).hexdigest()
    return {"sha256_12": h[:12], "sha256_full": h}


# ---------------------------------------------------------------- 基因型判定
def _revcomp(s: str) -> str:
    return s.translate(COMPLEMENT)[::-1]


def _context_variants(marker: Marker) -> list[str]:
    ctx = marker.context.upper()
    v = len(ctx) // 2
    outs = [ctx[:v] + base + ctx[v + 1 :] for base in "ACGT"]
    return outs + [_revcomp(x) for x in outs]


def call_from_sequence(seq: str, marker: Marker) -> dict | None:
    """在序列中寻找恰好覆盖变异位点的参考上下文。

    判定规则：以变异位点为中心，中心左侧 30 bp 与右侧 30 bp 分别与参考上下文
    比对，每侧允许 <=1 处差异；中心碱基可在 A/C/G/T 中任取（纯合/杂合都能读出）。
    找不到上下文就返回 None（未检出），绝不做插补。
    """
    c0 = marker.context.upper()
    v = len(c0) // 2
    left_flank = c0[:v]
    right_flank = c0[v + 1:]
    # 锚点：左翼最后 14 bp，保证在长序列里定位稳定
    anchor = left_flank[-14:]
    candidates: set[tuple[int, str]] = set()

    def scan(hay: str) -> None:
        start = 0
        while True:
            pos = hay.find(anchor, start)
            if pos < 0:
                return
            start = pos + 1
            w_start = pos - (len(left_flank) - len(anchor))
            w_end = w_start + len(c0)
            if w_start < 0 or w_end > len(hay):
                continue
            window = hay[w_start:w_end]
            lm = sum(1 for i in range(v) if window[i] != c0[i])
            rm = sum(1 for i in range(v + 1, len(c0)) if window[i] != c0[i])
            if lm <= 1 and rm <= 1 and window[v] in "ACGT":
                candidates.add((w_start, window[v]))

    scan(seq)
    if len(seq) < 6_000_000:
        scan(_revcomp(seq))
    if not candidates:
        return None
    hits = len(candidates)
    center = c0[v]
    for _, base in sorted(candidates):
        if base != center:
            return {
                "gt": "".join(sorted({marker.ref_allele, base})),
                "method": "context-scan",
                "quality": round(max(0.4, 1.0 - min(hits, 8) * 0.06), 2),
                "hits": hits,
            }
    return {
        "gt": marker.ref_allele * 2,
        "method": "context-ref",
        "quality": round(max(0.35, 1.0 - min(hits, 8) * 0.08), 2),
        "hits": hits,
    }


def judge_markers(dna: DNAData) -> tuple[list[dict], dict]:
    scan_seq = dna.sequences[0].seq[:2_000_000] if dna.sequences else ""
    dna.scan_bases = len(scan_seq)
    results: list[dict] = []
    for m in MARKERS:
        gt = None
        method = ""
        quality = 0.0
        if m.rsid in dna.genotypes:
            gt = dna.genotypes[m.rsid]
            method = "genotype-file"
            quality = 1.0
        elif m.rsid in dna.declared:
            value = dna.declared[m.rsid]
            if re.fullmatch(r"[ACGT]{1,2}", value):
                gt = value
                method = "declared"
                quality = 0.9
        if gt is None and scan_seq:
            call = call_from_sequence(scan_seq, m)
            if call:
                gt = call["gt"]
                method = call["method"]
                quality = call["quality"]
        if gt is None:
            continue
        gt = "".join(sorted(gt))
        if not re.fullmatch(r"[ACGT]{1,2}", gt):
            continue
        copies = gt.count(m.functional)
        genotype = f"{gt[0]}/{gt[-1]}" if len(gt) == 2 else gt[0]
        results.append({
            "rsid": m.rsid,
            "gene": m.gene,
            "chromosome": m.chromosome,
            "pos": m.pos,
            "genotype": genotype,
            "ref": m.ref_allele,
            "functional": m.functional,
            "copies": copies,
            "dose": round(copies / 2, 2) if len(gt) == 2 else round(copies, 2),
            "trait": m.trait,
            "effect": m.effect,
            "note": m.note,
            "method": method,
            "quality": round(float(quality), 2),
            "confidence": m.confidence,
            "zygosity_known": method != "context-scan",
            "direction": m.direction,
        })
    coverage = {
        "markers_hit": len(results),
        "markers_total": len(MARKERS),
        "coverage": round(len(results) / len(MARKERS), 3),
        "used_sequence": bool(scan_seq),
        "scan_bases": len(scan_seq),
        "from_file": sum(1 for r in results if r["method"] in ("genotype-file", "declared")),
    }
    return results, coverage


# ---------------------------------------------------------------- 投影
def gene_tendencies(markers: list[dict]) -> tuple[dict[str, float], dict[str, list[dict]]]:
    """把基因型剂量投影为 7 个倾向（0.15~0.85），并记录来源以便 UI 解释。"""
    num = {t: 0.0 for t in TRAITS}
    den = {t: 0.0 for t in TRAITS}
    sources: dict[str, list[dict]] = {t: [] for t in TRAITS}
    for m in markers:
        dirs = m.get("direction") or {}
        if not dirs:
            continue
        for trait, direction in dirs.items():
            if trait not in num:
                continue
            weight = 1.0 if m["confidence"] == "high" else 0.7 if m["confidence"] == "medium" else 0.4
            num[trait] += direction * weight * m["dose"]
            den[trait] += abs(direction) * weight
            sources[trait].append({
                "rsid": m["rsid"], "gene": m["gene"], "genotype": m["genotype"],
                "note": m["effect"], "direction": direction,
            })
    tendencies = {}
    for trait in TRAITS:
        if den[trait] <= 0:
            tendencies[trait] = 0.5
            continue
        centered = num[trait] / den[trait]  # 约 -1 ~ 1
        tendencies[trait] = round(sig.clamp(0.5 + 0.32 * centered, 0.15, 0.85), 3)
    return tendencies, sources


def micro_insights(markers: list[dict]) -> list[dict]:
    out = []
    for m in markers:
        table = INSIGHT_RULES.get(m["rsid"])
        if not table:
            continue
        key = m["genotype"].replace("/", "")
        text = table.get(key) or table.get("".join(sorted(key)))
        if text:
            out.append({"rsid": m["rsid"], "gene": m["gene"], "genotype": m["genotype"], "text": text})
    # 优先展示高把握度、非“性格”的可见性状
    out.sort(key=lambda x: (x["gene"] in ("COMT", "BDNF", "OXTR", "MAOA"), x["rsid"]))
    return out[:8]


# ---------------------------------------------------------------- 汇总
def analyze(dna: DNAData, subject: str = "") -> dict:
    markers, coverage = judge_markers(dna)
    tendencies, sources = gene_tendencies(markers)
    insights = micro_insights(markers)
    seq = dna.sequences[0].seq if dna.sequences else ""
    gc = round(gc_content(seq) * 100, 2) if seq else None
    stats = {
        "kind": dna.kind,
        "total_bases": dna.total_bases or (len(seq) if seq else 0),
        "scan_bases": dna.scan_bases or (len(seq) if seq else 0),
        "gc_percent": gc,
        "composition": base_composition(seq) if seq else None,
        "gc_track": gc_track(seq) if seq else [],
        "orfs": orfs(seq) if seq and len(seq) >= 3000 else [],
        "repeats": repeat_summary(seq) if seq else [],
        "seq_name": dna.sequences[0].name if dna.sequences else "",
        "fingerprint": hashes(seq)["sha256_12"] if seq else "",
    }
    parts = []
    if coverage["markers_hit"]:
        parts.append(min(1.0, coverage["markers_hit"] / 10) * 0.7)
    if seq:
        parts.append(min(1.0, math.log10(max(10, len(seq))) / 6) * 0.3)
    confidence = round(sum(parts), 3) if parts else 0.0
    return {
        "kind": dna.kind,
        "source": dna.source,
        "notes": dna.notes,
        "subject": subject,
        "coverage": coverage,
        "confidence": confidence,
        "stats": stats,
        "markers": markers,
        "tendencies": tendencies,
        "sources": sources,
        "insights": insights,
        "missing": [
            {"rsid": m.rsid, "gene": m.gene, "trait": m.trait}
            for m in MARKERS if m.rsid not in {x["rsid"] for x in markers}
        ][:10],
        "disclaimer": "基因倾向为艺术化权重，非医学或心理诊断；单基因效应极小，环境与经历的作用更大。",
    }


def load_path(path: str) -> DNAData:
    import os
    with open(path, "rb") as f:
        return parse_bytes(f.read(), os.path.basename(path))


# ---------------------------------------------------------------- 示例基因
def _flanked(marker: Marker, gt: str, rng) -> str:
    ctx = list(marker.context.upper())
    v = len(ctx) // 2
    # 变体序列：把中心碱基改成基因型里实际携带的那个等位
    if gt and gt[-1] != marker.ref_allele:
        ctx[v] = gt[-1]
    else:
        ctx[v] = marker.ref_allele
    back = "".join(rng.choice("ACGT") for _ in range(700))
    front = "".join(rng.choice("ACGT") for _ in range(700))
    return front + "".join(ctx) + back


def _pad_to_frame(seq: str, frame: int) -> str:
    need = (-len(seq)) % 3
    return seq + "".join(seq[-1] for _ in range(need)) if need else seq


def demo_fasta(gt: dict[str, str] | None = None, seed: int = 11) -> str:
    """生成一份可被本系统真正读懂的演示 FASTA（随机背景 + 真实参考上下文）。"""
    import random
    rng = random.Random(seed)
    gt = gt or {}
    lines = [
        ">EchoMind_demo_subject synthetic marker panel (NOT a real genome)",
        "; 演示用：随机背景 + 20 个常见变异位点的 GRCh38 参考上下文。",
        "; 不含任何真实受试者数据。",
    ]
    for m in MARKERS:
        lines.append(_flanked(m, gt.get(m.rsid, m.ref_allele * 2), rng))
    # 结尾放一段可读 ORF，用于 ORF 面板
    codons = ["GCT", "AAA", "CTG", "TTC", "GAA", "CAG", "AGC", "GTG", "ATC"]
    orf = "ATG" + "".join(rng.choice(codons) for _ in range(120)) + "TAA"
    lines.append(orf)
    return "\n".join(lines) + "\n"


def demo_genotype_file(gt: dict[str, str] | None = None) -> str:
    gt = gt or {}
    rows = [
        "# EchoMind demo genotype (synthetic; not a real person)",
        "# rsid\tchromosome\tposition\tgenotype",
    ]
    for m in MARKERS:
        rows.append("\t".join([m.rsid, m.chromosome, str(m.pos), gt.get(m.rsid, m.ref_allele * 2)]))
    return "\n".join(rows) + "\n"


def demo_vcf(gt: dict[str, str] | None = None) -> str:
    gt = gt or {}
    rows = [
        "##fileformat=VCFv4.2",
        "##source=EchoMind-demo",
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tDEMO",
    ]
    for m in MARKERS:
        call = gt.get(m.rsid, m.ref_allele * 2)
        alt = m.functional if call.count(m.functional) else next(b for b in "ACGT" if b != m.ref_allele)
        allele_idx = []
        for ch in call:
            allele_idx.append("0" if ch == m.ref_allele else "1")
        if len(allele_idx) == 1:
            allele_idx = allele_idx * 2
        rows.append("\t".join([
            m.chromosome, str(m.pos), m.rsid, m.ref_allele, alt, ".", "PASS", ".",
            "GT", "/".join(allele_idx[:2]),
        ]))
    return "\n".join(rows) + "\n"
