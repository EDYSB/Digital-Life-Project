# -*- coding: utf-8 -*-
"""Second pass: tick the group checkbox and clean the stray underscore line."""
import docx
from docx.shared import Pt

SRC = r"C:\Users\Lenovo\Desktop\附件2-已填写.docx"

d = docx.Document(SRC)

for p in d.paragraphs:
    if "竞赛组别" not in p.text:
        continue
    full = p.text
    new = full.replace("□人工智能组", "☑人工智能组")
    # 去掉那一行多余的下划线
    new = new.replace("\n" + "_" * 10, "").strip()
    new = new.rstrip("_").rstrip()
    if new == full:
        continue
    # 保留第一个 run 的格式，其余清空
    if p.runs:
        p.runs[0].text = new
        for r in p.runs[1:]:
            r.text = ""
    else:
        p.add_run(new)
    for r in p.runs:
        r.font.size = Pt(10.5)
    print("fixed paragraph:", new[:40], "...")

d.save(SRC)

chk = docx.Document(SRC)
line = next(p.text for p in chk.paragraphs if "竞赛组别" in p.text)
print("checked:", "☑人工智能组" in line)
print("stray underscores:", "___" in line)
