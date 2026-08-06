#!/bin/bash
# 一键全量重建 + 渲染 + 全部校验（唯一标准流程）
set -e
cd "$(dirname "$0")"
echo "=== ① 全量重建 db ==="
rm -f db/virtual_time.db
python3 db_schema.py            # Schema 初始化（唯一权威）
python3 build_semesters.py 1 2 3 4 5 6
echo "=== ② 渲染课表 ==="
python3 render_major.py
echo "=== ③ 时间冲突校验 ==="
python3 check_conflicts.py | tail -1
echo "=== ④ 地点冲突校验 ==="
python3 check_locations.py | tail -1
echo "=== ⑤ 数据完整性自检 ==="
python3 check_data.py
echo "=== ✅ 重建完成 ==="
