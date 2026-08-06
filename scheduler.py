#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用智能排课器（CSP · per-girl 直接排课，无 offset）
============================================================
为每个 girl 直接求解合法课表，每门课只受自身约束：
  ① 每人 0 时间冲突（同格同周不双课）
  ② 类型时段：实验=仅下午/晚间(slot5-9,12)；理论=白天(slot1-6)；选修=晚间(slot7-9,12)；讲座=下午
  ③ 楼约束：研楼三门=研楼；马原/习概=综合楼中；实验=物电院；Python/形势政策=综合楼；体育=体育馆；四史=自习
  ④ 相邻同楼：同人同日间隔≤30min 的课次必须同楼
  ⑤ 教室唯一：同一时刻同楼不共用教室（不同班错开教室）
  ⑥ 同课两行间隔≥2天；周二下午禁课
  ⑦ 同班同步：电气(surrey/taiyuan)核心课同时间同老师；公共课4人同时；同老师不跨班同时
输出：data/schedule_sem4.json + girl_schedules/*_sem4.md + db表 girl_course_schedule
用法：python3 scheduler.py [--dry] [--debug]
"""
import json
import os
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).parent
DB = BASE / "db" / "virtual_time.db"
DEBUG = "--debug" in sys.argv
DRY = "--dry" in sys.argv

GIRLS = ["surrey", "orage", "sakawa", "taiyuan"]
EE = {"surrey", "taiyuan"}
WD_CN = ["周一", "周二", "周三", "周四", "周五"]
SLOT_TIME = {1: "08:00", 2: "08:55", 3: "09:50", 4: "10:55", 5: "14:30",
             6: "16:10", 7: "19:00", 8: "19:55", 9: "20:50", 12: "21:35"}
SLOT_END = {1: "08:45", 2: "09:40", 3: "10:45", 4: "11:40", 5: "16:00",
            6: "17:40", 7: "19:45", 8: "20:40", 9: "21:35", 12: "22:20"}
AFTERNOON = {5, 6}
EVENING = {7, 8, 9, 12}
DAYTIME = {1, 2, 3, 4, 5, 6}
# 排课时段偏好：优先 slot3(早上10点起) 与 slot6(下午4点起)，其次 slot5，最后 slot1；晚间按序
SLOT_PREF = {3: 0, 6: 1, 5: 2, 1: 3, 7: 4, 9: 5, 12: 6}

ROOMS = {
    "研楼": [f"研楼{c}{l}0{n}" for c in "ABC" for l in range(1, 4) for n in range(1, 6)],
    "综合楼中": ["综合楼301(中)", "综合楼302(中)", "综合楼303(中)", "综合楼304(中)", "综合楼305(中)",
               "综合楼306(中)", "综合楼308(中)", "综合楼309(中)", "综合楼311(中)", "综合楼312(中)",
               "综合楼313(中)", "综合楼314(中)", "综合楼401(中)", "综合楼402(中)", "综合楼403(中)"],
    "综合楼大": ["综合楼104(大)", "综合楼106(大)", "综合楼205(大)"],
    "物电院": ["物电院实验室1", "物电院实验室2", "物电院实验室3",
               "物电院实验室4", "物电院实验室5", "物电院实验室6"],
    "体育馆": ["体育馆", "田径场(全校)"],
    "自习": ["自习（无教室）"],
}
BUILDING = {"研楼": "研楼", "综合楼中": "综合楼", "综合楼大": "综合楼",
            "物电院": "物电院", "体育馆": "体育馆", "自习": "自习"}


def log(msg):
    if DEBUG:
        print(f"  [SCH] {msg}")


# =====================================================================
# 课程定义（S4）
# pattern: full_half=16+8 / full=16 / full+part5=16+5 / biweekly=单周8 / single=weeks指定
# =====================================================================
def C(course, ctype, building, hours, pattern, teachers=None, public=False,
      weeks=None, slot_fixed=None, day_fixed=None, hps=2, sync=False, block_after=False,
      fixed=None):
    return dict(course=course, type=ctype, building=building, hours=hours, pattern=pattern,
                teachers=teachers or {}, public=public, weeks=weeks,
                slot_fixed=slot_fixed, day_fixed=day_fixed, hps=hps, sync=sync,
                block_after=block_after, fixed=fixed or [])


S4 = [
    C("电磁场与波", "理论", "研楼", 48, "full_half",
      teachers={"surrey": "O301", "taiyuan": "O302", "orage": "O303", "sakawa": "O302"}),
    C("模拟电子技术基础", "理论", "研楼", 48, "full_half", sync=True,
      teachers={"surrey": "T1700", "taiyuan": "T1700", "orage": "T1701", "sakawa": "T1702"}),
    C("数字电子技术基础", "理论", "研楼", 48, "full_half", sync=True,
      teachers={"surrey": "T1600", "taiyuan": "T1600", "orage": "T1601", "sakawa": "T1602"}),
    C("马克思主义基本原理", "理论", "综合楼中", 54, "full+part5", public=True,
      teachers={"*": "P06"}, fixed=[(1, 1, list(range(1, 17))), (3, 1, list(range(1, 6)))]),
    C("习近平新时代中国特色社会主义思想概论", "理论", "综合楼中", 36, "full", public=True,
      teachers={"*": "P08"}, fixed=[(2, 1, list(range(1, 17)))]),
    C("Python语言程序设计", "选修", "综合楼中", 32, "full", public=True,
      teachers={"*": "P36"}, fixed=[(3, 7, list(range(1, 17)))]),
    C("模拟电子技术实验", "实验", "物电院", 32, "biweekly", sync=True,
      teachers={"surrey": "E400", "taiyuan": "E400", "orage": "E401", "sakawa": "E402"}, hps=4),
    C("数字电子技术实验", "实验", "物电院", 32, "biweekly", sync=True,
      teachers={"surrey": "E500", "taiyuan": "E500", "orage": "E501", "sakawa": "E502"}, hps=4),
    C("体育（4）", "体育", "体育馆", 32, "full", public=True,
      teachers={"*": "PE"}, day_fixed=2, slot_fixed=5, block_after=True,
      fixed=[(2, 5, list(range(1, 17)))]),
    C("形势与政策(4)", "讲座", "综合楼中", 4, "single", public=True,
      teachers={"*": "P17"}, weeks=[3, 4], slot_fixed=5,
      fixed=[(4, 5, [3, 4])]),
    C("四史·③", "四史", "自习", 15, "single",
      teachers={"orage": "自习"}, weeks=[1, 2, 3, 4, 5], slot_fixed=7, hps=3,
      fixed=[(0, 7, list(range(1, 6)))]),
    C("四史·④", "四史", "自习", 15, "single",
      teachers={"sakawa": "自习"}, weeks=[1, 2, 3, 4, 5], slot_fixed=7, hps=3,
      fixed=[(1, 7, list(range(1, 6)))]),
]


def row_weeks(c, ri):
    p = c["pattern"]
    if p == "full_half":
        return [list(range(1, 17)), list(range(1, 9))][ri]
    if p == "full":
        return list(range(1, 17))
    if p == "full+part5":
        return [list(range(1, 17)), list(range(1, 6))][ri]
    if p == "biweekly":
        return list(range(1, 16, 2))
    if p == "single":
        return c["weeks"]
    raise ValueError(p)


def n_rows(c):
    return {"full_half": 2, "full": 1, "full+part5": 2, "biweekly": 1, "single": 1}[c["pattern"]]


def gap_ok(prev_slot, next_slot):
    if prev_slot not in SLOT_END or next_slot not in SLOT_TIME:
        return False
    h1, m1 = map(int, SLOT_END[prev_slot].split(":"))
    h2, m2 = map(int, SLOT_TIME[next_slot].split(":"))
    return 0 <= (h2 * 60 + m2) - (h1 * 60 + m1) <= 30


def slots_of(c, slot):
    """一次课占用的小节（按时段学时换算）：
    下午 slot5/6 = 90分钟 = 2学时 → 1小节；上午 slot1-4 = 45分钟/节 → 2小节=2学时；
    晚间 slot7-12 = 45分钟/节 → 2小节=2学时；四史3小节=3学时；实验4小节=4学时"""
    if c["type"] in ("体育", "讲座"):
        return [slot]
    if slot in (5, 6):                 # 下午：1小节 = 一次课(2学时)
        return [slot]
    if c["type"] == "四史":            # 3学时 = 晚间3小节（slot7-8-9）
        return [slot, slot + 1, slot + 2]
    if c["type"] == "实验" and c.get("hps", 2) == 4:   # 4学时 = 晚间4小节（slot7-8-9-12）
        return [7, 8, 9, 12] if slot == 7 else [slot]
    return [slot, slot + 1]            # 上午/晚间：2小节


# =====================================================================
# 求解器
# =====================================================================
class Scheduler:
    def __init__(self, courses, only=None):
        self.courses = courses
        self.only = only or GIRLS
        self.solution = {}          # course -> {girl|'*': [(wd, slot, weeks)]}
        self.rooms = {}             # (course, girl|'*', ri) -> room
        # grid[girl][(wd,slot)] = list[(weeks_set, building)]
        self.grid = {g: {} for g in GIRLS}
        self.room_occ = {}          # room -> {(wd,slot): weeks_set}
        self.teacher_occ = {}       # teacher -> {(wd,slot): weeks_set}
        self.nodes = 0

    # ---------- 基础查询 ----------
    def grid_hit(self, girl, wd, slot, weeks):
        return any(w & set(weeks) for w, _ in self.grid[girl].get((wd, slot), []))

    def slot_cands(self, c):
        t = c["type"]
        if t == "实验":
            return [7]                # 4学时一次：晚间4小节(slot7-8-9-12)连续
        if t == "理论":
            return [1, 3, 5, 6]       # 上午2小节(1-2/3-4) 或 下午1小节(5/6)
        if t == "选修":
            return [7, 9]             # 晚间2小节(7-8 / 9-12)
        if t == "讲座":
            return [5, 6]
        return [c["slot_fixed"]]

    # ---------- 行合法性 ----------
    def ok(self, c, girl, wd, slot, weeks, prev_rows):
        self.nodes += 1
        if c["slot_fixed"] is not None and slot != c["slot_fixed"]:
            return False
        if c["day_fixed"] is not None and wd != c["day_fixed"]:
            return False
        if wd == 1 and slot in (5, 6):
            return False
        slots = slots_of(c, slot)
        if not slots:
            return False
        b = BUILDING[c["building"]]
        targets = GIRLS if girl == "*" else [girl]
        for g in targets:
            ggrid = self.grid[g]
            for s in slots:
                # 时间冲突
                if self.grid_hit(g, wd, s, weeks):
                    return False
                # 相邻同楼：邻槽若有课且楼不同 → 冲突
                for nb in (s - 1, s + 1):
                    if nb not in SLOT_TIME:
                        continue
                    if gap_ok(nb, s) if nb < s else gap_ok(s, nb):
                        for (wset, nb_b) in ggrid.get((wd, nb), []):
                            if wset & set(weeks) and nb_b != b:
                                return False
        # 同课两行间隔≥2天
        for (pwd, pslot, pweeks) in prev_rows:
            if abs(wd - pwd) < 2:   # 同课两行间隔≥2天（周内直接距离）
                return False
        # 老师：同老师不同班不同时
        t = c["teachers"].get(girl) or c["teachers"].get("*")
        if t:
            for s in slots:
                if self.teacher_occ.get(t, {}).get((wd, s), set()) & set(weeks):
                    return False
        return True

    def pick_room(self, c, wd, slot, weeks):
        for room in ROOMS[c["building"]]:
            occ = self.room_occ.get(room, {})
            if all(not (occ.get((wd, s), set()) & set(weeks)) for s in slots_of(c, slot)):
                return room
        return None

    # ---------- place / unplace ----------
    def place(self, c, girl, wd, slot, weeks, room, ri):
        b = BUILDING[c["building"]]
        slots = slots_of(c, slot)
        targets = GIRLS if girl == "*" else [girl]
        if girl == "surrey" and c.get("sync"):
            targets.append("taiyuan")
        for g in targets:
            for s in slots:
                self.grid[g].setdefault((wd, s), []).append((set(weeks), b))
        self.room_occ.setdefault(room, {}).setdefault((wd, slot), set()).update(weeks)
        for s in slots:
            self.room_occ.setdefault(room, {}).setdefault((wd, s), set()).update(weeks)
        t = c["teachers"].get(girl) or c["teachers"].get("*")
        if t:
            for s in slots:
                self.teacher_occ.setdefault(t, {}).setdefault((wd, s), set()).update(weeks)
        self.solution.setdefault(c["course"], {}).setdefault(girl, []).append((wd, slot, list(weeks)))
        self.rooms[(c["course"], girl, ri)] = room
        # 体育后第二节禁课（如周三 slot5 体育 → 周三 slot6 留空）
        if c.get("block_after") and slot + 1 in SLOT_TIME:
            for g in targets:
                self.grid[g].setdefault((wd, slot + 1), []).append((set(weeks), "体育馆"))

    def unplace(self, c, girl, wd, slot, weeks, room, ri):
        b = BUILDING[c["building"]]
        slots = slots_of(c, slot)
        targets = GIRLS if girl == "*" else [girl]
        for g in targets:
            for s in slots:
                lst = self.grid[g].get((wd, s), [])
                for i, (wset, nb) in enumerate(lst):
                    if wset == set(weeks):
                        lst.pop(i)
                        break
        for s in slots:
            occ = self.room_occ.get(room, {}).get((wd, s))
            if occ:
                occ.difference_update(weeks)
        t = c["teachers"].get(girl) or c["teachers"].get("*")
        if t:
            for s in slots:
                occ = self.teacher_occ.get(t, {}).get((wd, s))
                if occ:
                    occ.difference_update(weeks)
        self.solution[c["course"]][girl].pop()
        del self.rooms[(c["course"], girl, ri)]
        if c.get("block_after") and slot + 1 in SLOT_TIME:
            for g in targets:
                lst = self.grid[g].get((wd, slot + 1), [])
                for i, (wset, nb) in enumerate(lst):
                    if wset == set(weeks) and nb == "体育馆":
                        lst.pop(i)
                        break

    # ---------- 求解（行任务级回溯）----------
    MAX_NODES = 2_000_000

    def solve(self):
        # 0) 放置固定课（公共课/四史等已定位置：沿用已验证的原课表）
        for c in self.courses:
            if not c.get("fixed"):
                continue
            for ri, (wd, slot, weeks) in enumerate(c["fixed"]):
                room = self.pick_room(c, wd, slot, weeks)
                if room is None:
                    room = ROOMS[c["building"]][0]
                girl = "*" if c["public"] else next(iter(c["teachers"]))
                self.place(c, girl, wd, slot, weeks, room, ri)
        # 1) 展开行任务：仅非固定课
        tasks = []
        for c in self.courses:
            if c.get("fixed"):
                continue
            for ri in range(n_rows(c)):
                weeks = row_weeks(c, ri)
                if c["public"]:
                    tasks.append((c, "*", ri, weeks))
                else:
                    for girl in self.only:
                        if c.get("sync") and girl == "taiyuan":
                            continue   # 电气同班：taiyuan 跟随 surrey 同步放置
                        tasks.append((c, girl, ri, weeks))
        # 排序：研楼理论课先（占用大者优先）
        def key(t):
            c = t[0]
            return (0 if c["type"] == "理论" and c["building"] == "研楼" else 1,
                    -n_rows(c))
        tasks.sort(key=key)
        self.tasks = tasks
        return self._dfs(list(range(len(tasks))))

    def _dfs(self, remaining):
        self.nodes += 1
        if self.nodes > self.MAX_NODES:
            raise TimeoutError("节点超限")
        if not remaining:
            return True
        # MRV：选剩余候选中候选数最少的任务
        best_i, best_cands = None, None
        for i in remaining:
            c, girl, ri, weeks = self.tasks[i]
            prev = self.solution.get(c["course"], {}).get(girl, [])
            cands = []
            for wd in range(5):
                for slot in self.slot_cands(c):
                    if not self.ok(c, girl, wd, slot, weeks, prev):
                        continue
                    room = self.pick_room(c, wd, slot, weeks)
                    if room is not None:
                        cands.append((wd, slot, room))
            if not cands:
                if os.environ.get('DIAG'):
                    print(f'  ⚠️ 无候选: {c["course"]} {girl} ri{ri} W{weeks[0]}-{weeks[-1]}')
                    g_ref = "surrey" if girl == "*" else girl
                    for wd in range(5):
                        for slot in self.slot_cands(c):
                            hit = self.slots_of(c, slot)
                            reason = []
                            for s in hit:
                                for (wset, b) in self.grid[g_ref].get((wd, s), []):
                                    if wset & set(weeks): reason.append(f'{WD_CN[wd]}slot{s}[{b}]W{min(wset)}-{max(wset)}')
                            if reason: print(f'      槽位 {WD_CN[wd]} slot{slot}: 占用 ' + ', '.join(reason))
                return False
            if best_i is None or len(cands) < len(best_cands):
                best_i, best_cands = i, cands
                if len(cands) == 1:
                    break
        c, girl, ri, weeks = self.tasks[best_i]
        new_remaining = remaining[:] 
        new_remaining.remove(best_i)
        # 候选排序：分散天启发式
        g_ref = "surrey" if girl == "*" else girl
        def ckey(item):
            wd, slot, room = item
            score = sum(len(self.grid[g_ref].get((wd, s), [])) for s in slots_of(c, slot))
            return (SLOT_PREF.get(slot, 9), score, wd, slot)
        best_cands.sort(key=ckey)
        for wd, slot, room in best_cands:
            self.place(c, girl, wd, slot, weeks, room, ri)
            log(f"{c['course']} {girl} ri{ri} {WD_CN[wd]} slot{slot} W{weeks[0]}-{weeks[-1]} {room}")
            if self._dfs(new_remaining):
                return True
            self.unplace(c, girl, wd, slot, weeks, room, ri)
        return False





# =====================================================================
# 校验 + 渲染 + 写库
# =====================================================================
GIRL_CN = {"surrey": "萨里", "orage": "暴风雨", "sakawa": "酒匂", "taiyuan": "太原"}
MAJOR = {"surrey": "电气工程", "taiyuan": "电气工程", "orage": "自动化", "sakawa": "测控"}
LABEL = {"surrey": "皇家重巡", "orage": "自由鸢尾驱逐", "sakawa": "重樱轻巡", "taiyuan": "东煌驱逐"}
SEM_LABEL = {4: "大二下(2023-24-2)"}


def fmt_w(weeks):
    wl = sorted(weeks)
    if wl == list(range(1, 17)): return "1-16周"
    if wl == list(range(1, 9)): return "1-8周"
    if wl == list(range(1, 6)): return "1-5周"
    if wl == [3, 4]: return "3,4周"
    if all(x % 2 == 1 for x in wl): return f"单周{wl[0]}-{wl[-1]}"
    return f"{wl[0]}-{wl[-1]}周"


def verify(s):
    """独立校验：时间/相邻楼/时段/周二禁/间隔/老师/教室"""
    errs = []
    rooms_occ = {}   # room -> {(wd, slot): weeks}
    teacher_occ = {}
    for c in s.courses:
        for girl, rows in s.solution.get(c["course"], {}).items():
            targets = GIRLS if girl == "*" else [girl]
            b = BUILDING[c["building"]]
            for ri, (wd, slot, weeks) in enumerate(rows):
                weeks_set = set(weeks)
                # 时段
                if c["type"] == "实验" and not (set(slots_of(c, slot)) & (AFTERNOON | EVENING)):
                    errs.append(f"{c['course']} {girl} 实验时段非法 slot{slot}")
                if c["type"] == "理论" and any(s not in DAYTIME for s in slots_of(c, slot)):
                    errs.append(f"{c['course']} {girl} 理论课晚间 slot{slot}")
                # 周二下午
                if wd == 1 and slot in (5, 6):
                    errs.append(f"{c['course']} {girl} 周二下午禁课违规")
                # 同课间隔
                for (pwd, pslot, pweeks) in rows[:ri]:
                    if abs(wd - pwd) < 2:
                        errs.append(f"{c['course']} {girl} 行间隔<2天 ({WD_CN[pwd]}→{WD_CN[wd]})")
                # 时间冲突 + 相邻楼（per target）
                for g in targets:
                    ggrid = s.grid[g]
                    for s_ in slots_of(c, slot):
                        for (wset, nb) in ggrid.get((wd, s_), []):
                            if wset == weeks_set:
                                continue
                            if wset & weeks_set:
                                errs.append(f"{c['course']} {g} {WD_CN[wd]} slot{s_} 时间冲突")
                        # 相邻楼
                        for nb_s in (s_ - 1, s_ + 1):
                            if nb_s not in SLOT_TIME: continue
                            if gap_ok(nb_s, s_) if nb_s < s_ else gap_ok(s_, nb_s):
                                for (wset, nb_b) in ggrid.get((wd, nb_s), []):
                                    if wset & weeks_set and nb_b != b:
                                        errs.append(f"{c['course']} {g} {WD_CN[wd]} slot{s_} 相邻{WD_CN[wd]}slot{nb_s} 不同楼({b} vs {nb_b})")
                # 教室唯一
                room = s.rooms.get((c["course"], girl, ri))
                if room:
                    for s_ in slots_of(c, slot):
                        occ = rooms_occ.setdefault(room, {}).setdefault((wd, s_), set())
                        if occ & weeks_set:
                            errs.append(f"{c['course']} {girl} 教室{room} 冲突")
                        occ.update(weeks_set)
                # 老师
                t = c["teachers"].get(girl) or c["teachers"].get("*")
                if t:
                    for s_ in slots_of(c, slot):
                        occ = teacher_occ.setdefault(t, {}).setdefault((wd, s_), set())
                        if occ & weeks_set:
                            errs.append(f"{c['course']} {girl} 老师{t} 同时两班")
                        occ.update(weeks_set)
    return errs


def render_md(s, girl):
    """渲染 girl_schedules/{girl}_sem4.md（与 render_major 格式一致）"""
    cfg_major = MAJOR[girl]
    # 课表格：(wd, slot) -> [(课名, 周次串, 老师, 教室)]
    cell = {}
    for c in s.courses:
        for g, rows in s.solution.get(c["course"], {}).items():
            if g != "*" and g != girl and not (c.get("sync") and girl == "taiyuan" and g == "surrey"):
                continue   # 电气同班：taiyuan 复用 surrey 行
            for ri, (wd, slot, weeks) in enumerate(rows):
                room = s.rooms.get((c["course"], g, ri), "")
                t = c["teachers"].get(girl) or c["teachers"].get("*")
                name = c["course"]
                if name.startswith("四史"):
                    name = {"四史·③": "改革开放史", "四史·④": "新中国史"}.get(name, name)
                if c["type"] == "体育":
                    name = {"surrey": "体育舞蹈·提高", "orage": "田径", "sakawa": "瑜伽·提高", "taiyuan": "武术·提高"}[girl]
                    t = {"surrey": "PE-舞蹈组A", "orage": "PE-定向越野队", "sakawa": "PE-瑜伽组B", "taiyuan": "PE-武术组C"}[girl]
                for s_ in slots_of(c, slot):
                    cell.setdefault((wd, s_), []).append((name, fmt_w(weeks), t, room))
    lines = []
    SLOT_LABEL = [(1, "第一节①", "08:00-08:45"), (2, "第一节②", "08:55-09:40"),
                  (3, "第二节①", "09:50-10:45"), (4, "第二节②", "10:55-11:40"),
                  (5, "第三节", "14:30-16:00"), (6, "第四节", "16:10-17:40"),
                  (7, "第五节①", "19:00-19:45"), (8, "第五节②", "19:55-20:40"),
                  (9, "第五节③", "20:50-21:35"), (12, "第五节④", "21:35-22:20")]
    for s_, lab, tm in SLOT_LABEL:
        line = f"| {lab} {tm} |"
        for wd in range(5):
            parts = []
            for (name, wstr, t, room) in sorted(cell.get((wd, s_), []), key=lambda x: x[1]):
                tg = "🔬" if "实验" in name else ""
                loc = f"·{room}" if room and room != "自习（无教室）" else ""
                tstr = f"·{t}" if t and t != "自习" else ""
                parts.append(f"{name}{tg}{wstr}{tstr}{loc}")
            line += (" " + "<br>".join(parts) + " |") if parts else " — |"
        lines.append(line)
    return (f"# {girl.capitalize()}（{LABEL[girl]} · {MAJOR[girl]}专业） · {SEM_LABEL[4]}\n\n"
            f"> **第4学期 完整固定课表** · 专业班级：{MAJOR[girl]}（智能排课器生成）\n\n"
            f"| 时段 | 周一 | 周二 | 周三 | 周四 | 周五 |\n|---|---|---|---|---|---|\n"
            + "\n".join(lines) + "\n")


def export_db(s):
    """写入 db 新表 girl_course_schedule（供 virtual_time 查询）"""
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    # 补第4学期 terms（rebuild 跳过 S4 共享排课，但学期时间线必须存在）
    cur.execute("INSERT OR IGNORE INTO terms (semester_no, term_code, start_date, end_date, note) "
                "VALUES (4, '2023-24-2', '2024-02-26', '2024-06-30', '第4学期（2023-2024学年第二学期）')")
    cur.execute("""CREATE TABLE IF NOT EXISTS girl_course_schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT, girl TEXT, semester_no INTEGER,
        course TEXT, weekday INTEGER, slot_index INTEGER, session_weeks TEXT,
        hours REAL, course_type TEXT, teacher TEXT, location TEXT, has_seminar INTEGER)""")
    cur.execute("DELETE FROM girl_course_schedule WHERE semester_no=4")
    hps = {c["course"]: c["hps"] for c in s.courses}
    SISHI_NAME = {"四史·③": "改革开放史", "四史·④": "新中国史"}
    PE_NAME = {"surrey": "体育舞蹈·提高", "orage": "田径", "sakawa": "瑜伽·提高", "taiyuan": "武术·提高"}
    for c in s.courses:
        for g, rows in s.solution.get(c["course"], {}).items():
            targets = GIRLS if g == "*" else [g]
            for ri, (wd, slot, weeks) in enumerate(rows):
                room = s.rooms.get((c["course"], g, ri), "")
                t = c["teachers"].get("*") if g == "*" else c["teachers"].get(g, "")
                if c.get("sync") and g == "surrey":
                    targets = [g, "taiyuan"]   # 电气同班同步
                for girl in targets:
                    # 渲染名（virtual_time/syllabus 用）
                    cname = c["course"]
                    if cname in SISHI_NAME:
                        cname = SISHI_NAME[cname]
                    elif c["type"] == "体育":
                        cname = PE_NAME[girl]
                        t = {"surrey": "PE-舞蹈组A", "orage": "PE-定向越野队",
                             "sakawa": "PE-瑜伽组B", "taiyuan": "PE-武术组C"}[girl]
                    for s_ in slots_of(c, slot):
                        cur.execute(
                            "INSERT INTO girl_course_schedule "
                            "(girl, semester_no, course, weekday, slot_index, session_weeks, hours, course_type, teacher, location, has_seminar) "
                            "VALUES (?,?,?,?,?,?,?,?,?,?,0)",
                            (girl, 4, cname, wd, s_, ",".join(map(str, weeks)),
                             hps.get(c["course"], 2) / len(slots_of(c, slot)),
                             c["type"], t or "", room or "", ))
    conn.commit()
    n = cur.execute("SELECT COUNT(*) FROM girl_course_schedule WHERE semester_no=4").fetchone()[0]
    conn.close()
    return n


if __name__ == "__main__":
    s = Scheduler(S4)
    ok = s.solve()
    print(f"求解完成: {'✅ 全部课程排定' if ok else '❌ 无解'} (节点 {s.nodes})")
    if not ok:
        sys.exit(1)
    errs = verify(s)
    print(f"独立校验: {'✅ 0 问题' if not errs else '❌ ' + str(len(errs)) + ' 处'}")
    for e in errs[:20]:
        print("  ", e)
    if errs:
        sys.exit(1)
    if "--apply" in sys.argv:
        (BASE / "girl_schedules").mkdir(exist_ok=True)
        for g in GIRLS:
            (BASE / "girl_schedules" / f"{g}_sem4.md").write_text(render_md(s, g), encoding="utf-8")
        n = export_db(s)
        print(f"✅ 4份课表已渲染 → girl_schedules/*_sem4.md; db 写入 {n} 行 → girl_course_schedule")
    elif "--dry" not in sys.argv:
        for g in GIRLS:
            print(f"--- {g} ---")
            print(render_md(s, g))
