#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成老师分配 data/teachers.json：
- public 公共课：1名老师 Pxx，4人相同（时间必同）
- core 专业核心课：每门3名老师（T*0电气/T*1自动化/T*2测控），同班同老师、跨班不同
- optional 可选课（电磁场/电路）：每门3名老师 Oxxx，4人分配（同老师时间必同）
- lab 实验课：每门3个实验组 E*0/E*1/E*2，同班同组、跨班异组（时间必异）
老师先用ID命名。"""
import json
from pathlib import Path

PUBLIC = [
    "高等数学A（1）","高等数学A（2）","大学英语A（1）","大学英语A（2）",
    "思想道德与法治","马克思主义基本原理","毛泽东思想和中国特色社会主义理论体系概论",
    "习近平新时代中国特色社会主义思想概论","中国近现代史纲要",
    "体育（1）","体育（2）","体育（3）","体育（4）",
    "形势与政策(1)","形势与政策(2)","形势与政策(3)","形势与政策(4)","形势与政策(5)","形势与政策(6)",
    "军事理论","大学生心理健康教育","工程制图","导师课程",
    "土木工程防灾概论","社会学导论","新中国史",
    "计算与人工智能概论","普通物理A（1）","普通物理A（2）","线性代数A","概率论与数理统计A",
    "复变函数与积分变换","离散数学","C++面向对象程序设计","软件技术基础","Python语言程序设计",
    "普通物理A（2）·讨论",
]
OPTIONAL = ["电磁场与波", "电路"]     # 可选课：3名老师
LABS = [
    "普通物理实验A（1）","电路实验","普通物理实验A（2）","模拟电子技术实验","数字电子技术实验",
    "自动控制原理实验","电力电子技术基础实践","微机原理及其应用实践","信号与系统实验",
    "电机学（上）实验","电机学（下）实验",
]
CORE = [  # 其余专业核心
    "自动控制原理","电机学（上）","电力电子技术基础","微机原理及其应用","电力系统基础（上）",
    "信号与系统","高电压技术基础","传感与检测技术","电气工程新技术导论","电机学（下）",
    "电力系统基础（下）","电机控制技术","电力系统过电压","高电压绝缘","新能源发电技术",
    "数字电子技术基础","模拟电子技术基础","机电技术创新实训","信号与系统·讨论","传感与检测技术·讨论",
]
GIRLS = ["surrey", "taiyuan", "orage", "sakawa"]
BAND_OFF = {"surrey": 0, "taiyuan": 0, "orage": 2, "sakawa": 3}   # 班级偏移（电气0/自动化2/测控3）

def build():
    out = {}
    # 公共课
    for i, c in enumerate(PUBLIC, 1):
        out[c] = {"type": "public", "assign": {g: {"teacher": f"P{i:02d}", "offset": 0} for g in GIRLS}}
    # 专业核心
    for i, c in enumerate(CORE, 1):
        out[c] = {"type": "core", "assign": {
            g: {"teacher": f"T{i*10}{b}", "offset": BAND_OFF[g]} for g, b in
            zip(GIRLS, [0, 0, 1, 2])}}
    # 可选课：3名老师，4人分配（同老师时间必同）
    opt_plan = {
        "电磁场与波":  {"teachers": ["O301", "O302", "O303"],
                        "pick": {"surrey": "O301", "taiyuan": "O302", "orage": "O303", "sakawa": "O302"},
                        "off": {"O301": 1, "O302": 3, "O303": 2}},
        "电路":        {"teachers": ["O401", "O402", "O403"],
                        "pick": {"surrey": "O401", "taiyuan": "O402", "orage": "O403", "sakawa": "O401"},
                        "off": {"O401": 2, "O402": 4, "O403": 1}},
    }
    for c, p in opt_plan.items():
        out[c] = {"type": "optional", "assign": {
            g: {"teacher": p["pick"][g], "offset": p["off"][p["pick"][g]]} for g in GIRLS}}
    # 实验课：实验组 E*0电气 / E*1自动化 / E*2测控（同班同组、跨班异组）
    for i, c in enumerate(LABS, 1):
        out[c] = {"type": "lab", "assign": {
            g: {"teacher": f"E{i*10}{b}", "offset": BAND_OFF[g]} for g, b in
            zip(GIRLS, [0, 0, 1, 2])}}
    Path("data/teachers.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out

if __name__ == "__main__":
    d = build()
    n = len(d)
    types = {}
    for v in d.values(): types[v["type"]] = types.get(v["type"], 0) + 1
    print(f"✅ 老师分配已生成：{n}门课（{types}）")
    print("   示例：电路 →", d["电路"]["assign"])
    print("   示例：自动控制原理实验 →", d["自动控制原理实验"]["assign"])
