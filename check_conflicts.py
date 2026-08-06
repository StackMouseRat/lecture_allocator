#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""时间冲突校验：任意 (学期,周,天,槽位) 不得同时被 ≥2 门不同课占用
覆盖：常规课（按周次）+ 学期事件（形势政策/军训/思政实践等）"""
import sqlite3
from pathlib import Path

conn = sqlite3.connect(Path(__file__).parent / "db" / "virtual_time.db")
conn.row_factory = sqlite3.Row
WD = ["周一","周二","周三","周四","周五"]
SLOTS = {1:"08:00",2:"08:55",3:"10:00",4:"10:55",5:"14:30",6:"16:10",7:"19:00",8:"19:55",9:"20:50", 10:"21:35"}

def main():
    total = 0
    block_reported = {i: set() for i in range(1, 7)}
    for sem in range(1, 7):
        # 常规课：weekday, slot → 周次集合
        grid = {}
        for r in conn.execute("SELECT course, weekday, slot_index, session_weeks FROM virtual_course_schedule WHERE semester_no=?", (sem,)):
            weeks = {int(x) for x in r["session_weeks"].split(",") if x.strip()}
            grid.setdefault((r["weekday"], r["slot_index"]), []).append((r["course"], weeks))
        # 事件：week, weekday, slot（集中实践=设计叠加，查看器过滤；其余=须排他）
        events = {}
        for r in conn.execute("SELECT course, week_no, weekday, slot_index FROM semester_events WHERE semester_no=?", (sem,)):
            events.setdefault((r["week_no"], r["weekday"], r["slot_index"]), []).append(r["course"])
        BLOCK_EVENTS = {"军事技能（集中军训）", "思政实践（社会实践）",
                        "电子技术综合设计（集中）", "劳动教育与素养"}
        sem_conflicts = 0
        for (wd, slot), courses in sorted(grid.items()):
            for week in range(1, 17):
                hit = [c for c, ws in courses if week in ws]
                ev = events.get((week, wd, slot))
                if ev:
                    hit += [f"[事件]{c}" for c in ev]
                hit = list(dict.fromkeys(hit))   # 去重（同一课多行如2小节）
                if len(hit) >= 2:
                    # 集中实践事件与课程叠加=设计（查看器过滤）；其余=真冲突
                    ev_hit = [c for c in hit if c.startswith("[事件]")]
                    is_block = ev_hit and all(c[4:] in BLOCK_EVENTS for c in ev_hit)
                    if is_block:
                        if week not in block_reported[sem]:
                            print(f"  ℹ️ 第{sem}学期 W{week} 集中实践叠加（设计，查看器过滤）: {ev_hit[0][4:]}")
                            block_reported[sem].add(week)
                        continue
                    sem_conflicts += 1
                    total += 1
                    print(f"  ❌ 第{sem}学期 W{week} {WD[wd]} slot{slot}({SLOTS[slot]}) 真冲突: {' + '.join(hit)}")
        print(f"第{sem}学期: {sem_conflicts} 处冲突")
    print(f"\n共 {total} 处时间冲突")
    conn.close()

if __name__ == "__main__":
    main()
