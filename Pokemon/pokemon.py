# -*- coding: utf-8 -*-
"""SPI 屏宝可梦图鉴 —— 主界面（第四世代 / 白金版, 493 只）。

用法:
    python pokemon.py            # 进入主界面(推荐入口)
    python pokemon.py --screenshot  # 渲染各风格界面样例存 PNG 后退出

主界面(选项居中, Q 版卡片):
    全部(n)     浏览所选世代的宝可梦
    未发现(n)   只看还没查看过的
    已发现(m)   只看已查看过的
    设置        显示顺序 + 第 1～4 世代筛选(界面风格在主界面"设置"里全局选择)
                + 重置发现(两次 K3 确认清空全部世代的发现记录)
                底部一行: 左 取消 | 右 保存

按键:
    主界面:  K1 (GPIO5) 向上    K2 (GPIO23) 向下    K3 (GPIO24) 确定
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

import show_pokemon as sp   # 先导入: 由此完成显示初始化/字体/数据/按键(并把项目根目录加入 sys.path)
from common import ui_theme  # 全局界面风格(主界面"设置"里选择)
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
# 界面风格: 全局统一, 由主界面"设置"选择(定义见 common/ui_theme.py)
# ---------------------------------------------------------------------------
STYLES = ui_theme.STYLES
STYLE_NAMES = ui_theme.STYLE_NAMES
ORDER_NAMES = ["正序", "倒序", "随机"]
GENERATION_RANGES = sp.GENERATION_RANGES

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
    if not isinstance(s, dict):
        s = {}
    s.setdefault("order", "正序")
    s.pop("style", None)  # 界面风格已移到主界面全局设置
    if s["order"] not in ORDER_NAMES:
        s["order"] = "正序"
    s["generations"] = sp.normalize_generations(s.get("generations"))
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


def generation_pokemon(settings):
    """返回所选世代的宝可梦；旧设置默认包含全部世代。"""
    return sp.generation_pokemon(settings.get("generations"))


def menu_counts(settings, discovered):
    visible = generation_pokemon(settings)
    found = sum(pokemon["id"] in discovered for pokemon in visible)
    return len(visible), len(visible) - found, found


_last_random_order = None


def build_list(mode, settings, discovered):
    """按世代和发现状态过滤，并按设置排序。mode: all / unseen / found"""
    global _last_random_order
    lst = generation_pokemon(settings)
    if mode == "found":
        lst = [pokemon for pokemon in lst if pokemon["id"] in discovered]
    elif mode == "unseen":
        lst = [pokemon for pokemon in lst if pokemon["id"] not in discovered]
    order = settings.get("order", "正序")
    if order == "倒序":
        lst.reverse()
    elif order == "随机":
        random.SystemRandom().shuffle(lst)
        current_order = tuple(pokemon["id"] for pokemon in lst)
        if len(lst) > 1 and current_order == _last_random_order:
            lst.append(lst.pop(0))
            current_order = tuple(pokemon["id"] for pokemon in lst)
        _last_random_order = current_order
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


def draw_hint(st, buttons):
    global _hint_button_rects
    pygame.draw.rect(screen, st["hint_bg"], (0, FB_HEIGHT - 18, FB_WIDTH, 18))
    text = "    ".join(label for _, label in buttons)
    t = sp.font_tiny.render(text, True, st["sub"])
    y = FB_HEIGHT - 16
    screen.blit(t, ((FB_WIDTH - t.get_width()) // 2, y))
    _hint_button_rects = sp.spi_lcd.text_button_rects(text, sp.font_tiny, y, buttons)


_hint_button_rects = []


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
    st = ui_theme.style()
    screen.fill(st["bg"])
    draw_deco(st, t)
    draw_title(st, "宝可梦图鉴", "白金版 · %d 只" % counts[0],
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
    draw_hint(st, (("K1", "上一项"), ("K2", "下一项"), ("K3", "确定")))


def draw_settings_page(row, cur_order, t, confirm=False, found=0, generations=None):
    """设置页: 显示顺序、世代筛选和重置发现。

    row: 0=显示顺序 1=世代筛选 2=重置发现 3=取消 4=保存
    confirm: 重置发现的二次确认状态
    found: 当前已发现数量(重置行右侧显示)
    """
    st = ui_theme.style()
    if generations is None:
        generations = list(GENERATION_RANGES)
    screen.fill(st["bg"])
    draw_deco(st, t)
    draw_title(st, "设置", "保存后一直有效", 20 if not PORTRAIT else 32)

    items = [
        ("显示顺序", cur_order, False),
        ("世代筛选", "/".join(str(generation) for generation in generations) or "未选择", False),
        ("重置发现", "再按确认" if confirm else "全部%d只" % found, confirm),
    ]
    if PORTRAIT:
        card_h, gap, top, bottom = 32, 6, 92, FB_HEIGHT - 64
    else:
        card_h, gap, top, bottom = 24, 3, 68, FB_HEIGHT - 52
    card_w = min(240, FB_WIDTH - 12)
    total = len(items) * card_h + (len(items) - 1) * gap
    y0 = top + max(0, (bottom - top - total) // 2)
    x0 = (FB_WIDTH - card_w) // 2
    click_rects = []
    for i, (label, value, warn) in enumerate(items):
        selected = i == row
        y = y0 + i * (card_h + gap)
        if selected:  # 选中项上下轻跳
            y += int(2 * math.sin(t * 5))
        rect = (x0, y, card_w, card_h)
        click_rects.append(("ROW_%d" % i, pygame.Rect(rect)))
        fill = (150, 60, 60) if (selected and warn) else \
               st["panel_hi"] if selected else st["panel"]
        rrect(rect, 12, fill, border=st["accent"], bw=2 if selected else 0,
              shadow=selected)
        lab = sp.font_mid.render(label, True, ui_theme.pick(fill, st["text"]))
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
        click_rects.append(("ROW_%d" % sel_row, pygame.Rect(rect)))
        fill = (150, 60, 60) if (selected and i == 0) else \
               (60, 140, 90) if (selected and i == 1) else st["panel"]
        rrect(rect, 10, fill, border=st["accent"], bw=2 if selected else 0,
              shadow=selected)
        lab = sp.font_small.render(label, True, ui_theme.pick(fill, st["text"]))
        screen.blit(lab, (rect[0] + (bw_ - lab.get_width()) // 2,
                          rect[1] + (bh - lab.get_height()) // 2))
    draw_hint(st, (("K1", "上一项"), ("K2", "下一项"),
                   ("K3", "切换" if row == 0 else "确定")))
    return click_rects


def draw_generations_page(row, generations, t):
    st = ui_theme.style()
    screen.fill(st["bg"])
    draw_deco(st, t)
    draw_title(st, "选择世代", "保存设置后生效", 32 if PORTRAIT else 20)

    card_h, gap, top = (32, 6, 94) if PORTRAIT else (24, 4, 70)
    card_w = min(240, FB_WIDTH - 12)
    x0 = (FB_WIDTH - card_w) // 2
    click_rects = []
    for index, generation in enumerate(GENERATION_RANGES):
        rect = pygame.Rect(x0, top + index * (card_h + gap), card_w, card_h)
        selected = row == index
        rrect(rect, 7, st["panel_hi"] if selected else st["panel"],
              border=st["accent"], bw=2 if selected else 0)
        checkbox = pygame.Rect(rect.x + 14, rect.centery - 8, 16, 16)
        color = st["accent"] if generation in generations else st["sub"]
        pygame.draw.rect(screen, color, checkbox, 2, border_radius=3)
        if generation in generations:
            pygame.draw.lines(screen, color, False,
                              [(checkbox.x + 3, checkbox.y + 8),
                               (checkbox.x + 6, checkbox.y + 11),
                               (checkbox.x + 12, checkbox.y + 4)], 2)
        label = sp.font_mid.render("第%d世代" % generation, True, st["text"])
        screen.blit(label, label.get_rect(midleft=(rect.x + 42, rect.centery)))
        click_rects.append(("GEN_%d" % generation, rect))

    height, top = (30, FB_HEIGHT - 56) if PORTRAIT else (26, FB_HEIGHT - 46)
    done = pygame.Rect((FB_WIDTH - 92) // 2, top, 92, height)
    selected = row == len(GENERATION_RANGES)
    rrect(done, 7, st["panel_hi"] if selected else st["panel"],
          border=st["accent"], bw=2 if selected else 0)
    label = sp.font_small.render("完 成", True, st["text"])
    screen.blit(label, label.get_rect(center=done.center))
    click_rects.append(("GEN_DONE", done))
    draw_hint(st, (("K1", "上一项"), ("K2", "下一项"),
                   ("K3", "完成" if row == len(GENERATION_RANGES) else "勾选")))
    return click_rects


def draw_message(text, t):
    st = ui_theme.style()
    screen.fill(st["bg"])
    draw_deco(st, t)
    lines = text.split("\n")
    y = FB_HEIGHT // 2 - 30
    for i, line in enumerate(lines):
        f = sp.font_mid if i == 0 else sp.font_small
        r = f.render(line, True, st["text"] if i == 0 else st["sub"])
        screen.blit(r, ((FB_WIDTH - r.get_width()) // 2, y))
        y += 26
    draw_hint(st, (("K3", "返回"),))


# ---------------------------------------------------------------------------
# 事件处理(真机 GPIO 轮询 / 模拟键盘)
# ---------------------------------------------------------------------------
def pump(handler, click_rects=(), hold=None):
    """处理一帧按键；模拟模式可额外指定可点击区域。"""
    def mouse_action(event):
        return (sp.spi_lcd.button_from_mouse(event, _hint_button_rects)
                or sp.spi_lcd.button_from_mouse(event, click_rects))

    actions = sp.input_actions(mouse_action, hold)
    if actions is None:
        return False
    for name in actions:
        handler(name)
    return True


# ---------------------------------------------------------------------------
# 各个子界面循环
# ---------------------------------------------------------------------------
def generations_loop(generations, hold=None):
    selected = set(generations)
    row = 0
    if hold is None:
        hold = sp.spi_lcd.SimulatedHold("K3", "BACK", K3_HOLD_BACK)
    clock = pygame.time.Clock()

    while True:
        click_rects = draw_generations_page(row, selected, time.time())
        if not sp.spi_lcd.present(poll_events=False):
            return None
        actions = []
        if not pump(actions.append, click_rects, hold):
            return None
        for action in actions:
            generation = None
            if action == "BACK":
                return sorted(generations)
            elif action == "K1":
                row = (row - 1) % (len(GENERATION_RANGES) + 1)
            elif action == "K2":
                row = (row + 1) % (len(GENERATION_RANGES) + 1)
            elif action == "GEN_DONE" or (action == "K3" and row == len(GENERATION_RANGES)):
                return sorted(selected)
            elif action.startswith("GEN_"):
                generation = int(action[4:])
                row = generation - 1
            elif action == "K3":
                generation = row + 1
            if generation is not None:
                if generation in selected:
                    selected.remove(generation)
                else:
                    selected.add(generation)
        clock.tick(24)


def settings_loop(saved, discovered, hold=None):
    """设置页循环。取消或长按 K3 返回原设置，关闭窗口或 Esc 返回 None。

    discovered 以引用传入: 在"重置发现"行两次 K3 确认后原地清空并落盘。
    """
    cur = dict(saved)
    cur["generations"] = list(saved.get("generations", GENERATION_RANGES))
    row = 0
    confirm_t0 = [None]          # 重置二次确认的起始时刻(None=未确认)
    CONFIRM_WAIT = 5.0           # 确认状态保持秒数
    if hold is None:
        hold = sp.spi_lcd.SimulatedHold("K3", "BACK", K3_HOLD_BACK)
    clock = pygame.time.Clock()

    def confirming(now=None):
        return (confirm_t0[0] is not None
                and (now or time.time()) - confirm_t0[0] < CONFIRM_WAIT)

    while True:
        click_rects = draw_settings_page(row, cur["order"], time.time(),
                                         confirm=confirming(), found=len(discovered),
                                         generations=cur["generations"])
        if not sp.spi_lcd.present(poll_events=False):
            return None
        acts = []
        if not pump(acts.append, click_rects, hold):
            return None
        ok_confirm = confirming()
        for name in acts:
            if name == "BACK":
                return saved
            if name.startswith("ROW_"):
                selected_row = int(name[4:])
                if row != selected_row:
                    confirm_t0[0] = None
                    ok_confirm = False
                row = selected_row
                name = "K3"
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
                elif row == 1:    # 世代筛选
                    generations = generations_loop(cur["generations"], hold)
                    if generations is None:
                        return None
                    cur["generations"] = generations
                    break
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


def message_loop(text, hold):
    """提示页: 等待 K3 返回。"""
    clock = pygame.time.Clock()
    while True:
        draw_message(text, time.time())
        if not sp.spi_lcd.present(poll_events=False):
            return
        acts = []
        if not pump(acts.append, hold=hold):
            return
        if "K3" in acts:
            return
        clock.tick(24)


def main():
    settings = load_settings()
    discovered = load_discovered()
    sel = [0]
    hold = sp.spi_lcd.SimulatedHold("K3", "BACK", K3_HOLD_BACK)
    clock = pygame.time.Clock()
    running = True
    print("主界面启动: K1 上一项 / K2 下一项 / K3 确定, 长按 K3 退出; 模拟模式可点击底栏功能文字。")

    def on_key(name):
        nonlocal settings, running
        if name == "BACK":
            running = False
        elif name == "K1":
            sel[0] = (sel[0] - 1) % 4
        elif name == "K2":
            sel[0] = (sel[0] + 1) % 4
        elif name == "K3":
            if sel[0] == 3:                                   # 设置
                updated_settings = settings_loop(settings, discovered, hold)
                if updated_settings is None:
                    running = False
                    return
                settings = updated_settings
            else:                                             # 全部/未发现/已发现
                mode = ("all", "unseen", "found")[sel[0]]
                lst = build_list(mode, settings, discovered)
                if lst:
                    sp.browse(lst, on_viewed=lambda p: discovered.add(p["id"]), hold=hold)
                else:
                    if not settings.get("generations", GENERATION_RANGES):
                        msg = "没有选择宝可梦世代\n请在设置中勾选"
                    elif mode == "found":
                        msg = "所选世代还没有已发现\n先去 全部 里逛逛吧!"
                    elif mode == "unseen":
                        msg = "所选世代没有未发现\n全部都发现啦!"
                    else:
                        msg = "所选世代没有宝可梦\n请检查世代设置"
                    message_loop(msg, hold)
                save_discovered(discovered)                    # 浏览记录落盘

    try:
        while running:
            counts = menu_counts(settings, discovered)
            draw_menu(settings, sel[0], counts, time.time())
            running = sp.spi_lcd.present(poll_events=False)
            if running:
                actions = []
                running = pump(actions.append, hold=hold)
                for action in actions:
                    on_key(action)
                    if action in ("K3", "BACK"):
                        break
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
    counts = menu_counts(settings, discovered)

    out = []
    original = ui_theme.style_name()
    for i, style in enumerate(STYLE_NAMES):       # 各风格主界面
        ui_theme.set_style(style)
        draw_menu(settings, i % 4, counts, time.time())
        path = os.path.join(BASE_DIR, "_menu_%d.png" % i)
        pygame.image.save(screen, path)
        out.append(path)
    ui_theme.set_style("夜空")
    draw_settings_page(0, "随机", time.time(), confirm=False, found=128)
    path = os.path.join(BASE_DIR, "_menu_4.png")
    pygame.image.save(screen, path)
    out.append(path)
    draw_settings_page(2, "随机", time.time(), confirm=True, found=128)
    path = os.path.join(BASE_DIR, "_menu_6.png")
    pygame.image.save(screen, path)
    out.append(path)
    ui_theme.set_style("糖果")
    draw_message("还没有已发现的宝可梦\n先去 全部 里逛逛吧!", time.time())
    path = os.path.join(BASE_DIR, "_menu_5.png")
    pygame.image.save(screen, path)
    out.append(path)
    ui_theme.set_style(original)
    for p in out:
        print("已保存:", p)


if __name__ == "__main__":
    if "--screenshot" in sys.argv:
        run_screenshots()
        pygame.quit()
        sys.exit()
    main()
