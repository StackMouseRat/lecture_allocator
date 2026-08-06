#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""授课方案质量检查：重复内容 / 禁词（复习答疑习题研讨等凑数）/ 素材不足循环
用法：python3 check_syllabus.py [sem...] 默认 1 2"""
import json, sys
from pathlib import Path
BASE = Path(__file__).parent / "data"

BAN = ["复习", "答疑", "机动", "考前", "习题课", "研讨", "总结", "考核", "考试", "测验", "阶段", "考前冲刺", ]
# 注意：体育的"技能测试/体质测试"是考核不算凑数；"总结与考核"算

def check(sem):
    f = BASE / f"syllabus_sem{sem}.json"
    if not f.exists():
        print(f"第{sem}学期: 无 syllabus 文件"); return 0
    d = json.load(open(f, encoding="utf-8"))
    print(f"\n{'='*60}\n第{sem}学期 syllabus 检查（{len(d)}门课）\n{'='*60}")
    total_bad = 0
    for name, info in d.items():
        topics = [r["topic"] for r in info["rows"]]
        dup = len(topics) - len(set(topics))
        ban_hit = [t for t in topics if any(w in t for w in BAN)]
        # 素材数（去重）
        n_items = len(set(topics))
        n_rows = len(topics)
        issues = []
        if dup: issues.append(f"重复{dup}")
        if ban_hit: issues.append(f"禁词{len(ban_hit)}: {ban_hit[:3]}")
        # 内容太短/疑似占位（少于6字且无·分割）
        short = [t for t in topics if len(t) < 8 and "·" not in t]
        if short: issues.append(f"疑似占位{len(short)}: {short[:3]}")
        if issues:
            total_bad += 1
            print(f"  ❌ {name}: {n_rows}节/素材{n_items} {'；'.join(issues)}")
    if total_bad == 0:
        print("  ✅ 全部课程无凑数/重复")
    return total_bad

bad = 0
sems = [int(x) for x in sys.argv[1:]] or [1, 2]
for s in sems:
    bad += check(s)
print(f"\n共 {bad} 门课存在问题")
