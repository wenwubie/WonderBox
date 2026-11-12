# -*- coding: utf-8 -*-
"""SPI 屏宝可梦图鉴 —— 主界面（第四世代 / 白金版, 493 只）。

用法:
    python pokemon.py            # 进入主界面(推荐入口)
    python pokemon.py --screenshot  # 渲染各风格界面样例存 PNG 后退出

主界面(选项居中, Q 版卡片):
    全部(493)   浏览全部宝可梦
    未发现(n)   只看还没查看过的
    已发现(m)   只看已查看过的
    设置        显示顺序(正序/倒序/随机) + 界面风格(夜空/糖果/森林/海洋)
                + 重置发现(两次 K3 确认清空已发现记录)
                底部一行: 左 取消 | 右 保存

按键:
    主界面:  K1 (GPIO18) 向上    K2 (GPIO23) 向下    K3 (GPIO24) 确定
    浏览页:  K1 翻页  K2 上一只  K3 下一只;  长按 K3 返回主界面
    查看过的宝可梦自动记为"已发现", 持久保存于 pokedex_data/discovered.json

设置持久保存于 pokedex_data/settings.json, 一直有效。
"""
import json
import math
import os
import random
import sys
import time

import show_pokemon as sp   # 先导入: 由此完成显示初始化/字体/数据/按键
import pygame

screen = sp.screen
FB_WIDTH = sp.FB_WIDTH
FB_HEIGHT = sp.FB_HEIGHT
PORTRAIT = FB_HEIGHT > FB_WIDTH

BASE_DIR = sp.BASE_DIR
DATA_DIR = os.path.join(BASE_DIR, "pokedex_data")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
DISCOVERED_FILE = os.path.join(DATA_DIR, "discovered.json")

# ---------------------------------------------------------------------------
# 界面风格(可自由增删, key 出现在设置项里)
# ---------------------------------------------------------------------------
STYLES = {
    "夜空": {
        "bg": (16, 20, 34), "panel": (32, 40, 60), "panel_hi": (48, 60, 88),
        "text": (235, 238, 244), "sub": (150, 160, 178),
        "accent": (255, 200, 80), "title": (255, 220, 120),
        "deco": (110, 130, 180), "hint_bg": (26, 32, 48),
    },
    "糖果": {
        "bg": (255, 214, 226), "panel": (255, 235, 242), "panel_hi": (255, 245, 250),
        "text": (110, 44, 78), "sub": (172, 104, 134),
        "accent": (255, 90, 140), "title": (240, 80, 130),
        "deco": (255, 255, 255), "hint_bg": (250, 196, 212),
    },
    "森林": {
        "bg": (14, 40, 26), "panel": (28, 64, 44), "panel_hi": (40, 88, 60),
        "text": (230, 245, 235), "sub": (150, 190, 165),
        "accent": (140, 255, 170), "title": (180, 255, 200),
        "deco": (70, 130, 95), "hint_bg": (20, 52, 34),
    },
    "海洋": {
        "bg": (10, 26, 52), "panel": (24, 50, 88), "panel_hi": (36, 68, 116),
        "text": (225, 240, 255), "sub": (140, 170, 210),
        "accent": (90, 200, 255), "title": (150, 220, 255),
        "deco": (70, 110, 170), "hint_bg": (16, 38, 70),
    },
}
STYLE_NAMES = list(STYLES)
ORDER_NAMES = ["正序", "倒序", "随机"]

K3_HOLD_BACK = 0.8  # 浏览页长按 K3 返回主界面的秒数


# ---------------------------------------------------------------------------
# 设置 / 已发现 记录(持久化)
# ---------------------------------------------------------------------------
def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            s = json.load(f)
    except Exception:
        s = {}
    s.setdefault("order", "正序")
    s.setdefault("style", "夜空")
    if s["order"] not in ORDER_NAMES:
        s["order"] = "正序"
    if s["style"] not in STYLES:
        s["style"] = "夜空"
    return s


def save_settings(s):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)


def load_discovered():
    try:
        with open(DISCOVERED_FILE, encoding="utf-8") as f:
            data = json.load(f)
        ids = set(data.get("ids", []))
    except Exception:
        ids = set()
    valid = {p["id"] for p in sp.POKEMONS}
    return ids & valid


def save_discovered(ids):
    with open(DISCOVERED_FILE, "w", encoding="utf-8") as f:
        json.dump({"ids": sorted(ids)}, f, ensure_ascii=False)


def build_list(mode, settings, discovered):
    """按模式过滤 + 按设置排序的浏览列表。mode: all / unseen / found"""
    if mode == "found":
        lst = [p for p in sp.POKEMONS if p["id"] in discovered]
    elif mode == "unseen":
        lst = [p for p in sp.POKEMONS if p["id"] not in discovered]
    else:
        lst = list(sp.POKEMONS)
    order = settings.get("order", "正序")
    if order == "倒序":
        lst.reverse()
    elif order == "随机":
        random.shuffle(lst)
    return lst


# ---------------------------------------------------------------------------
# 绘图小工具
# ---------------------------------------------------------------------------
def darker(c, f=0.55):
    return tuple(max(0, int(v * f)) for v in c)


def rrect(rect, radius, fill, border=None, bw=0, shadow=False):
    """圆角矩形(可带阴影描边)。"""
    x, y, w, h = rect
    if shadow:
        pygame.draw.rect(screen, darker(fill, 0.5), (x, y + 3, w, h),
                         border_radius=radius)
    pygame.draw.rect(screen, fill, rect, border_radius=radius)
    if border and bw:
        pygame.draw.rect(screen, border, rect, bw, border_radius=radius)


def draw_deco(st, t):
    """背景装饰: 两个大圆圈 + 一圈小圆点(随时间轻微呼吸)。"""
    for cx, cy, r in ((-30, -30, 70), (FB_WIDTH + 40, FB_HEIGHT + 46, 86)):
        pygame.draw.circle(screen, st["panel"], (cx, cy), r, 2)
    for i in range(14):
        x = (i * 61 + 17) % FB_WIDTH
        y = (i * 47 + 9) % (FB_HEIGHT - 20)
        r = 1 + int(1.4 + 1.2 * math.sin(t * 2 + i * 1.7))
        pygame.draw.circle(screen, st["deco"], (x, y), r)


def draw_icon(kind, cx, cy, st):
    """Q 版小图标: 精灵球 / 问号 / 星星 / 齿轮。"""
    r = 10
    if kind == "ball":
        # 上半彩色 + 下半白: 整圆填色后再覆盖下半
        pygame.draw.circle(screen, st["accent"], (cx, cy), r)
        pygame.draw.rect(screen, (240, 240, 240), (cx - r, cy + 1, 2 * r, r))
        pygame.draw.circle(screen, st["accent"], (cx, cy), r, 2)   # 外描边
        pygame.draw.line(screen, st["text"], (cx - r, cy), (cx + r, cy), 3)
        pygame.draw.circle(screen, (240, 240, 240), (cx, cy), r // 2 + 2)
        pygame.draw.circle(screen, st["text"], (cx, cy), r // 2 + 2, 2)
    elif kind == "q":
        pygame.draw.circle(screen, st["panel_hi"], (cx, cy), r)
        t = sp.font_mid.render("?", True, st["accent"])
        screen.blit(t, (cx - t.get_width() // 2, cy - t.get_height() // 2))
    elif kind == "star":
        pts = []
        for k in range(10):
            rad = r if k % 2 == 0 else r * 0.45
            ang = -math.pi / 2 + k * math.pi / 5
            pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
        pygame.draw.polygon(screen, st["accent"], pts)
        pygame.draw.polygon(screen, darker(st["accent"], 0.7), pts, 2)
    elif kind == "gear":
        pygame.draw.circle(screen, st["panel_hi"], (cx, cy), r - 1)
        for k in range(8):
            ang = k * math.pi / 4
            tx = cx + (r + 2) * math.cos(ang)
            ty = cy + (r + 2) * math.sin(ang)
            pygame.draw.circle(screen, st["panel_hi"], (int(tx), int(ty)), 3)
        pygame.draw.circle(screen, st["bg"], (cx, cy), r // 2)
        pygame.draw.circle(screen, st["accent"], (cx, cy), r // 2, 2)


def draw_hint(st, text):
    pygame.draw.rect(screen, st["hint_bg"], (0, FB_HEIGHT - 18, FB_WIDTH, 18))
    t = sp.font_tiny.render(text, True, st["sub"])
    screen.blit(t, ((FB_WIDTH - t.get_width()) // 2, FB_HEIGHT - 16))


def draw_title(st, title, sub, y):
    t = sp.font_big.render(title, True, st["title"])
    screen.blit(t, ((FB_WIDTH - t.get_width()) // 2, y))
    t2 = sp.font_tiny.render(sub, True, st["sub"])
    screen.blit(t2, ((FB_WIDTH - t2.get_width()) // 2, y + 32))


# ---------------------------------------------------------------------------
# 主界面 / 设置页 绘制
# ---------------------------------------------------------------------------
def _card_layout(n):
    """n 张卡片: 返回 (x0, y0, 卡宽, 卡高, 间距), 垂直居中于标题与底栏之间。"""
    if PORTRAIT:
        card_h, gap = 42, 12
        top, bottom = 92, FB_HEIGHT - 26
    else:
        card_h, gap = 30, 6
        top, bottom = 72, FB_HEIGHT - 24
    card_w = min(240, FB_WIDTH - 12)
    total = n * card_h + (n - 1) * gap
    y0 = top + max(0, (bottom - top - total) // 2)
    return (FB_WIDTH - card_w) // 2, y0, card_w, card_h, gap


def draw_menu(settings, sel, counts, t):
    """主界面: 全部/未发现/已发现/设置。counts=(总数, 未发现, 已发现)。"""
    st = STYLES[settings["style"]]
    screen.fill(st["bg"])
    draw_deco(st, t)
    draw_title(st, "宝可梦图鉴", "第四世代 · 白金版 · %d 只" % counts[0],
               20 if not PORTRAIT else 32)

    items = [
        ("全部", "(%d)" % counts[0], "ball"),
        ("未发现", "(%d)" % counts[1], "q"),
        ("已发现", "(%d)" % counts[2], "star"),
        ("设置", "", "gear"),
    ]
    x0, y0, w, h, gap = _card_layout(4)
    for i, (label, count, icon) in enumerate(items):
        selected = i == sel
        y = y0 + i * (h + gap)
        if selected:  # 选中项上下轻跳
            y += int(2 * math.sin(t * 5))
        rect = (x0, y, w, h)
        rrect(rect, 12, st["panel_hi"] if selected else st["panel"],
              border=st["accent"], bw=2 if selected else 0, shadow=selected)
        draw_icon(icon, x0 + 20, y + h // 2, st)
        lab = sp.font_mid.render(label, True, st["text"])
        screen.blit(lab, (x0 + 38, y + (h - lab.get_height()) // 2))
        if count:
            c = sp.font_mid.render(count, True, st["accent"])
            screen.blit(c, (x0 + w - c.get_width() - 12, y + (h - c.get_height()) // 2))
    draw_hint(st, "K1 上    K2 下    K3 确定")


def draw_settings_page(style_name, row, cur_order, t, confirm=False, found=0):
    """设置页: 显示顺序 / 界面风格 / 重置发现 + 底部一行(左取消|右保存, 稍小)。

    row: 0=显示顺序 1=界面风格 2=重置发现 3=取消 4=保存
    confirm: 重置发现的二次确认状态
    found: 当前已发现数量(重置行右侧显示)
    """
    st = STYLES[style_name]
    screen.fill(st["bg"])
    draw_deco(st, t)
    draw_title(st, "设置", "保存后一直有效", 20 if not PORTRAIT else 32)

    # ---- 三张设置卡(垂直居中于 标题 与 底部按钮行 之间) ----
    items = [
        ("显示顺序", cur_order, False),
        ("界面风格", style_name, False),
        ("重置发现", "再按K3确认" if confirm else "已发现%d只" % found, confirm),
    ]
    if PORTRAIT:
        card_h, gap, top, bottom = 42, 12, 92, FB_HEIGHT - 64
    else:
        card_h, gap, top, bottom = 30, 8, 72, FB_HEIGHT - 52
    card_w = min(240, FB_WIDTH - 12)
    total = 3 * card_h + 2 * gap
    y0 = top + max(0, (bottom - top - total) // 2)
    x0 = (FB_WIDTH - card_w) // 2
    for i, (label, value, warn) in enumerate(items):
        selected = i == row
        y = y0 + i * (card_h + gap)
        if selected:  # 选中项上下轻跳
            y += int(2 * math.sin(t * 5))
        rect = (x0, y, card_w, card_h)
        fill = (150, 60, 60) if (selected and warn) else \
               st["panel_hi"] if selected else st["panel"]
        rrect(rect, 12, fill, border=st["accent"], bw=2 if selected else 0,
              shadow=selected)
        lab = sp.font_mid.render(label, True, st["text"])
        screen.blit(lab, (x0 + 14, y + (card_h - lab.get_height()) // 2))
        v = sp.font_mid.render(value, True,
                               (255, 130, 130) if warn else st["accent"])
        screen.blit(v, (x0 + card_w - v.get_width() - 12,
                        y + (card_h - v.get_height()) // 2))

    # ---- 底部一行: 左 取消 | 右 保存(稍小) ----
    if PORTRAIT:
        bh, bw_, by = 30, 92, FB_HEIGHT - 56
    else:
        bh, bw_, by = 26, 92, FB_HEIGHT - 46
    gapx = 18
    bx = (FB_WIDTH - (2 * bw_ + gapx)) // 2
    for i, (label, sel_row) in enumerate((("取 消", 3), ("保 存", 4))):
        selected = row == sel_row
        rect = (bx + i * (bw_ + gapx), by, bw_, bh)
        fill = (150, 60, 60) if (selected and i == 0) else \
               (60, 140, 90) if (selected and i == 1) else st["panel"]
        rrect(rect, 10, fill, border=st["accent"], bw=2 if selected else 0,
              shadow=selected)
        lab = sp.font_small.render(label, True, st["text"])
        screen.blit(lab, (rect[0] + (bw_ - lab.get_width()) // 2,
                          rect[1] + (bh - lab.get_height()) // 2))
    draw_hint(st, "K1 上  K2 下  K3 切换/确定")


def draw_message(style_name, text, t):
    st = STYLES[style_name]
    screen.fill(st["bg"])
    draw_deco(st, t)
    lines = text.split("\n")
    y = FB_HEIGHT // 2 - 30
    for i, line in enumerate(lines):
        f = sp.font_mid if i == 0 else sp.font_small
        r = f.render(line, True, st["text"] if i == 0 else st["sub"])
        screen.blit(r, ((FB_WIDTH - r.get_width()) // 2, y))
        y += 26
    draw_hint(st, "按任意键返回")


# ---------------------------------------------------------------------------
# 事件处理(真机 GPIO 轮询 / 模拟键盘)
# ---------------------------------------------------------------------------
def pump(handler):
    """处理一帧输入事件, 调用 handler(按键名)。返回 False 表示退出程序。"""
    if sp.gpio is not None:
        for name in sp.poll_buttons():
            handler(name)
        return sp.spi_lcd.pump()
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_q):
                return False
            name = sp.handle_key(event.key)
            if name:
                handler(name)
    return True


# ---------------------------------------------------------------------------
# 各个子界面循环
# ---------------------------------------------------------------------------
def settings_loop(saved, discovered):
    """设置页循环。返回(可能更新并已保存的)设置; 取消则原样返回。

    discovered 以引用传入: 在"重置发现"行两次 K3 确认后原地清空并落盘。
    """
    cur = dict(saved)
    row = 0
    confirm_t0 = [None]          # 重置二次确认的起始时刻(None=未确认)
    CONFIRM_WAIT = 5.0           # 确认状态保持秒数
    clock = pygame.time.Clock()

    def confirming(now=None):
        return (confirm_t0[0] is not None
                and (now or time.time()) - confirm_t0[0] < CONFIRM_WAIT)

    while True:
        draw_settings_page(cur["style"], row, cur["order"], time.time(),
                           confirm=confirming(), found=len(discovered))
        if not sp.spi_lcd.present():
            return saved
        acts = []
        if not pump(lambda n: acts.append(n)):
            return saved
        ok_confirm = confirming()
        for name in acts:
            if name == "K1":
                row = (row - 1) % 5
                confirm_t0[0] = None
            elif name == "K2":
                row = (row + 1) % 5
                confirm_t0[0] = None
            elif name == "K3":
                if row == 0:      # 切换显示顺序
                    cur["order"] = ORDER_NAMES[
                        (ORDER_NAMES.index(cur["order"]) + 1) % len(ORDER_NAMES)]
                elif row == 1:    # 切换界面风格(即时预览)
                    cur["style"] = STYLE_NAMES[
                        (STYLE_NAMES.index(cur["style"]) + 1) % len(STYLE_NAMES)]
                elif row == 2:    # 重置发现(两次 K3 确认)
                    if ok_confirm:
                        discovered.clear()
                        save_discovered(discovered)
                        print("已重置发现记录, 可重新发现宝可梦。")
                        confirm_t0[0] = None
                    else:
                        confirm_t0[0] = time.time()
                elif row == 3:    # 取消
                    return saved
                else:             # 保存
                    save_settings(cur)
                    print("设置已保存:", cur)
                    return cur
        clock.tick(24)


def message_loop(style_name, text):
    """提示页: 等待任意按键返回。"""
    clock = pygame.time.Clock()
    while True:
        draw_message(style_name, text, time.time())
        if not sp.spi_lcd.present():
            return
        acts = []
        if not pump(lambda n: acts.append(n)):
            return
        if acts:
            return
        clock.tick(24)


def main():
    settings = load_settings()
    discovered = load_discovered()
    sel = [0]
    clock = pygame.time.Clock()
    running = True
    print("主界面启动: K1 上 / K2 下 / K3 确定; 浏览页长按 K3 返回。")

    def on_key(name):
        nonlocal settings, running
        if name == "K1":
            sel[0] = (sel[0] - 1) % 4
        elif name == "K2":
            sel[0] = (sel[0] + 1) % 4
        elif name == "K3":
            # 等待 K3 物理松开并复位按键状态:
            # 否则长按连发事件会被下方子界面/主界面误判为新按键
            sp.wait_release("K3")
            if sel[0] == 3:                                   # 设置
                settings = settings_loop(settings, discovered)
                sp.wait_release("K3")      # 设置页按 K3 退出后可能仍按住
            else:                                             # 全部/未发现/已发现
                mode = ("all", "unseen", "found")[sel[0]]
                lst = build_list(mode, settings, discovered)
                if lst:
                    sp.browse(lst,
                              on_viewed=lambda p: discovered.add(p["id"]),
                              back_hold=K3_HOLD_BACK)
                else:
                    msg = ("还没有已发现的宝可梦\n先去 全部 里逛逛吧!"
                           if mode == "found"
                           else "没有未发现的宝可梦\n全部都发现啦!")
                    message_loop(settings["style"], msg)
                save_discovered(discovered)                    # 浏览记录落盘

    try:
        while running:
            total = len(sp.POKEMONS)
            found = len(discovered)
            draw_menu(settings, sel[0], (total, total - found, found), time.time())
            running = sp.spi_lcd.present()
            if running and not pump(on_key):
                running = False
            clock.tick(24)
    finally:
        if sp.gpio is not None:
            sp.gpio.cleanup()
        pygame.quit()


# ---------------------------------------------------------------------------
# 截图模式(界面验证)
# ---------------------------------------------------------------------------
def run_screenshots():
    settings = load_settings()
    discovered = load_discovered()
    total = len(sp.POKEMONS)
    found = len(discovered)
    counts = (total, total - found, found)

    out = []
    for i, style in enumerate(STYLE_NAMES):       # 各风格主界面
        s = dict(settings, style=style)
        draw_menu(s, i % 4, counts, time.time())
        path = os.path.join(BASE_DIR, "_menu_%d.png" % i)
        pygame.image.save(screen, path)
        out.append(path)
    draw_settings_page("夜空", 1, "随机", time.time(), confirm=False, found=128)
    path = os.path.join(BASE_DIR, "_menu_4.png")
    pygame.image.save(screen, path)
    out.append(path)
    draw_settings_page("夜空", 2, "随机", time.time(), confirm=True, found=128)
    path = os.path.join(BASE_DIR, "_menu_6.png")
    pygame.image.save(screen, path)
    out.append(path)
    draw_message("糖果", "还没有已发现的宝可梦\n先去 全部 里逛逛吧!", time.time())
    path = os.path.join(BASE_DIR, "_menu_5.png")
    pygame.image.save(screen, path)
    out.append(path)
    for p in out:
        print("已保存:", p)


if __name__ == "__main__":
    if "--screenshot" in sys.argv:
        run_screenshots()
        pygame.quit()
        sys.exit()
    main()
