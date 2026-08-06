#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能偏移分配器（CSP 求解 · 按人分解 + MRV）
============================================================
db 是"班级共享课表"（无 girl 维度），渲染层按 teachers.json 的
assign[girl].offset 做天偏移，为 3 个专业班（电气/自动化/测控）和可选课
生成各自渲染课表。手工维护 offset 易产生渲染层冲突（db 0 冲突 ≠ 渲染 0 冲突）。

对每门"班级差异化课"×每人自动求解 offset ∈ {0..4}：
  ① 渲染后 4 人 × 6 学期 0 时间冲突（与 check_render 同口径）
  ② 周二下午(slot5/6)禁课；实验课仅下午/晚间（集中实践全天块允许）
  ③ 同班同步：电气班(surrey/taiyuan)同门课同时间
  ④ 同老师错开：同老师带的不同班时间必须错开（目前仅电磁场 O302）

效率设计：4 人课表相互独立（不同老师），按 girl 分解求解；
每个 girl 内用 MRV（最少剩余候选优先）+ 节点上限保护。

用法
    python3 assign_offsets.py            # 求解并写回
    python3 assign_offsets.py --dry      # 只求解不写回
    python3 assign_offsets.py --debug    # 打印求解轨迹
"""
import json
import sqlite3
import sys
import shutil
from pathlib import Path

BASE = Path(__file__).parent
DB = BASE / "db" / "virtual_time.db"
TEACHERS_FILE = BASE / "data" / "teachers.json"
ELECTIVE_FILE = BASE / "data" / "elective_content.json"

DEBUG = "--debug" in sys.argv
DRY = "--dry" in sys.argv
MAX_NODES = 2_000_000

GIRLS = ["surrey", "orage", "sakawa", "taiyuan"]
EE_GROUP = {"surrey", "taiyuan"}
AFTERNOON_EVENING = {5, 6, 7, 8, 9, 10}
PREF = {"surrey": [0], "taiyuan": [0], "orage": [2, 0, 3, 1, 4], "sakawa": [3, 0, 2, 1, 4]}
PREF_RANK = {g: {o: i for i, o in enumerate(lst)} for g, lst in PREF.items()}


def log(msg):
    if DEBUG:
        print(f"  [CSP] {msg}")


# ------------------------------------------------------------------
def load_data():
    teachers = json.load(open(TEACHERS_FILE, encoding="utf-8"))
    elective = json.load(open(ELECTIVE_FILE, encoding="utf-8"))
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    course_rows = {}  # course -> sem -> [(wd, slot, weeks, ctype)]
    for r in conn.execute("SELECT semester_no, course, weekday, slot_index, session_weeks, course_type "
                          "FROM virtual_course_schedule ORDER BY semester_no, weekday, slot_index"):
        weeks = {int(x) for x in r["session_weeks"].split(",") if x.strip()}
        course_rows.setdefault(r["course"], {}).setdefault(r["semester_no"], []).append(
            (r["weekday"], r["slot_index"], weeks, r["course_type"]))
    conn.close()

    adjustable = {c for c, info in teachers.items()
                  if any(a.get("offset", 0) != 0 for a in info.get("assign", {}).values())}

    def elective_selected(girl, cname):
        if ("选修" not in cname) and not cname.startswith("四史"):
            return True
        m = elective.get(cname)
        if not m:
            return False
        n = m.get(girl) or m.get("default")
        return n not in (None, "未选")

    return teachers, course_rows, adjustable, elective_selected


# ------------------------------------------------------------------
def build_fixed_occ(course_rows, adjustable, elective_selected, teachers):
    """固定课（非可调）渲染后占用：occ[girl][sem][(wd,slot)] = weeks"""
    occ = {g: {sem: {} for sem in range(1, 7)} for g in GIRLS}
    for cname, by_sem in course_rows.items():
        if cname in adjustable:
            continue
        for sem, rows in by_sem.items():
            for (wd, slot, weeks, ctype) in rows:
                for g in GIRLS:
                    if not elective_selected(g, cname):
                        continue
                    a = teachers.get(cname, {}).get("assign", {}).get(g, {})
                    wd2 = (wd + a.get("offset", 0)) % 5
                    occ[g][sem].setdefault((wd2, slot), set()).update(weeks)
    return occ


# ------------------------------------------------------------------
class Solver:
    """按 girl 分组求解 · 分支定界最小化变更。
    目标：在 0 时间冲突前提下，尽可能保持现有 offset（成本 0），
    不得已才调整（成本 1）——即"最小改动"的最优解。"""

    def __init__(self, teachers, course_rows, fixed_occ, vars_, teacher_pairs, cur_val=None):
        self.teachers = teachers
        self.course_rows = course_rows
        self.fixed_occ = fixed_occ
        self.vars_ = vars_
        self.teacher_pairs = teacher_pairs  # [(course, g1, g2)] 同老师需错开
        self.cur = cur_val or {}
        self.assigned = {}
        self.added_occ = {g: {sem: {} for sem in range(1, 7)} for g in GIRLS}
        self.nodes = 0
        self.best_cost = float("inf")
        self.best_solution = None

    # -- 基础候选（仅固定占用 + 硬规则）--
    def base_candidates(self, course, girl):
        cand = []
        for off in range(5):
            ok = True
            for sem, rows in self.course_rows.get(course, {}).items():
                occ = self.fixed_occ[girl][sem]
                for (wd, slot, weeks, ctype) in rows:
                    wd2 = (wd + off) % 5
                    if wd2 == 1 and slot in (5, 6):
                        ok = False; break
                    if ctype == "实验" and slot not in AFTERNOON_EVENING:
                        ok = False; break
                    if any(w in occ.get((wd2, slot), set()) for w in weeks):
                        ok = False; break
                if not ok:
                    break
            if ok:
                cand.append(off)
        return cand

    # -- 实时候选（基础候选 - 与已赋值可调课冲突 - 老师约束）--
    def live_candidates(self, course, girl, base):
        good = []
        for off in base:
            if self.conflicts_added(course, girl, off):
                continue
            if not self.teacher_ok(course, girl, off):
                continue
            good.append(off)
        return good

    def conflicts_added(self, course, girl, off):
        for sem, rows in self.course_rows.get(course, {}).items():
            added = self.added_occ[girl][sem]
            for (wd, slot, weeks, ctype) in rows:
                wd2 = (wd + off) % 5
                if any(w in added.get((wd2, slot), set()) for w in weeks):
                    return True
        return False

    def teacher_ok(self, course, girl, off):
        t = self.teachers.get(course, {}).get("assign", {}).get(girl, {}).get("teacher")
        if not t:
            return True
        for (c2, g1, g2) in self.teacher_pairs:
            if c2 != course:
                continue
            if girl not in (g1, g2):
                continue
            other = g2 if girl == g1 else g1
            o = self.assigned.get((course, other))
            if o is not None and o == off:
                return False
        return True

    def commit(self, course, girl, off):
        self.assigned[(course, girl)] = off
        for sem, rows in self.course_rows.get(course, {}).items():
            for (wd, slot, weeks, ctype) in rows:
                wd2 = (wd + off) % 5
                self.added_occ[girl][sem].setdefault((wd2, slot), set()).update(weeks)

    def rollback(self, course, girl):
        off = self.assigned.pop((course, girl))
        for sem, rows in self.course_rows.get(course, {}).items():
            for (wd, slot, weeks, ctype) in rows:
                wd2 = (wd + off) % 5
                cell = self.added_occ[girl][sem].get((wd2, slot))
                if cell:
                    cell.difference_update(weeks)
                    if not cell:
                        del self.added_occ[girl][sem][(wd2, slot)]

    def solve_group(self, group):
        """group: [(course, girl, base_cands)]，分支定界最小化变更。返回 (最小成本, 最优解)。"""
        self.base = {(c, g): list(cands) for (c, g, cands) in group}
        self.best_cost = float("inf")
        self.best_solution = None
        keys = list(self.base.keys())
        self._dfs(keys, 0)
        # 回滚本组全部赋值，再重放最优解（保证 assigned/added_occ 与 best 一致，供下组同老师约束使用）
        for (c, g) in keys:
            if (c, g) in self.assigned:
                self.rollback(c, g)
        if self.best_solution is not None:
            for (c, g), off in self.best_solution.items():
                if (c, g) in self.base:
                    self.commit(c, g, off)
        return self.best_cost, self.best_solution

    def _dfs(self, remaining, cost):
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise TimeoutError("节点数超限")
        if cost >= self.best_cost:
            return
        if not remaining:
            if cost < self.best_cost:
                self.best_cost = cost
                self.best_solution = dict(self.assigned)
                log(f"★ 新最优: 变更 {cost} (节点 {self.nodes})")
            return
        # MRV：选剩余候选最少的变量
        best_key, best_idx, best_cands = None, -1, None
        for i, key in enumerate(remaining):
            course, girl = key
            cands = self.live_candidates(course, girl, self.base[key])
            if not cands:
                return
            if best_key is None or len(cands) < len(best_cands):
                best_key, best_idx, best_cands = key, i, cands
                if len(cands) == 1:
                    break
        course, girl = best_key
        new_remaining = remaining[:best_idx] + remaining[best_idx + 1:]
        # 当前值优先（成本0），其余按偏好
        cur = self.cur.get(best_key)
        ordered = sorted(best_cands,
                         key=lambda o: (0 if o == cur else 1, PREF_RANK[girl].get(o, 99)))
        for off in ordered:
            new_cost = cost + (0 if off == cur else 1)
            if new_cost >= self.best_cost:
                continue
            self.commit(course, girl, off)
            log(f"{course} / {girl} = {off}")
            self._dfs(new_remaining, new_cost)
            self.rollback(course, girl)
        return


# ------------------------------------------------------------------
def main():
    teachers, course_rows, adjustable, elective_selected = load_data()
    fixed_occ = build_fixed_occ(course_rows, adjustable, elective_selected, teachers)

    # 变量（电气班 core/lab 固定 0；电磁场全员可调）
    vars_ = []
    for c in sorted(adjustable):
        if c not in course_rows:
            continue
        for g in GIRLS:
            if g in EE_GROUP and c != "电磁场与波":
                continue
            vars_.append((c, g))

    # 同老师需错开：电磁场 O302 带 taiyuan+sakawa
    teacher_pairs = []
    t2g = {}
    for g in GIRLS:
        t = teachers.get("电磁场与波", {}).get("assign", {}).get(g, {}).get("teacher")
        if t:
            t2g.setdefault(t, []).append(g)
    for t, gs in t2g.items():
        for i in range(len(gs)):
            for j in range(i + 1, len(gs)):
                if not (gs[i] in EE_GROUP and gs[j] in EE_GROUP):
                    teacher_pairs.append(("电磁场与波", gs[i], gs[j]))

    print(f"可调课 {len(adjustable)} 门 / 变量 {len(vars_)} 个（电气班 core/lab 固定 0，电磁场全员可调）")

    cur_val = {(c, g): teachers.get(c, {}).get("assign", {}).get(g, {}).get("offset", 0)
               for (c, g) in vars_}

    # 基础候选预检（无解则说明固定课已占满，需 db 调整）
    probe = Solver(teachers, course_rows, fixed_occ, vars_, [])
    base = {key: probe.base_candidates(*key) for key in vars_}
    dead = [key for key, c in base.items() if not c]
    if dead:
        print("❌ 基础候选为空（固定课已把该格占满，需 db 调整基准行）:")
        for key in dead:
            print(f"   - {key[0]} / {key[1]}")
        return 1

    # 按 girl 分组求解（顺序：orage → sakawa → taiyuan → surrey；同老师约束后置者）
    order = ["orage", "sakawa", "taiyuan", "surrey"]
    solution = {}
    total_cost = 0
    mode = "strict"

    def run(groups, tp):
        sol = {}
        cost = 0
        s = Solver(teachers, course_rows, fixed_occ, vars_, tp, cur_val=cur_val)
        for g in order:
            group = [(c, gg, cands) for (c, gg, cands) in groups if gg == g]
            c, best = s.solve_group(group)
            if best is None:
                return None, None, s.nodes
            cost += c
            sol.update(best)
        return sol, cost, s.nodes

    try:
        solution, total_cost, nodes = run([(c, g, base[(c, g)]) for (c, g) in vars_], teacher_pairs)
        if solution is None:
            mode = "relaxed"
            print("  ⚠️ 同老师错开约束无解（共享行模型表达力上限），自动放宽为『合班模式』…")
            solution, total_cost, nodes = run([(c, g, base[(c, g)]) for (c, g) in vars_], [])
        if solution is None:
            print("  ❌ 合班模式仍无解 —— 该课需 db 基准行调整（见报告）")
            return 1
        print(f"  求解完成：变更 {total_cost} 处，约束检查 {nodes} 节点")
    except TimeoutError as e:
        print(f"❌ {e} —— 解空间过大，需进一步剪枝")
        return 1

    warn = check_teacher_same_time(teachers, course_rows, solution)
    if warn:
        print(f"\n⚠️ 同老师同时刻上课（不同班合班，确认可接受）:")
        for w in warn:
            print(f"   - {w}")

    # 报告
    cur = {(c, g): teachers.get(c, {}).get("assign", {}).get(g, {}).get("offset", 0)
           for (c, g) in vars_}
    changed = [(c, g, cur[(c, g)], solution[(c, g)]) for (c, g) in vars_ if solution[(c, g)] != cur[(c, g)]]
    print(f"\n=== 求解报告：{len(changed)} 处偏移调整 ===")
    by_course = {}
    for (c, g, o, n) in sorted(changed, key=lambda x: x[0]):
        by_course.setdefault(c, []).append(f"{g} {o}→{n}")
    for c, lst in by_course.items():
        print(f"  {c}: " + ", ".join(lst))

    if not DRY:
        backup = TEACHERS_FILE.with_suffix(".json.bak")
        if not backup.exists():
            shutil.copy(TEACHERS_FILE, backup)
            print(f"\n已备份原文件 → {backup.name}")
        for (c, g) in vars_:
            teachers[c]["assign"][g]["offset"] = solution[(c, g)]
        json.dump(teachers, open(TEACHERS_FILE, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print("✅ 已写回 data/teachers.json（建议立即 rebuild.sh 验证）")
    return 0


def check_teacher_same_time(teachers, course_rows, solution):
    """渲染后同老师同时刻给多个不同班上课 → 警告（合班模式，不阻塞）"""
    warn = []
    for c in course_rows:
        assign = teachers.get(c, {}).get("assign", {})
        t2g = {}
        for g in GIRLS:
            t = assign.get(g, {}).get("teacher")
            if t:
                t2g.setdefault(t, []).append(g)
        for t, gs in t2g.items():
            if len(gs) < 2:
                continue
            for i in range(len(gs)):
                for j in range(i + 1, len(gs)):
                    g1, g2 = gs[i], gs[j]
                    if g1 in EE_GROUP and g2 in EE_GROUP:
                        continue  # 同班
                    o1 = solution.get((c, g1)); o2 = solution.get((c, g2))
                    if o1 is None or o2 is None:
                        continue
                    if o1 == o2:
                        warn.append(f"{c} · 老师{t} 同时带 {g1}(off={o1}) 与 {g2}(off={o2})（合班）")
    return warn


if __name__ == "__main__":
    sys.exit(main())
