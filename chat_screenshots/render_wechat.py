#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""微信风格聊天截图渲染器 v3（纯 PIL 离线渲染）
v3: 同人连续消息合并为一组 —— 头像只显示组尾, 组内气泡紧贴, 组首对方显示昵称
用法: python3 render_wechat.py input.md 群名 输出.png [--max-height N]
输入: **【12月1日 19:42】** 时间节点; **名字**：内容 消息(首个=自己/右侧绿泡)
"""
import re, sys, os
from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/wenquanyi/wqy-microhei/wqy-microhei.ttc"
AVATARS = [f"/workspace/blhx_scheduler/chat_screenshots/avatars/avatar_{i}.png" for i in (1, 2, 3, 4)]
AVATAR_DIR = "/workspace/blhx_scheduler/chat_screenshots/avatars"

W = 750
BG = (237, 237, 237)
STATUS_H, NAV_H = 56, 132
MARGIN = 24
AV = 96
NAME_SIZE, TEXT_SIZE, TIME_SIZE = 24, 31, 22
PAD_X, PAD_Y = 22, 16
RADIUS = 14
AV_GAP = 20
LINE_H = TEXT_SIZE + 10
GAP_GROUP = 30        # 组间距(换人/时间)
GAP_IN_GROUP = 6       # 组内气泡间距
SELF_GREEN = (149, 236, 105)
NAME_GRAY = (178, 178, 178)
TIME_GRAY = (178, 178, 178)
LEFT_BUBBLE = MARGIN + AV + AV_GAP        # 140 对方气泡左线
RIGHT_BUBBLE = W - MARGIN - AV - AV_GAP   # 610 自己气泡右线
MAX_BUBBLE = RIGHT_BUBBLE - LEFT_BUBBLE - PAD_X * 2

MD_MSG = re.compile(r'^\*\*(.+?)\*\*\s*[：:]\s*(.+)$')
MD_TIME = re.compile(r'^\*{0,2}【(.+?)】\*{0,2}$')


def parse(text):
    users, msgs = [], []
    for raw in text.split('\n'):
        line = raw.strip()
        if not line:
            continue
        mt = MD_TIME.match(line)
        if mt:
            msgs.append({'type': 'time', 'content': mt.group(1)})
            continue
        m = MD_MSG.match(line)
        if m:
            name = m.group(1).replace(' ', '').strip()
            if name not in users:
                users.append(name)
            msgs.append({'type': 'text', 'name': name, 'content': m.group(2).strip()})
    return users, msgs


def font(size):
    return ImageFont.truetype(FONT, size)


def wrap(text, f, maxw):
    lines, cur = [], ''
    for ch in text:
        if f.getlength(cur + ch) <= maxw:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def round_avatar(path, size):
    im = Image.open(path).convert('RGBA').resize((size, size), Image.LANCZOS)
    mask = Image.new('L', (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse((0, 0, size - 1, size - 1), fill=255)
    im.putalpha(mask)
    return im


def group_msgs(msgs):
    """连续同人消息合并为一组; 时间节点独立成组"""
    groups = []
    cur = []
    for m in msgs:
        if m['type'] == 'time':
            if cur:
                groups.append(cur); cur = []
            groups.append([m])
        elif cur and cur[-1]['type'] == 'text' and cur[-1]['name'] == m['name']:
            cur.append(m)
        else:
            if cur:
                groups.append(cur)
            cur = [m]
    if cur:
        groups.append(cur)
    for g in groups:
        n = len(g)
        for i, m in enumerate(g):
            if m['type'] == 'text':
                m['show_avatar'] = (i == n - 1)          # 头像只在组尾
                m['show_name'] = (i == 0)                 # 昵称只在组首(对方)
    return groups


class Renderer:
    def __init__(self, group_name):
        self.group = group_name
        self.f_time = font(TIME_SIZE)
        self.f_name = font(NAME_SIZE)
        self.f_text = font(TEXT_SIZE)
        self.avatars = {}
        self.self_name = None

    def avatar_for(self, name):
        if name not in self.avatars:
            cand = None
            for ext in ('.png', '.jpg', '.jpeg'):
                p = os.path.join(AVATAR_DIR, name + ext)
                if os.path.exists(p):
                    cand = p
                    break
            if cand is None:
                cand = AVATARS[len(self.avatars) % len(AVATARS)]
            self.avatars[name] = round_avatar(cand, AV)
        return self.avatars[name]

    def bubble(self, lines):
        if len(lines) == 1:
            bw = max(self.f_text.getlength(l) for l in lines) + PAD_X * 2   # 单行自适应
        else:
            bw = RIGHT_BUBBLE - LEFT_BUBBLE                                 # 多行固定(左右对齐)
        bh = len(lines) * LINE_H + PAD_Y * 2
        if len(lines) == 1:
            bh = max(bh, AV)      # 单行气泡高度 = 头像高度(微信样式)
        return bw, bh

    def is_self(self, m):
        return m['type'] == 'text' and m['name'] == self.self_name

    def group_height(self, g):
        if g[0]['type'] == 'time':
            return TIME_SIZE + 26
        h = 0
        for i, m in enumerate(g):
            lines = wrap(m['content'], self.f_text, MAX_BUBBLE)
            _, bh = self.bubble(lines)
            if i == 0 and not self.is_self(m):
                h += NAME_SIZE + 10 + bh
            else:
                h += bh
            if i < len(g) - 1:
                h += GAP_IN_GROUP
        return h

    def total_height(self, groups):
        y = STATUS_H + NAV_H + 22
        for gi, g in enumerate(groups):
            if gi > 0:
                y += GAP_GROUP
            y += self.group_height(g)
        return y + 70

    def split_pages(self, groups, max_h):
        pages, page = [], []
        y = STATUS_H + NAV_H + 22
        content_limit = max_h - STATUS_H - NAV_H - 22 - 70
        for g in groups:
            gh = self.group_height(g)
            if page and y + GAP_GROUP + gh > content_limit:
                pages.append((page, y + 70))
                page, y = [], STATUS_H + NAV_H + 22
            if page:
                y += GAP_GROUP
            page.append(g)
            y += gh
        if page:
            pages.append((page, y + 70))
        while len(pages) >= 2 and pages[-1][1] < max_h * 0.5:
            prev_g, prev_h = pages[-2]
            last_g, last_h = pages[-1]
            merged = prev_g + last_g
            mh = STATUS_H + NAV_H + 22 + sum(GAP_GROUP + self.group_height(g) for g in merged) + 70 - GAP_GROUP
            if mh <= max_h * 1.2:
                pages[-2] = (merged, mh)
                pages.pop()
            else:
                break
        return pages

    def render_page(self, groups, out_path):
        img = Image.new('RGB', (W, self.total_height(groups)), BG)
        d = ImageDraw.Draw(img)
        self.draw_status(d)
        self.draw_nav(d)
        y = STATUS_H + NAV_H + 22
        for gi, g in enumerate(groups):
            if gi > 0:
                y += GAP_GROUP
            if g[0]['type'] == 'time':
                t = self.f_time.getlength(g[0]['content'])
                d.text(((W - t) / 2, y), g[0]['content'], font=self.f_time, fill=TIME_GRAY)
                y += TIME_SIZE + 26
                continue
            y = self.draw_group(d, img, g, y)
        img.save(out_path)
        print(f"✅ {out_path}  ({W}x{img.size[1]})")

    def draw_group(self, d, img, g, y):
        """绘制一组连续同人消息; 返回组底部 y"""
        g_top = y
        items = []
        for i, m in enumerate(g):
            lines = wrap(m['content'], self.f_text, MAX_BUBBLE)
            bw, bh = self.bubble(lines)
            if i == 0 and not self.is_self(m):
                block = NAME_SIZE + 10 + bh
            else:
                block = bh
            items.append((m, lines, bw, bh))
            y += block + (GAP_IN_GROUP if i < len(g) - 1 else 0)
        g_bottom = y
        # 组尾头像: 顶部与组内第一条消息对齐(微信样式, 头像覆盖整个组高)
        last = items[-1]
        av_top = g_top
        if self.is_self(last[0]):
            img.paste(self.avatar_for(last[0]['name']), (W - MARGIN - AV, av_top), self.avatars[last[0]['name']])
        else:
            img.paste(self.avatar_for(last[0]['name']), (MARGIN, av_top), self.avatars[last[0]['name']])
        # 逐条画气泡
        yy = g_top
        for i, (m, lines, bw, bh) in enumerate(items):
            is_self = self.is_self(m)
            if is_self:
                bx = RIGHT_BUBBLE - bw          # 单行贴右(自适应), 多行=140(左对齐)
                d.rounded_rectangle((bx, yy, bx + bw, yy + bh), radius=RADIUS, fill=SELF_GREEN)
                if i == 0:                     # 尾巴在组头(微信样式)
                    d.polygon([(bx + bw - 2, yy + 14), (bx + bw + 8, yy + 22), (bx + bw - 2, yy + 32)], fill=SELF_GREEN)
                tx = bx + PAD_X
                base_y = yy
            else:
                if i == 0:
                    d.text((LEFT_BUBBLE, yy), m['name'], font=self.f_name, fill=NAME_GRAY)
                    yy2 = yy + NAME_SIZE + 10
                else:
                    yy2 = yy
                d.rounded_rectangle((LEFT_BUBBLE, yy2, LEFT_BUBBLE + bw, yy2 + bh), radius=RADIUS, fill=(255, 255, 255))
                if i == 0:                     # 尾巴在组头(微信样式)
                    d.polygon([(LEFT_BUBBLE + 2, yy2 + 14), (LEFT_BUBBLE - 8, yy2 + 22), (LEFT_BUBBLE + 2, yy2 + 32)], fill=(255, 255, 255))
                tx = LEFT_BUBBLE + PAD_X
                base_y = yy2
            # 单行文字垂直居中于气泡; 多行保持顶部 PAD_Y
            ty = base_y + ((bh - TEXT_SIZE) // 2 if len(lines) == 1 else PAD_Y)
            for l in lines:
                d.text((tx, ty), l, font=self.f_text, fill=(0, 0, 0))
                ty += LINE_H
            # 组首对方消息含昵称空间, 推进高度必须一致(group_height 同口径)
            block = (NAME_SIZE + 10 + bh) if (i == 0 and not is_self) else bh
            yy += block + (GAP_IN_GROUP if i < len(items) - 1 else 0)
        return g_bottom

    def draw_status(self, d):
        d.rectangle((0, 0, W, STATUS_H), fill=(255, 255, 255))
        d.text((30, 14), "9:41", font=font(34), fill=(0, 0, 0))
        for i in range(4):
            hh = 17 - i * 3
            x = W - 152 + i * 17
            d.rounded_rectangle((x, 36 - hh, x + 9, 36), radius=2, fill=(0, 0, 0))
        bx, by, bw, bh = W - 48, 20, 32, 18
        d.rounded_rectangle((bx, by, bx + bw, by + bh), radius=5, outline=(0, 0, 0), width=2)
        d.rectangle((bx + bw + 1, by + 6, bx + bw + 5, by + 12), fill=(0, 0, 0))
        d.rounded_rectangle((bx + 3, by + 3, bx + 3 + int(bw * 0.7), by + bh - 3), radius=2, fill=(0, 0, 0))

    def draw_nav(self, d):
        d.rectangle((0, STATUS_H, W, STATUS_H + NAV_H), fill=BG)
        d.line((0, STATUS_H + NAV_H, W, STATUS_H + NAV_H), fill=(200, 200, 200))
        d.polygon([(36, STATUS_H + 66), (58, STATUS_H + 48), (58, STATUS_H + 84)], fill=(0, 0, 0))
        gt = self.f_text.getlength(self.group)
        d.text(((W - gt) / 2, STATUS_H + 44), self.group, font=font(36), fill=(0, 0, 0))
        for i in range(3):
            cx = W - 96 + i * 22
            d.ellipse((cx, STATUS_H + 56, cx + 12, STATUS_H + 68), fill=(0, 0, 0))

    def draw(self, msgs, out_path, max_h=4000):
        self.self_name = next((m['name'] for m in msgs if m['type'] == 'text'), None)
        groups = group_msgs(msgs)
        pages = self.split_pages(groups, max_h)
        if len(pages) == 1:
            self.render_page(pages[0][0], out_path)
        else:
            base, ext = os.path.splitext(out_path)
            for i, (p, _h) in enumerate(pages, 1):
                self.render_page(p, f"{base}_{i:02d}{ext}")
            print(f"   ↳ 已分 {len(pages)} 页")


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    inp, group, out = sys.argv[1], sys.argv[2], sys.argv[3]
    max_h = 4000
    if '--max-height' in sys.argv:
        max_h = int(sys.argv[sys.argv.index('--max-height') + 1])
    users, msgs = parse(open(inp, encoding='utf-8').read())
    Renderer(group).draw(msgs, out, max_h=max_h)


if __name__ == '__main__':
    main()
