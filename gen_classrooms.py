#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""综合楼教室模型：5层，每层15个编号(X01-X15)
- X10 = 办公室（不用于上课）
- 1-2楼：X04/X05 = 大教室；其余(X01-03,06-09,11-15) = 中教室
- 3-5楼：X01-03,06-09,11-15 = 中教室；X04/X05 = 小教室
生成 data/classrooms.json"""
import json
from pathlib import Path

rooms = {}
for floor in range(1, 6):
    for n in range(1, 16):
        num = f"{floor}{n:02d}"
        if n == 10:
            rooms[num] = {"type": "办公室"}
        elif floor <= 2:
            rooms[num] = {"type": "大教室" if n in (4, 5) else "中教室"}
        else:
            rooms[num] = {"type": "中教室" if n in (1,2,3,6,7,8,9,11,12,13,14,15) else "小教室"}

data = {
    "综合楼": {
        "floors": 5, "per_floor": 15, "office": "X10",
        "rooms": rooms
    }
}
Path("data/classrooms.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

from collections import Counter
cnt = Counter(r["type"] for r in rooms.values())
print("✅ 综合楼教室模型已生成：")
print(f"   共{len(rooms)}个房间（含办公室{cnt['办公室']}）")
print(f"   大教室{cnt['大教室']}个: 104,105,204,205")
print(f"   中教室{cnt['中教室']}个（每层12个）")
print(f"   小教室{cnt['小教室']}个: 304,305,404,405,504,505")
print(f"   办公室{cnt['办公室']}个: 110,210,310,410,510")
