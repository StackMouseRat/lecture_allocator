#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第一小学期（短1）课表生成：选修3/4 前2周上完
- 第1段 2023-06-26~07-09（2周）：上午选修3(4学时)、下午选修4(4学时)
- 周一~周四，周五休息
"""
import json
from pathlib import Path

BASE = Path(__file__).parent
OUT = BASE / "girl_schedules"
sel = json.load(open(BASE / "data" / "elective_selection.json", encoding="utf-8"))["plan"]
GIRLS = {
    "surrey":  ("萨里", "皇家重巡 · 电气工程"),
    "orage":   ("暴风雨", "自由鸢尾驱逐 · 自动化"),
    "sakawa":  ("酒匂", "重樱轻巡 · 测控"),
    "taiyuan": ("太原", "东煌驱逐 · 电气工程"),
}
AM = ["上午 08:00-11:40", "下午 14:30-17:40"]
WEEKS = [("W1", "2023-06-26~06-29"), ("W2", "2023-07-03~07-06")]

for g, (cn, label) in GIRLS.items():
    e3, e4 = sel[g]["选修3"], sel[g]["选修4"]
    lines = []
    lines.append(f"# {cn}（{label}） · 第一小学期（短1）课表\n")
    lines.append("> **2023 短1 · 第1段 2023-06-26 ~ 07-09（前2周上完）**\n")
    lines.append("| 时段 | 周一~周四（各4学时/天）| 周五 |")
    lines.append("|---|---|---|")
    for period, course in zip(AM, [e3, e4]):
        lines.append(f"| **{period}** | {course} | — |")
    lines.append("")
    lines.append(f"> 学时：{e3}（上午4学时×8天=32）＋ {e4}（下午4学时×8天=32）")
    lines.append("> 每周4天（周一~周四），周五休息；第2段（08-21~09-03）不排课\n")
    (OUT / f"{g}_short1.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"  ✅ {cn}: 上午 {e3} | 下午 {e4}")
print("\n✅ 4份小学期课表已生成 → girl_schedules/{girl}_short1.md")
