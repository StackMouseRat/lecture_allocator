#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用选修课内容渲染：把课表中的占位符（通识选修·晚间① 等）替换为自定义课程名。
内容来自 data/elective_content.json；girl 为 4 位舰娘代号（surrey/orage/sakawa/taiyuan）。
"""
import json
from pathlib import Path

BASE = Path(__file__).parent
_CONTENT = None

def load_content() -> dict:
    global _CONTENT
    if _CONTENT is None:
        _CONTENT = json.load(open(BASE / "data" / "elective_content.json", encoding="utf-8"))
    return _CONTENT

def render_name(placeholder: str, girl: str = "default") -> str:
    """占位符 → 具体课程名（按人设）"""
    m = load_content().get(placeholder)
    if not m:
        return placeholder
    return m.get(girl) or m.get("default") or placeholder

def render_table(text: str, girl: str = "default") -> str:
    """替换文本中的所有选修占位符"""
    for ph in load_content():
        text = text.replace(ph, render_name(ph, girl))
    return text

def apply_to_db(girl: str = "default"):
    """（可选）直接更新数据库中的占位符为具体课程名（girl=default 时写入默认课程）"""
    import sqlite3
    conn = sqlite3.connect(BASE / "db" / "virtual_time.db")
    for ph, m in load_content().items():
        name = m.get(girl) or m.get("default") or ph
        if name == ph:
            continue
        conn.execute("UPDATE virtual_course_schedule SET course=? WHERE course=?", (name, ph))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    import sys
    girl = sys.argv[1] if len(sys.argv) > 1 else "default"
    apply_to_db(girl)
    print(f"✅ 已应用选修内容映射（girl={girl}）")
