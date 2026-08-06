#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据完整性自检：表齐全 / 每学期课次 / 周二下午0 / 实验周次模式 / 事件数"""
import sqlite3
from pathlib import Path

conn = sqlite3.connect(Path(__file__).parent / "db" / "virtual_time.db")
conn.row_factory = sqlite3.Row
ok = True

def chk(cond, msg):
    global ok
    print(("  ✅ " if cond else "  ❌ ") + msg)
    if not cond: ok = False

print("【表完整性】")
need = {"terms","virtual_course_schedule","semester_events","schedule","virtual_time","time_log"}
have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
chk(need <= have, f"全部表存在 {sorted(need - have) or '✓'}")

print("【虚拟时钟基准】")
r = conn.execute("SELECT virtual_datetime FROM virtual_time WHERE id=1").fetchone()
chk(r and r[0] == "2023-09-14 08:30:00", f"基准={r[0] if r else '缺失'}")
chk(conn.execute("SELECT COUNT(*) FROM schedule").fetchone()[0] == 10, "schedule 10时段（含第10节21:35-22:20）")

print("【各学期】")
for sem in range(1, 7):
    if sem in (4, 5):
        # per-girl 学期：以 surrey 为代表统计
        n = conn.execute("SELECT COUNT(DISTINCT course) FROM girl_course_schedule WHERE semester_no=? AND girl='surrey'", (sem,)).fetchone()[0]
        rows = conn.execute("SELECT COUNT(*) FROM girl_course_schedule WHERE semester_no=? AND girl='surrey'", (sem,)).fetchone()[0]
        ev = conn.execute("SELECT COUNT(*) FROM semester_events WHERE semester_no=?", (sem,)).fetchone()[0]
        tue = conn.execute("SELECT COUNT(*) FROM girl_course_schedule WHERE semester_no=? AND girl='surrey' AND weekday=1 AND slot_index IN (5,6)", (sem,)).fetchone()[0]
    else:
        n = conn.execute("SELECT COUNT(DISTINCT course) FROM virtual_course_schedule WHERE semester_no=?", (sem,)).fetchone()[0]
        rows = conn.execute("SELECT COUNT(*) FROM virtual_course_schedule WHERE semester_no=?", (sem,)).fetchone()[0]
        ev = conn.execute("SELECT COUNT(*) FROM semester_events WHERE semester_no=?", (sem,)).fetchone()[0]
        tue = conn.execute("SELECT COUNT(*) FROM virtual_course_schedule WHERE semester_no=? AND weekday=1 AND slot_index IN (5,6)", (sem,)).fetchone()[0]
    chk(tue == 0, f"第{sem}学期: {n}门课/{rows}行/{ev}事件, 周二下午违规={tue}")

print("【实验周次模式】")
if conn.execute("SELECT COUNT(*) FROM girl_course_schedule WHERE course_type='实验'").fetchone()[0] > 0:
    for r in conn.execute("SELECT DISTINCT semester_no, course, session_weeks FROM girl_course_schedule WHERE course_type='实验' AND girl='surrey'"):
        wks = [int(x) for x in r["session_weeks"].split(",")]
        sem = r["semester_no"]
        if sem == 4:   # 大二下：隔周
            if len(wks) >= 2:
                odd = all(w % 2 == wks[0] % 2 for w in wks)
                chk(odd, f"第{sem}学期 {r['course']}: 隔周模式 {wks[0]%2}")
        # 第5学期：大三连续周（check_conflicts/check_locations 已覆盖），此处不重复
for r in conn.execute("SELECT DISTINCT semester_no, course, session_weeks FROM virtual_course_schedule WHERE course_type='实验'"):
    wks = [int(x) for x in r["session_weeks"].split(",")]
    sem = r["semester_no"]
    if sem <= 4 and len(wks) >= 2:   # 大一大二：隔周（连续周如CAD上机W9-12合法）
        continuous = any(wks[i+1] - wks[i] == 1 for i in range(len(wks)-1))
        if not continuous:
            odd = all(w % 2 == wks[0] % 2 for w in wks)
            chk(odd, f"第{sem}学期 {r['course']}: 隔周模式 {wks[0]%2}")

conn.close()
print("\n" + ("✅ 全部检查通过" if ok else "❌ 存在异常"))
