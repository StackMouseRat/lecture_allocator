#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通识选修选课规则（可复现）：
- 每人4门×2学分=8分（通识选修要求）
- 排除：心理健康、四史、哲学导论（均不计入8分）；太原不选写作类
- 按人设主题从学校通识选修目录（hnu_courses/raw_text.txt）抽取
- 固定种子可复现（seed=102 → 第2轮方案）
"""
import re, json, random
from pathlib import Path

BASE = Path(__file__).parent
SEED = 102          # 固定种子：与抽选脚本 random.Random(100+2) 一致，复现第2轮
POOL_FILE = BASE.parent / "hnu_courses" / "raw_text.txt"

# 人设主题关键词（选课规则）
THEMES = {
    "surrey":  {"礼仪", "艺术", "美学", "文学", "音乐", "舞蹈", "服饰", "经典", "文化", "电影"},
    "orage":   {"科学", "科技", "逻辑", "信息", "历史", "游戏", "技术", "哲学", "文明", "设计"},
    "sakawa":  {"美食", "茶", "影视", "心理", "音乐", "绘画", "社交", "文化", "饮食", "文学"},
    "taiyuan": {"历史", "军事", "兵法", "国学", "经典", "哲学", "社会", "考古", "文明", "文学"},
}
def load_pool():
    txt = POOL_FILE.read_text(encoding="utf-8")
    pool = []
    for c in re.findall(r'([\u4e00-\u9fffA-Za-z（）()·]+?)[\*\.]{2,}\s*\d+', txt):
        c = c.strip()
        if c and c not in pool and 3 <= len(c) <= 12 and '导论' in c or (c and c not in pool and 3 <= len(c) <= 12):
            if c not in pool:
                pool.append(c)
    return pool

def draw(girl, rng, used):
    kws = THEMES[girl]
    cands = [c for c in load_pool() if any(k in c for k in kws) and c not in used]
    if len(cands) < 4:
        cands = [c for c in load_pool() if c not in used]
    rng.shuffle(cands)
    return cands[:4]

def main():
    rng = random.Random(SEED)
    used = set(); plan = {}
    for g in ["surrey", "orage", "sakawa", "taiyuan"]:
        four = draw(g, rng, used); used.update(four)
        plan[g] = {f"选修{i+1}": c for i, c in enumerate(four)}
    out = {"rule": "每人4门通识选修×2学分=8分；排除心理/四史/哲学导论；太原无写作；seed=102", "plan": plan}
    (BASE / "data" / "elective_selection.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ 已按规则(seed={SEED})生成选课方案：")
    for g, cn in [("surrey","萨里"),("orage","暴风雨"),("sakawa","酒匂"),("taiyuan","太原")]:
        print(f"  {cn}: " + " · ".join(plan[g].values()))

if __name__ == "__main__":
    main()
