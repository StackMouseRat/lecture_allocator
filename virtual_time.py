#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
虚拟时间模块 —— 为碧蓝航线调度器提供虚拟时钟服务
数据库：blhx_scheduler/db/virtual_time.db
初始基准：2023-09-14（周四，工作日）08:30:00

用法：
    from virtual_time import VirtualClock
    vc = VirtualClock()
    now = vc.now()                # 获取当前虚拟时间 datetime
    info = vc.info()              # 获取结构化信息 dict
    vc.advance(minutes=30)        # 推进 30 分钟
    vc.advance(days=1)            # 推进 1 天
    vc.set('2023-09-15 09:00:00') # 直接设定
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "db" / "virtual_time.db"

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


class VirtualClock:
    """虚拟时钟：对 virtual_time 单行表的读写封装"""

    def __init__(self, db_path=None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        if not self.db_path.exists():
            raise FileNotFoundError(f"虚拟时间数据库不存在: {self.db_path}（请先运行 init 脚本）")

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def now(self) -> datetime:
        """返回当前虚拟时间（datetime 对象）"""
        conn = self._connect()
        row = conn.execute("SELECT virtual_datetime FROM virtual_time WHERE id=1").fetchone()
        conn.close()
        if row is None:
            raise RuntimeError("virtual_time 表为空")
        return datetime.strptime(row["virtual_datetime"], "%Y-%m-%d %H:%M:%S")

    def info(self) -> dict:
        """返回当前虚拟时间的结构化信息"""
        conn = self._connect()
        row = conn.execute("SELECT * FROM virtual_time WHERE id=1").fetchone()
        conn.close()
        if row is None:
            raise RuntimeError("virtual_time 表为空")
        d = dict(row)
        d["weekday_cn"] = WEEKDAY_CN[d["weekday"]]
        d["period"] = self._period_of_day(d["hour"])
        d["is_workday_cn"] = "工作日" if d["is_workday"] else "休息日"
        return d

    def _period_of_day(self, hour: int) -> str:
        """按小时划分时段，供调度器按场景筛选台词"""
        if hour < 6:
            return "深夜"
        if hour < 9:
            return "早晨"
        if hour < 12:
            return "上午"
        if hour < 14:
            return "中午"
        if hour < 18:
            return "下午"
        if hour < 22:
            return "晚上"
        return "深夜"

    def _write(self, new_dt: datetime, action: str, old_dt: datetime | None, note: str = ""):
        conn = self._connect()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("""
            UPDATE virtual_time SET
                virtual_datetime=?, year=?, month=?, day=?, weekday=?,
                hour=?, minute=?, second=?, is_workday=?, updated_at=?
            WHERE id=1
        """, (new_dt.strftime("%Y-%m-%d %H:%M:%S"), new_dt.year, new_dt.month, new_dt.day,
              new_dt.weekday(), new_dt.hour, new_dt.minute, new_dt.second,
              1 if new_dt.weekday() < 5 else 0, now_str))
        conn.execute("INSERT INTO time_log (action, old_time, new_time, note, created_at) VALUES (?,?,?,?,?)",
                     (action, old_dt.strftime("%Y-%m-%d %H:%M:%S") if old_dt else None,
                      new_dt.strftime("%Y-%m-%d %H:%M:%S"), note, now_str))
        conn.commit()
        conn.close()

    def advance(self, seconds=0, minutes=0, hours=0, days=0, note: str = ""):
        """推进虚拟时间（可组合：advance(days=1, hours=2)）"""
        old = self.now()
        new = old + timedelta(seconds=seconds, minutes=minutes, hours=hours, days=days)
        self._write(new, "advance", old, note or f"+{days}天{hours}小时{minutes}分{seconds}秒")
        return new

    def set(self, dt_str: str, note: str = ""):
        """直接设定虚拟时间，接受 'YYYY-MM-DD HH:MM:SS' 或 'YYYY-MM-DD HH:MM'"""
        fmt = "%Y-%m-%d %H:%M:%S"
        try:
            new = datetime.strptime(dt_str, fmt)
        except ValueError:
            new = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        old = self.now()
        self._write(new, "set", old, note)
        return new

    def history(self, limit: int = 20) -> list:
        """查看最近的时间变更记录"""
        conn = self._connect()
        rows = conn.execute("SELECT * FROM time_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ---------- 学期判定 ----------

    def semester_of(self, dt: datetime | None = None) -> int:
        """
        由虚拟日期推算学期序号（基准：2022年9月入学 = 第1学期）
        编号与培养方案一致：1,2,短1,3,4,短2,5,6,短3,7,8（此处短学期返回 -1）
        """
        dt = dt or self.now()
        y, m = dt.year, dt.month
        if m in (9, 10, 11, 12):
            sem = 1 + 2 * (y - 2022)      # 2022秋=1, 2023秋=3, 2024秋=5, 2025秋=7
        elif m in (1,):
            sem = 1 + 2 * (y - 1 - 2022)  # 2023-01=1
        elif m in (2, 3, 4, 5, 6):
            sem = 2 + 2 * (y - 1 - 2022)  # 2023春=2, 2024春=4, 2025春=6, 2026春=8
        else:  # 7~8月 短学期
            return -1
        return sem

    def term_start(self, semester_no: int) -> str | None:
        """查询某学期开学日期（YYYY-MM-DD）"""
        conn = self._connect()
        row = conn.execute("SELECT start_date FROM terms WHERE semester_no=?", (semester_no,)).fetchone()
        conn.close()
        return row["start_date"] if row else None

    def week_of_term(self, dt: datetime | None = None) -> int:
        """计算虚拟日期处于学期第几周（开学当周为第1周；开学前返回0）"""
        dt = dt or self.now()
        sem = self.semester_of(dt)
        start = self.term_start(sem)
        if not start:
            return 0
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        delta = (dt.date() - start_dt.date()).days
        if delta < 0:
            return 0
        return delta // 7 + 1

    # ---------- 课程联动 ----------

    def current_course(self, dt: datetime | None = None) -> dict:
        """
        查询虚拟时间当前正在上的课程。
        返回：{status: in_class/free/weekend/break/short_term,
               semester_no, weekday_cn, slot_index, period,
               course, credits, category, course_type, start_time, end_time}
        """
        dt = dt or self.now()
        sem = self.semester_of(dt)
        if sem == -1:
            return {"status": "short_term", "semester_no": sem,
                    "time": dt.strftime("%H:%M"), "course": None}
        wd = dt.weekday()
        if wd >= 5:
            return {"status": "weekend", "semester_no": sem, "weekday_cn": WEEKDAY_CN[wd],
                    "time": dt.strftime("%H:%M"), "course": None}
        t = dt.strftime("%H:%M")
        conn = self._connect()
        # 找到当前 slot
        slot = conn.execute(
            "SELECT slot_index, period, start_time, end_time FROM schedule "
            "WHERE start_time <= ? AND ? < end_time ORDER BY slot_index LIMIT 1", (t, t)
        ).fetchone()
        if slot is None:
            conn.close()
            return {"status": "break", "semester_no": sem, "weekday_cn": WEEKDAY_CN[wd],
                    "time": t, "course": None, "slot_index": None}
        week = self.week_of_term(dt)
        base = {"semester_no": sem, "week_no": week, "weekday_cn": WEEKDAY_CN[wd],
                "slot_index": slot["slot_index"], "period": slot["period"],
                "time": t, "start_time": slot["start_time"], "end_time": slot["end_time"]}
        # ① 学期事件课优先（如形势与政策：一学期仅2次）
        ev = conn.execute(
            "SELECT course, credits, category, course_type, start_time, end_time, note "
            "FROM semester_events WHERE semester_no=? AND week_no=? AND weekday=? AND slot_index=?",
            (sem, week, wd, slot["slot_index"])
        ).fetchone()
        if ev is not None:
            conn.close()
            base.update({"status": "in_class", "course": ev["course"], "credits": ev["credits"],
                         "category": ev["category"], "course_type": ev["course_type"],
                         "event": True, "event_note": ev["note"],
                         "start_time": ev["start_time"], "end_time": ev["end_time"]})
            return base
        # ② 每周课表
        row = conn.execute(
            "SELECT course, credits, category, course_type, hours, start_time, end_time, "
            "session_weeks, has_seminar "
            "FROM virtual_course_schedule WHERE semester_no=? AND weekday=? AND slot_index=?",
            (sem, wd, slot["slot_index"])
        ).fetchone()
        # 按 session_weeks（课次所在周次列表）过滤
        if row is not None and row["session_weeks"]:
            sw = {int(x) for x in row["session_weeks"].split(",") if x.strip()}
            if week not in sw:
                row = None
        conn.close()
        if row is None:
            base.update({"status": "free", "course": None, "event": False})
        else:
            base.update({"status": "in_class", "course": row["course"],
                         "credits": row["credits"], "category": row["category"],
                         "course_type": row["course_type"], "hours": row["hours"],
                         "has_seminar": bool(row["has_seminar"]), "event": False})
        return base

    # ---------- 时段/课程表 ----------

    def schedule(self) -> list:
        """返回完整时间表（schedule 表全部记录）"""
        conn = self._connect()
        rows = conn.execute("SELECT * FROM schedule ORDER BY slot_index").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def current_slot(self, dt: datetime | None = None) -> dict | None:
        """
        根据虚拟时间判断当前所处时段。
        返回 dict：{slot_index, period, segment, start_time, end_time, is_in_slot,
                    day_period(早晨/上午/…), is_workday}
        若不在任何时段内（课间/午休/夜间）返回 None 或 status='break'。
        """
        dt = dt or self.now()
        t = dt.strftime("%H:%M")
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM schedule WHERE start_time <= ? AND ? < end_time ORDER BY slot_index LIMIT 1",
            (t, t)
        ).fetchone()
        conn.close()
        if rows is None:
            return {
                "status": "break",
                "time": t,
                "slot_index": None,
                "period": None,
                "segment": None,
                "day_period": self._period_of_day(dt.hour),
                "is_workday": dt.weekday() < 5,
            }
        d = dict(rows)
        d["status"] = "in_slot"
        d["time"] = t
        d["day_period"] = self._period_of_day(dt.hour)
        d["is_workday"] = dt.weekday() < 5
        return d


if __name__ == "__main__":
    vc = VirtualClock()
    print("=== 当前虚拟时间 ===")
    for k, v in vc.info().items():
        print(f"  {k}: {v}")
