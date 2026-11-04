"""记忆与心情的单元测试。"""

import datetime
import sys

sys.path.insert(0, ".")

from suoling import memory, pipeline

NOW = datetime.datetime.now().astimezone()


def fresh():
    p = {"traits": [{"key": "empathy", "value": 0.7}, {"key": "stability", "value": 0.6},
                    {"key": "alertness", "value": 0.4}],
         "persona": {"name": "测试", "greeting": "我在。"}, "id": "mind_test"}
    memory.ensure(p, {"empathy": 0.7, "stability": 0.6, "alertness": 0.4},
                  birth=["我出生时被读到的是一段 10 秒的脑波。"])
    return p


def main():
    ok = True
    def check(name, cond, detail=""):
        nonlocal ok
        print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else " :: " + str(detail)))
        ok = ok and cond

    p = fresh()
    check("出生记忆", len(p["mind"]["memories"]) == 1)
    check("心情基线", p["mind"]["mood"]["label"])

    out = memory.observe(p, "我的猫叫年糕，它最近总在凌晨叫。", "", "fact", NOW)
    check("学到情景记忆", len(out["learned"]) >= 1, out["learned"])
    check("记忆条数增加", len(p["mind"]["memories"]) >= 2)

    rec = memory.recall(p, "年糕最近怎么样？", NOW)
    check("能召回年糕", any("年糕" in r["text"] for r in rec), rec)
    check("召回留存高", rec and rec[0]["retention"] > 0.9, rec[0] if rec else None)

    m = next(x for x in p["mind"]["memories"] if "年糕" in x["text"])
    check("初始留存接近 1", memory.retention(m, NOW) > 0.95)

    # 30 天后：衰减
    later = NOW + datetime.timedelta(days=30)
    r30 = memory.retention(m, later)
    check("30 天后明显衰减", r30 < 0.2, r30)

    # 复述强化
    future = NOW + datetime.timedelta(days=12)
    before = memory.retention(m, future)
    memory.reinforce(p, [m["id"]], NOW)
    after = memory.retention(m, future)
    check("回忆一次延缓遗忘", after > before, (before, after))

    # 遗忘后 recall 不再返回
    m2 = dict(m)
    m2["last"] = (NOW - datetime.timedelta(days=200)).isoformat(timespec="seconds")
    old = {"mind": {"memories": [m2]}}
    check("极久远记忆召回为空", memory.recall(old, "年糕", NOW) == [])

    # 心情：负面消息降低愉悦度
    v0 = p["mind"]["mood"]["valence"]
    mood = memory.update_mood(p, "我最近很焦虑，睡不着，压力很大。", "sleep", NOW)
    check("负面心情下降", mood["valence"] < v0, (v0, mood["valence"]))
    check("唤醒度上升", mood["arousal"] > 0.3, mood["arousal"])
    check("心情有标签", bool(mood["label"]))

    # 时间流逝回归基线
    p["mind"]["mood"]["updated"] = (NOW - datetime.timedelta(hours=30)).isoformat(timespec="seconds")
    mood2 = memory.update_mood(p, "今天天气不错。", "", NOW)
    base = p["mind"]["mood"]["baseline"]["valence"]
    check("心情向基线回落", abs(mood2["valence"] - base) < abs(mood["valence"] - base) + 0.02,
          (mood2["valence"], base))

    # 存档往返
    path = pipeline.save({"id": "mind_abcdef012345", "persona": {"name": "测试"},
                          "traits": p["traits"], "mind": p["mind"],
                          "created_at": NOW.isoformat(timespec="seconds")})
    loaded = pipeline.load("mind_abcdef012345")
    check("存档保留记忆", len(loaded["mind"]["memories"]) == len(p["mind"]["memories"]))
    check("存档保留心情", loaded["mind"]["mood"]["label"] == p["mind"]["mood"]["label"])
    import os
    os.remove(path)

    # 结构化摘要
    s = memory.summary(p)
    check("摘要字段", {"count", "live", "faded", "mood", "strong"} <= set(s))
    print("\nMEMORY", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
