#!/bin/bash
# 一键全量重建 + 智能偏移求解 + 渲染 + 全部校验（唯一标准流程）
set -e
cd "$(dirname "$0")"
echo "=== ① 全量重建 db（第4学期由智能排课器生成，不在此排）==="
rm -f db/virtual_time.db
python3 db_schema.py            # Schema 初始化（唯一权威）
python3 build_semesters.py 1 2 3 5 6
echo "=== ② 第4学期智能排课（CSP per-girl，研楼三门/实验时段/相邻同楼全约束）==="
python3 scheduler.py --apply
echo "=== ③ 智能偏移求解（第1-3学期 CSP 最小变更，避免渲染层冲突）==="
python3 assign_offsets.py
echo "=== ④ 渲染课表（第1-3学期；第4学期已由②生成）==="
python3 render_major.py
echo "=== ⑤ 时间冲突校验（db 层 S1-3）==="
python3 check_conflicts.py | tail -1
echo "=== ⑥ 渲染层冲突校验（S1-3 老师偏移后）==="
python3 check_render.py | tail -1
echo "=== ⑦ 地点冲突校验（S1-4）==="
python3 check_locations.py | tail -1
echo "=== ⑧ 数据完整性自检 ==="
python3 check_data.py
echo "=== ✅ 重建完成 ==="
