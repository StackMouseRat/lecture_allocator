#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
专业班级模式渲染器：4舰娘×6学期 完整课表
- 专业分组（同专业非选修核心课时间一致，不同专业不同）：
    surrey 萨里  = 电气工程（offset 0）
    taiyuan 太原 = 电气工程（offset 0，与萨里同专业）
    orage 暴风雨 = 自动化（offset +2 天轮转）
    sakawa 酒匂  = 测控（offset +3 天轮转）
- 可选课（电磁场与波、电路）：每人独立天偏移（同专业也可不同）
- 选修课：按 elective_content.json 按人设渲染，时间不偏移（本就因人而异）
- 集中事件：不偏移（全校/专业统一活动）
"""
import sqlite3, json
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).parent
DB = BASE / "db" / "virtual_time.db"
OUT = BASE / "girl_schedules"

# 体育专项：4人选的体育项目（依据pe_options.md选项制）
PE_PLAN = {
    "surrey":  {"体育（1）":"体育舞蹈","体育（2）":"体育舞蹈","体育（3）":"体育舞蹈","体育（4）":"体育舞蹈·提高",
                "teacher": "PE-舞蹈组A"},
    "orage":   {"体育（1）":"定向越野","体育（2）":"定向越野","体育（3）":"定向越野","体育（4）":"田径",
                "teacher": "PE-定向越野队"},
    "sakawa":  {"体育（1）":"瑜伽","体育（2）":"瑜伽","体育（3）":"瑜伽","体育（4）":"瑜伽·提高",
                "teacher": "PE-瑜伽组B"},
    "taiyuan": {"体育（1）":"武术","体育（2）":"武术","体育（3）":"武术","体育（4）":"武术·提高",
                "teacher": "PE-武术组C"},
}

MAJORS = {
    "surrey":  {"major": "电气工程", "offset": 0, "opt_offset": 1, "label": "皇家重巡"},
    "taiyuan": {"major": "电气工程", "offset": 0, "opt_offset": 3, "label": "东煌驱逐"},
    "orage":   {"major": "自动化",   "offset": 2, "opt_offset": 2, "label": "自由鸢尾驱逐"},
    "sakawa":  {"major": "测控",     "offset": 3, "opt_offset": 4, "label": "重樱轻巡"},
}
OPTIONAL = {"电磁场与波", "电路"}           # 可选课：同专业也可不同
NO_SCHEDULE = ("思政实践", "电子技术综合设计", "劳动教育")                  # 无课表课程：不占用/不显示于周课表
SISHI = {"中共党史", "社会主义发展史", "改革开放史", "新中国史"}   # 四史：只上5次，多余学时自行复习
SEM_LABEL = {1:"大一上(2022-23-1)",2:"大一下(2022-23-2)",3:"大二上(2023-24-1)",
             4:"大二下(2023-24-2)",5:"大三上(2024-25-1)",6:"大三下(2024-25-2)"}
SLOTS = [(1,"第一节①","08:00-08:45"),(2,"第一节②","08:55-09:40"),(3,"第二节①","09:50-10:45"),
         (4,"第二节②","10:55-11:40"),(5,"第三节","14:30-16:00"),(6,"第四节","16:10-17:40"),
         (7,"第五节①","19:00-19:45"),(8,"第五节②","19:55-20:40"),(9,"第五节③","20:50-21:35")]
WD = ["周一","周二","周三","周四","周五"]

def fmt_w(sw):
    wl = sorted(int(x) for x in sw.split(','))
    for lo,hi in [(1,16),(1,15),(1,14),(1,13),(1,12),(1,11),(1,10),(1,8),(1,6),(1,5),(1,4),(1,3),(1,2),
                  (2,7),(4,6),(4,7),(5,8),(6,9),(6,13),(7,10),(9,16),(9,14),(9,12),(10,13),(12,16),(13,16)]:
        if wl == list(range(lo,hi+1)): return f"{lo}-{hi}周"
    if all(x%2==1 for x in wl) and len(wl)>=3: return f"单周{wl[0]}-{wl[-1]}"
    if all(x%2==0 for x in wl) and len(wl)>=3: return f"双周{wl[0]}-{wl[-1]}"
    return ",".join(map(str,wl[:3]))+"…"

LOC1 = None
PE_LOC = None
def load_loc1():
    global LOC1
    if LOC1 is None:
        LOC1 = json.load(open(BASE/"data"/"locations_sem1.json", encoding="utf-8"))
    return LOC1
def load_pe_loc():
    global PE_LOC
    if PE_LOC is None:
        PE_LOC = json.load(open(BASE/"data"/"pe_plan.json", encoding="utf-8"))
    return PE_LOC

TEACHERS = None
def load_teachers():
    global TEACHERS
    if TEACHERS is None:
        TEACHERS = json.load(open(BASE/"data"/"teachers.json", encoding="utf-8"))
    return TEACHERS

def load_elective():
    d = json.load(open(BASE/"data"/"elective_content.json", encoding="utf-8"))
    def name(ph, girl):
        m = d.get(ph)
        if not m: return ph
        n = m.get(girl) or m.get("default")
        return n if n != "未选" else None
    return name

def render(girl):
    cfg = MAJORS[girl]
    rname = load_elective()
    conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row
    for sem in range(1,7):
        rows = conn.execute("SELECT * FROM virtual_course_schedule WHERE semester_no=? ORDER BY weekday, slot_index",(sem,)).fetchall()
        evs = conn.execute("SELECT * FROM semester_events WHERE semester_no=?",(sem,)).fetchall()
        cell = defaultdict(list)   # (wd,slot) -> 显示条目
        for r in rows:
            cname, ct = r["course"], r["course_type"]
            wd, slot, wks = r["weekday"], r["slot_index"], r["session_weeks"]
            loc = ""
            # 选修占位符 → 人设课程名；未选则跳过
            if ("选修" in cname) or cname.startswith("四史"):
                ph = cname
                real = rname(cname, girl)
                if real is None: continue
                cname, ct = real, "选修"
                loc = load_loc1().get("courses", {}).get(ph, "")
            # 四史：只上5次课（多余学时自行复习），仅显示第1-5周
            if cname in SISHI:
                wks = ",".join(map(str, range(1, 6)))   # 5次
                ct = "四史"
                cell[(wd, slot)].append((cname, ct, wks, "自习", "自习（无教室）"))
                continue
            # 体育课 → 具体专项（按人设），时间不变（同公共课周三下午）
            if cname in PE_PLAN.get(girl, {}):
                pname = PE_PLAN[girl][cname]
                tname = PE_PLAN[girl]["teacher"]
                ct = "体育"
                cname = pname
                tinfo = None  # 体育专项时间固定，不参与天偏移
                loc = load_pe_loc().get(girl, {}).get("location", "")
            else:
                tname = ""
            # 天偏移：按老师分配（同老师同偏移→时间必同；不同老师可不同）
            tinfo = load_teachers().get(cname)
            if tinfo and not tname:
                a = tinfo["assign"].get(girl)
                if a:
                    wd = (wd + a["offset"]) % 5
                    tname = a["teacher"]
            if not loc:
                # 老师级教室优先（不同老师教室必不同），再课程级
                loc = load_loc1().get("teacher_rooms", {}).get(tname, "") or load_loc1().get("courses", {}).get(cname, "")
            cell[(wd,slot)].append((cname, ct, wks, tname, loc))
        ev_cell = defaultdict(list)
        for e in evs:
            if any(k in e["course"] for k in NO_SCHEDULE):   # 无课表课程不显示
                continue
            ev_cell[(e["weekday"], e["slot_index"])].append((e["course"], e["week_no"]))
        lines = []
        for s, lab, tm in SLOTS:
            line = f"| {lab} {tm} |"
            for wd in range(5):
                parts = []
                for cname, wn in sorted(ev_cell.get((wd,s),[])):
                    parts.append(f"⚠️{cname[:8]}(W{wn})")
                for cname, ct, wks, tname, loc in sorted(cell.get((wd,s),[]), key=lambda x: min(int(y) for y in x[2].split(','))):
                    if ct == "四史":
                        parts.append(f"{cname}（5次·自习）{fmt_w(wks)}")
                        continue
                    tg = "🔬" if ct=="实验" else ("🏭" if ct=="实践" else "")
                    loc_str = f"·{loc}" if loc else ""
                    parts.append(f"{cname[:8]}{tg}{fmt_w(wks)}{('·'+tname) if tname else ''}{loc_str}")
                line += (" "+"<br>".join(parts)+" |") if parts else " — |"
            lines.append(line)
        out = OUT / f"{girl}_sem{sem}.md"
        with open(out,"w",encoding="utf-8") as f:
            f.write(f"# {girl.capitalize()}（{cfg['label']} · {cfg['major']}专业） · {SEM_LABEL[sem]}\n\n")
            f.write(f"> **第{sem}学期 完整固定课表** · 专业班级：{cfg['major']}（核心课按专业同步）\n\n")
            f.write("| 时段 | 周一 | 周二 | 周三 | 周四 | 周五 |\n|---|---|---|---|---|---|\n")
            f.write("\n".join(lines)+"\n")
    conn.close()

if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for g in MAJORS: render(g)
    print("✅ 24份专业班级课表已生成 → girl_schedules/")
