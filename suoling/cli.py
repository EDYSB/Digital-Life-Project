"""数字生命初级 · 命令行。

  python -m suoling.cli serve [--port 8017]
  python -m suoling.cli scan --eeg samples/eeg_meditation.csv --dna samples/dna_sensitive.fasta --name 我
  python -m suoling.cli chat --id mind_xxxx
  python -m suoling.cli list
  python -m suoling.cli export --id mind_xxxx
  python -m suoling.cli demo
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import webbrowser

from . import card as card_mod, dialogue, eeg as eeg_mod, genome as genome_mod, pipeline
from .eeg import EEGError
from .genome import DNAError


USAGE = """数字生命初级 · 命令行

  dl                          显示这份帮助
  dl serve [--port 8017]      启动本地界面（默认 8017）
  dl list                     列出已保存的数字生命
  dl scan --eeg 文件 --dna 文件 [--name 名字]
                              从脑电与基因文件生成一份档案
  dl chat --id 编号           与已保存的档案对话
  dl tui [--id 编号]          在终端里开一个独立界面（不依赖浏览器）
  dl final [--id 编号]        说出最后一句；Y 确认后写手记并自毁档案
  dl stats [--id 编号]        后台：查看全部参数（前台不显示）
  dl card --id 编号 [--out 文件] [--no-open]
                              生成可打印的数字生命卡
  dl export --id 编号 [--format md|json]
                              导出档案
  dl demo                     用内置样本跑一遍完整流程

示例：
  dl scan --eeg samples/eeg_meditation.csv --dna samples/dna_sensitive.fasta --name 我
  dl list"""


def cmd_help(args) -> None:
    print(USAGE)


def _check(path: str, what: str) -> str:
    if not os.path.isfile(path):
        raise SystemExit("找不到%s文件：%s" % (what, path))
    return path


def cmd_scan(args) -> None:
    with open(_check(args.eeg, "脑电"), "rb") as f:
        eeg = eeg_mod.parse_bytes(f.read(), os.path.basename(args.eeg))
    with open(_check(args.dna, "基因"), "rb") as f:
        dna = genome_mod.parse_bytes(f.read(), os.path.basename(args.dna))

    def show(stage, pct, message, track):
        print("  [%3d%%] %-7s %s" % (pct, track, message), flush=True)

    profile = pipeline.build(eeg, dna, subject=args.name, voice=args.voice, progress=show)
    if not args.no_save:
        path = pipeline.save(profile)
        print("\n已保存：%s" % path)
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=1)
        print("已输出 JSON：%s" % args.json)
    if args.markdown:
        os.makedirs(os.path.dirname(os.path.abspath(args.markdown)), exist_ok=True)
        with open(args.markdown, "w", encoding="utf-8") as f:
            f.write(pipeline.export_markdown(profile))
        print("已输出 Markdown：%s" % args.markdown)

    per = profile["persona"]
    print("\n" + "=" * 64)
    print("%s · %s" % (per["name"], per["title"]))
    print("编号：%s" % profile["id"])
    print("-" * 64)
    print(per["summary"])
    print("-" * 64)
    for t in profile["traits"]:
        bar = "█" * int(round(t["value"] * 20))
        print("  %-4s %5.0f  %s" % (t["name"], t["value"] * 100, bar))
    print("-" * 64)
    print("脑波：%.1fs · 主频 %s Hz · %s · 质量 %.0f%%" % (
        profile["eeg"]["seconds"], profile["eeg"]["peak_hz"], profile["eeg"]["mood"],
        profile["eeg"]["quality"]["score"] * 100))
    print("基因：%d/%d 位点 · 置信度 %.0f%%" % (
        profile["dna"]["coverage"]["markers_hit"], profile["dna"]["coverage"]["markers_total"],
        profile["dna"]["confidence"] * 100))
    if profile["dna"]["insights"]:
        print("身体线索：")
        for x in profile["dna"]["insights"][:4]:
            print("  - [%s %s] %s" % (x["gene"], x["genotype"], x["text"]))
    print("=" * 64)
    print("边界：%s" % per["limits"])
    print("提示：python -m suoling.cli chat --id %s" % profile["id"])


def cmd_chat(args) -> None:
    profile = pipeline.load(args.id)
    per = profile["persona"]
    print("\n%s · %s" % (per["name"], per["title"]))
    print("（输入 /quit 退出；/save 导出对话）")
    print(per["greeting"])
    print("-" * 60)
    history: list[dict] = []
    lines: list[str] = ["# 与 %s 的对话" % per["name"], ""]
    while True:
        try:
            text = input("你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text in ("/quit", "/exit", "exit"):
            break
        if text == "/save":
            with open("conversation.md", "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            print("已保存到 conversation.md")
            continue
        r = dialogue.reply(profile, text, history)
        print("%s > %s" % (per["name"], r["text"]))
        if r.get("followup"):
            print("      （它想问：%s）" % r["followup"])
        history.append({"role": "user", "text": text})
        history.append({"role": "assistant", "text": r["text"]})
        lines.append("**你**：%s\n" % text)
        lines.append("**%s**：%s\n" % (per["name"], r["text"]))


def cmd_mode(args) -> None:
    """gpu / pet / auto。没有 GPU 就用桌宠。"""
    from . import config

    if not args.name:
        cfg = config.load()
        print("")
        print("  当前模式：%s" % (cfg.get("mode") or "auto"))
        print("  gpu  —— 接 VoxEMW / LiveTalking 这类后端，真人级口型")
        print("  pet  —— 没有 GPU 时的小窗桌宠，会呼吸、眨眼、说话")
        print("  auto —— 有 voice_backend 就 gpu，否则 pet")
        print("")
        print("  切换：dl mode gpu | dl mode pet | dl mode auto")
        print("")
        return
    name = args.name.lower()
    if name not in ("gpu", "web", "auto"):
        print("  只有 gpu / pet / auto 三种。")
        return
    config.save({"mode": name})
    print("  已切到 %s 模式。" % name)


def cmd_api(args) -> None:
    """看或设置 API key：dl api sk-xxx / dl api --clear / dl api"""
    from . import config

    if args.clear:
        config.save({"deepseek_api_key": ""})
        print("  已清空 key。对话回到本地规则。")
        return
    key = (args.key or "").strip()
    if key:
        config.save({"deepseek_api_key": key})
        print("  已写入 config.json：%s" % config.mask(key))
        print("  模型 %s · 端点 %s" % (config.load().get("deepseek_model"), config.load().get("deepseek_base")))
        return
    cfg = config.load()
    print("")
    print("  DeepSeek")
    print("  " + "─" * 40)
    print("  key       %s" % config.mask(cfg.get("deepseek_api_key", "")))
    print("  model     %s" % cfg.get("deepseek_model"))
    print("  base      %s" % cfg.get("deepseek_base"))
    print("  voice     %s" % (cfg.get("voice_backend") or "（未接后端）"))
    print("")
    print("  设置：dl api sk-xxxxx     清空：dl api --clear")
    print("")


def cmd_account(args) -> None:
    """建账户（可选）。不建也能用，只是档案在公共目录。"""
    from . import lock
    import getpass

    if args.off:
        lock.clear()
        lock.set_current("")
        print("  已取消账户。回到公共目录。")
        return
    if lock.users():
        print("  已有账户：%s" % "、".join(lock.users()))
    name = (args.user or "").strip() or input("  账户名：").strip()
    if not name:
        print("  没有名字，算了。")
        return
    pw = getpass.getpass("  口令：")
    if not pw:
        print("  没有口令，算了。")
        return
    if pw != getpass.getpass("  再来一次："):
        print("  两次不一样。")
        return
    lock.add_user(name, pw)
    lock.set_current(name)
    print("  账户已建：%s。之后你的档案在 minds/%s/。" % (name, name))


def cmd_login(args) -> None:
    from . import lock
    if not lock.has_accounts():
        print("  还没有账户。要建一个吗？运行 dl account")
        return
    if args.user:
        import getpass
        if lock.verify(args.user, getpass.getpass("  口令：")):
            lock.set_current(args.user)
            print("  你好，%s。" % args.user)
        else:
            print("  不对。")
        return
    if lock.login():
        pass


def cmd_logout(args) -> None:
    from . import lock
    lock.set_current("")
    print("  已退出。档案回到公共目录。")


def cmd_whoami(args) -> None:
    from . import lock
    if not lock.has_accounts():
        print("  没有账户体系：公共目录，谁都能看。")
        return
    who = lock.current_user()
    print("  当前账户：%s" % (who or "（未登录，公共目录）"))
    print("  档案目录：%s" % pipeline.mind_dir())


def cmd_tui(args) -> None:
    from . import tui as tui_mod
    tui_mod.main(args.id or None)


def cmd_brain(args) -> None:
    """看它现在脑子里最亮的是哪一块。"""
    from . import brain as brain_mod

    items = pipeline.list_minds()
    if not items:
        print("还没有档案。先运行：dl demo")
        return
    profile = pipeline.load(args.id) if args.id else pipeline.load(items[0]["id"])
    if args.poke:
        thought = brain_mod.pulse(profile, args.poke)
        pipeline.save(profile)
        print("  它想：%s" % thought)
        print("")
    snap = brain_mod.snapshot(profile)
    print("  大脑 · %d 拍" % snap["ticks"])
    print("  " + "─" * 40)
    for name, v in snap["regions"]:
        bar = "█" * int(round(v * 24))
        print("  %-4s %4.2f  %s" % (name, v, bar))
    print("")
    print("  最亮：%s" % snap["top"])
    print("")


def cmd_brain_ui(args) -> None:
    """打开大脑的独立可视化页面（不自动启动，只在这个命令里开）。"""
    import socket
    import time
    import webbrowser

    port = 8017
    alive = False
    for _ in range(2):
        sk = socket.socket()
        sk.settimeout(0.3)
        alive = sk.connect_ex(("127.0.0.1", port)) == 0
        sk.close()
        if alive:
            break

    if not alive:
        import subprocess
        import sys as _sys

        subprocess.Popen(
            [_sys.executable, "app.py", "serve", "--port", str(port), "--no-browser"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        for _ in range(20):
            time.sleep(0.3)
            sk = socket.socket()
            sk.settimeout(0.3)
            alive = sk.connect_ex(("127.0.0.1", port)) == 0
            sk.close()
            if alive:
                break

    url = "http://127.0.0.1:%d/brain.html" % port
    print("  大脑：%s" % url)
    try:
        webbrowser.open(url)
    except Exception:
        pass


def cmd_stats(args) -> None:
    """后台：参数只在这里看。"""
    items = pipeline.list_minds()
    if not items:
        print("还没有档案。先运行：dl demo")
        return
    profile = pipeline.load(args.id) if args.id else pipeline.load(items[0]["id"])
    per = profile.get("persona") or {}
    eeg = profile.get("eeg") or {}
    dna = profile.get("dna") or {}
    mind = profile.get("mind") or {}
    stats = mind.get("stats") or {}
    cov = dna.get("coverage") or {}
    q = eeg.get("quality") or {}
    print("")
    print("  后台 · %s" % (per.get("code") or profile.get("id")))
    print("  " + "─" * 46)
    print("  编号      %s" % profile.get("id"))
    print("  名称      %s" % (per.get("name") or "—"))
    print("  脑波      %d 导联 · %.1f 秒 · 主频 %s Hz · 采样 %s Hz"
          % (eeg.get("n_channels", 0), float(eeg.get("seconds", 0)),
             eeg.get("peak_hz", "—"), eeg.get("fs", "—")))
    print("  质量      %.0f%% · 眨眼 %s 次 · 削顶 %.2f%% · 工频 %.4f"
          % (float(q.get("score", 0)) * 100, q.get("blinks", 0),
             float(q.get("clipped_ratio", 0)) * 100, float(q.get("line_noise", 0))))
    print("  基因      %d / %d 位点 · 置信度 %.0f%%"
          % (cov.get("markers_hit", 0), cov.get("markers_total", 0),
             float(dna.get("confidence", 0)) * 100))
    print("  来源      %s / %s" % ((profile.get("origin") or {}).get("eeg_source", "—"),
                                    (profile.get("origin") or {}).get("dna_source", "—")))
    print("  会话/消息 %s / %s" % (stats.get("sessions", 0), stats.get("messages", 0)))
    print("  记忆      %d 条" % len(mind.get("memories") or []))
    print("  心情      %s" % (eeg.get("mood") or "—"))
    print("  七维      " + "  ".join(
        "%s %d" % (t.get("name", ""), round(float(t.get("value", 0)) * 100))
        for t in (profile.get("traits") or [])))
    print("")


def cmd_final(args) -> None:
    from . import final as final_mod
    items = pipeline.list_minds()
    if args.id:
        profile = pipeline.load(args.id)
    elif items:
        profile = pipeline.load(items[0]["id"])
    else:
        print("还没有档案。先运行：dl demo")
        return
    final_mod.run(profile, assume_yes=args.yes)


def cmd_list(args) -> None:
    items = pipeline.list_minds()
    if not items:
        print("还没有档案。先运行 scan 或 serve。")
        return
    for it in items:
        print("%-22s %-9s %s  %s  %s" % (
            it["id"], it.get("code") or "—", it.get("created_at", "")[:16],
            it.get("name") or "—", it.get("title") or ""))


def cmd_export(args) -> None:
    p = pipeline.load(args.id)
    if args.format == "md":
        print(pipeline.export_markdown(p))
    else:
        print(json.dumps(p, ensure_ascii=False, indent=1))


def cmd_card(args) -> None:
    profile = pipeline.load(args.id)
    per = profile.get("persona") or {}
    code = per.get("code") or ("DL-" + profile["id"][-6:].upper())
    out = os.path.abspath(args.out or os.path.join("out", code + "-card.html"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(card_mod.build(profile))
    print("已生成数字生命卡：%s" % out)
    if not args.no_open:
        try:
            webbrowser.open(pathlib.Path(out).as_uri())
        except Exception:
            pass


def cmd_demo(args) -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    eeg_p = os.path.join(root, "samples", "eeg_meditation.csv")
    dna_p = os.path.join(root, "samples", "dna_sensitive.fasta")
    if not (os.path.isfile(eeg_p) and os.path.isfile(dna_p)):
        raise SystemExit("示例数据不存在，请先运行：python tools/make_samples.py")
    args.eeg, args.dna = eeg_p, dna_p
    args.name = args.name or "演示体"
    cmd_scan(args)


def cmd_serve(args) -> None:
    from .server import serve
    serve(port=args.port, open_browser=not args.no_browser)


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    if not argv:
        print(USAGE)
        return

    ap = argparse.ArgumentParser(prog="suoling", description="数字生命初级 · 数字生命录入")
    sub = ap.add_subparsers(dest="cmd", required=True)

    h = sub.add_parser("help", help="显示帮助")
    h.set_defaults(func=cmd_help)

    s = sub.add_parser("serve", help="启动本地 Web 界面")
    s.add_argument("--port", type=int, default=int(os.environ.get("ECHOMIND_PORT", "8017")))
    s.add_argument("--no-browser", action="store_true")
    s.set_defaults(func=cmd_serve)

    sc = sub.add_parser("scan", help="从两个文件生成档案")
    sc.add_argument("--eeg", required=True)
    sc.add_argument("--dna", required=True)
    sc.add_argument("--name", default="")
    sc.add_argument("--voice", default="calm", choices=["calm", "warm", "sharp", "neutral"])
    sc.add_argument("--no-save", action="store_true")
    sc.add_argument("--json", default="")
    sc.add_argument("--markdown", default="")
    sc.set_defaults(func=cmd_scan)

    c = sub.add_parser("chat", help="与已保存的副本对话")
    c.add_argument("--id", required=True)
    c.set_defaults(func=cmd_chat)

    t = sub.add_parser("tui", help="在终端里打开独立界面")
    t.add_argument("--id", default="")
    t.set_defaults(func=cmd_tui)

    ca = sub.add_parser("card", help="生成可打印的数字生命卡")
    ca.add_argument("--id", required=True)
    ca.add_argument("--out", default="")
    ca.add_argument("--no-open", action="store_true")
    ca.set_defaults(func=cmd_card)

    fi = sub.add_parser("final", help="说出最后一句；确认后写手记并自毁档案")
    fi.add_argument("--id", default="")
    fi.add_argument("--yes", action="store_true", help="跳过 Y/N 确认（会直接自毁）")
    fi.set_defaults(func=cmd_final)

    bu = sub.add_parser("brain-ui", help="打开大脑的独立可视化页面")
    bu.set_defaults(func=cmd_brain_ui)

    br = sub.add_parser("brain", help="看它现在脑子里最亮的是哪块")
    br.add_argument("--id", default="")
    br.add_argument("--poke", default="", help="给一句话，让它想一拍")
    br.set_defaults(func=cmd_brain)

    st = sub.add_parser("stats", help="后台：查看全部参数（前台不显示）")
    st.add_argument("--id", default="")
    st.set_defaults(func=cmd_stats)

    md = sub.add_parser("mode", help="gpu / pet / auto")
    md.add_argument("name", nargs="?", default="")
    md.set_defaults(func=cmd_mode)

    ap_ = sub.add_parser("api", help="看或设置 DeepSeek API key")
    ap_.add_argument("key", nargs="?", default="")
    ap_.add_argument("--clear", action="store_true", help="清空 key")
    ap_.set_defaults(func=cmd_api)

    ac = sub.add_parser("account", help="建账户（可选）：档案分到 minds/<账户>/")
    ac.add_argument("--user", default="")
    ac.add_argument("--off", action="store_true", help="取消账户，回到公共目录")
    ac.set_defaults(func=cmd_account)

    lg = sub.add_parser("login", help="登录到自己的目录")
    lg.add_argument("--user", default="")
    lg.set_defaults(func=cmd_login)

    lo = sub.add_parser("logout", help="退出，回到公共目录")
    lo.set_defaults(func=cmd_logout)

    wh = sub.add_parser("whoami", help="看当前账户与档案目录")
    wh.set_defaults(func=cmd_whoami)

    li = sub.add_parser("list", help="列出已保存档案")
    li.set_defaults(func=cmd_list)

    e = sub.add_parser("export", help="导出档案")
    e.add_argument("--id", required=True)
    e.add_argument("--format", default="md", choices=["md", "json"])
    e.set_defaults(func=cmd_export)

    d = sub.add_parser("demo", help="用内置样本跑一次完整流程")
    d.add_argument("--name", default="")
    d.add_argument("--voice", default="calm", choices=["calm", "warm", "sharp", "neutral"])
    d.add_argument("--no-save", action="store_true")
    d.add_argument("--json", default="")
    d.add_argument("--markdown", default="")
    d.set_defaults(func=cmd_demo)

    args = ap.parse_args(argv)
    try:
        args.func(args)
    except (EEGError, DNAError, pipeline.PipelineError) as exc:
        raise SystemExit("错误：%s" % exc) from exc


if __name__ == "__main__":
    main()
