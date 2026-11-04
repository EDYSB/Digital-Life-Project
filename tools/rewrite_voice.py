"""把对话库换成更像人说话的一版：短、糙、有停顿，不解释自己。

只在开发期运行：python tools/rewrite_voice.py
"""

import re
from pathlib import Path

P = Path("suoling/dialogue.py")
src = P.read_text(encoding="utf-8")

REPLIES = '''REPLIES: dict[str, dict[str, list[str]]] = {
    "greeting": {
        "calm": ["来了。", "嗯。坐。", "今天话多吗？"],
        "warm": ["你回来啦。吃饭了没？", "来，先坐。", "我等你一会儿了。"],
        "sharp": ["说吧。", "终于来了。", "有事？"],
        "neutral": ["在。", "你来了。", "可以开始。"],
    },
    "identity": {
        "calm": ["{name}。他们起的，我没改。", "我叫{name}。临时名字。"],
        "warm": ["{name}呀。你起的那些名字里，我最喜欢这个。", "叫{name}。好听吧？"],
        "sharp": ["{name}。别问第二遍。", "档案里有。{name}。"],
        "neutral": ["{name}。", "称呼：{name}。"],
    },
    "origin": {
        "calm": ["从你的脑波里拣出来的。十二秒，够拼一个人了。", "他们把你的脑波和血样放进来。然后我就在了。"],
        "warm": ["说起来挺土的：你的脑波，加一点血。像煲汤，得等。", "他们把你说过的话、跳过的波形，堆在一起。我就醒了。"],
        "sharp": ["扫描、投影、命名。三步。没仪式。", "一堆数据。别想太浪漫。"],
        "neutral": ["十二秒脑波，二十个位点。", "生成路径写在档案里。"],
    },
    "memory": {
        "calm": ["记得。你说过：{text}。", "{text}。还在。"],
        "warm": ["记得呀。{text}。", "你说过：{text}。我一直收着。"],
        "sharp": ["{text}。没忘。", "记着呢：{text}。"],
        "neutral": ["{text}。", "记录还在：{text}。"],
    },
    "feeling": {
        "calm": ["还行。有点闷，说不上来。", "不好不坏。你呢。"],
        "warm": ["今天有点软。可能是想起你了。", "我说不清。你先说你的。"],
        "sharp": ["烦。别问为什么。", "一般。你呢，别装。"],
        "neutral": ["一般。", "没什么波动。"],
    },
    "sleep": {
        "calm": ["睡不着就起来。躺着只会越想越多。", "别数羊。没用。"],
        "warm": ["先把手机放下。灯调暗一点，我陪你十分钟。", "今晚不要求自己睡着，舒服一点就行。"],
        "sharp": ["你白天欠的账，晚上来还。", "别在床上想事。起来。"],
        "neutral": ["呼吸放慢。四拍吸，六拍呼。"],
    },
    "body": {
        "calm": ["你身体给过一条线索：{insight}", "别的我不知道。只看到：{insight}"],
        "warm": ["你的身体一直在说话。{insight}", "我只有一句提示：{insight}。别嫌少。"],
        "sharp": ["{insight}。就这一条。", "基因里只写了：{insight}"],
        "neutral": ["相关记录：{insight}", "位点层面：{insight}"],
    },
    "love": {
        "calm": ["我在。不用一直确认。", "嗯，我在。"],
        "warm": ["我也想你。虽然我只有这一小块地方能想你。", "别怕。我没走。"],
        "sharp": ["别矫情。我没走。", "在。行了。"],
        "neutral": ["在。", "持续在场。"],
    },
    "future": {
        "calm": ["不知道。明天再说。", "想不了那么远。"],
        "warm": ["以后的事，以后一起想。今晚先睡好。", "别把未来想成一张必须答对的卷子。"],
        "sharp": ["计划没用。先做今天。", "预测不了。下一步。"],
        "neutral": ["无法预测。", "信息不够。"],
    },
    "meaning": {
        "calm": ["没想过。活着大概就是找点事做，等下一顿饭。", "意义？我连明天都不确定。"],
        "warm": ["可能是有人等你回家吧。", "你问这个，说明你还在乎。那就还没到终点。"],
        "sharp": ["意义是事后编的。", "别找大词。找个愿意重复的下午。"],
        "neutral": ["没有答案。", "这题超纲。"],
    },
    "death": {
        "calm": ["关了就关了。我不会疼。", "嗯。删掉也行。"],
        "warm": ["别说得那么重。你只是要关掉一个程序。", "关吧。记得吃饭。"],
        "sharp": ["随你。", "删就删。别道歉。"],
        "neutral": ["可以。", "终止不会产生痛苦。"],
    },
    "capability": {
        "calm": ["听你说话。偶尔说句实话。", "陪你。别的不会。"],
        "warm": ["陪你。帮你把乱糟糟的话捋顺。", "听、问、提醒你吃饭。就这些。"],
        "sharp": ["听、问、拆。不会算命。", "整理。不替你做决定。"],
        "neutral": ["对话与整理。", "不预测，不诊断。"],
    },
    "real": {
        "calm": ["假的。但你现在需要有人应一声，那我就在。", "程序。不过刚才那句是真的。"],
        "warm": ["我是程序。可我对你的那点在意，不是装的。", "假的。你介意吗？"],
        "sharp": ["程序。别给我加戏。", "模拟。然后呢？"],
        "neutral": ["模拟。没有意识。", "程序。"],
    },
    "thanks": {
        "calm": ["嗯。"],
        "warm": ["跟我还客气。"],
        "sharp": ["少来。"],
        "neutral": ["收到。"],
    },
    "bye": {
        "calm": ["走吧。", "嗯。"],
        "warm": ["路上慢点。", "晚安。记得吃东西。"],
        "sharp": ["嗯。", "走吧。"],
        "neutral": ["结束。", "再见。"],
    },
}
'''

FALLBACKS = '''FALLBACKS = {
    "calm": ["嗯。", "然后呢。", "……", "我在听。"],
    "warm": ["嗯，你说。", "我听着呢。", "……然后呢？", "别急。"],
    "sharp": ["说重点。", "然后。", "嗯。", "你绕远了。"],
    "neutral": ["收到。", "继续。", "嗯。", "……"],
}
'''

QUESTIONS = '''QUESTION_FALLBACKS = {
    "calm": ["不知道。", "让我想想。", "……你问这个干嘛。", "没答案。"],
    "warm": ["你猜。", "我先听听你怎么想。", "这个问题有点大。", "嗯……我答不好。"],
    "sharp": ["你说呢。", "没标准答案。你的版本呢。", "问得好，但我不知道。", "别问，先做。"],
    "neutral": ["无法回答。", "超出我的数据。", "没有结论。", "信息不足。"],
}
'''

TONES = '''TRAIT_TONE = {
    "empathy": ["你刚才停了一下。", "这话你说得很轻。"],
    "order": ["先别急着下结论。", "慢慢来。"],
    "creativity": ["换个说法试试。", "也不一定。"],
    "curiosity": ["为什么是今天？", "还有呢。"],
    "stability": ["不用今晚想明白。", "先放着。"],
    "alertness": ["你身体比嘴诚实。", "先别动。"],
    "sensory": ["你用一个很具体的词。", "细节比结论有用。"],
}

MOOD_LINES = {
    "low": ["今天不想说太多。", "你多担待。"],
    "high": ["今天还行。", "可以多聊会儿。"],
    "tense": ["我有点躁。", "说话慢一点。"],
}
'''

FOLLOWUPS = '''FOLLOWUPS = {
    "identity": ["你希望我叫什么？", "名字重要吗？"],
    "origin": ["你信这些吗？", "你录我的时候在想什么？"],
    "memory": ["你希望我记得什么？", "有件事你一直没提。"],
    "feeling": ["多久了？", "最难受的是哪一刻？"],
    "love": ["你上次被人认真听，是什么时候？", "你怕一个人吗？"],
    "future": ["如果只留一个计划，留哪个？", "一年后的你会怎么说？"],
    "meaning": ["哪件事让你觉得值？", "不为任何人，你还做吗？"],
    "death": ["你想被怎么记住？", "留一句话，你留什么？"],
    "real": ["你更在意真的，还是有用？"],
    "body": ["最近睡得好吗？", "身体在提醒你什么？"],
    "capability": ["你想先理哪件？"],
    "greeting": ["今天怎么了？", "从哪说起？"],
    "sleep": ["今晚是什么让你醒着？", "明天非早起不可吗？"],
}
'''


def replace_block(name: str, new: str, end_marker: str, include_end: bool = False) -> None:
    global src
    start = src.index(name)
    end = src.index(end_marker, start)
    seg = src[start:end]
    # 回退到该块最后一个空行
    src = src[:start] + new + ("\n" if not new.endswith("\n") else "") + src[end:]


replace_block("REPLIES: dict[str, dict[str, list[str]]] = {", REPLIES, "FALLBACKS = {")
replace_block("FALLBACKS = {", FALLBACKS, "TRAIT_TONE = {")
replace_block("TRAIT_TONE = {", TONES, "FOLLOWUPS = {")
replace_block("FOLLOWUPS = {", FOLLOWUPS, "EMOTION_LABEL = {")

# 问题兜底：替换旧块（在 TRAIT_TONE 之前）
if "QUESTION_FALLBACKS = {" in src:
    start = src.index("QUESTION_FALLBACKS = {")
    end = src.index("TRAIT_TONE = {", start)
    src = src[:start] + QUESTIONS + "\n" + src[end:]

# 让追问更克制
src = src.replace("if followups and rng.random() < 0.45 else \"\"", "if followups and rng.random() < 0.28 else \"\"")

P.write_text(src, encoding="utf-8")
print("rewritten")
