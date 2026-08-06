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

MAJORS = {
    "surrey":  {"major": "电气工程", "offset": 0, "opt_offset": 1, "label": "皇家重巡"},
    "taiyuan": {"major": "电气工程", "offset": 0, "opt_offset": 3, "label": "东煌驱逐"},
    "orage":   {"major": "自动化",   "offset": 2, "opt_offset": 2, "label": "自由鸢尾驱逐"},
    "sakawa":  {"major": "测控",     "offset": 3, "opt_offset": 4, "label": "重樱轻巡"},
}
OPTIONAL = {"电磁场与波", "电路"}           # 可选课：同专业也可不同
SEM_LABEL = {1:"大一上(2022-23-1)",2:"大一下(2022-23-2)",3:"大二上(2023-24-1)",
             4:"大二下(2023-24-2)",5:"大三上(2024-25-1)",6:"大三下(2024-25-2)"}
SLOTS = [(1,"第一节①","08:00-08:45"),(2,"第一节②","08:55-09:40"),(3,"第二节①","09:50-10:45"),
         (4,"第二节②","10:55-11:40"),(5,"第三节","14:30-16:00"),(6,"第四节","16:10-17:40"),
         (7,"第五节①","19:00-19:45"),(8,"第五节②","19:55-20:40"),(9,"第五节③","20:50-21:35")]
WD = ["周一","周二","周三","周四","周五"]

def fmt_w(sw):
    wl = sorted(int(x) for x in sw.split(','))
    for lo,hi in [(1,16),(1,15),(1,13),(1,12),(1,11),(1,10),(1,8),(1,6),(1,5),(1,4),(1,3),(1,2),
                  (2,7),(4,6),(4,7),(5,8),(6,9),(6,13),(7,10),(9,14),(10,13),(12,16)]:
        if wl == list(range(lo,hi+1)): return f"{lo}-{hi}周"
    if all(x%2==1 for x in wl) and len(wl)>=3: return f"单周{wl[0]}-{wl[-1]}"
    if all(x%2==0 for x in wl) and len(wl)>=3: return f"双周{wl[0]}-{wl[-1]}"
    return ",".join(map(str,wl[:3]))+"…"

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
            # 选修占位符 → 人设课程名；未选则跳过
            if ("选修" in cname) or cname.startswith("四史"):
                real = rname(cname, girl)
                if real is None: continue
                cname, ct = real, "选修"
            # 天偏移：可选课按个人、其余核心课按专业
            if cname in OPTIONAL:
                wd = (wd + cfg["opt_offset"]) % 5
            elif ct in ("实验","实践","理论","讨论"):
                wd = (wd + cfg["offset"]) % 5
            cell[(wd,slot)].append((cname, ct, wks))
        ev_cell = defaultdict(list)
        for e in evs:
            ev_cell[(e["weekday"], e["slot_index"])].append((e["course"], e["week_no"]))
        lines = []
        for s, lab, tm in SLOTS:
            line = f"| {lab} {tm} |"
            for wd in range(5):
                parts = []
                for cname, wn in sorted(ev_cell.get((wd,s),[])):
                    parts.append(f"⚠️{cname[:8]}(W{wn})")
                for cname, ct, wks in sorted(cell.get((wd,s),[]), key=lambda x: min(int(y) for y in x[2].split(','))):
                    tg = "🔬" if ct=="实验" else ("🏭" if ct=="实践" else "")
                    parts.append(f"{cname[:9]}{tg}{fmt_w(wks)}")
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
