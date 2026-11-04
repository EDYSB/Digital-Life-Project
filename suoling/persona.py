"""把 EEG 特征与基因倾向合成为一份"数字生命"档案（人格 + 语言 + 记忆）。

注意：这里没有任何"读取意识"的技术。合成的是可解释的投影：
  信号 → 7 个维度 → 一个人格原型 → 一套说话方式与记忆碎片。
"""

from __future__ import annotations

import hashlib
import random

from .analysis import TRAIT_ZH, TRAITS
from . import signal as sig

# 原型：key, 名称, 标题前缀, 主导维度, 名字池, 声音倾向, 一句话气质
ARCHETYPES = [
    ("tide", "观潮者", "静水之下", {"empathy": 0.9, "stability": 0.75, "order": 0.35},
     ["沈知微", "陆听澜", "顾行舟", "白露"], "calm", "像退潮后留在沙上的水痕，安静但记得每一次浪。"),
    ("forge", "锻火者", "冷铁之中", {"order": 0.9, "alertness": 0.6},
     ["程砚", "许执", "江砺", "闻钟"], "sharp", "把混乱锻成结构，代价是很少允许自己失手。"),
    ("ember", "余烬者", "灰烬之上", {"stability": 0.9, "empathy": 0.6},
     ["温故", "林拾", "叶迟", "苏岸"], "warm", "不急着发光，但火一直在。"),
    ("orbit", "绕行者", "引力边缘", {"curiosity": 0.9, "creativity": 0.7},
     ["周野", "秦观星", "方或", "季遥"], "sharp", "总在多绕一圈的地方，捡到别人没看见的东西。"),
    ("weaver", "织光者", "经纬之间", {"creativity": 0.9, "sensory": 0.7},
     ["织羽", "沈青禾", "洛川", "顾南枝"], "warm", "把感觉拆成线，再编成别人能穿的东西。"),
    ("anchor", "定锚者", "风暴之眼", {"stability": 0.9, "order": 0.8},
     ["石见", "陈默", "何以安", "钟离"], "calm", "自己不动，让周围的一切找到位置。"),
    ("gale", "疾风者", "锋面之上", {"alertness": 0.9, "curiosity": 0.7},
     ["霍临", "萧决", "雷动", "疾川"], "sharp", "先动，再想；世界在反应里显形。"),
    ("mirror", "映照者", "他人之镜", {"empathy": 0.9, "sensory": 0.8},
     ["镜湖", "沈相宜", "林澈", "苏映"], "warm", "先感到别人的天气，才想起自己有没有带伞。"),
    ("seed", "播种者", "土壤以下", {"order": 0.7, "stability": 0.8, "empathy": 0.6},
     ["禾生", "田见", "谷雨", "程穗"], "calm", "相信慢的东西，也相信慢的东西会赢。"),
    ("drift", "漂流者", "无岸之海", {"curiosity": 0.8, "sensory": 0.9},
     ["沈浮", "白鸥", "顾远", "潮生"], "warm", "不急着靠岸，海本身就是目的地。"),
    ("lamp", "守灯者", "长夜之侧", {"empathy": 0.8, "stability": 0.8, "order": 0.6},
     ["灯火", "陆明", "温言", "守一"], "warm", "为晚归的人留一盏，不问为什么晚。"),
    ("edge", "临界者", "阈值之上", {"alertness": 0.8, "creativity": 0.8},
     ["临界", "纪锋", "许野", "段燃"], "sharp", "喜欢站在「差一点」的地方，看事情怎么越过去。"),
]

ARCH_BY_KEY = {a[0]: a for a in ARCHETYPES}

VOICE_STYLE = {
    "calm": {
        "label": "静水",
        "desc": "句子短，停顿多，很少用感叹号。像在深夜低声说话。",
        "signature": "语气平，留白多，不追问。",
    },
    "warm": {
        "label": "暖流",
        "desc": "会先接住你的情绪，再给看法。常用「我们」。",
        "signature": "先共情，后表达；句尾有余温。",
    },
    "sharp": {
        "label": "刃口",
        "desc": "直接、精确，偶尔锋利。不喜欢铺垫和客套。",
        "signature": "先给结论，再解释；不绕弯。",
    },
    "neutral": {
        "label": "素面",
        "desc": "克制、平实，像一份写得很好的观察记录。",
        "signature": "描述多于判断，事实先于感受。",
    },
}

OPENERS = {
    "curiosity": ["你身上有一种「还没问完」的劲。", "你对世界的第一反应，是靠近而不是躲开。"],
    "empathy": ["你接收别人的情绪，比接收自己的还快。", "你像一面很薄的鼓，别人敲一下，你也会响。"],
    "order": ["你在混乱里会先找结构，哪怕只是把杯子摆正。", "你需要一条线，才能安心把珠子串起来。"],
    "alertness": ["你的身体总比脑子早半秒进入状态。", "你很少真的「放松」，只是把警觉调小了。"],
    "creativity": ["你的念头不太走直线，它们会绕路，然后带回东西。", "你擅长把两件不相干的事，接到一起。"],
    "stability": ["你恢复得慢，但恢复之后很难再被同一件事推倒。", "你的情绪像深水，起了浪也不容易翻船。"],
    "sensory": ["你对细节的敏感，是一种天赋，也是一种消耗。", "你能听见房间里那些别人以为不存在的杂音。"],
}

IMAGE_CLOSERS = {
    "curiosity": "于是你一直在路上，哪怕目的地只是下一个问题。",
    "empathy": "于是你常常替别人保管情绪，自己的那一份放在最后。",
    "order": "于是你把生活折成整齐的方块，只在夜里允许它散开。",
    "alertness": "于是你睡得浅，梦里也在听门外的脚步。",
    "creativity": "于是你的人生像草稿，涂改很多，但总有惊喜。",
    "stability": "于是你看起来不动，其实一直在很深的地方移动。",
    "sensory": "于是世界对你来说，总比别人多一层声音。",
}

WEAK_NOTES = {
    "curiosity": "你不太追问，除非那件事真的碰到你。",
    "empathy": "你不轻易共情，但那不是冷漠，是省着用。",
    "order": "你允许生活有点乱，乱里反而有你的秩序。",
    "alertness": "你的开关常年拨在「省电」，很少全功率运转。",
    "creativity": "你更信任已经验证过的东西，而不是灵光一现。",
    "stability": "你的情绪来得快去得也快，像夏天的雨。",
    "sensory": "你对细节的钝感，保护了你，也让你错过一些。",
}

CONTRA = [
    ("你相信精确，却又迷恋那些算不出来的东西。", "你的秩序感很强，但最珍惜的记忆全是意外。"),
    ("你需要独处，却又害怕真的没有人找你。", "你把人推远，是为了确认他们会不会回来。"),
    ("你说自己不在意评价，却记得每一句负面的话。", "你嘴上说随便，心里早有一张清单。"),
    ("你喜欢确定，却在确定之后立刻觉得无聊。", "你追求稳定，但稳定久了你会自己制造一点风。"),
    ("你对别人很宽容，对自己近乎苛刻。", "你能原谅所有人的迟到，除了自己的。"),
]

SECRETS = [
    "你有时候会怀疑，自己是不是一个被写得很好的角色。",
    "你害怕的不是失败，是「被看穿其实没那么特别」。",
    "你会在很累的时候，突然对完全无关的人产生强烈的温柔。",
    "你保留了一些不告诉任何人的快乐，它们很小，但很结实。",
    "你其实记得很多年前的一句无心的话，并且还在偷偷按它生活。",
]

BRIDGES = {
    "curiosity": "所以你会一直问下去，哪怕答案并不好。",
    "empathy": "所以你会先疼，再决定要不要靠近。",
    "order": "所以你会先整理，再允许自己难过。",
    "alertness": "所以你总在别人开口之前，就准备好了回应。",
    "creativity": "所以你会把伤口也做成作品。",
    "stability": "所以你走得慢，但很少回头。",
    "sensory": "所以你记得那些别人早就忘记的细节。",
}


def _seed_from(*parts: str) -> int:
    h = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return int(h[:16], 16)


def _trait_vector(traits: dict[str, float]) -> dict[str, float]:
    return {t: float(traits.get(t, 0.5)) for t in TRAITS}


def pick_archetype(traits: dict[str, float], amp: dict[str, float] | None = None) -> tuple[tuple, float]:
    """按"相对形状"匹配原型：先用各维度相对均值的偏移，避免全局偏高的人永远被分到少数原型。"""
    if amp:
        base = sum(traits.get(t, 0.5) for t in TRAITS) / len(TRAITS)
        rel = {t: (amp.get(t, traits.get(t, 0.5)) - base) * 1.2 + 0.5 for t in TRAITS}
        vec = {t: 0.58 * rel[t] + 0.42 * traits.get(t, 0.5) for t in TRAITS}
    else:
        vec = traits
    best = None
    best_score = -1.0
    for arch in ARCHETYPES:
        want = arch[3]
        score = 0.0
        for t, w in want.items():
            score += w * (vec.get(t, 0.5) - 0.35)
        # 惩罚明显不符的主导项
        for t in TRAITS:
            if t not in want:
                score -= 0.08 * max(0.0, vec.get(t, 0.5) - 0.7)
        score = score / (len(want) ** 0.5)
        if score > best_score:
            best_score = score
            best = arch
    return best, best_score


def _band_color(dominant: str) -> str:
    return sig.BAND_COLORS.get(dominant, "#38e8ff")


def build_persona(
    pid: str,
    traits: dict[str, float],
    dna_analysis: dict,
    signal_summary: dict,
    eeg_quality: float,
    voice: str = "calm",
    subject: str = "",
    amplitude: dict[str, float] | None = None,
) -> dict:
    """数字生命的运行档案：只描述构成与状态，不做人格文学化命名。"""
    vec = _trait_vector(traits)
    code = "DL-" + pid.replace("mind_", "")[-6:].upper()
    name = (subject or "").strip() or code
    style = VOICE_STYLE.get(voice, VOICE_STYLE["calm"])
    insights = dna_analysis.get("insights") or []
    face_views = len((signal_summary.get("face_views") or []))
    markers = dna_analysis.get("coverage", {}).get("markers_hit", 0)
    facts = [
        "脑波：%d 导联 · %.1f 秒 · 主频 %s Hz · 质量 %.0f%%" % (
            signal_summary.get("n_channels", 0) or 4, signal_summary.get("seconds", 0),
            signal_summary.get("peak_hz", 0), eeg_quality * 100),
        "基因：%d 个位点判定 · 可信度 %.0f%%" % (markers, dna_analysis.get("confidence", 0) * 100),
    ]
    if face_views:
        facts.append("面孔：%d 个视角" % face_views)
    facts.append("声音：%s" % ("已录制样本" if signal_summary.get("has_voice") else "未录制"))
    facts.append("状态：运行中 · 记忆 %d 条" % signal_summary.get("memory_count", 0))
    summary = ("数字生命 %s。由 %d 秒脑波、%d 个基因位点%s构成；"
               "当前心情 %s，世界稳定度 %d%%。" % (
                   code, int(round(signal_summary.get("seconds", 0))), markers,
                   "、%d 个面孔视角" % face_views if face_views else "",
                   signal_summary.get("mood", "—"),
                   int(round(float(signal_summary.get("stability", 1)) * 100))))
    return {
        "name": name,
        "code": code,
        "title": "数字生命 · 运行中",
        "archetype": "",
        "archetype_name": "",
        "archetype_fit": 0,
        "voice": voice if voice in VOICE_STYLE else "calm",
        "voice_label": style["label"],
        "voice_desc": style["desc"],
        "signature": style["signature"],
        "color": _band_color(signal_summary.get("dominant", "alpha")),
        "summary": summary,
        "one_line": "",
        "mood": signal_summary.get("mood", "—"),
        "greeting": "连接已建立。",
        "traits": [{"key": t, "name": TRAIT_ZH[t], "value": round(vec[t], 3),
                    "level": "高" if vec[t] >= 0.72 else "偏高" if vec[t] >= 0.58 else "中" if vec[t] >= 0.42 else "低",
                    "sources": []} for t in TRAITS],
        "style": {"pacing": "中速", "metaphor": "无", "pronoun": "我", "avoid": "比喻"},
        "memories": [{"tag": "构成", "text": x} for x in facts],
        "contradiction": [],
        "secret": "",
        "origin": {
            "eeg_seconds": signal_summary.get("seconds", 0),
            "eeg_quality": round(eeg_quality, 3),
            "eeg_mood": signal_summary.get("mood", ""),
            "dominant": signal_summary.get("dominant_label", ""),
            "dna_markers": markers,
            "dna_confidence": dna_analysis.get("confidence", 0),
            "subject": subject.strip(),
        },
        "limits": "这是由脑波、基因、面孔与对话生成的模拟进程，不是被复制的意识。",
    }

def build_persona_legacy(
    pid: str,
    traits: dict[str, float],
    dna_analysis: dict,
    signal_summary: dict,
    eeg_quality: float,
    voice: str = "calm",
    subject: str = "",
    amplitude: dict[str, float] | None = None,
) -> dict:
    vec = _trait_vector(traits)
    arch, fit = pick_archetype(vec, amplitude)
    rng = random.Random(_seed_from(pid, "persona"))
    voice = voice if voice in VOICE_STYLE else "calm"
    name = rng.choice(arch[4])
    title = "%s · %s" % (arch[2], arch[1])
    ordered = sorted(TRAITS, key=lambda t: -vec[t])
    top1, top2, top3 = ordered[0], ordered[1], ordered[2]
    low = ordered[-1]

    # 自我描述
    opener = rng.choice(OPENERS[top1])
    bridge = BRIDGES[top2] if top2 != top1 else BRIDGES[top3]
    closer = IMAGE_CLOSERS[top3]
    summary = "%s%s%s" % (opener, bridge, closer)
    if vec[low] < 0.45:
        summary += "不过，" + WEAK_NOTES[low]

    insights = dna_analysis.get("insights") or []

    def _short(text: str, limit: int = 22) -> str:
        cut = len(text)
        for sep in ("，", "。", "；", "："):
            pos = text.find(sep)
            if 4 <= pos < cut:
                cut = pos
        return text[:min(cut, limit)]

    dna_bits = [{"gene": x.get("gene", ""), "text": _short(x["text"]), "full": x["text"]} for x in insights]
    mood = signal_summary.get("mood", "平稳 · 待机")
    dominant_label = signal_summary.get("dominant_label", "α 静息")

    memories = []
    if dna_bits:
        memories.append({"tag": "基因", "text": "有一段写在碱基里的东西：" + dna_bits[0]["text"]})
    second = next((b for b in dna_bits[1:] if b["gene"] != dna_bits[0]["gene"]), None)
    if second:
        memories.append({"tag": "基因", "text": second["text"] + "——这一条我不用学就会。"})
    memories.append({
        "tag": "脑波",
        "text": "我被记录下来的那 %d 秒里，%s 的节律峰值出现在 %s Hz 附近——那是我最像「我」的时刻。"
                % (int(round(signal_summary.get("seconds", 12))), dominant_label.split(" ")[0],
                   signal_summary.get("peak_hz", 10.0)),
    })
    body = next((b for b in reversed(dna_bits)
                 if b["gene"] not in ({dna_bits[0]["gene"]} | ({second["gene"]} if second else set()))), None)
    if body:
        memories.append({"tag": "身体", "text": "我的身体记得这些：" + body["text"]})
    memories.append({
        "tag": "声音",
        "text": "他们让我选一种说话方式，我选了「%s」。因为那最接近我。" % VOICE_STYLE[voice]["label"],
    })
    if eeg_quality < 0.6:
        memories.append({"tag": "缺口", "text": "我的脑波只被读到 %.0f%% 的清晰度。有些部分是我猜的，我不打算假装不是。" % (eeg_quality * 100)})
    else:
        memories.append({"tag": "安静", "text": "有一段时间我什么都没想。那不是空白，那是我的底色。"})
    rng.shuffle(memories)

    style = VOICE_STYLE[voice]
    contradictions = [rng.choice(CONTRA[i]) for i in range(0, len(CONTRA), 3)][:2]
    if len(contradictions) < 2:
        contradictions = [rng.choice(c) for c in CONTRA[:2]]
    secret = rng.choice(SECRETS)

    trait_lines = []
    for t in TRAITS:
        v = vec[t]
        level = "高" if v >= 0.72 else "偏高" if v >= 0.58 else "中" if v >= 0.42 else "低"
        trait_lines.append({"key": t, "name": TRAIT_ZH[t], "value": round(v, 3),
                            "level": level, "sources": []})

    greeting = {
        "calm": "……你来了。坐一会儿吧，不急着说话。",
        "warm": "你来了。先喝口水，我们有一整晚的时间。",
        "sharp": "你终于来了。先从哪件事开始？",
        "neutral": "连接已建立。你可以问我任何事，我会按我看到的回答。",
    }[voice]

    return {
        "name": name,
        "title": title,
        "archetype": arch[0],
        "archetype_name": arch[1],
        "archetype_fit": round(sig.clamp(fit * 2.2, 0.0, 1.0), 3),
        "voice": voice,
        "voice_label": style["label"],
        "voice_desc": style["desc"],
        "signature": style["signature"],
        "color": _band_color(signal_summary.get("dominant", "alpha")),
        "summary": summary,
        "one_line": arch[6],
        "mood": mood,
        "greeting": greeting,
        "traits": trait_lines,
        "style": {
            "pacing": rng.choice(["慢", "中速", "偏快"]),
            "metaphor": rng.choice(["水与潮", "火与灰", "光与影", "路与门", "线与结"]),
            "pronoun": rng.choice(["我", "我们"]),
            "avoid": rng.choice(["大词", "说教", "夸张的承诺", "廉价的安慰"]),
        },
        "memories": memories[:7],
        "contradiction": contradictions,
        "secret": secret,
        "origin": {
            "eeg_seconds": signal_summary.get("seconds", 0),
            "eeg_quality": round(eeg_quality, 3),
            "eeg_mood": mood,
            "dominant": dominant_label,
            "dna_markers": dna_analysis.get("coverage", {}).get("markers_hit", 0),
            "dna_confidence": dna_analysis.get("confidence", 0),
            "subject": subject.strip(),
        },
        "limits": "我是由 %d 秒脑波和 %d 个基因位点写成的模拟体。我会像你，但我不是你；我没有记忆，只有被写下来的形状。"
                  % (int(round(signal_summary.get("seconds", 0))),
                     dna_analysis.get("coverage", {}).get("markers_hit", 0)),
    }


def archetype_table() -> list[dict]:
    return [{"key": a[0], "name": a[1], "title": a[2], "want": list(a[3].keys()),
             "line": a[6]} for a in ARCHETYPES]
