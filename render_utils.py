#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""渲染公共层：db 原始课程名 → 人设课程名 + 老师 + 地点
供 render_major.py（课表）与 virtual_time.py（虚拟时钟 current_course）共用"""
import json
from pathlib import Path

BASE = Path(__file__).parent
_CACHE = {}

def _load(name, path):
    if name not in _CACHE:
        _CACHE[name] = json.load(open(BASE / path, encoding="utf-8"))
    return _CACHE[name]

def elective_content():
    return _load("elective", "data/elective_content.json")

def teachers():
    return _load("teachers", "data/teachers.json")

def locations():
    return _load("locations", "data/locations_sem1.json")

def pe_plan():
    return _load("pe", "data/pe_plan.json")

SISHI = {"中共党史", "社会主义发展史", "改革开放史", "新中国史"}
_SYLLABUS = {}

def syllabus_topic(course_name: str, semester_no: int, week: int, weekday: int, slot_index: int) -> str | None:
    """查授课进度：当前这一节讲什么（syllabus_semN.json）
    节次序号 = 该课在当周课表中的次序（按天/槽位排序）"""
    global _SYLLABUS
    f = BASE / "data" / f"syllabus_sem{semester_no}.json"
    if not f.exists():
        return None
    if semester_no not in _SYLLABUS:
        _SYLLABUS[semester_no] = json.load(open(f, encoding="utf-8"))
    data = _SYLLABUS[semester_no]
    for name, info in data.items():
        if name != course_name:
            continue
        rows = info.get("rows", [])
        this_week = [r for r in rows if r["week"] == week]
        # 该课当周课次顺序（由 virtual_time 传入的 weekday/slot 直接映射 session）
        # session 序号：rows 中 week 内第 n 个（按 session 字段）
        for r in this_week:
            if r["session"] == session_of_week(course_name, semester_no, week, weekday, slot_index):
                return r["topic"]
        return None
    return None

def session_of_week(course_name, semester_no, week, weekday, slot_index):
    """该课当周第几节：按 db 中该课分布的不同天排序（同课次2小节算1节）"""
    import sqlite3
    conn = sqlite3.connect(BASE / "db" / "virtual_time.db")
    rows = conn.execute(
        "SELECT DISTINCT weekday FROM virtual_course_schedule "
        "WHERE semester_no=? AND course=? ORDER BY weekday",
        (semester_no, course_name)).fetchall()
    conn.close()
    days = [r[0] for r in rows]
    if weekday in days:
        return days.index(weekday) + 1
    return 1
PE_COURSES = {f"体育（{i}）" for i in range(1, 5)}

def resolve(girl: str, raw_name: str, semester_no: int = 1):
    """db 原始课程名 → 渲染后信息。返回 dict(name, teacher, location, course_type)
    girl: surrey/orage/sakawa/taiyuan；选修占位符→人设课名；体育→专项；四史→自习"""
    # 选修占位符（通识/专业选修、四史）
    if ("选修" in raw_name) or raw_name.startswith("四史"):
        m = elective_content().get(raw_name)
        if m:
            name = m.get(girl) or m.get("default")
            if name == "未选" or name is None:
                return None
            if name in SISHI:
                return {"name": name, "teacher": "自习", "location": "自习（无教室）",
                        "course_type": "四史", "placeholder": raw_name}
            loc = locations().get("courses", {}).get(raw_name, "")
            return {"name": name, "teacher": "", "location": loc,
                    "course_type": "选修", "placeholder": raw_name}
    # 体育 → 专项（第1-3学期=基础专项，第4学期=提高班）
    if raw_name in PE_COURSES and girl in pe_plan():
        p = pe_plan()[girl]
        sname = p.get("sem4" if semester_no >= 4 else "sem1_3", raw_name)
        return {"name": sname, "teacher": p.get("teacher", ""),
                "location": p.get("location", ""), "course_type": "体育"}
    # 四史（渲染后名）
    if raw_name in SISHI:
        return {"name": raw_name, "teacher": "自习", "location": "自习（无教室）",
                "course_type": "四史"}
    # 普通课：老师 + 地点
    tinfo = teachers().get(raw_name, {})
    a = tinfo.get("assign", {}).get(girl, {})
    teacher = a.get("teacher", "")
    loc = locations().get("teacher_rooms", {}).get(teacher, "") or \
          locations().get("courses", {}).get(raw_name, "")
    return {"name": raw_name, "teacher": teacher, "location": loc,
            "course_type": "理论", "placeholder": None}
