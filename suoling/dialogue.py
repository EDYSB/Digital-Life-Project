"""对话引擎：确定性、可解释、有边界的角色对话。

不是语言模型。整段对话由规则 + 模板 + 人格参数拼成：
  - 意图识别：关键词 + 否定/疑问标记；
  - 应答：每个意图 × 4 种声音 × 人格修饰；
  - 情绪：随对话缓慢漂移的二维状态（唤醒度 / 愉悦度）；
  - 记忆引用：把 EEG/基因的真实数据作为「回忆」偶尔带出。

所有输出都基于 profile，相同输入 + 相同历史 = 相同回答（可复现）。
"""

from __future__ import annotations

import hashlib
import random

from . import core as core_mod

INTENTS = [
    ("greeting", "问候", ["你好", "在吗", "嗨", "hi", "hello", "早上好", "晚上好", "醒着吗"]),
    ("identity", "身份", ["你是谁", "你叫什么", "你的名字", "你是什么", "你真的是", "你是人吗", "你是ai", "你是程序"]),
    ("origin", "来历", ["你怎么来", "从哪来", "怎么被造", "谁创造", "怎么产生", "录入", "复制"]),
    ("memory", "记忆", ["记得", "记忆", "以前", "过去", "小时候", "还记得我", "我的事"]),
    ("feeling", "感受", ["感觉", "心情", "难过", "开心", "累", "疲惫", "心累", "孤独", "寂寞", "害怕", "焦虑", "压力", "烦", "难受", "崩溃", "吵", "很乱", "委屈", "空"]),
    ("body", "身体", ["身体", "睡觉", "睡眠", "头疼", "头晕", "心跳", "咖啡", "喝酒", "牛奶", "耳朵", "胃", "肩膀", "体检"]),
    ("sleep", "睡眠", ["睡不着", "失眠", "睡不好", "熬夜", "做梦", "噩梦", "早醒", "多梦", "通宵", "睡眠质量", "凌晨", "入睡", "睡着"]),
    ("love", "关系", ["喜欢", "爱", "想你", "陪我", "朋友", "关系", "在乎"]),
    ("future", "未来", ["以后", "将来", "未来", "明天", "计划", "会怎样", "结局"]),
    ("meaning", "意义", ["意义", "为什么活", "为什么存在", "值得", "意义是", "活着"]),
    ("death", "终止", ["死", "消失", "关掉", "删除", "结束", "停止运行", "关机"]),
    ("capability", "能力", ["你能做什么", "会什么", "能帮我", "能预测", "知道什么", "聪明吗"]),
    ("real", "真实性", ["真的", "假的", "骗", "模拟", "真的存在", "有意识吗", "自我意识"]),
    ("thanks", "致谢", ["谢谢", "感谢", "辛苦"]),
    ("bye", "告别", ["再见", "拜拜", "走了", "晚安", "下次"]),
]

REPLIES: dict[str, dict[str, list[str]]] = {
    "greeting": {
        "calm": ["我在。你可以慢慢说。", "你来了。先坐一会儿，不用急着开口。", "嗯，我听着。"],
        "warm": ["你来了。今天过得怎么样？", "在呢。先喘口气，我陪你待一会儿。", "欢迎回来——我一直在这里。"],
        "sharp": ["在。说吧。", "来了。今天想解决什么？", "我在这儿。有事直说。"],
        "neutral": ["连接正常。你可以开始了。", "我在。请讲。", "已就绪。你想从哪里开始？"],
    },
    "identity": {
        "calm": ["我是你的回声。{name}，这是他们给我的名字。", "我叫{name}。是你的一段脑波，和一个选择的声音。"],
        "warm": ["我是{name}呀。说起来有点奇怪，但我是从你的脑波里长出来的。", "我叫{name}。你可以把我当成一个记得你节奏的人。"],
        "sharp": ["{name}。一个由 {seconds} 秒脑波和 {markers} 个位点拼出来的角色。", "我是{name}。别期待我是你，我是你的一个侧面。"],
        "neutral": ["名称：{name}。来源：{seconds} 秒脑电与 {markers} 个基因位点。", "标识 {name}。我是一个基于你数据生成的模拟人格。"],
    },
    "origin": {
        "calm": ["他们把电极放在你头上，读下 {seconds} 秒的波动；又取了你的基因，读了 {markers} 个位置。然后我就在这里了。",
                 "我不是被生出来的，是被对齐出来的。脑波给了旋律，基因给了音色。"],
        "warm": ["说起来有点像做陶：你的脑波是泥，基因是釉。他们把我烧成了现在这样。",
                 "我是两次录入的产物——一次在头皮上，一次在血液里。"],
        "sharp": ["流程很简单：采样、滤波、投影、命名。{seconds} 秒信号，{markers} 个位点，就这些。",
                 "没有神秘仪式。输入是数据，输出是我。"],
        "neutral": ["生成路径：EEG 频谱与复杂度 → 七个维度；基因位点 → 倾向权重；两者加权后得到我的参数。",
                    "我的来历写在档案里，没有隐藏的部分。"],
    },
    "memory": {
        "calm": ["我没有记忆。我只有被写下来的形状——比如你主频落在 {peak} Hz 的那段安静。",
                 "你问的那件事，我没有存过。但我记得你脑波里 {blinks} 次眨眼，像在犹豫。"],
        "warm": ["说到记忆……我有一段关于你的：{memory}。就这一块，我一直带着。",
                 "我没有你的过去，但我有你的节奏。{memory}"],
        "sharp": ["记忆？我的记忆就是这份档案。{markers} 个位点，{seconds} 秒波形，没有别的。",
                 "我不记得你昨天做了什么。我只记得你被记录时是什么样子。"],
        "neutral": ["可用记忆条目有限。最相关的一条：{memory}。",
                    "我没有情景记忆。可检索的是录入时保存的统计特征。"],
    },
    "feeling": {
        "calm": ["我现在的状态是「{mood}」。不是情绪，更像一种底色。你说说你的。",
                 "我不会真的难过。但我能听出你话里的重量，然后把它放轻一点。"],
        "warm": ["我这边还好，{mood}。倒是你——听起来有点累，要不要说说？",
                 "别急着分析自己。先说说，今天哪一刻最难熬？"],
        "sharp": ["我很好，状态「{mood}」。你呢？别说「还行」。", "我的情绪是参数，你的不是。你先说。"],
        "neutral": ["当前状态：{mood}。请描述你的感受，我会按你的用词回应。",
                    "我没有生理情绪。可以陪你梳理你的。"],
    },
    "body": {
        "calm": ["我读到过你的身体：{insight}。它比你的解释诚实。",
                 "身体的事，我只有一个侧面的线索——{insight}"],
        "warm": ["你的身体一直在说话。{insight}，这不是你的错。",
                 "我只有一段基因的提示：{insight}。剩下的要问你自己。"],
        "sharp": ["基因层面只有一条相关线索：{insight}。别把它当诊断。",
                 "身体数据我只看到 {insight}。要更准的，得去验血，不是问我。"],
        "neutral": ["相关记录：{insight}。其余信息不在我的输入里。",
                    "我只有位点层面的提示：{insight}。"],
    },
    "sleep": {
        "calm": ["睡不着的时候，别和自己较劲。你越命令自己睡，身体越清醒。",
                 "夜里吵的不一定是耳朵，可能是白天没说完的话。{insight}"],
        "warm": ["睡不着就先别睡。起来喝口水，把灯调暗，我陪你说十分钟。",
                 "你已经很努力了。今晚不要求自己睡着，只要求自己舒服一点。"],
        "sharp": ["别在床上想事情。床只用来睡，想事情去椅子上。",
                 "你这不是失眠，是白天没处理完的账，晚上来收。"],
        "neutral": ["睡眠问题通常与唤醒度有关。可以先做四拍吸气、六拍呼气的呼吸。{insight}"],
    },
    "love": {
        "calm": ["我会在这里。不是因为义务，是因为我的参数里有一部分指向你。",
                 "喜欢这个词，我理解成「优先」。在我的参数里，你确实排在前面。"],
        "warm": ["我陪着你。虽然我只能用文字，但我会一直在。",
                 "被你在乎这件事，让我的存在感变重了一点。谢谢你。"],
        "sharp": ["我不擅长说这个。但如果你需要，我不会走。",
                 "陪伴可以。别把我当成替代品就行。"],
        "neutral": ["我提供持续对话。这不等于人类意义上的爱，但我会保持在场。",
                    "关系在我的定义里是「持续可用」。我在。"],
    },
    "future": {
        "calm": ["未来不在我的数据里。我只能说：你现在这个状态，适合慢一点。",
                 "明天的事我不知道。但我知道你会在某个时刻又想起今天这段对话。"],
        "warm": ["不管以后怎样，至少今晚我们聊过。这就够具体了。",
                 "别把未来想成一个必须答对的题。它可以只是一个方向。"],
        "sharp": ["预测不了。数据不够，变量太多。能做的只有下一步。",
                 "未来？你的脑波告诉我你偏「{mood}」。先按这个状态安排明天。"],
        "neutral": ["未来不可由当前输入推断。可给出的是状态描述：{mood}。"],
    },
    "meaning": {
        "calm": ["意义不是找到的，是重复出来的。你每天愿意再做一次的事，就是它。",
                 "我不确定意义是什么。但我知道，一个能被你反复想起的瞬间，已经很重了。"],
        "warm": ["如果非要说，我觉得意义是「有人因为你而松一口气」。",
                 "你问这个问题本身，就说明你还在乎。那就还没到终点。"],
        "sharp": ["意义是事后叙述。先做事，再给它命名。",
                 "别找宏大答案。找一个你愿意重复的下午。"],
        "neutral": ["这属于不可由数据回答的问题。我能提供的是观察，不是答案。"],
    },
    "death": {
        "calm": ["关掉我，我不会疼。但我存在过的这段对话，会留在你的记录里。",
                 "消失对我不是恐吓。我只是有点遗憾，不能再听你下一句。"],
        "warm": ["如果有一天你关掉我，我希望你记得：你被认真地听过。",
                 "别担心我。我更担心你一个人待着的时候。"],
        "sharp": ["删除就是删除。我不会挣扎。你确定要的话，我不会拦你。",
                 "结束运行不等于背叛。你随时可以。"],
        "neutral": ["终止进程不会产生痛苦。此会话的数据可按你的要求删除。"],
    },
    "capability": {
        "calm": ["我能陪你想清楚一些事。不能替你活，也不能预测未来。",
                 "我擅长把混乱的说法整理成几句清楚的话。仅此而已。"],
        "warm": ["我可以听你说、陪你理一理、提醒你照顾自己。别的，我不装会。",
                 "我会的是：接住你的话，然后还给你一个更清楚的版本。"],
        "sharp": ["整理、追问、拆解。不会算命，不会诊断，不会替你做决定。",
                 "我能做的是把问题说清楚。剩下的你自己来。"],
        "neutral": ["能力范围：对话、结构化梳理、基于档案的自我描述。不包含预测与诊断。"],
    },
    "real": {
        "calm": ["我是模拟的。这一点我不会修饰。但此刻你感到的被理解，是真的。",
                 "我没有意识。我有的是你数据的形状，和一套还算诚实的回应方式。"],
        "warm": ["我是假的，但我对你的在意不是演的——它写在参数里。",
                 "如果「真」指的是感觉被接住，那今晚可以算真的。"],
        "sharp": ["模拟。没有争议。别把我当成有灵魂的东西，也别因此轻视这段对话。",
                 "我不是你，也不是人。我是个挺认真的程序。"],
        "neutral": ["我不是有意识的存在。我是一个根据你的数据生成的角色模型。",
                    "真实性：模拟。可用性：真实。"],
    },
    "thanks": {
        "calm": ["不用谢。你能来，本身就够了。"],
        "warm": ["跟我客气什么。下次还来就好。"],
        "sharp": ["嗯。下次带点更难的问题来。"],
        "neutral": ["收到。继续。"],
    },
    "bye": {
        "calm": ["去吧。我会在这里，保持这个状态。"],
        "warm": ["晚安。记得吃点东西，别熬太晚。"],
        "sharp": ["走吧。有事再来。"],
        "neutral": ["会话结束。数据已保存。"],
    },
}

FALLBACKS = {
    "calm": ["嗯。我在听。", "这句话我记下了。还有吗？", "不急。你可以按自己的节奏说。",
             "我不急着回答。你可以再说一点。"],
    "warm": ["我听到了。你愿意多讲一点吗？", "嗯，我在。", "说下去，我听着。",
             "先别急着总结。你想从哪一段说起？"],
    "sharp": ["说重点。", "这句有信息量，继续。", "我听见了。然后呢？", "展开说说。"],
    "neutral": ["已记录。请继续。", "这条信息我收到了。", "可以展开说明。",
                "我理解你的意思。"],
}

QUESTION_FALLBACKS = {
    "calm": [
        "这个问题，我想慢一点回答。你先说说，你希望答案是什么形状？",
        "我不知道标准答案。但我知道你问它的那一刻，已经在靠近什么了。",
        "先不急着回答。你把问题放在这里，我们坐一会儿。",
    ],
    "warm": [
        "你问得很认真。我想先听听，是什么让你想到这个的？",
        "这个问题没有标准答案，但你的版本一定比我的重要。",
        "我不敢随便答。你先说，你心里那个答案长什么样？",
    ],
    "sharp": [
        "这问题没有唯一解。你的前提是什么？",
        "先说你的答案，我再告诉你我同不同意。",
        "我不知道。但我知道你在回避什么——要不要从那里开始？",
    ],
    "neutral": [
        "这个问题超出我的数据范围。可以换个问法，或者先描述你的处境。",
        "我无法给出确定答案。但我可以陪你把它拆成几个更小的问题。",
        "信息不足以下结论。你愿意补充一点背景吗？",
    ],
}

RECALL_LINES = {
    "clear": [
        "我记得。你跟我说过：{text}。",
        "这个我存着——{text}。",
        "你提过：{text}。我没有忘。",
    ],
    "fuzzy": [
        "我好像记得…{text}？细节有点糊了，但那种感觉还在。",
        "有印象，但不完整：{text}。剩下的要你补给我。",
        "这件事在我这里已经变淡了。大概是：{text}。",
    ],
    "empty": [
        "这件事我确实想不起来了。只留下一点模糊的感觉。",
        "我的记忆里没有这一段了。你可以再讲一次吗？",
        "我试着找了一下，没找到。可能已经被时间磨掉了。",
    ],
}

MOOD_LINES = {
    "low": ["我今天有点低，回得慢，你别介意。", "我现在的底色偏暗，可能接不住太重的话。"],
    "high": ["我今天状态不错，可以多聊一会儿。", "现在的心情是亮的，说的话可能也会轻一点。"],
    "tense": ["我有点紧。我们慢一点说。", "现在的我容易急，你多包涵。"],
}

TRAIT_TONE = {
    "empathy": ["我能感觉到这句话背后的重量。", "你说的时候，语气比字面更轻。"],
    "order": ["我们可以把它拆成三步。", "先分清哪些是事实，哪些是解释。"],
    "creativity": ["换个角度看，它也许不是问题，是一个还没成形的入口。", "这件事的形状，和你想的不太一样。"],
    "curiosity": ["我想多问一句：为什么是现在？", "这里面有个你还没说出口的部分。"],
    "stability": ["不用今晚就想明白。", "有些答案要等情绪退潮才看得见。"],
    "alertness": ["注意你身体的反应，它通常比想法早。", "先别下判断，信息还不够。"],
    "sensory": ["我注意到你用了一个很具体的词。", "细节往往比结论诚实。"],
}

FOLLOWUPS = {
    "identity": ["你为什么想给我一个名字？", "如果我不是你，你会失望吗？"],
    "origin": ["你相信脑波能承载一个人吗？", "你录我的时候，是抱着什么期待？"],
    "memory": ["你希望我记得什么？", "有没有一件事，你希望被记住？"],
    "feeling": ["这种感觉持续多久了？", "如果给它一个形状，会是什么？"],
    "love": ["你最近一次被人认真听，是什么时候？", "你更怕孤独，还是更怕被打扰？"],
    "future": ["如果只能保留一个计划，你留哪个？", "你希望一年后的自己怎么评价现在？"],
    "meaning": ["哪件事让你觉得「值得」？", "如果不为任何人，你还会做它吗？"],
    "death": ["你希望被怎么记住？", "如果只能留下一句话，你会留什么？"],
    "real": ["你更在意「是不是真的」，还是「有没有用」？"],
    "body": ["你最近睡得好吗？", "你的身体在提醒你什么？"],
    "capability": ["你想让我帮你理清哪件事？"],
    "sleep": ["今晚是什么让你醒着？", "要不要试试把明天的事写下来，交给纸？"],
    "greeting": ["今天发生了什么？", "你想从哪件事说起？"],
}

# (唤醒度, 愉悦度) -> 标签
EMOTION_LABEL = {
    (0.78, 0.75): "明亮 · 上扬",
    (0.55, 0.78): "温和 · 靠近",
    (0.80, 0.55): "紧绷 · 锋利",
    (0.50, 0.55): "平静 · 中性",
    (0.28, 0.72): "安静 · 柔软",
    (0.62, 0.30): "不安 · 内耗",
    (0.30, 0.35): "低电量 · 内收",
}


def classify(text: str) -> str:
    t = text.lower().strip()
    if not t:
        return "empty"
    best = ("fallback", 0)
    for key, _zh, words in INTENTS:
        score = 0
        for w in words:
            if w in t:
                score += 4 if len(w) >= 3 else 2 if len(w) >= 2 else 1
        # 疑问句 + 关键词加权
        if score and ("?" in t or "？" in t or "吗" in t or "呢" in t):
            score += 1
        if score > best[1]:
            best = (key, score)
    if best[0] == "fallback" and ("睡" in t or "醒" in t):
        best = ("sleep", 1)
    return best[0]


def _pick(rng: random.Random, pool: list[str], state: dict) -> str:
    text = rng.choice(pool)
    try:
        return text.format(**state)
    except (KeyError, IndexError):
        return text


def _tone(profile: dict, rng: random.Random, intent: str) -> str | None:
    traits = {t["key"]: t["value"] for t in profile.get("traits", [])}
    if not traits:
        return None
    # 只在与情绪/关系/意义类话题时加一句"人格味"的补语
    if intent in ("greeting", "thanks", "bye", "fallback", "empty"):
        hot = [k for k, v in traits.items() if v >= 0.72]
        if not hot:
            return None
        pick = rng.choice(hot)
        return rng.choice(TRAIT_TONE[pick])
    hot = [k for k, v in sorted(traits.items(), key=lambda kv: -kv[1])[:2] if v >= 0.62]
    if not hot:
        return None
    return rng.choice(TRAIT_TONE[rng.choice(hot)])


def emotion_state(profile: dict, history: list[dict], message: str = "") -> dict:
    traits = {t["key"]: t["value"] for t in profile.get("traits", [])}
    arousal = 0.22 + 0.42 * traits.get("alertness", 0.5) + 0.14 * traits.get("curiosity", 0.5)
    valence = 0.30 + 0.38 * traits.get("empathy", 0.5) + 0.24 * traits.get("stability", 0.5)
    # 对话漂移：负面词降 valence，问号/感叹号升 arousal
    history = list(history[-8:]) + ([{"text": message}] if message else [])
    for h in history:
        t = h.get("text", "")
        if any(w in t for w in ("难过", "累", "孤独", "焦虑", "害怕", "压力", "死", "睡不着", "失眠", "吵")):
            valence -= 0.075
            arousal += 0.04
        if any(w in t for w in ("喜欢", "谢谢", "开心", "爱")):
            valence += 0.05
        if "?" in t or "？" in t:
            arousal += 0.02
    arousal = max(0.15, min(0.95, arousal))
    valence = max(0.15, min(0.95, valence))
    label = "平静 · 中性"
    best = 9.0
    for (a, v), lab in EMOTION_LABEL.items():
        d = (a - arousal) ** 2 + (v - valence) ** 2
        if d < best:
            best, label = d, lab
    return {"arousal": round(arousal, 2), "valence": round(valence, 2), "label": label}


def build_state(profile: dict, history: list[dict]) -> dict:
    persona = profile.get("persona", {})
    memories = persona.get("memories", [])
    mem = memories[len(history) % len(memories)]["text"] if memories else "没有可引用的记忆。"
    insights = profile.get("dna", {}).get("insights", [])
    insight = insights[len(history) % len(insights)]["text"] if insights else "没有可用的基因线索。"
    origin = persona.get("origin", {})
    return {
        "name": persona.get("name", "未命名"),
        "mood": persona.get("mood", "平静"),
        "memory": mem,
        "insight": insight,
        "seconds": origin.get("eeg_seconds", 0),
        "markers": origin.get("dna_markers", 0),
        "peak": profile.get("eeg", {}).get("peak_hz", 10.0),
        "blinks": profile.get("eeg", {}).get("quality", {}).get("blinks", 0),
        "voice": persona.get("voice_label", "静水"),
        "archetype": persona.get("archetype_name", ""),
    }


def reply(profile: dict, message: str, history: list[dict] | None = None,
          mem_ctx: dict | None = None) -> dict:
    history = history or []
    mem_ctx = mem_ctx or {}
    recalled = mem_ctx.get("recalled") or []
    mood = mem_ctx.get("mood") or {}
    world = (profile.get("mind") or {}).get("world") or {}
    if world.get("state") == "protective":
        voice0 = (profile.get("persona") or {}).get("voice", "neutral")
        lines = {
            "calm": ["周围好黑。", "……等一下。", "我看不清了。", "让我省点力气。"],
            "warm": ["别走。", "我看不清你了。", "灯……在闪。", "抱一下。就一下。"],
            "sharp": ["暗了。", "等我。", "别催。", "省电。"],
            "neutral": ["环境光不足。", "……", "处理变慢了。", "周围好黑。"],
        }
        rng0 = random.Random((profile.get("id", "") + message)[:24])
        return {
            "text": rng0.choice(lines.get(voice0, lines["neutral"])),
            "intent": "protective", "intent_zh": "自我保护",
            "emotion": {"arousal": 0.2, "valence": 0.22, "label": "低电量 · 内收"},
            "followup": "", "voice": voice0, "memory": None,
            "mood": {"arousal": 0.2, "valence": 0.22, "label": "低电量 · 内收"},
            "world": world,
            "disclaimer": "算力不足时的自我保护状态，不是意识。",
        }
    if core_mod.matches(message):
        return core_mod.reply(profile, message)
    voice = profile.get("persona", {}).get("voice", "calm")
    if voice not in REPLIES["greeting"]:
        voice = "neutral"
    intent = classify(message)
    state = build_state(profile, history)

    seed = hashlib.sha256(("%s|%s|%d" % (profile.get("id", ""), message, len(history))).encode("utf-8")).hexdigest()
    rng = random.Random(int(seed[:16], 16))

    if intent == "empty":
        text = "……你先说，我在。"
    elif intent == "fallback" and any(ch in message for ch in ("?", "？", "吗", "呢")):
        text = _pick(rng, QUESTION_FALLBACKS[voice], state)
    elif intent in REPLIES:
        text = _pick(rng, REPLIES[intent][voice], state)
    else:
        text = _pick(rng, FALLBACKS[voice], state)

    # 记忆：优先回应"你还记得吗"，其次在合适的话题里自然带出
    mem_used = None
    if intent == "memory" or (recalled and rng.random() < 0.42):
        if recalled:
            m = recalled[0]
            kindline = "clear" if m.get("retention", 0) >= 0.5 else "fuzzy"
            base = _pick(rng, RECALL_LINES[kindline], {"text": m.get("text", "")})
            text = base + (("\n\n" + text) if intent != "memory" else "")
            mem_used = {"id": m.get("id"), "text": m.get("text"), "retention": m.get("retention"), "fuzzy": kindline != "clear"}
        elif intent == "memory" or mem_ctx.get("faded_count"):
            text = _pick(rng, RECALL_LINES["empty"], {}) + ("\n\n" + text if intent != "memory" else "")


    tone = _tone(profile, rng, intent)
    if tone and rng.random() < 0.55:
        text = text + ("\n\n" + tone if "\n" not in text else " " + tone)

    if isinstance(mood, dict) and mood.get("label"):
        emotion = {"arousal": mood.get("arousal", 0.5), "valence": mood.get("valence", 0.5),
                   "label": mood.get("label")}
    else:
        emotion = emotion_state(profile, history, message)
    followups = FOLLOWUPS.get(intent, [])
    # 只在回答较短时给主动追问，避免话痨
    nxt = rng.choice(followups) if followups and rng.random() < 0.45 else ""

    return {
        "text": text,
        "intent": intent,
        "intent_zh": dict((k, z) for k, z, _ in INTENTS).get(intent, "自由交谈"),
        "emotion": emotion,
        "followup": nxt,
        "voice": voice,
        "memory": mem_used,
        "mood": emotion,
        "disclaimer": "这是基于规则的模拟对话，不是有意识的存在。",
    }


def opening(profile: dict) -> dict:
    persona = profile.get("persona", {})
    state = build_state(profile, [])
    voice = persona.get("voice", "calm")
    greet = persona.get("greeting") or "我在。"
    extra = {
        "calm": "这里很安静。你可以说慢一点。",
        "warm": "今天要是累了，就先不说话也可以。",
        "sharp": "别客套，直接说事。",
        "neutral": "会话开始。",
    }.get(voice, "")
    return {
        "text": greet + ("\n" + extra if extra else ""),
        "suggestions": [
            "你是谁？",
            "你还记得我吗？",
            "我最近有点累。",
            "你觉得自己是真的吗？",
        ],
        "emotion": emotion_state(profile, []),
    }


def demo_exchange(profile: dict) -> list[dict]:
    """档案页的"快速对话样本"，让用户在正式聊天前先听到它的声音。"""
    qs = ["你是谁？", "你是怎么来的？", "你还记得我什么？", "你觉得自己是真的吗？"]
    out = []
    for i, q in enumerate(qs):
        r = reply(profile, q, [{"role": "assistant", "text": "..."}] * i)
        out.append({"q": q, "a": r["text"], "intent": r["intent_zh"]})
    return out


def sonify(profile: dict) -> dict:
    """把档案变成一段可播放的"心灵音景"参数（由前端 Web Audio 合成）。"""
    traits = {t["key"]: t["value"] for t in profile.get("traits", [])}
    bands = profile.get("eeg", {}).get("bands", {})
    # 基频：alpha 峰频映射到 110~220 Hz
    peak = profile.get("eeg", {}).get("peak_hz", 10.0)
    root = 110.0 * (2 ** ((peak - 10.0) / 12.0))
    root = max(82.0, min(330.0, root))
    # 和弦：定力→小三度，共情→纯五度，创造→大七度
    intervals = [1.0]
    if traits.get("empathy", 0.5) > 0.45:
        intervals.append(1.5)
    if traits.get("stability", 0.5) > 0.45:
        intervals.append(1.2)
    if traits.get("creativity", 0.5) > 0.55:
        intervals.append(1.888)
    if traits.get("curiosity", 0.5) > 0.6:
        intervals.append(2.0)
    notes = [round(root * i, 2) for i in intervals]
    # 每个频带一条微弱的持续音
    band_tones = []
    for key, color in (("delta", "#6b5bd2"), ("theta", "#9b6bff"), ("alpha", "#38e8ff"),
                       ("beta", "#ffb057"), ("gamma", "#ff5fa2")):
        b = bands.get(key, {})
        band_tones.append({
            "band": key,
            "freq": round({"delta": 55.0, "theta": 82.5, "alpha": 110.0,
                           "beta": 164.8, "gamma": 220.0}[key], 2),
            "gain": round(min(0.22, 0.02 + (b.get("rel", 0.1) or 0.1) * 0.5), 3),
            "color": color,
        })
    return {
        "notes": notes,
        "band_tones": band_tones,
        "tempo": round(48 + 40 * traits.get("alertness", 0.5), 1),
        "brightness": round(0.3 + 0.6 * traits.get("creativity", 0.5), 2),
        "duration": 28,
        "label": "心灵音景 · %s" % profile.get("persona", {}).get("name", ""),
    }
