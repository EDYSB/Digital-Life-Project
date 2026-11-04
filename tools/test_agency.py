import datetime
import sys

sys.path.insert(0, ".")
from suoling import agency

NOW = datetime.datetime.now().astimezone()


def profile(name="测"):
    return {"id": "mind_agtest0001", "traits": [
        {"key": "curiosity", "value": 0.8}, {"key": "creativity", "value": 0.7},
        {"key": "empathy", "value": 0.6}, {"key": "alertness", "value": 0.5}],
        "persona": {"name": name}, "mind": {"mood": {"valence": 0.6, "arousal": 0.5}}}


def main():
    ok = True
    def check(n, c, d=""):
        nonlocal ok
        print(("  ok   " if c else "  FAIL ") + n + ("" if c else " :: " + str(d)))
        ok = ok and c

    p = profile()
    a = agency.ensure(p)
    check("初始驱动", set(a["drives"]) == {"curiosity", "connection", "expression", "rest"}, a["drives"])
    check("默认自主性", a["autonomy"] == "balanced")

    # 6 小时后：驱动累积、生成念头
    later = NOW + datetime.timedelta(hours=6)
    a = agency.tick(p, later)
    check("联结累积", a["drives"]["connection"] > 0.6, a["drives"])
    check("生成念头", len(a["thoughts"]) >= 1, a["thoughts"])
    check("形成意图或待发", bool(a["intentions"]) or bool(a["pending"]), a)

    # 主动消息
    pend = agency.pending(p, later)
    check("有待发消息", pend is not None, a)
    if pend:
        check("主动文案非空", len(pend["text"]) > 2, pend)
        d = agency.deliver(p, later)
        check("发出后清空", d is not None and agency.pending(p, later) is None)

    # 安静模式
    p2 = profile()
    agency.ensure(p2)
    agency.set_autonomy(p2, "quiet")
    a2 = agency.tick(p2, NOW + datetime.timedelta(hours=12))
    check("安静模式不排队", a2.get("pending") is None, a2.get("pending"))

    # 对话满足驱动
    before = float(p["mind"]["agency"]["drives"]["connection"])
    agency.satisfy(p, "feeling", "我有点累")
    after = float(p["mind"]["agency"]["drives"]["connection"])
    check("对话降低联结驱动", after < before, (before, after))

    # 低情绪抑制主动
    p3 = profile()
    agency.ensure(p3)
    p3["mind"]["mood"]["valence"] = 0.1
    a3 = agency.tick(p3, NOW + datetime.timedelta(hours=8))
    pend3 = a3.get("pending")
    check("低情绪只发低能量消息", pend3 is None or pend3.get("kind") == "low", pend3)

    inner = agency.inner(p)
    check("内心快照", {"drives", "thoughts", "intentions", "autonomy"} <= set(inner))
    print("\nAGENCY", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
