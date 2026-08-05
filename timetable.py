#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
虚拟周课表查看器 —— 按周次查看课表，标记本周实际上课的课次
用法：
    python3 timetable.py              # 查看当前虚拟周
    python3 timetable.py 5            # 查看第5周
    python3 timetable.py 2023-10-16   # 按日期查看
"""

import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from virtual_time import VirtualClock

SLOTS = [
    (1, "第一节①", "08:00-08:45"),
    (2, "第一节②", "08:55-09:40"),
    (3, "第二节①", "09:50-10:45"),
    (4, "第二节②", "10:55-11:40"),
    (5, "第三节", "14:30-16:00"),
    (6, "第四节", "16:10-17:40"),
    (7, "第五节①", "19:00-19:45"),
    (8, "第五节②", "19:55-20:40"),
    (9, "第五节③", "20:50-21:35"),
]
WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def main():
    vc = VirtualClock()
    if len(sys.argv) >= 2:
        arg = sys.argv[1]
        if arg.isdigit():
            week_no = int(arg)
            sem = vc.semester_of(vc.now())
            start = datetime.strptime(vc.term_start(sem), "%Y-%m-%d")
            anchor = start + timedelta(weeks=week_no - 1)
        else:
            anchor = datetime.strptime(arg, "%Y-%m-%d")
            week_no = vc.week_of_term(anchor)
    else:
        anchor = vc.now()
        week_no = vc.week_of_term(anchor)

    sem = vc.semester_of(anchor)
    week_start = anchor - timedelta(days=anchor.weekday())  # 周一
    week_end = week_start + timedelta(days=6)
    print(f"\n===== 虚拟课表：第{week_no}周（第{sem}学期）=====")
    print(f"      {week_start:%Y-%m-%d}(周一) ~ {week_end:%Y-%m-%d}(周日)")
    print(f"      ✅=本周上课   ⏸=课表有此课但本周不上\n")

    conn = sqlite3.connect(Path(__file__).parent / "db" / "virtual_time.db")
    conn.row_factory = sqlite3.Row

    events = conn.execute(
        "SELECT * FROM semester_events WHERE semester_no=? AND week_no=?", (sem, week_no)).fetchall()

    for wd in range(5):
        print(f"--- {WEEKDAY_CN[wd]} ---")
        for s, label, tm in SLOTS:
            row = conn.execute(
                "SELECT * FROM virtual_course_schedule WHERE semester_no=? AND weekday=? AND slot_index=?",
                (sem, wd, s)).fetchone()
            ev = next((e for e in events if e["weekday"] == wd and e["slot_index"] == s), None)
            if ev:
                print(f"  {label} {tm}  {ev['course']} 【事件】（{ev['hours']}学时）")
                continue
            if row:
                weeks = {int(x) for x in row["session_weeks"].split(",")}
                on = week_no in weeks
                sem_tag = "·讨论" if (row["has_seminar"] and "讨论" not in row["course"]) else ""
                wstr = row["session_weeks"]
                if on:
                    print(f"  {label} {tm}  {row['course']}{sem_tag} ✅（{row['hours']}学时）")
                else:
                    print(f"  {label} {tm}  {row['course']}{sem_tag} ⏸（本周不上，上课周次[{wstr}]）")
            else:
                print(f"  {label} {tm}  — 空闲")
        print()
    conn.close()


if __name__ == "__main__":
    main()
