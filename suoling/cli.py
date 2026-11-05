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


def cmd_tui(args) -> None:
    from . import tui as tui_mod
    tui_mod.main(args.id or None)


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
