# -*- coding: utf-8 -*-
"""Fill in the competition registration form (附件2.docx).

Keeps the original layout; only replaces placeholder underscores and writes
the project description into the two narrative sections.
"""
import copy
import os

import docx
from docx.shared import Pt

SRC = r"C:\Users\Lenovo\Desktop\附件2.docx"
DST = r"C:\Users\Lenovo\Desktop\附件2-已填写.docx"

PROJECT = "数字生命初级：脑波与基因驱动的可交互数字档案系统"
FIELD = "人工智能应用 / 人机交互与数字内容生成"
INTRO = (
    "面向“数字生命”这一新型交互形态，团队开发了一套本地运行的原型系统："
    "读取脑电与基因样本，完成频谱、复杂度与位点检测，投影为七维人格向量，"
    "生成可对话、可保存、可复现的数字档案；配合记忆衰减、心情漂移与五区激活模型，"
    "使档案在长期交互中呈现连续性与可解释性。全部计算在本机完成，零第三方依赖。"
)
DEMO = (
    "自备 Windows 笔记本 1 台（无需独立显卡），预装 Python 3.10+；"
    "现场演示浏览器界面与命令行双入口，投屏用 HDMI 线自备；"
    "需 1 个 220V 电源插座与可用 Wi-Fi（仅用于投屏，不影响本地计算）。"
    "演示数据均为内置合成样本，不含真实个人生物信息，无安全风险。"
)

d = docx.Document(SRC)


def set_para(idx, text):
    p = d.paragraphs[idx]
    for r in p.runs[1:]:
        r.text = ""
    if p.runs:
        p.runs[0].text = text
    else:
        p.add_run(text)


# 1) 勾选组别：把 □人工智能组 换成 ☑人工智能组
for p in d.paragraphs:
    if "人工智能组" in p.text:
        for r in p.runs:
            if "□人工智能组" in r.text:
                r.text = r.text.replace("□人工智能组", "☑人工智能组")
        break

# 2) 项目名称 / 领域 / 两段说明
for i, p in enumerate(d.paragraphs):
    t = p.text
    if t.startswith("参赛项目名称"):
        set_para(i, "参赛项目名称：" + PROJECT)
    elif t.startswith("项目领域"):
        set_para(i, "项目领域（对应组别岗位方向）：" + FIELD)

# 3) 简介与演示条件：找到带下划线的占位段，替换为正文
narratives = [INTRO, DEMO]
k = 0
for i, p in enumerate(d.paragraphs):
    if p.text.strip().startswith("____") and k < len(narratives):
        set_para(i, narratives[k])
        k += 1

# 4) 正文段落样式：中文小四、行距 1.5
for p in d.paragraphs:
    if p.text.strip() in (INTRO, DEMO) or p.text.startswith(("参赛项目名称", "项目领域")):
        for r in p.runs:
            r.font.size = Pt(12)

# 5) 队员表：填写角色行提示（姓名等由学生自填，不代填个人信息）
t = d.tables[0]
for ri in range(1, len(t.rows)):
    cell = t.rows[ri].cells[0]
    if not cell.text.strip():
        cell.text = str(ri)

d.save(DST)

# 校验
chk = docx.Document(DST)
print("saved:", DST, os.path.getsize(DST), "bytes")
print("组别勾选:", any("☑人工智能组" in p.text for p in chk.paragraphs))
print("项目名称:", any(p.text.startswith("参赛项目名称：数字生命") for p in chk.paragraphs))
print("简介字数:", len(INTRO), "演示条件字数:", len(DEMO))
