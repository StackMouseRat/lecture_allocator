#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一查询入口（只读 CLI）—— 外界访问系统数据的唯一通道

设计原则：
- 只读：不修改 db / data / 任何文件；查询不产生副作用（now --at 传入 dt 而非 set 虚拟时间）
- 口径统一：渲染名/老师/地点/授课进度一律复用 render_utils（resolve/syllabus_topic），
  虚拟时间复用 virtual_time.VirtualClock；禁止在本模块重复实现换算
- 输出规范：默认人类可读文本；--json 输出结构化 JSON（供程序消费）
- 退出码：0=成功 2=未找到 3=数据异常 4=参数错误

用法：python3 query.py <子命令> [选项]
子命令：timetable / course / syllabus / now / teacher / room / check / summary / girl / help
详见 docs/CLI规范.md
"""
import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent
DB = BASE / "db" / "virtual_time.db"
GIRLS = ["surrey", "orage", "sakawa", "taiyuan"]
GIRL_CN = {"surrey": "萨里", "orage": "暴风雨", "sakawa": "酒匂", "taiyuan": "太原"}
WD_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
SLOTS = {1: ("第一节①", "08:00", "08:45"), 2: ("第一节②", "08:55", "09:40"),
         3: ("第二节①", "10:00", "10:45"), 4: ("第二节②", "10:55", "11:40"),
         5: ("第三节", "14:30", "16:00"), 6: ("第四节", "16:10", "17:40"),
         7: ("第五节①", "19:00", "19:45"), 8: ("第五节②", "19:55", "20:40"),
         9: ("第五节③", "20:50", "21:35"), 10: ("第五节④", "21:35", "22:20")}


def _conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def _load(path):
    return json.load(open(BASE / path, encoding="utf-8"))


def _fmt_weeks(sw):
    if not sw:
        return ""
    wl = sorted(int(x) for x in sw.split(","))
    return f"{wl[0]}-{wl[-1]}周" if len(wl) > 1 else f"{wl[0]}周"


# ======================================================================
# 数据访问（统一口径）
# ======================================================================
def rows_for_sem(sem, girl=None):
    """返回 (weekday, slot, course_raw, weeks_set, teacher, location, ctype)
    S4/5 走 girl_course_schedule（per-girl，老师/地点入库）；S1-3/6 走共享行 + resolve 渲染层"""
    import render_utils as ru
    conn = _conn()
    out = []
    if sem in (4, 5):
        g = girl or "surrey"
        for r in conn.execute(
                "SELECT course, weekday, slot_index, session_weeks, teacher, location, course_type "
                "FROM girl_course_schedule WHERE semester_no=? AND girl=? ORDER BY weekday, slot_index",
                (sem, g)):
            weeks = {int(x) for x in r["session_weeks"].split(",") if x.strip()}
            out.append((r["weekday"], r["slot_index"], r["course"], weeks,
                        r["teacher"] or "", r["location"] or "", r["course_type"]))
    else:
        g = girl or "surrey"
        for r in conn.execute(
                "SELECT course, weekday, slot_index, session_weeks, course_type "
                "FROM virtual_course_schedule WHERE semester_no=? ORDER BY weekday, slot_index", (sem,)):
            weeks = {int(x) for x in r["session_weeks"].split(",") if x.strip()}
            resolved = ru.resolve(g, r["course"], sem)
            if resolved is None:
                continue
            out.append((r["weekday"], r["slot_index"], resolved["name"], weeks,
                        resolved.get("teacher", ""), resolved.get("location", ""), resolved.get("course_type", "")))
    conn.close()
    return out


def term_of(sem):
    conn = _conn()
    r = conn.execute("SELECT term_code, start_date FROM terms WHERE semester_no=?", (sem,)).fetchone()
    conn.close()
    return dict(r) if r else None


def events_of(sem):
    conn = _conn()
    rows = conn.execute(
        "SELECT course, week_no, weekday, slot_index, note FROM semester_events "
        "WHERE semester_no=? ORDER BY week_no, weekday, slot_index", (sem,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ======================================================================
# 子命令实现
# ======================================================================
def cmd_timetable(a):
    """课表查询：--sem 必填，--girl/--week 可选"""
    sem = a.sem
    girl = a.girl or "surrey"
    if sem is None or sem not in range(1, 7):
        print("timetable 需要 --sem 1-6", file=sys.stderr)
        return 4
    rows = rows_for_sem(sem, girl)
    events = [e for e in events_of(sem) if a.week is None or e["week_no"] == a.week]
    cells = {}
    for wd, slot, cname, weeks, teacher, loc, ct in rows:
        if a.week is not None and a.week not in weeks:
            continue
        cells.setdefault((wd, slot), []).append(
            {"course": cname, "weeks": sorted(weeks), "teacher": teacher, "location": loc, "type": ct})
    for e in events:
        if e["slot_index"] == 0:   # 哨兵事件（线上课/集中设计）不占格
            continue
        cells.setdefault((e["weekday"], e["slot_index"]), []).append(
            {"course": e["course"], "weeks": [e["week_no"]], "teacher": "", "location": "", "type": "事件"})
    if a.json:
        print(json.dumps({"semester": sem, "girl": girl, "term": term_of(sem),
                          "cells": {f"{wd},{slot}": v for (wd, slot), v in sorted(cells.items())}},
                         ensure_ascii=False, indent=1))
        return 0
    print(f"# 第{sem}学期 课表 · {GIRL_CN[girl]}" + (f" · 第{a.week}周" if a.week else ""))
    print(f"| 时段 | 周一 | 周二 | 周三 | 周四 | 周五 |")
    print(f"|---|---|---|---|---|---|")
    for slot in range(1, 11):
        lab, st, et = SLOTS[slot]
        line = [f"| {lab} {st}-{et} |"]
        for wd in range(5):
            parts = []
            for item in sorted(cells.get((wd, slot), []), key=lambda x: min(x["weeks"])):
                wstr = _fmt_weeks(",".join(map(str, item["weeks"])))
                parts.append(f"{item['course']}{wstr}{'·'+item['teacher'] if item['teacher'] else ''}"
                             f"{'·'+item['location'] if item['location'] else ''}")
            line.append((" " + "<br>".join(parts) + " |") if parts else " — |")
        print("".join(line))
    return 0


def cmd_course(a):
    """课程信息：--name 必填（支持渲染名或占位符）；可选 --sem"""
    name = a.name
    if not name:
        print("course 需要 --name", file=sys.stderr)
        return 4
    conn = _conn()
    plan = _load("data/plan_courses.json").get(name, {})
    teacher_map = _load("data/teachers.json").get(name, {}).get("assign", {})
    sem_rows = {}
    for sem in range(1, 7):
        if sem in (4, 5):
            rows = conn.execute(
                "SELECT girl, weekday, slot_index, session_weeks, teacher, location FROM girl_course_schedule "
                "WHERE semester_no=? AND course=? ORDER BY weekday, slot_index", (sem, name)).fetchall()
            if rows:
                sem_rows[sem] = [dict(r) for r in rows]
        else:
            rows = conn.execute(
                "SELECT weekday, slot_index, session_weeks FROM virtual_course_schedule "
                "WHERE semester_no=? AND course=?", (sem, name)).fetchall()
            if rows:
                sem_rows[sem] = [dict(r) for r in rows]
    syl = {}
    for sem in range(1, 7):
        f = BASE / "data" / f"syllabus_sem{sem}.json"
        if f.exists():
            d = json.load(open(f, encoding="utf-8"))
            if name in d:
                syl[sem] = {"节数": len(d[name]["rows"]), "每次学时": d[name].get("hps", 2)}
    conn.close()
    if not plan and not teacher_map and not sem_rows and not syl:
        print(f"未找到课程: {name}", file=sys.stderr)
        return 2
    out = {"course": name, "plan": plan, "teachers": teacher_map,
           "schedules": sem_rows, "syllabus": syl}
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0
    print(f"# {name}")
    print(f"  培养方案: {json.dumps(plan, ensure_ascii=False) if plan else '（未在 plan_courses 中）'}")
    if teacher_map:
        print("  老师: " + "；".join(f"{GIRL_CN[g]}={v.get('teacher','')}" for g, v in teacher_map.items()))
    for sem, rows in sem_rows.items():
        print(f"  第{sem}学期: {len(rows)} 行")
        for r in rows:
            print(f"    {WD_CN[r['weekday']]} slot{r['slot_index']} {_fmt_weeks(r['session_weeks'])}"
                  f"{' · '+r.get('teacher','') if r.get('teacher') else ''}"
                  f"{' · '+r.get('location','') if r.get('location') else ''}")
    for sem, info in syl.items():
        print(f"  第{sem}学期授课方案: {info['节数']}节 × {info['每次学时']}学时")
    return 0


def cmd_syllabus(a):
    """授课进度：--sem 必填；--course 单门；--week 过滤"""
    if a.sem is None:
        print("syllabus 需要 --sem", file=sys.stderr)
        return 4
    f = BASE / "data" / f"syllabus_sem{a.sem}.json"
    if not f.exists():
        print(f"第{a.sem}学期无授课方案文件", file=sys.stderr)
        return 3
    d = json.load(open(f, encoding="utf-8"))
    if a.course and a.course not in d:
        print(f"未找到课程: {a.course}", file=sys.stderr)
        return 2
    keys = [a.course] if a.course else list(d.keys())
    if a.json:
        out = {k: {"rows": [r for r in d[k]["rows"] if a.week is None or r["week"] == a.week],
                   "hps": d[k].get("hps", 2)} for k in keys}
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0
    for k in keys:
        rows = d[k]["rows"]
        print(f"# {k}（{len(rows)}节 × {d[k].get('hps',2)}学时）")
        for r in rows:
            if a.week is None or r["week"] == a.week:
                print(f"  W{r['week']:>2}·{r['session']}  {r['topic']}")
    return 0


def cmd_now(a):
    """虚拟时间当前课：--girl 可选（默认 surrey）；--at 'YYYY-MM-DD HH:MM' 指定时间（不污染虚拟时钟）"""
    from virtual_time import VirtualClock
    vc = VirtualClock()
    girl = a.girl or "surrey"
    if a.at:
        dt = datetime.strptime(a.at, "%Y-%m-%d %H:%M")
        info = vc.current_course(dt=dt, girl=girl)
    else:
        info = vc.current_course(girl=girl)
    if a.json:
        print(json.dumps(info, ensure_ascii=False, indent=1))
        return 0
    print(f"# 虚拟时间 {vc.now().strftime('%Y-%m-%d %H:%M')} · {GIRL_CN[girl]}")
    for k, v in info.items():
        if v is None:
            v = ""
        print(f"  {k}: {v}")
    return 0


def cmd_teacher(a):
    """老师课程安排：--id 必填（如 T800/E1100/P19a）；可选 --sem"""
    tid = a.id
    if not tid:
        print("teacher 需要 --id", file=sys.stderr)
        return 4
    tmap = _load("data/teachers.json")
    assigned = {}
    for cname, info in tmap.items():
        for g, av in info.get("assign", {}).items():
            if av.get("teacher") == tid:
                assigned.setdefault(cname, []).append(g)
    conn = _conn()
    sem_rows = {}
    for sem in range(1, 7):
        if sem in (4, 5):
            rows = conn.execute(
                "SELECT course, girl, weekday, slot_index, session_weeks, location FROM girl_course_schedule "
                "WHERE semester_no=? AND teacher=? ORDER BY weekday, slot_index", (sem, tid)).fetchall()
            if rows:
                sem_rows[sem] = [dict(r) for r in rows]
        else:
            rows = conn.execute(
                "SELECT course, weekday, slot_index, session_weeks FROM virtual_course_schedule "
                "WHERE semester_no=? ORDER BY weekday, slot_index", (sem,)).fetchall()
            hit = []
            for r in rows:
                if tid in {av.get("teacher") for av in tmap.get(r["course"], {}).get("assign", {}).values()}:
                    hit.append(dict(r))
            if hit:
                sem_rows[sem] = hit
    conn.close()
    out = {"teacher": tid, "courses": assigned, "schedules": sem_rows}
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0
    print(f"# 老师 {tid}")
    if assigned:
        print("  授课课程: " + "、".join(f"{c}({'/'.join(GIRL_CN[g] for g in gs)})" for c, gs in assigned.items()))
    for sem, rows in sem_rows.items():
        print(f"  第{sem}学期: {len(rows)} 行")
        for r in rows:
            print(f"    {WD_CN[r['weekday']]} slot{r['slot_index']} {r['course']} {_fmt_weeks(r['session_weeks'])}")
    return 0


def cmd_room(a):
    """教室占用：--name 必填（如 '复临舍202(中)' / '中楼102(中)' / '电气院实验室1'）；可选 --sem"""
    room = a.name
    if not room:
        print("room 需要 --name", file=sys.stderr)
        return 4
    conn = _conn()
    occ = {}
    for sem in range(1, 7):
        if sem in (4, 5):
            rows = conn.execute(
                "SELECT course, girl, weekday, slot_index, session_weeks FROM girl_course_schedule "
                "WHERE semester_no=? AND location=? ORDER BY weekday, slot_index", (sem, room)).fetchall()
            if rows:
                occ[sem] = [dict(r) for r in rows]
        else:
            import render_utils as ru
            rows = conn.execute(
                "SELECT course, weekday, slot_index, session_weeks FROM virtual_course_schedule "
                "WHERE semester_no=? ORDER BY weekday, slot_index", (sem,)).fetchall()
            hit = []
            for r in rows:
                for g in GIRLS:
                    res = ru.resolve(g, r["course"], sem)
                    if res and res.get("location") == room:
                        hit.append(dict(r))
                        break
            if hit:
                occ[sem] = hit
    conn.close()
    out = {"room": room, "occupancy": occ}
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0
    print(f"# 教室 {room}")
    found = False
    for sem, rows in occ.items():
        print(f"  第{sem}学期: {len(rows)} 行")
        for r in rows:
            found = True
            print(f"    {WD_CN[r['weekday']]} slot{r['slot_index']} {r['course']} {_fmt_weeks(r['session_weeks'])}")
    if not found:
        print("  （该教室无排课记录）")
    return 0


def _run_script(script, args=None):
    """以子进程运行既有校验脚本（隔离 sys.argv/全局），返回末行结果"""
    import subprocess
    r = subprocess.run([sys.executable, str(BASE / script)] + (args or []),
                       capture_output=True, text=True)
    out = (r.stdout or "").strip().splitlines()
    return out[-1] if out else f"❌ {script} 无输出(rc={r.returncode})"


def cmd_check(a):
    """全量校验：调用既有 check_* 脚本（复用权威口径），输出汇总"""
    results = {
        "conflicts": _run_script("check_conflicts.py"),
        "render": _run_script("check_render.py"),
        "locations": _run_script("check_locations.py"),
        "syllabus": _run_script("check_syllabus.py", ["1", "2", "4", "5", "6"]),
        "data": _run_script("check_data.py"),
    }
    if a.json:
        print(json.dumps(results, ensure_ascii=False, indent=1))
        return 0
    print("# 全量校验")
    for k, v in results.items():
        print(f"  {k}: {v}")
    return 0


def cmd_summary(a):
    """学期总览：学分/门数/课次/事件（可选 --sem 单学期）
    学分统一取培养方案 plan_courses.json（唯一权威，避免 per-girl 表无 credits 列）"""
    conn = _conn()
    plan = _load("data/plan_courses.json")
    out = {}
    for sem in range(1, 7):
        if a.sem and sem != a.sem:
            continue
        if sem in (4, 5):
            # per-girl 表无 credits 列 → 学分取培养方案 plan_courses
            rows = conn.execute(
                "SELECT DISTINCT course FROM girl_course_schedule WHERE semester_no=? AND girl='surrey'", (sem,)).fetchall()
            ev = conn.execute("SELECT COUNT(*) c FROM semester_events WHERE semester_no=?", (sem,)).fetchone()["c"]
            n_rows = conn.execute("SELECT COUNT(*) c FROM girl_course_schedule WHERE semester_no=? AND girl='surrey'", (sem,)).fetchone()["c"]
            cred = sum((plan.get(r["course"], {}).get("credits") or 0) for r in rows)
        else:
            # 共享行带 credits（build 权威写入，含占位符学分）
            rows = conn.execute(
                "SELECT DISTINCT course, credits FROM virtual_course_schedule WHERE semester_no=?", (sem,)).fetchall()
            ev = conn.execute("SELECT COUNT(*) c FROM semester_events WHERE semester_no=?", (sem,)).fetchone()["c"]
            n_rows = conn.execute("SELECT COUNT(*) c FROM virtual_course_schedule WHERE semester_no=?", (sem,)).fetchone()["c"]
            cred = sum(r["credits"] or 0 for r in rows)
        out[sem] = {"门数": len(rows), "学分": cred, "课次行数": n_rows, "事件": ev}
    conn.close()
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0
    print("# 学期总览")
    for sem, v in out.items():
        print(f"  第{sem}学期: {v['门数']}门/{v['学分']}学分/{v['课次行数']}行/{v['事件']}事件")
    return 0


def _effective_slot(t):
    """虚拟时刻所处的最近已开始 slot（课间/进行中均取已开始的最大 slot）"""
    hm = t.strftime("%H:%M")
    for s in range(10, 0, -1):
        if hm >= SLOTS[s][1]:
            return s
    return 0


def cmd_progress(a):
    """课程进度：某虚拟时间下某门课的 已学/当前/未学 清单
    用法：progress --course X [--at 'YYYY-MM-DD HH:MM'] [--girl G] [--sem N]
    口径：当前节=VirtualClock.current_course 权威（syllabus 字段）；
         已学/未学=按该课 syllabus 行序（week×session 时间线）相对当前时刻分割"""
    from virtual_time import VirtualClock
    course = a.course
    if not course:
        print("progress 需要 --course", file=sys.stderr)
        return 4
    vc = VirtualClock()
    dt = datetime.strptime(a.at, "%Y-%m-%d %H:%M") if a.at else vc.now()
    girl = a.girl or "surrey"
    info = vc.current_course(dt=dt, girl=girl)
    sem = a.sem or info.get("semester_no")
    if sem is None or sem == -1:
        print(f"该时刻 {dt} 非教学学期（假期/小学期）", file=sys.stderr)
        return 3
    week = info.get("week_no")
    if week is None or week > 16:
        print(f"该时刻为第{sem}学期非教学周（week={week}）", file=sys.stderr)
        return 3
    f = BASE / "data" / f"syllabus_sem{sem}.json"
    if not f.exists():
        print(f"第{sem}学期无授课方案文件", file=sys.stderr)
        return 3
    d = json.load(open(f, encoding="utf-8"))
    if course not in d:
        print(f"第{sem}学期无该课授课方案: {course}", file=sys.stderr)
        return 2
    rows = d[course]["rows"]
    # 该课周次→天分布（db 权威，用于非在课时的 key 比较）
    conn = _conn()
    if sem in (4, 5):
        q = conn.execute(
            "SELECT weekday, slot_index, session_weeks FROM girl_course_schedule "
            "WHERE semester_no=? AND course=? AND girl=?", (sem, course, girl)).fetchall()
    else:
        q = conn.execute(
            "SELECT weekday, slot_index, session_weeks FROM virtual_course_schedule "
            "WHERE semester_no=? AND course=?", (sem, course)).fetchall()
    conn.close()
    wmap = {}
    for r in q:
        for w in [int(x) for x in r["session_weeks"].split(",") if x.strip()]:
            wmap.setdefault(w, {}).setdefault(r["weekday"], r["slot_index"])
    wlist = {w: sorted((wd, s) for wd, s in wd_s.items()) for w, wd_s in wmap.items()}

    on_course = info.get("status") == "in_class" and info.get("course") == course
    cur_topic = info.get("syllabus") if on_course else None
    learned, current, pending = [], [], []
    if on_course and cur_topic:
        # 权威锚点：正在上的这节课
        cur_row = next((r for r in rows if r["topic"] == cur_topic), None)
        if cur_row is not None:
            idx = rows.index(cur_row)
            learned, current, pending = rows[:idx], [cur_row], rows[idx + 1:]
    if not current:
        # 非在课：按该课时间线 (week, weekday, slot) 相对当前定位
        cur_key = (week, dt.weekday(), _effective_slot(dt))
        for r in rows:
            lst = wlist.get(r["week"], [])
            wd, slot = (lst[r["session"] - 1] if r["session"] - 1 < len(lst) else (0, 0))
            if (r["week"], wd, slot) < cur_key:
                learned.append(r)
            else:
                pending.append(r)
    out = {"course": course, "girl": girl, "semester": sem, "week": week,
           "time": dt.strftime("%Y-%m-%d %H:%M"), "on_course": on_course,
           "total": len(rows), "learned": learned, "current": current, "pending": pending}
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0
    print(f"# 课程进度 · {course}（{GIRL_CN[girl]}）@ {out['time']}（第{sem}学期 第{week}周）")
    print(f"  状态: {'🕐 正在上课' if on_course else '未在课上'} ｜ 总 {out['total']} 节 ｜ "
          f"已学 {len(learned)} ｜ 当前 {len(current)} ｜ 未学 {len(pending)}")
    if current:
        print("  ▶ 当前:")
        for r in current:
            print(f"      W{r['week']}·{r['session']}  {r['topic']}")
    if learned:
        print("  ✔ 已学:")
        for r in learned:
            print(f"      W{r['week']}·{r['session']}  {r['topic']}")
    if pending:
        print("  ○ 未学:")
        for r in pending[:12]:
            print(f"      W{r['week']}·{r['session']}  {r['topic']}")
        if len(pending) > 12:
            print(f"      … 其余 {len(pending) - 12} 节")
    return 0


def cmd_girl(a):
    """女孩档案：专业/选修/个人调度/课表文件"""
    girl = a.girl or "surrey"
    from render_major import MAJORS, PE_PLAN
    ec = _load("data/elective_content.json")
    pr = _load("data/personal_rules.json").get(girl, {})
    cfg = MAJORS.get(girl, {})
    out = {"girl": girl, "name": GIRL_CN[girl], "major": cfg.get("major"), "label": cfg.get("label"),
           "pe": PE_PLAN.get(girl), "electives": {k: v.get(girl) for k, v in ec.items() if v.get(girl)},
           "personal": pr, "schedules": [f"girl_schedules/{girl}_sem{s}.md" for s in range(1, 7)]}
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0
    print(f"# {GIRL_CN[girl]}（{girl}）")
    print(f"  专业: {cfg.get('major')}（S5 起全班同专业电气）")
    print(f"  体育: {json.dumps(PE_PLAN.get(girl), ensure_ascii=False)}")
    print("  专业选修: " + "、".join(v for v in out["electives"].values() if v and v != "未选"))
    print("  个人调度: " + json.dumps(pr, ensure_ascii=False))
    print("  课表文件: " + "、".join(out["schedules"]))
    return 0


def cmd_help(a):
    print(__doc__)
    return 0


COMMANDS = {
    "timetable": (cmd_timetable, "课表查询"),
    "course": (cmd_course, "课程信息"),
    "syllabus": (cmd_syllabus, "授课进度"),
    "now": (cmd_now, "虚拟时间当前课"),
    "teacher": (cmd_teacher, "老师课程安排"),
    "room": (cmd_room, "教室占用"),
    "check": (cmd_check, "全量校验"),
    "summary": (cmd_summary, "学期总览"),
    "progress": (cmd_progress, "课程进度（已学/当前/未学）"),
    "girl": (cmd_girl, "女孩档案"),
    "help": (cmd_help, "帮助"),
}


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    if cmd not in COMMANDS:
        print(f"未知子命令: {cmd}\n可用: {', '.join(COMMANDS)}", file=sys.stderr)
        return 4
    p = argparse.ArgumentParser(prog=f"query.py {cmd}", description=COMMANDS[cmd][1])
    p.add_argument("--sem", type=int, default=None)
    p.add_argument("--girl", choices=GIRLS, default=None)
    p.add_argument("--week", type=int, default=None)
    p.add_argument("--course", default=None)
    p.add_argument("--name", default=None)
    p.add_argument("--id", default=None)
    p.add_argument("--at", default=None)
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv[1:])
    try:
        return COMMANDS[cmd][0](a)
    except (ValueError, KeyError) as e:
        print(f"查询失败: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
