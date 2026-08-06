#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第3学期地点模型：data/locations_sem3.json
- 电路：研楼（A/B/C 楼 × 01-05 教室，3名可选老师随机分配，seed可复现）
- 实验：物电院实验室；晚间课：综合楼；体育：按项目"""
import json, random
from pathlib import Path

random.seed(20230904)   # 固定种子可复现

# 研楼教室：A/B/C 区 × 3层 × 01-05（研楼A101~C305）
YANLOU = [f"研楼{b}{f}{n:02d}" for b in "ABC" for f in range(1, 4) for n in range(1, 6)]
# 电路3老师随机3个不同教室
rooms = random.sample(YANLOU, 3)
O401, O402, O403 = rooms

LOC = {
    "电路": "研楼（按老师）",
    "电路实验": "物电院实验室",
    "普通物理实验A（2）": "物电院实验室",
    "C++面向对象程序设计": "综合楼207(中)",
    "软件技术基础": "综合楼208(中)",
    "军事理论": "综合楼109(中)",
    "体育（3）": "体育馆/田径场（按项目）",
    "形势与政策(3)": "综合楼201/202/203(中·按老师)",
}
TEACHER_ROOMS = {
    "O401": O401, "O402": O402, "O403": O403,   # 电路（研楼随机）
    "E200": "物电院实验室", "E201": "物电院实验室", "E202": "物电院实验室",
    "E300": "物电院实验室", "E301": "物电院实验室", "E302": "物电院实验室",
    "P16a": "综合楼201(中)", "P16b": "综合楼202(中)", "P16c": "综合楼203(中)",
}
out = {"buildings": ["综合楼", "研楼(A/B/C×3层×01-05)", "物电院", "体育馆", "田径场", "前进楼"],
       "courses": LOC, "teacher_rooms": TEACHER_ROOMS}
Path("data/locations_sem3.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("✅ 第3学期地点模型已生成（研楼电路随机分配）")
print(f"  O401(电气) → {O401}")
print(f"  O402(电气) → {O402}")
print(f"  O403(自动化) → {O403}")
print(f"  研楼教室池: {YANLOU}")
