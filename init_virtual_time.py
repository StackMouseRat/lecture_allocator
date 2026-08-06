#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
虚拟时间数据库初始化：补建 virtual_time / time_log / schedule 三表
并写入基准时间 2023-09-14（周四）08:30:00。
用法：python3 build_semesters.py && python3 init_virtual_time.py
"""
import sqlite3
from datetime import datetime
from pathlib import Path

DB = Path(__file__).parent / "db" / "virtual_time.db"

SLOTS = [
    (1, "第一节①", "08:00", "08:45"), (2, "第一节②", "08:55", "09:40"),
    (3, "第二节①", "10:00", "10:45"), (4, "第二节②", "10:55", "11:40"),
    (5, "第三节", "14:30", "16:00"), (6, "第四节", "16:10", "17:40"),
    (7, "第五节①", "19:00", "19:45"), (8, "第五节②", "19:55", "20:40"),
    (9, "第五节③", "20:50", "21:35"),
]

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("""CREATE TABLE IF NOT EXISTS virtual_time (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    virtual_datetime TEXT NOT NULL,
    year INTEGER, month INTEGER, day INTEGER, weekday INTEGER,
    hour INTEGER, minute INTEGER, second INTEGER, is_workday INTEGER,
    updated_at TEXT
)""")
cur.execute("""CREATE TABLE IF NOT EXISTS time_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT, old_time TEXT, new_time TEXT, note TEXT, created_at TEXT
)""")
cur.execute("""CREATE TABLE IF NOT EXISTS schedule (
    slot_index INTEGER PRIMARY KEY, period TEXT, start_time TEXT, end_time TEXT
)""")
for s in SLOTS:
    cur.execute("INSERT OR REPLACE INTO schedule VALUES (?,?,?,?)", s)
dt = datetime(2023, 9, 14, 8, 30, 0)
cur.execute("""INSERT OR REPLACE INTO virtual_time
    (id, virtual_datetime, year, month, day, weekday, hour, minute, second, is_workday, updated_at)
    VALUES (1,?,?,?,?,?,?,?,?,?,?)""",
    (dt.strftime("%Y-%m-%d %H:%M:%S"), dt.year, dt.month, dt.day, dt.weekday(),
     dt.hour, dt.minute, dt.second, 1, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
conn.commit()
conn.close()
print("✅ 虚拟时间已初始化：2023-09-14 08:30:00（周四，基准）")
