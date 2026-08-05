#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
虚拟课程分配器 v4 —— 按具体学时规则排课（课次化模型）
============================================================
学时规则（用户定义）：
  32学时 → 每周1次×2学时，1-16周（每次课=2学时）
  64学时 → 每周2次×2学时，1-16周
  48学时 → 前半学期每周2节 + 后半学期每周1节（每次2学时）
            （或后半学期每周2节 + 前半学期每周1节，由 intensive_half 指定）
            = 8周×2次×2学时(32) + 8周×1次×2学时(16) = 48
  36学时（体育/军事理论）→ 每周1次×2学时，1-16周
  含小班讨论 → 单独标记（has_seminar）
  实验课 → 仅晚间占满3节(slot7-9)：
            大物A2 为 3或6学时/次；其余实验（电路/信号/电机/电力电子）一律4学时/次
            电路实验32学时=8次×4学时；大物A2实际24学时=8次×3学时(含8学时虚拟不排课)
用法：
    python3 course_scheduler.py            # 分配并写入数据库
    python3 course_scheduler.py --show     # 查看已生成的虚拟课表
"""

import sqlite3
import json
from pathlib import Path

BASE = Path(__file__).parent
DB_PATH = BASE / "db" / "virtual_time.db"
COURSE_FILE = BASE / "data" / "courses_2023-24-1.json"

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

SLOTS = [
    (1, "第一节", 1, "08:00", "08:45", 1),
    (2, "第一节", 2, "08:55", "09:40", 1),
    (3, "第二节", 1, "09:50", "10:45", 1),
    (4, "第二节", 2, "10:55", "11:40", 1),
    (5, "第三节", 1, "14:30", "16:00", 2),
    (6, "第四节", 1, "16:10", "17:40", 2),
    (7, "第五节", 1, "19:00", "19:45", 1),
    (8, "第五节", 2, "19:55", "20:40", 1),
    (9, "第五节", 3, "20:50", "21:35", 1),
]

SLOT_2H = {"上午": [(1, 2), (3, 4)], "下午": [(5,), (6,)], "晚上": [(7, 8)]}   # 晚上：普通选修课优先
SLOT_1H = {"上午": [(1,), (2,), (3,), (4,)], "下午": [(5,), (6,)]}   # 1学时课（讨论等）
SLOT_EVENING = [(7, 8, 9)]
SLOT_AFTERNOON_BLOCK = [(5, 6)]   # 下午4学时块（实验优先）
ALL_WEEKS = list(range(1, 17))

# 保留槽位：周二下午两节（slot5/6）——仅军事理论/形势与政策可用，且优先排别处
RESERVED_WEEKDAY = 1   # 0=周一, 1=周二
RESERVED_SLOTS = {5, 6}
RESERVED_ONLY_COURSES = {"军事理论", "形势与政策"}


def is_reserved(w, combo):
    return w == RESERVED_WEEKDAY and any(s in RESERVED_SLOTS for s in combo)


def load_courses():
    return json.loads(COURSE_FILE.read_text(encoding="utf-8"))


def gen_session_weeks(n_sessions, week_from=1, week_to=16, offset=0):
    """把 n 次实验均匀隔周分布到 [week_from, week_to]，返回周次列表"""
    weeks = []
    w = week_from + offset
    while w <= week_to and len(weeks) < n_sessions:
        weeks.append(w)
        w += 2
    w = week_from + (1 if offset else 0)
    while len(weeks) < n_sessions and w <= week_to:
        if w not in weeks:
            weeks.append(w)
        w += 1
    return sorted(weeks)


def build_lesson_plans(course):
    """把一门课拆成若干『课次』：{weeks, slots, hours}。slots=None 待分配。
    通用学时拆分（每次课=2学时）：
      每32学时 → 1个全学期槽(1-16周)
      每16学时 → 1个半学期槽(1-8或9-16周)
      剩余 → 学期末加课槽（2学时/次×N周）
    例：32→1全；48→1全+1半；64→2全；80→2全+1半；96→3全；
        54→1全+1半+3周加课；40→1全+4周加课
    """
    if course["type"] == "实验":
        hps = course.get("hours_per_session", 4)
        total = course.get("total_hours", 32)
        sessions = course.get("sessions", max(1, round(total / hps)))
        return [{"weeks": None, "slots": (7, 8, 9), "hours": hps, "sessions": sessions}]
    # 块状课程（机电创新实训等）：每周1个半天/全天块；支持混合（半天段→全天段，全天一旦开始持续到结束）
    if course.get("block"):
        BLOCKS = {"full": (1, 2, 3, 4, 5, 6), "half-am": (1, 2, 3, 4), "half-pm": (5, 6)}
        plans = []
        if course.get("half_weeks"):          # 前半：每周1个下午半天
            wf, wt = (int(x) for x in course["half_weeks"].split("-"))
            plans.append({"weeks": list(range(wf, wt + 1)), "slots": BLOCKS["half-pm"], "hours": 4})
        if course.get("full_weeks"):          # 后半：每周1个全天（一旦开始持续到结束）
            wf, wt = (int(x) for x in course["full_weeks"].split("-"))
            plans.append({"weeks": list(range(wf, wt + 1)), "slots": BLOCKS["full"], "hours": 8})
        if not plans:                         # 纯半天或纯全天
            slots = BLOCKS[course["block"]]
            hps = 8 if course["block"] == "full" else 4
            wf, wt = (int(x) for x in course.get("weeks", "1-16").split("-"))
            plans.append({"weeks": list(range(wf, wt + 1)), "slots": slots, "hours": hps})
        return plans
    # 半学期标志课：每周2次×2学时，第12周前结束（周次=min(12, 总学时/4)）
    if course.get("half_term"):
        n = max(1, min(12, round(course.get("total_hours", 32) / 4)))
        weeks = list(range(1, n + 1))
        return [{"weeks": weeks, "slots": None, "hours": 2},
                {"weeks": weeks, "slots": None, "hours": 2}]
    # 显式指定每周次数/每次学时（讨论课等）
    if "sessions_per_week" in course:
        spw = course["sessions_per_week"]
        hps = course.get("hours_per_session", 2)
        wf, wt = (int(x) for x in course.get("weeks", "1-16").split("-"))
        return [{"weeks": list(range(wf, wt + 1)), "slots": None, "hours": hps}
                for _ in range(spw)]
    total = course.get("total_hours", 32)
    # 特殊课程（体育等）：每周1次×2学时，1-16周
    if course.get("weekly_fixed"):
        return [{"weeks": ALL_WEEKS, "slots": None, "hours": 2}]
    base = course.get("lecture") or total
    # 大班学时 32<base≤48：全学期槽16次 + 半学期槽(次课-16)次（思政42→5次、电力电子40→4次、信号38→3次、48→8次）
    if 32 < base <= 48:
        extra = max(1, round(base / 2) - 16)
        half_weeks = list(range(1, min(extra, 8) + 1))
        return [{"weeks": ALL_WEEKS, "slots": None, "hours": 2},
                {"weeks": half_weeks, "slots": None, "hours": 2}]
    # 标准档（≥64学时按大班学时归档）
    std = min([32, 48, 64, 80, 96], key=lambda x: (abs(x - base), -x))
    first, second = list(range(1, 9)), list(range(9, 17))
    half = first if course.get("intensive_half") != "second" else second
    plans = []
    n_full = std // 32                                  # 全学期槽
    for _ in range(n_full):
        plans.append({"weeks": ALL_WEEKS, "slots": None, "hours": 2})
    if std % 32 == 16:                                  # 半学期槽
        plans.append({"weeks": half, "slots": None, "hours": 2})
    return plans
    return []


def allocate(data):
    """分配：返回课次列表 [(course, weekday, slot_combo, weeks_str, hours, seminar)]"""
    ndays = data["weekdays"]
    used = {w: set() for w in range(ndays)}
    load = {w: 0 for w in range(ndays)}
    placed_records = []
    two_slot_idx = 0        # 2课次课模式轮换计数器
    # 周次感知槽位：used_weeks[天][slot] = 已占用周次集合（支持1-8周/9-16周不同课复用同一槽位）
    used_weeks = {w: {s: set() for s in range(1, 10)} for w in range(ndays)}
    ALL_W = set(range(1, 17))

    def pick_slot(combo_pool, prefs, allow_reserved=False, exclude_days=(), no_evening=False,
                  forbid=None, weeks=None):
        weeks = weeks or ALL_W
        all_parts = ["上午", "下午"] if no_evening else ["上午", "下午", "晚上"]
        forbid = forbid or set()
        for pref in prefs + [p for p in all_parts if p not in prefs]:
            for combo in combo_pool.get(pref, []):
                cands = [w for w in range(ndays)
                         if w not in forbid
                         and all(not (used_weeks[w][s] & weeks) for s in combo)
                         and (allow_reserved or not is_reserved(w, combo))
                         and all(abs(w - d) >= 2 for d in exclude_days)]
                if not cands:
                    continue
                w = min(cands, key=lambda x: load[x])
                for s in combo:
                    used_weeks[w][s].update(weeks)
                load[w] += len(combo)
                return w, combo
        return None, None

    def find_combo_on_day(w, combo_pool, prefs, hours, exclude_days=(), weeks=None):
        """在指定天找空闲课位（天模式阶段只试 prefer 时段[默认上午]，把下午留给实验）"""
        weeks = weeks or ALL_W
        if any(abs(w - d) < 2 for d in exclude_days):
            return None
        for pref in prefs:                       # 天模式只试优先时段（必修默认上午）
            for combo in combo_pool.get(pref, []):
                if is_reserved(w, combo):
                    continue
                if all(not (used_weeks[w][s] & weeks) for s in combo):
                    return combo
        return None

    specials = [c for c in data["courses"] if c["name"] in RESERVED_ONLY_COURSES]
    # 分配顺序：体育(固定槽位) → 必修/专业选修 → 普通选修(晚上优先) → 实训(block最后) → 军事理论兜底
    fixed_first = [c for c in data["courses"] if c.get("fixed_slot")]
    common = [c for c in data["courses"]
              if c["type"] != "实验" and c["name"] not in RESERVED_ONLY_COURSES
              and not c.get("fixed_slot") and not c.get("block") and c.get("category") != "普通选修"]
    block_courses = [c for c in data["courses"] if c.get("block")]
    elective_eve = [c for c in data["courses"] if c.get("category") == "普通选修"]
    courses = fixed_first + sorted(common, key=lambda c: -c.get("total_hours", 0)) +               sorted(elective_eve, key=lambda c: -c.get("total_hours", 0))
    for course in courses:
        seminar = 1 if course.get("seminar", 0) else 0
        course_days = []          # 同课课次所在天（间隔≥2天，同天/相邻天均禁止）
        # 天模式：每门课计算一次（3课次→{0,2,4}；2课次→{1,3}/{0,4}轮换，保证间隔≥2天）
        n_plans = len(build_lesson_plans(course))
        if n_plans == 3:
            day_seq = [0, 2, 4]
        elif n_plans == 2:
            day_seq = ([1, 3] if two_slot_idx % 2 == 0 else [0, 4])
            two_slot_idx += 1
        else:
            day_seq = None
        for plan in build_lesson_plans(course):
            # 固定槽位课程（如体育课固定第三节，且课后一节留空）
            if course.get("fixed_slot"):
                s = course["fixed_slot"]
                cands = [w for w in range(ndays)
                         if not (used_weeks[w][s] & ALL_W) and not is_reserved(w, (s,))]
                if not cands:
                    print(f"  ⚠️ 无法分配(固定槽位): {course['name']}")
                    continue
                # 体育优先中间天（周三/四/五），避开周一高峰
                day_order = [2, 3, 4, 0, 1]
                cands.sort(key=lambda x: day_order.index(x))
                w = cands[0]
                combo = (s,)
                for x in combo:
                    used_weeks[w][x].update(ALL_W)
                load[w] += len(combo)
                if course.get("block_next"):
                    used_weeks[w][s + 1].update(ALL_W)   # 课后下一节整学期留空
                weeks = ",".join(map(str, plan["weeks"]))
                placed_records.append((course["name"], course["credits"], course["category"],
                                       course["type"], w, combo, weeks, plan["hours"], seminar))
                continue
            pool = SLOT_1H if plan["hours"] == 1 else SLOT_2H
            # 只有普通选修课允许排晚上；必修/专业选修均不排晚上
            no_eve = course.get("category") != "普通选修" or course.get("no_evening", False)
            prefs = course.get("prefer") or ["上午"]
            w, combo = None, None
            wks = set(plan["weeks"]) if plan.get("weeks") else ALL_W
            if course["name"] in ("电力系统基础（上）", "电力电子技术基础", "微机原理及其应用", "电机学（上）", "自动控制原理"):
                print(f"    [A] {course['name']} 课次{len(course_days)} day_seq={day_seq} course_days={course_days} 分配前周一s1={used_weeks[0][1]}")
            if day_seq and len(course_days) < len(day_seq):
                # 依次尝试模式内未用天（排除已用天相邻）
                for target in day_seq[len(course_days):]:
                    combo = find_combo_on_day(target, pool, prefs, plan["hours"],
                                              exclude_days=tuple(course_days), weeks=wks)
                    if combo:
                        w, combo = target, combo
                        break
            if w is None:
                # fallback：仅禁止已用天±1（保证课次间隔≥2天）
                forbid = set()
                for d in course_days:
                    forbid.update([d - 1, d, d + 1])
                w, combo = pick_slot(pool, prefs, exclude_days=tuple(course_days),
                                     no_evening=no_eve, forbid=forbid, weeks=wks)
            if w is None:
                print(f"  ⚠️ 无法分配: {course['name']}")
                continue
            for s in combo:
                used_weeks[w][s].update(wks)
            load[w] += len(combo)
            course_days.append(w)
            if course["name"] in ("电力系统基础（上）", "电力电子技术基础", "微机原理及其应用", "电机学（上）", "自动控制原理"):
                print(f"    [B] {course['name']} 课次{len(course_days)-1} → 周{w+1} slot{combo} 周次{min(wks)}-{max(wks)} | 周一s1现在={used_weeks[0][1]}")
            weeks = ",".join(map(str, plan["weeks"]))
            placed_records.append((course["name"], course["credits"], course["category"],
                                   course["type"], w, combo, weeks, plan["hours"], seminar))

    # 军事理论/形势与政策：最后分配，优先非保留槽位，别无选择才用周二下午
    for course in specials:
        seminar = 1 if course.get("seminar", 0) else 0
        plan = build_lesson_plans(course)[0]
        pool = SLOT_1H if plan["hours"] == 1 else SLOT_2H
        w, combo = pick_slot(pool, course.get("prefer") or ["下午"], allow_reserved=False)
        if w is None:
            w, combo = pick_slot(pool, ["下午"], allow_reserved=True)   # 兜底：允许保留槽位
        if w is None:
            print(f"  ⚠️ 无法分配(兜底): {course['name']}")
            continue
        weeks = ",".join(map(str, plan["weeks"]))
        placed_records.append((course["name"], course["credits"], course["category"],
                               course["type"], w, combo, weeks, plan["hours"], seminar))
        if is_reserved(w, combo):
            print(f"  📌 {course['name']} 无奈占用周二下午保留槽位（slot{combo}）")

    # 实验课（普通课分配后）：课时多的优先排下午(slot5+6)，下午排不下再排晚上(3节连上)
    # 大三起(学期≥5)实验可连续周进行；大一大二保持隔周（单/双周）
    continuous = data.get("semester_no", 0) >= 5
    exp_courses = sorted([c for c in data["courses"] if c["type"] == "实验"],
                         key=lambda c: -(c.get("sessions") or 0))
    exp_placed = []          # 实验分配记录（含下午/晚间标记，供降级）
    exp_cnt = [0] * 17       # 每周实验数（约束：每周≤3）
    for course in exp_courses:
        plan = build_lesson_plans(course)[0]
        sessions = plan.get("sessions", 8)
        hps = plan["hours"]
        segs = course.get("split") or [sessions]    # 拆段（如 4+4 → [4,4]）
        seg_total = 0
        for seg_n in segs:
            placed = False
            for slot_group in ["下午", "晚上"]:      # 下午优先，晚上兜底
                pool = {"下午": SLOT_AFTERNOON_BLOCK, "晚上": SLOT_EVENING}[slot_group]
                if continuous:
                    week_opts = [list(range(s, s + seg_n)) for s in range(1, 17 - seg_n + 1)]
                else:
                    week_opts = [gen_session_weeks(seg_n, 1, 16, off) for off in [0, 1]]
                for sw in week_opts:
                    if any(exp_cnt[x] >= 3 for x in sw):   # 每周最多3个实验
                        continue
                    sw_set = set(sw)
                    w, combo = pick_slot({slot_group: pool}, [slot_group], allow_reserved=True, weeks=sw_set)
                    if w is not None:
                        placed_records.append((course["name"], course["credits"], course["category"],
                                               "实验", w, combo, ",".join(map(str, sw)), hps, 0))
                        exp_placed.append((course["name"], w, combo, sw, hps, slot_group, "下午"))
                        for x in sw:
                            exp_cnt[x] += 1
                        loc = "下午" if slot_group == "下午" else "晚"
                        mode = "连续" if continuous else "隔周"
                        print(f"  📌 实验 {course['name']}[段{len(segs)>1 and seg_total and '2' or '1' if False else ''}] {loc}: 周{w+1} slot{combo} {seg_n}次×{hps}学时，{mode}周次={sw}")
                        placed = True
                        break
                if placed:
                    break
            if not placed:
                print(f"  ⚠️ 无法分配实验段: {course['name']}（{seg_n}次）")
            else:
                seg_total += 1
        if seg_total != len(segs):
            print(f"  ⚠️ 实验 {course['name']} 部分段未分配")

    # ============ 实训（块课程）分配：比例自动调整 + 实验自动降级 ============
    BLOCK_DEFS = {"half-pm": (5, 6), "full": (1, 2, 3, 4, 5, 6)}   # 半天/全天槽位

    def try_place(bc, N_half, M_full):
        """尝试按 半天N周+全天M周 分配 block 课程；成功返回分配记录列表，失败回滚返回 None"""
        plans = [{"weeks": list(range(1, N_half + 1)), "slots": (5, 6), "hours": 4},
                 {"weeks": list(range(1, M_full + 1)), "slots": (1, 2, 3, 4, 5, 6), "hours": 8}]
        if N_half == 0:
            plans = plans[1:]
        seg_floor = 0
        seg_done = []
        for plan in plans:
            max_end = plan["weeks"][-1]
            lo = max(0, seg_floor - plan["weeks"][0] + 1) if seg_floor else 0
            done = False
            for shift in range(lo, 16 - max_end + 1):
                wks = sorted(w + shift for w in plan["weeks"])
                wks_set = set(wks)
                cands = [w for w in range(ndays)
                         if all(not (used_weeks[w][s] & wks_set) for s in plan["slots"])
                         and not is_reserved(w, plan["slots"])]
                if not cands:
                    continue
                w = min(cands, key=lambda x: load[x])
                for s in plan["slots"]:
                    used_weeks[w][s].update(wks_set)
                seg_done.append((w, plan["slots"], wks_set, plan["hours"]))
                seg_floor = max(wks)
                done = True
                break
            if not done:
                break
        if len(seg_done) != len(plans):      # 有段失败 → 回滚
            for w, slots, wks_set, hps in seg_done:
                for s in slots:
                    used_weeks[w][s] -= wks_set
            return None
        return seg_done

    def place_block_courses():
        """全部 block 课程；比例从默认开始、失败则自动调整（全天周数从多到少）"""
        ok_all = True
        for bc in block_courses:
            total = bc.get("total_hours", 64)
            # 候选比例：4N+8M=64 → (N, M)；默认(4,6)优先，其余按全天M降序
            cands = []
            for k in range(0, 9):
                N, M = 2 * k, 8 - k
                if 4 * N + 8 * M == total and N + M <= 16 and M >= 2:
                    cands.append((N, M))
            default = (4, 6)
            cands = [default] + [c for c in cands if c != default]
            cands.sort(key=lambda c: (c != default, -c[1]))   # 默认最优先，其余全天多优先
            placed = False
            for N, M in cands:
                seg_done = try_place(bc, N, M)
                if seg_done is not None:
                    for w, slots, wks_set, hps in seg_done:
                        placed_records.append((bc["name"], bc["credits"], bc["category"],
                                               bc["type"], w, slots,
                                               ",".join(map(str, sorted(wks_set))), hps, seminar))
                        kind = "全天" if hps == 8 else "下午半天"
                        print(f"  📌 实训 {bc['name']} {kind}: 周{w+1} slot{slots} 第{min(wks_set)}-{max(wks_set)}周×{hps}学时（比例 半天{N}+全天{M}）")
                    placed = True
                    break
            if not placed:
                print(f"  ⚠️ 实训 {bc['name']}: 全部比例均不可行，降级实验到晚间…")
                ok_all = False
        return ok_all

    ok = place_block_courses()
    pm_exps = [e for e in exp_placed if e[5] == "下午"]
    pm_exps.sort(key=lambda e: len(e[3]))            # 课时(次数)少→多
    while not ok and pm_exps:
        cname, w, combo, sw, hps, sgroup, _ = pm_exps.pop(0)
        sw_set = set(sw)
        for s in combo:
            used_weeks[w][s] -= sw_set               # 撤销下午占用
        for x in sw:
            exp_cnt[x] -= 1
        for rec in list(placed_records):
            if rec[0] == cname and rec[4] == w:
                placed_records.remove(rec)
        if any(exp_cnt[x] >= 3 for x in sw):
            print(f"  ⚠️ 降级失败: {cname}（周{sw}实验数将超3）")
            continue
        w2, combo2 = pick_slot({"晚上": SLOT_EVENING}, ["晚上"], allow_reserved=True, weeks=sw_set)
        if w2 is not None:
            for s in combo2:
                used_weeks[w2][s].update(sw_set)
            for x in sw:
                exp_cnt[x] += 1
            placed_records.append((cname, 0.0, "", "实验", w2, combo2,
                                   ",".join(map(str, sw)), hps, 0))
            print(f"  🔄 降级: {cname} 从下午移到周{w2+1}晚 slot{combo2}（周次{sw}）")
        else:
            print(f"  ⚠️ 降级失败: {cname} 晚上也无位置")
        ok = place_block_courses()
    if not ok:
        print("  ⚠️ 实训最终无法分配（比例+实验降级均已用尽）")
    return placed_records


def write_db(data, records):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("CREATE TABLE IF NOT EXISTS terms (semester_no INTEGER PRIMARY KEY, term_code TEXT, start_date TEXT, end_date TEXT, note TEXT)")
    cur.execute("DELETE FROM terms WHERE semester_no=?", (data.get("semester_no", 0),))
    cur.execute("INSERT INTO terms (semester_no, term_code, start_date, end_date, note) VALUES (?,?,?,?,?)",
                (data.get("semester_no", 0), data["term_code"], data.get("term_start"), None, data["term"]))

    cur.execute("""CREATE TABLE IF NOT EXISTS semester_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, term_code TEXT, semester_no INTEGER,
        week_no INTEGER, weekday INTEGER, weekday_cn TEXT, slot_index INTEGER,
        start_time TEXT, end_time TEXT, course TEXT, credits REAL, category TEXT,
        course_type TEXT, hours REAL, note TEXT)""")
    cur.execute("DELETE FROM semester_events WHERE semester_no=?", (data.get("semester_no", 0),))
    DUR_SLOTS = {   # 半天/全天展开
        "full":     [(s, st, et) for s, p, seg, st, et, h in SLOTS if s <= 6],
        "half-am":  [(s, st, et) for s, p, seg, st, et, h in SLOTS if s <= 4],
        "half-pm":  [(s, st, et) for s, p, seg, st, et, h in SLOTS if 5 <= s <= 6],
    }
    for ev in data.get("semester_events", []):
        for e in ev.get("events", []):
            if "duration" in e:
                slots = DUR_SLOTS.get(e["duration"], DUR_SLOTS["half-am"])
                hours = e.get("hours", 4 * len(slots) // 2)
                for s, st, et in slots:
                    cur.execute("INSERT INTO semester_events (term_code, semester_no, week_no, weekday, weekday_cn, slot_index, start_time, end_time, course, credits, category, course_type, hours, note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                (data["term_code"], data.get("semester_no", 0), e["week"], e["weekday"],
                                 WEEKDAY_CN[e["weekday"]], s, st, et,
                                 ev["name"], ev["credits"], ev["category"], ev["type"],
                                 hours, ev.get("note", "")))
            else:
                cur.execute("INSERT INTO semester_events (term_code, semester_no, week_no, weekday, weekday_cn, slot_index, start_time, end_time, course, credits, category, course_type, hours, note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (data["term_code"], data.get("semester_no", 0), e["week"], e["weekday"],
                             WEEKDAY_CN[e["weekday"]], e["slot"], e.get("start"), e.get("end"),
                             ev["name"], ev["credits"], ev["category"], ev["type"],
                             e.get("hours", 2), ev.get("note", "")))

    cur.execute("""CREATE TABLE IF NOT EXISTS virtual_course_schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        term_code TEXT, semester_no INTEGER,
        weekday INTEGER, weekday_cn TEXT,
        slot_index INTEGER, period TEXT, start_time TEXT, end_time TEXT,
        course TEXT, credits REAL, category TEXT, course_type TEXT,
        session_weeks TEXT, hours REAL, has_seminar INTEGER DEFAULT 0)""")
    cur.execute("DELETE FROM virtual_course_schedule WHERE semester_no=?", (data.get("semester_no", 0),))
    slot_map = {s: (period, st, et) for s, period, seg, st, et, h in SLOTS}
    for name, credits, cat, ctype, wd, combo, weeks, hours, seminar in records:
        for s in combo:
            period, st, et = slot_map[s]
            cur.execute("INSERT INTO virtual_course_schedule (term_code, semester_no, weekday, weekday_cn, slot_index, period, start_time, end_time, course, credits, category, course_type, session_weeks, hours, has_seminar) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (data["term_code"], data.get("semester_no", 0), wd, WEEKDAY_CN[wd],
                         s, period, st, et, name, credits, cat, ctype, weeks, hours, seminar))
    conn.commit()
    conn.close()


def show(data, records):
    sem = data.get("semester_no", "?")
    table = {}
    for name, credits, cat, ctype, wd, combo, weeks, hours, seminar in records:
        for s in combo:
            table[(wd, s)] = (name, credits, ctype, weeks, hours, seminar)
    print(f"\n===== 虚拟课程表：第{sem}学期（{data['term_code']}，大二上）=====\n")
    for w in range(data["weekdays"]):
        print(f"--- {WEEKDAY_CN[w]} ---")
        for s, period, seg, st, et, h in SLOTS:
            item = table.get((w, s))
            if item:
                name, credits, ctype, weeks, hours, seminar = item
                tag = "·讨论" if (seminar and "讨论" not in name) else ""
                if ctype == "实验":
                    wshow = f"[{weeks}周]"
                else:
                    wl = [int(x) for x in weeks.split(",")]
                    wshow = (f"({wl[0]}-{wl[-1]}周)" if len(wl) == 16 else f"[{weeks}周]")
                print(f"  [{period}·段{seg}] {st}-{et}  {name}{tag}{wshow}（{hours}学时/次）")
            else:
                print(f"  [{period}·段{seg}] {st}-{et}  — 空闲/自习")
        print()


if __name__ == "__main__":
    import sys
    data = load_courses()
    if "--show" in sys.argv:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM virtual_course_schedule WHERE term_code=? ORDER BY weekday, slot_index",
                            (data["term_code"],)).fetchall()
        conn.close()
        recs = []
        for r in rows:
            recs.append((r["course"], r["credits"], r["category"], r["course_type"],
                         r["weekday"], (r["slot_index"],), r["session_weeks"], r["hours"], r["has_seminar"]))
        show(data, recs)
    else:
        print(f"分配课程：{data['term']}（共 {len(data['courses'])} 门）")
        records = allocate(data)
        write_db(data, records)
        show(data, records)
        print("✅ 已写入数据库 virtual_course_schedule（v4 课次化学时规则）")
