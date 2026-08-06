#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""培养方案结构化：data/plan_courses.json
- 类别/学分/学时/开课单位：解析 plan_layout.txt
- 开课学期：以 db 实际排课为准（不猜测）；未排课程标注 pending"""
import re, json, sqlite3
from pathlib import Path

SRC = Path("/workspace/hnu_major/plan_layout.txt")
DB = Path(__file__).parent / "db" / "virtual_time.db"
OUT = Path(__file__).parent / "data" / "plan_courses.json"

lines = SRC.read_text(encoding="utf-8").split("\n")

CAT_KEYS = [("通识必","通识必修"),("通识选","通识选修"),("学门核","学门核心"),
            ("学类核","学类核心"),("专业核","专业核心"),("个性培","个性培养"),
            ("实践环","实践环节"),("环节","实践环节"),("实践","实践环节")]
cur_cat = None
courses = {}     # name -> dict
pending = {}     # 跨行课程名累积

def flush():
    for name, rec in pending.items():
        courses[name] = rec
    pending.clear()

for l in lines:
    for key, cat in CAT_KEYS:
        if key in l:
            cur_cat = cat
    s = l.rstrip()
    nums = re.findall(r"\d+(?:\.\d+)?", s)
    m = re.match(r"^\s*([\u4e00-\u9fffA-Za-z（）()·\-]{2,16})", s)
    if m and len(nums) >= 3 and cur_cat:
        name = m.group(1)
        if any(k in name for k in ["课程","类别","学分","开课","专业","实践","环节","必修","选修","核心","培养","通识","学门","学类"]):
            continue
        if len(name) < 3:
            continue
        credits = float(nums[0])
        hours = float(nums[-2]) if len(nums) >= 4 else float(nums[-1])
        # 单位（开课学院）：位于 学时数字 与 学期标记 之间，取最后的中文串
        unit = ""
        mu = re.findall(r"([\u4e00-\u9fff]{2,6}院|中心|部|武装)", s)
        if mu: unit = mu[-1]
        pending[name] = {"category": cur_cat, "credits": credits, "hours": hours,
                         "unit": unit, "semesters_db": [], "pending": False}
    else:
        # 跨行续名（如"概论"）
        t = s.strip()
        if t and pending and re.match(r"^[\u4e00-\u9fff]{2,4}$", t) and not re.match(r"^\d", t):
            key = list(pending)[-1]
            rec = pending.pop(key)
            rec["name_orig"] = key
            pending[key + t] = rec
flush()

# 合并 db 实际学期
conn = sqlite3.connect(DB)
for sem in range(1, 7):
    for (cname,) in conn.execute("SELECT DISTINCT course FROM virtual_course_schedule WHERE semester_no=?", (sem,)):
        # 匹配培养方案课程（含"概论"合并）
        for pname, rec in courses.items():
            if cname == pname or (cname.startswith(pname[:4]) and len(pname) >= 6):
                if sem not in rec["semesters_db"]:
                    rec["semesters_db"].append(sem)
conn.close()

# 未排课程标记
for rec in courses.values():
    if not rec["semesters_db"]:
        rec["pending"] = True

OUT.write_text(json.dumps(courses, ensure_ascii=False, indent=1), encoding="utf-8")
from collections import Counter
print(f"解析 {len(courses)} 门课")
print("类别:", dict(Counter(v['category'] for v in courses.values())))
print("\n=== 实践环节 ===")
for n, v in courses.items():
    if v["category"] == "实践环节":
        print(f"  {n}: {v['credits']}学分/{v['hours']}学时 {v['unit']} 排课学期{v['semesters_db']} {'⚠️未排' if v['pending'] else ''}")
print("\n=== 未排课程（全部类别）===")
for n, v in courses.items():
    if v["pending"]:
        print(f"  [{v['category']}] {n}: {v['credits']}学分/{v['hours']}学时")
