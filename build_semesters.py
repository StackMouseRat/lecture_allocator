#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多学期排课构建器 —— 为第1~6学期排课（小学期不排），每学期随机抽一周验证
学时取自《电气工程及其自动化本科专业指导性教学计划》(plan_layout.txt) + 成绩单选课。
规则：晚间实验3节连上(电路/电机/大物/电力电子仅晚间，大物3学时其余4学时)；
     体育课后一节留空；周二下午保留(仅军事理论/形势政策兜底)；同课相邻天约束。
用法：
    python3 build_semesters.py                 # 排全部学期
    python3 build_semesters.py --all            # 同上
    python3 build_semesters.py 3                # 只排第3学期
    python3 build_semesters.py --verify 2       # 排完并抽查某学期随机一周
"""
import sys
import json
import random
from pathlib import Path

BASE = Path(__file__).parent
DATA = BASE / "data"

# 通用字段缩写：th=理论 ex=实验 pe=体育 ds=讨论
def T(name, credits, hours, **kw):     # 理论课
    d = {"name": name, "credits": credits, "category": "必修", "type": "理论",
         "total_hours": hours, "prefer": ["上午"]}
    d.update(kw)
    return d

def E(name, credits, hours, hps=4, **kw):   # 实验课（下午优先，晚间兜底）
    d = {"name": name, "credits": credits, "category": "必修", "type": "实验",
         "total_hours": hours, "hours_per_session": hps, "evening_only": False,
         "prefer": ["下午"]}
    d.update(kw)
    return d

def PE(name, credits=1.0):              # 体育（固定第三节+课后留空）
    return {"name": name, "credits": credits, "category": "必修", "type": "体育",
            "total_hours": 36, "fixed_slot": 5, "block_next": True,
            "weekly_fixed": True, "prefer": ["下午"]}

def EV(name, credits, half="first", weeks="9-16", hps=2):  # 讨论/讲座课
    return {"name": name, "credits": credits, "category": "必修", "type": "讨论",
            "total_hours": 16, "sessions_per_week": 1, "hours_per_session": hps,
            "weeks": weeks, "seminar": 1, "prefer": ["下午"], "intensive_half": half}

def SX(name, credits, day=None, slot=None):   # 形势与政策：课程（非事件），相邻周W3+W4
    d = {"name": name, "credits": credits, "category": "必修", "type": "讲座",
         "total_hours": 4, "weeks": "3-4", "sessions_per_week": 1,
         "hours_per_session": 2, "prefer": ["下午"]}
    if day is not None: d["fx_day"] = day     # 指定天（如避让实训）
    if slot is not None: d["fx_slot"] = slot  # 指定槽位
    return d

# 培养方案大班授课学时（用于标准档判断：总学时含讨论/实践，大班学时才是排课主体）
LECTURE_MAP = {
    "高等数学A（1）": 80, "高等数学A（2）": 80, "计算与人工智能概论": 48, "电路": 64,
    "大学英语A（1）": 64, "大学英语A（2）": 64, "线性代数A": 40, "概率论与数理统计A": 40,
    "普通物理A（1）": 48, "普通物理A（2）": 48, "离散数学": 32, "复变函数与积分变换": 32,
    "毛泽东思想和中国特色社会主义理论体系概论": 48, "思想道德与法治": 42,
    "中国近现代史纲要": 42, "马克思主义基本原理": 42,
    "习近平新时代中国特色社会主义思想概论": 28, "电磁场与波": 42,
    "模拟电子技术基础": 42, "数字电子技术基础": 42, "微机原理及其应用": 42,
    "自动控制原理": 38, "信号与系统": 38, "传感与检测技术": 36,
    "电力电子技术基础": 36, "电机学（上）": 32, "电机学（下）": 48,
    "电力系统基础（上）": 34, "电力系统基础（下）": 34,
    "高电压技术基础": 32, "电机控制技术": 32, "工程制图": 28, "军事理论": 36,
    "导师课程": 16, "电气工程新技术导论": 32, "新能源发电技术": 32,
    "电力系统过电压": 32, "高电压绝缘": 32, "C++面向对象程序设计": 32,
    "软件技术基础": 32, "Python语言程序设计": 32, "土木工程防灾概论": 32,
    "社会学导论": 32, "大学生心理健康教育": 16, "新中国史": 16,
}

def _patch_lecture(courses):
    for c in courses:
        if c["name"] in LECTURE_MAP and "lecture" not in c:
            c["lecture"] = LECTURE_MAP[c["name"]]
    return courses

SEMESTERS = {
    # ================= 第1学期 2022-2023-1 =================
    1: {
        "term": "第1学期（2022-2023学年第一学期）", "term_code": "2022-23-1",
        "term_start": "2022-09-05", "intensive_note": "密集周=前半(1-8周)",
        "courses": [
            PE("体育（1）"),
            T("大学英语A（1）", 4.0, 64),
            T("思想道德与法治", 3.0, 54),
            T("工程制图", 2.0, 28, prefer=["下午"], sessions_per_week=1, hours_per_session=2, weeks="1-14"),   # 大班授课28学时=14周×2
            E("工程制图上机", 0.5, 8, hps=2, weeks="9,10,11,12", evening_only=True,
              desc="小班讨论实际为上机：8学时=晚间4次×2学时（W9-12），前进楼"),
            T("高等数学A（1）", 5.0, 96),
            T("通识选修·晚间①", 2.0, 32, lecture=32, category="普通选修", prefer=["晚上"], elective_slot="eve1"),
            T("通识选修·晚间②", 2.0, 32, lecture=32, category="普通选修", prefer=["晚上"], elective_slot="eve2"),
            T("通识选修·晚间③", 1.0, 16, lecture=16, category="普通选修", prefer=["晚上"], sessions_per_week=1,
              hours_per_session=2, weeks="1-8", elective_slot="eve3"),
            T("通识选修·晚间④", 1.0, 16, lecture=16, category="普通选修", prefer=["晚上"], sessions_per_week=1,
              hours_per_session=2, weeks="9-16", elective_slot="eve4"),
            T("四史·①", 1.0, 15, lecture=15, category="四史", type="四史", prefer=["晚上"],
              sessions_per_week=1, hours_per_session=3, weeks="1-5", elective_slot="hist1"),
            T("四史·②", 1.0, 15, lecture=15, category="四史", type="四史", prefer=["晚上"],
              sessions_per_week=1, hours_per_session=3, weeks="1-5", elective_slot="hist2"),
            SX("形势与政策(1)", 0.25),
        ],
        "semester_events": [
            {"name": "军事技能（集中军训）", "credits": 2.0, "category": "必修", "type": "实践",
             "note": "开学集中军训，全天×10天（第1-2周）",
             "events": [{"week": ww, "weekday": wd, "duration": "full", "hours": 8}
                        for ww in [1, 2] for wd in range(5)]},
            # 形势与政策(1) 已作为课程定义（见 courses）,
        ],
    },
    # ================= 第2学期 2022-2023-2 =================
    2: {
        "term": "第2学期（2022-2023学年第二学期）", "term_code": "2022-23-2",
        "term_start": "2023-02-20",
        "courses": [
            PE("体育（2）"),
            T("大学英语A（2）", 4.0, 64),
            T("中国近现代史纲要", 3.0, 54),
            T("计算与人工智能概论", 4.0, 80),
            T("线性代数A", 3.0, 48, lecture=48),
            T("普通物理A（1）", 3.0, 64),
            T("高等数学A（2）", 5.0, 96),
            T("导师课程", 1.0, 16, sessions_per_week=1, hours_per_session=2, weeks="9-16",
              prefer=["下午"]),
            E("普通物理实验A（1）", 1.0, 24, hps=3, desc="大物实验，32学时含8虚拟"),
            E("计算与人工智能概论上机", 1.0, 32, hps=4, evening_only=True,
              desc="培养方案80学时=48大班+32上机；上机8次×4学时隔周×16周，晚间，前进楼"),
            SX("形势与政策(2)", 0.25),
        ],
        "semester_events": [],  # 形势与政策(2) 已作为课程定义
    },
    # ================= 第3学期 2023-2024-1 =================
    3: {
        "term": "第3学期（2023-2024学年第一学期）", "term_code": "2023-24-1",
        "term_start": "2023-09-04",
        "courses": [
            PE("体育（3）"),
            T("电路", 4.0, 64),
            E("电路实验", 1.0, 32, hps=4),
            T("复变函数与积分变换", 2.0, 32),
            T("离散数学", 2.0, 32),
            T("通识选修·晚间⑤", 2.0, 32, lecture=32, category="普通选修", prefer=["晚上"], elective_slot="eve5"),
            T("通识选修·晚间⑥", 2.0, 32, lecture=32, category="普通选修", prefer=["晚上"], elective_slot="eve6"),
            T("毛泽东思想和中国特色社会主义理论体系概论", 3.0, 48, intensive_half="first"),
            T("概率论与数理统计A", 3.0, 48, intensive_half="second", other=8),
            T("普通物理A（2）", 3.0, 48, intensive_half="first"),
            EV("普通物理A（2）·讨论", 0.0, half="second", weeks="9-16"),
            E("普通物理实验A（2）", 1.0, 32, hps=3, virtual_hours=8,
              desc="总32学时含8学时虚拟（不排课）；实际24学时=8次×3学时"),
            T("军事理论", 1.0, 36, type="讲座", prefer=["下午"]),
            SX("形势与政策(3)", 0.25),
        ],
        "semester_events": [],  # 形势与政策(3) 已作为课程定义
    },
    # ================= 第4学期 2023-2024-2 =================
    4: {
        "term": "第4学期（2023-2024学年第二学期）", "term_code": "2023-24-2",
        "term_start": "2024-02-26",
        "courses": [
            PE("体育（4）"),
            T("电磁场与波", 3.0, 48, lecture=48),
            T("模拟电子技术基础", 3.0, 48, lecture=48),
            T("数字电子技术基础", 3.0, 48, lecture=48),
            T("马克思主义基本原理", 3.0, 54),
            T("习近平新时代中国特色社会主义思想概论", 2.0, 36, weekly_fixed=True),
            T("通识选修·晚间⑦", 2.0, 32, lecture=32, category="普通选修", prefer=["晚上"], elective_slot="eve7"),
            E("模拟电子技术实验", 1.0, 32, hps=4),
            E("数字电子技术实验", 1.0, 32, hps=4),
            T("四史·③", 1.0, 15, lecture=15, category="四史", type="四史", prefer=["晚上"],
              sessions_per_week=1, hours_per_session=3, weeks="1-5", elective_slot="hist3"),
            T("四史·④", 1.0, 15, lecture=15, category="四史", type="四史", prefer=["晚上"],
              sessions_per_week=1, hours_per_session=3, weeks="1-5", elective_slot="hist4"),
            SX("形势与政策(4)", 0.25),

        ],
        "semester_events": [
            {"name": "思政实践（社会实践）", "credits": 1.0, "category": "必修", "type": "实践",
             "note": "全天×8天=64学时（第14周5天+第15周3天）",
             "events": [{"week": ww, "weekday": wd, "duration": "full", "hours": 8}
                        for ww, nd in [(14, 5), (15, 3)] for wd in range(nd)]},
            # 形势与政策(4) 已作为课程定义（见 courses）,
        ],
    },
    # ================= 第5学期 2024-2025-1 =================
    5: {
        "term": "第5学期（2024-2025学年第一学期）", "term_code": "2024-25-1",
        "term_start": "2024-09-02",
        "courses": [
            T("信号与系统", 3.0, 38),
            T("电力电子技术基础", 3.0, 56, lecture=36),   # 大班36讲课
            E("电力电子技术基础实践", 1.0, 20, hps=4),    # 4实验+16上机=20学时→5次×4
            T("微机原理及其应用", 3.0, 48, lecture=48),
            T("自动控制原理", 3.0, 54),
            E("自动控制原理实验", 1.0, 12, hps=4),
            T("电机学（上）", 2.5, 44, half_term=True),
            E("电机学（上）实验", 1.0, 12, hps=4),     # 4实验+8上机
            T("电力系统基础（上）", 2.5, 40, half_term=True),   # 无实验，全部大班
            T("高电压技术基础", 2.0, 32),
            {"name": "机电技术创新实训", "credits": 2.0, "category": "必修", "type": "实践",
             "total_hours": 64, "block": "mixed", "half_weeks": "1-4", "full_weeks": "5-10",
             "desc": "前4周下午半天×4学时 + 后6周全全天×8学时 = 64（逐渐上调全天，全天一旦开始持续到结束）"},
            EV("信号与系统·讨论", 0.0, half="second", weeks="9-10"),
            E("信号与系统实验", 1.0, 12, hps=4),
            E("微机原理及其应用实践", 1.0, 32, hps=4, split=[4, 4]),   # 拆成4+4两段
            SX("形势与政策(5)", 0.25, day=4, slot=6),
        ],
        "semester_events": [

            {"name": "电子技术综合设计（集中）", "credits": 2.0, "category": "必修", "type": "实践",
             "note": "全天×8天=64学时（第13周5天+第14周3天）",
             "events": [{"week": ww, "weekday": wd, "duration": "full", "hours": 8}
                        for ww, nd in [(13, 5), (14, 3)] for wd in range(nd)]},
            # 形势与政策(5) 已作为课程定义（见 courses）,
        ],
    },
    # ================= 第6学期 2024-2025-2 =================
    6: {
        "term": "第6学期（2024-2025学年第二学期）", "term_code": "2024-25-2",
        "term_start": "2025-02-24",
        "courses": [
            T("传感与检测技术", 3.0, 52),
            T("电机学（下）", 3.5, 60, half_term=True),
            E("电机学（下）实验", 1.0, 12, hps=4),     # 4实验+8上机
            T("电力系统基础（下）", 2.5, 40, half_term=True),   # 无实验，全部大班
            T("电机控制技术", 2.0, 32),
            T("专业选修·下午①", 2.0, 32, lecture=32, category="专业选修", prefer=["下午"], no_evening=True, elective_slot="maj1"),
            T("专业选修·下午②", 2.0, 32, lecture=32, category="专业选修", prefer=["下午"], no_evening=True, elective_slot="maj2"),
            T("专业选修·下午③", 2.0, 32, lecture=32, category="专业选修", prefer=["下午"], no_evening=True, elective_slot="maj3"),
            T("专业选修·下午④", 2.0, 32, lecture=32, category="专业选修", prefer=["下午"], no_evening=True, elective_slot="maj4"),
            EV("传感与检测技术·讨论", 0.0, half="second", weeks="9-16"),
            SX("形势与政策(6)", 0.25),
        ],
        "semester_events": [
            {"name": "劳动教育与素养", "credits": 0.0, "category": "必修", "type": "实践",
             "note": "半天（上午）劳动教育",
             "events": [{"week": 10, "weekday": 3, "duration": "half-am", "hours": 4}]},
            # 形势与政策(6) 已作为课程定义（见 courses）,
        ],
    },
}


def build_one(sem_no, verify_week=None):
    import course_scheduler as cs
    data = SEMESTERS[sem_no]
    data.setdefault("semester_no", sem_no)
    data.setdefault("weekdays", 5)
    data.setdefault("teaching_weeks", 16)
    data["courses"] = _patch_lecture(data["courses"])
    # 写JSON
    f = DATA / f"courses_sem{sem_no}.json"
    f.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    # 排课
    cs.COURSE_FILE = f
    d = cs.load_courses()
    print(f"\n{'='*60}\n📚 排课：{d['term']}（{d['term_code']}）")
    records = cs.allocate(d)
    cs.write_db(d, records)
    print(f"  ✅ 已写入数据库（{len([r for r in records if r[3]!='实验'])}门理论/实践 + {len([r for r in records if r[3]=='实验'])}门实验）")
    return d, records


def verify_semester(sem_no, week_no=None):
    """随机抽一周展示课表"""
    import course_scheduler as cs
    f = DATA / f"courses_sem{sem_no}.json"
    if not f.exists():
        print(f"第{sem_no}学期数据不存在，请先排课")
        return
    cs.COURSE_FILE = f
    d = cs.load_courses()
    week_no = week_no or random.randint(1, 16)
    print(f"\n📅 第{sem_no}学期 · 随机抽第{week_no}周验证：")
    conn = __import__("sqlite3").connect(cs.DB_PATH)
    conn.row_factory = __import__("sqlite3").Row
    events = conn.execute("SELECT * FROM semester_events WHERE semester_no=? AND week_no=?",
                          (sem_no, week_no)).fetchall()
    from collections import defaultdict
    table = defaultdict(dict)
    rows = conn.execute("SELECT * FROM virtual_course_schedule WHERE semester_no=? ORDER BY weekday, slot_index",
                        (sem_no,)).fetchall()
    for r in rows:
        table[r["weekday"]][r["slot_index"]] = r
    conn.close()
    SLOTS = [(1,"第一节①","08:00-08:45"),(2,"第一节②","08:55-09:40"),(3,"第二节①","10:00-10:45"),
             (4,"第二节②","10:55-11:40"),(5,"第三节","14:30-16:00"),(6,"第四节","16:10-17:40"),
             (7,"第五节①","19:00-19:45"),(8,"第五节②","19:55-20:40"),(9,"第五节③","20:50-21:35"),
             (10,"第五节④","21:35-22:20")]
    WDN = ["周一","周二","周三","周四","周五","周六","周日"]
    for wd in range(5):
        line = [f"{WDN[wd]:<3}"]
        for s, lab, tm in SLOTS:
            ev = next((e for e in events if e["weekday"]==wd and e["slot_index"]==s), None)
            r = table[wd].get(s)
            if ev:
                line.append(f"{lab}:{ev['course'][:6]}⚠️")
            elif r:
                weeks = {int(x) for x in r["session_weeks"].split(",")}
                mark = "✅" if week_no in weeks else "⏸"
                line.append(f"{lab}:{r['course'][:8]}{mark}")
            else:
                line.append(f"{lab}:—")
        print("  " + "  ".join(line))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sems = [int(a) for a in args] if args else sorted(SEMESTERS.keys())
    for s in sems:
        build_one(s)
    # 每学期随机抽一周
    print("\n" + "=" * 60)
    print("🎲 各学期随机周验证：")
    for s in sems:
        verify_semester(s)
