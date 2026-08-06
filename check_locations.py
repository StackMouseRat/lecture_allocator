#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""地点冲突检查：相邻课次（时间连续，间隔≤30分钟）必须在同一栋楼"""
import sys, re, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from render_utils import resolve

# 第1学期课程（db）→ 每人课表行（含渲染地点）
import sqlite3
conn = sqlite3.connect(Path(__file__).parent / "db" / "virtual_time.db")
conn.row_factory = sqlite3.Row

SLOT_TIME = {1:"08:00", 2:"08:55", 3:"09:50", 4:"10:55", 5:"14:30", 6:"16:10", 7:"19:00", 8:"19:55", 9:"20:50"}
WD = ["周一","周二","周三","周四","周五"]
GIRLS = [("surrey","萨里"),("orage","暴风雨"),("sakawa","酒匂"),("taiyuan","太原")]

def building(loc):
    """地点 → 楼（同一楼=同一地点）"""
    if not loc: return None
    for b in ["综合楼","研楼","复临舍","前进楼","体育馆","田径场","游泳馆"]:
        if b in loc: return b
    if "自习" in loc: return "自习"
    return loc

print("="*72)
print("地点冲突检查（第1学期·相邻课次必须同一楼）")
print("="*72)
total_conflict = 0
for g, cn in GIRLS:
    # 该生第1学期全部课次（渲染地点）
    sessions = []   # (weekday, start_min, end_min, course, building)
    for r in conn.execute("SELECT * FROM virtual_course_schedule WHERE semester_no=1"):
        resolved = resolve(g, r["course"], 1)
        if not resolved: continue
        loc_b = building(resolved["location"])
        wd = r["weekday"]
        slot = r["slot_index"]
        # 该课次时段（以 slot 起止：2小节合并算一次课）
        t = SLOT_TIME[slot]
        hh, mm = (int(x) for x in t.split(":"))
        start = hh*60 + mm
        weeks = {int(x) for x in r["session_weeks"].split(",") if x.strip()}
        sessions.append((wd, start, start+45, resolved["name"], loc_b, weeks))
    # 按天+开始时间排序
    by_day = {}
    for s in sessions:
        by_day.setdefault(s[0], []).append(s)
    conflicts = []
    for wd, lst in by_day.items():
        lst.sort(key=lambda x: x[1])
        for i in range(len(lst)-1):
            cur = lst[i]; nxt = lst[i+1]
            gap = nxt[1] - cur[2]
            if gap <= 30 and gap >= 0 and (cur[5] & nxt[5]):   # 相邻且同周
                if cur[4] != nxt[4]:     # 楼不同
                    conflicts.append((cur, nxt))
    print(f"\n【{cn}】")
    if not conflicts:
        print("  ✅ 无相邻课地点冲突")
    else:
        for cur, nxt in conflicts:
            gap = nxt[1] - cur[2]
            print(f"  ❌ {WD[cur[0]]} {cur[1]//60:02d}:{cur[1]%60:02d}-{cur[2]//60:02d}:{cur[2]%60:02d} {cur[3]}({cur[4]})")
            print(f"     → 下一节 {nxt[1]//60:02d}:{nxt[1]%60:02d}-{nxt[2]//60:02d}:{nxt[2]%60:02d} {nxt[3]}({nxt[4]}) 间隔{gap}分钟 楼不同")
            total_conflict += 1
conn.close()
print(f"\n{'='*72}\n共 {total_conflict} 处相邻课地点冲突")
