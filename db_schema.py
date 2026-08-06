#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据库 Schema 唯一权威定义：所有表 + 种子数据
任何脚本需要建库/重建，一律调用 init_schema(conn)，禁止各自建表"""
import sqlite3

def init_schema(conn: sqlite3.Connection):
    """建全部表 + 种子（幂等：IF NOT EXISTS）"""
    cur = conn.cursor()
    # 1) 学期表
    cur.execute("CREATE TABLE IF NOT EXISTS terms (semester_no INTEGER PRIMARY KEY, term_code TEXT, start_date TEXT, end_date TEXT, note TEXT)")
    # 2) 课程表
    cur.execute("""CREATE TABLE IF NOT EXISTS virtual_course_schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT, term_code TEXT, semester_no INTEGER,
        course TEXT, weekday INTEGER, weekday_cn TEXT, slot_index INTEGER,
        period TEXT, start_time TEXT, end_time TEXT,
        session_weeks TEXT, credits REAL, category TEXT, course_type TEXT,
        hours REAL, has_seminar INTEGER, note TEXT)""")
    # 3) 学期事件表
    cur.execute("""CREATE TABLE IF NOT EXISTS semester_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, term_code TEXT, semester_no INTEGER,
        week_no INTEGER, weekday INTEGER, weekday_cn TEXT, slot_index INTEGER,
        start_time TEXT, end_time TEXT, course TEXT, credits REAL, category TEXT,
        course_type TEXT, hours REAL, note TEXT)""")
    # 4) 时段定义表（9时段，种子）
    cur.execute("""CREATE TABLE IF NOT EXISTS schedule (
        slot_index INTEGER PRIMARY KEY, period TEXT, segment TEXT,
        start_time TEXT, end_time TEXT)""")
    SLOT_DEFS = [(1,"第一节①","早晨","08:00","08:45"),(2,"第一节②","早晨","08:55","09:40"),
                 (3,"第二节①","上午","10:00","10:45"),(4,"第二节②","上午","10:55","11:40"),
                 (5,"第三节","下午","14:30","16:00"),(6,"第四节","下午","16:10","17:40"),
                 (7,"第五节①","晚上","19:00","19:45"),(8,"第五节②","晚上","19:55","20:40"),
                 (9,"第五节③","晚上","20:50","21:35"),
                 (12,"第五节④","晚上","21:35","22:20")]
    cur.executemany("INSERT OR IGNORE INTO schedule VALUES (?,?,?,?,?)", SLOT_DEFS)
    # 5) 虚拟时钟表（单行，基准 2023-09-14 周四 08:30）
    cur.execute("""CREATE TABLE IF NOT EXISTS virtual_time (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        virtual_datetime TEXT NOT NULL,
        year INTEGER, month INTEGER, day INTEGER, weekday INTEGER,
        hour INTEGER, minute INTEGER, second INTEGER,
        is_workday INTEGER, note TEXT, updated_at TEXT)""")
    cur.execute("INSERT OR IGNORE INTO virtual_time (id, virtual_datetime, year, month, day, weekday, hour, minute, second, is_workday, note, updated_at) "
                "VALUES (1, '2023-09-14 08:30:00', 2023, 9, 14, 3, 8, 30, 0, 1, '调度器初始设定：2023年9月中旬工作日早晨', '')")
    # 6) 虚拟时钟历史表
    cur.execute("""CREATE TABLE IF NOT EXISTS time_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, old_time TEXT,
        new_time TEXT, note TEXT, created_at TEXT)""")
    conn.commit()

def ensure_schema(db_path):
    """确保库完整：缺失即建（不删已有数据）"""
    conn = sqlite3.connect(db_path)
    init_schema(conn)
    conn.close()

if __name__ == "__main__":
    import sys
    from pathlib import Path
    db = Path(__file__).parent / "db" / "virtual_time.db"
    ensure_schema(db)
    conn = sqlite3.connect(db)
    print("Schema 就绪:", [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")])
    conn.close()
