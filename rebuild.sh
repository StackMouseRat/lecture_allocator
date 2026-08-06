#!/bin/bash
# 一键全量重建 + 智能偏移求解 + 渲染 + 全部校验（唯一标准流程）
set -e
cd "$(dirname "$0")"
echo "=== ① 全量重建 db ==="
rm -f db/virtual_time.db
python3 db_schema.py            # Schema 初始化（唯一权威）
python3 build_semesters.py 1 2 3 4 5 6
echo "=== ② 智能偏移求解（CSP 最小变更，自动避免渲染层冲突）==="
python3 assign_offsets.py
echo "=== ③ 渲染课表 ==="
python3 render_major.py
echo "=== ④ 时间冲突校验（db 层）==="
python3 check_conflicts.py | tail -1
echo "=== ⑤ 渲染层冲突校验（老师偏移后）==="
python3 check_render.py | tail -1
echo "=== ⑥ 地点冲突校验 ==="
python3 check_locations.py | tail -1
echo "=== ⑦ 数据完整性自检 ==="
python3 check_data.py
echo "=== ✅ 重建完成 ==="
