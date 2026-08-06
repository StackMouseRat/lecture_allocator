#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""渲染层时间冲突校验：4人×6学期，渲染(天偏移)后同格双课检查
db无冲突≠渲染无冲突（老师offset可能把课移到其他课槽位）"""
import sys, sqlite3, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from render_utils import resolve

TEACHERS = json.load(open(Path(__file__).parent / "data" / "teachers.json", encoding="utf-8"))
def render_wd(course_raw, girl, wd):
    """与 render_major 一致：老师 assign offset 天偏移"""
    ti = TEACHERS.get(course_raw)
    if ti:
        a = ti.get("assign", {}).get(girl)
        if a:
            return (wd + a.get("offset", 0)) % 5
    return wd

conn = sqlite3.connect(Path(__file__).parent / "db" / "virtual_time.db")
conn.row_factory = sqlite3.Row
WD = ["周一","周二","周三","周四","周五"]
GIRLS = [("surrey","萨里"),("orage","暴风雨"),("sakawa","酒匂"),("taiyuan","太原")]

def main():
    total = 0
    for g, cn in GIRLS:
        for sem in range(1, 7):
            grid = {}   # (wd, slot) -> [(course, weeks)]
            for r in conn.execute("SELECT course, weekday, slot_index, session_weeks FROM virtual_course_schedule WHERE semester_no=?", (sem,)):
                resolved = resolve(g, r["course"], sem)
                if not resolved: continue
                wd = render_wd(r["course"], g, r["weekday"]); slot = r["slot_index"]
                weeks = {int(x) for x in r["session_weeks"].split(",") if x.strip()}
                grid.setdefault((wd, slot), []).append((resolved["name"], weeks))
            for (wd, slot), lst in grid.items():
                for i in range(len(lst)):
                    for j in range(i+1, len(lst)):
                        if lst[i][1] & lst[j][1]:
                            total += 1
                            inter = sorted(lst[i][1] & lst[j][1])
                            print(f"  ❌ {cn}·第{sem}学期 {WD[wd]} slot{slot} W{inter[0]}-{inter[-1]}: {lst[i][0]} + {lst[j][0]}")
        print(f"【{cn}】检查完成")
    print(f"\n共 {total} 处渲染层时间冲突")
    conn.close()

if __name__ == "__main__":
    main()
