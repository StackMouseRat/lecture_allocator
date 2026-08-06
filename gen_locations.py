#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第1学期地点模型：data/locations_sem1.json
- 高数/大英/思道/心理健康：综合楼
- 工程制图：研楼
- 选修：随机分配 复临舍/综合楼（固定种子，可复现）
- 体育：按项目（体育馆/田径场）"""
import json, random
from pathlib import Path

random.seed(1)   # 固定种子，保证可复现（两楼混合）

LOC = {
    "高等数学A（1）": "综合楼",
    "大学英语A（1）": "综合楼",
    "思想道德与法治": "综合楼",
    "大学生心理健康教育": "综合楼",
    "工程制图": "研楼",
}
# 选修占位符随机分配
EVENING = ["通识选修·晚间①","通识选修·晚间②","通识选修·晚间③","通识选修·晚间④"]
for ph in EVENING:
    LOC[ph] = random.choice(["复临舍", "综合楼"])
# 体育按项目
LOC["体育（1）"] = "体育馆/田径场（按项目）"
# 四史：自习（无固定地点）
LOC["中共党史"] = LOC["社会主义发展史"] = LOC["改革开放史"] = LOC["新中国史"] = "自习（无教室）"

out = {"buildings": ["综合楼", "研楼", "复临舍", "体育馆", "田径场"], "courses": LOC}
Path("data/locations_sem1.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("✅ 第1学期地点模型已生成：")
for k, v in LOC.items():
    print(f"  {k}: {v}")
