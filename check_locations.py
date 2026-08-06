#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""地点冲突检查：相邻课次（时间连续，间隔≤30分钟）必须在同一栋楼
遍历所有已分配地点模型的学期（sem1/sem2）"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from render_utils import resolve

import sqlite3
conn = sqlite3.connect(Path(__file__).parent / "db" / "virtual_time.db")
conn.row_factory = sqlite3.Row

SLOT_TIME = {1:"08:00", 2:"08:55", 3:"09:50", 4:"10:55", 5:"14:30", 6:"16:10", 7:"19:00", 8:"19:55", 9:"20:50"}
WD = ["周一","周二","周三","周四","周五"]
GIRLS = [("surrey","萨里"),("orage","暴风雨"),("sakawa","酒匂"),("taiyuan","太原")]
SEM_LIST = [1, 2]   # 已分配地点的学期

def building(loc):
    if not loc: return None
    for b in ["综合楼","研楼","复临舍","前进楼","体育馆","田径场","游泳馆"]:
        if b in loc: return b
    if "自习" in loc: return "自习"
    return loc

print("="*72)
print("地点冲突检查（相邻课次必须同一楼）")
print("="*72)
total = 0
for sem_no in SEM_LIST:
    for g, cn in GIRLS:
        sessions = []
        for r in conn.execute("SELECT * FROM virtual_course_schedule WHERE semester_no=?", (sem_no,)):
            resolved = resolve(g, r["course"], sem_no)
            if not resolved: continue
            loc_b = building(resolved["location"])
            wd = r["weekday"]; slot = r["slot_index"]
            weeks = {int(x) for x in r["session_weeks"].split(",") if x.strip()}
            hh, mm = (int(x) for x in SLOT_TIME[slot].split(":"))
            start = hh*60 + mm
            sessions.append((wd, start, start+45, resolved["name"], loc_b, weeks))
        by_day = {}
        for s in sessions:
            by_day.setdefault(s[0], []).append(s)
        conflicts = []
        for wd, lst in by_day.items():
            lst.sort(key=lambda x: x[1])
            for i in range(len(lst)-1):
                cur, nxt = lst[i], lst[i+1]
                gap = nxt[1] - cur[2]
                if gap <= 30 and gap >= 0 and (cur[5] & nxt[5]):
                    if cur[4] != nxt[4]:
                        conflicts.append((cur, nxt))
        print(f"\n【{cn}·第{sem_no}学期】")
        if not conflicts:
            print("  ✅ 无相邻课地点冲突")
        else:
            for cur, nxt in conflicts:
                gap = nxt[1] - cur[2]
                print(f"  ❌ {WD[cur[0]]} {cur[1]//60:02d}:{cur[1]%60:02d}-{cur[2]//60:02d}:{cur[2]%60:02d} {cur[3]}({cur[4]})")
                print(f"     → {WD[nxt[0]]} {nxt[1]//60:02d}:{nxt[1]%60:02d} {nxt[3]}({nxt[4]}) 间隔{gap}分钟")
                total += 1
conn.close()
print(f"\n共 {total} 处相邻课地点冲突")
