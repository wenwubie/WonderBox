# -*- coding: utf-8 -*-
"""SPI 屏宝可梦图鉴浏览器（第四世代 / 白金版）。

主界面入口: python pokemon.py  (菜单 / 浏览记录 / 设置, 推荐从主界面进入)
本文件也可独立运行: python show_pokemon.py 直接浏览全部。

布局: 320x240
    第 1 页(概览): 左边图片, 右边 编号/名称/属性/白金获得方式
    第 2+ 页(招式): 全屏招式表, 行数自适应铺满到底部(无底部提示条)
    末页(克制): 本只宝可梦的属性克制关系(克制/被克制/抵抗/免疫)

按键:
    K1 (GPIO18): 下一页
    K2 (GPIO23): 切换到上一只宝可梦
    K3 (GPIO24): 切换到下一只宝可梦

本机模拟模式: 键盘 1/2/3 代替 K1/K2/K3, Esc 退出。
截图模式: python show_pokemon.py --screenshot  (渲染两页样例存 PNG 后退出)
"""
import json
import math
import os
import sys
import time

import spi_lcd

# ---------------------------------------------------------------------------
# 数据路径(相对本脚本所在目录)
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "pokedex_data", "pokemon_platinum.json")
IMG_DIR = os.path.join(BASE_DIR, "pokedex_data", "images")

FB_WIDTH = spi_lcd.FB_WIDTH
FB_HEIGHT = spi_lcd.FB_HEIGHT
# ---------------------------------------------------------------------------
# 颜色
# ---------------------------------------------------------------------------
BG_COLOR = (18, 22, 30)
PANEL_COLOR = (30, 38, 52)
BAR_COLOR = (40, 52, 74)
TEXT_COLOR = (235, 238, 244)
SUB_COLOR = (150, 160, 178)
ACCENT_COLOR = (0, 255, 140)
WARN_COLOR = (255, 200, 80)

TYPE_COLORS = {
    "一般": (168, 168, 120), "火": (240, 128, 48), "水": (104, 144, 240),
    "电": (248, 208, 48), "草": (120, 200, 80), "冰": (152, 216, 216),
    "格斗": (192, 48, 40), "毒": (160, 64, 160), "地面": (224, 192, 104),
    "飞行": (168, 144, 240), "超能力": (248, 88, 136), "虫": (168, 184, 32),
    "岩石": (184, 160, 56), "幽灵": (112, 88, 152), "龙": (112, 56, 248),
    "恶": (112, 88, 72), "钢": (184, 184, 208),
}

MOVES_PER_PAGE = 9  # 占位, 字体加载后按屏幕/字号自适应计算

# ---------------------------------------------------------------------------
# 初始化显示(必须在 import pygame 之前)
# ---------------------------------------------------------------------------
screen = spi_lcd.init()
import pygame  # noqa: E402

# 实际画布尺寸(init 后确定): 真机 rotate=90/270 → 320x240 横屏,
# rotate=0/180 → 240x320 竖屏; 模拟模式可用 --portrait 预览竖屏
FB_WIDTH, FB_HEIGHT = screen.get_size()
PORTRAIT = FB_HEIGHT > FB_WIDTH
IMG_SIZE = 92 if PORTRAIT else 118            # 概览页图片尺寸

font_big = spi_lcd.load_font(26)    # 中文名
font_mid = spi_lcd.load_font(17)    # 标题/属性
font_small = spi_lcd.load_font(14)  # 正文
font_tiny = spi_lcd.load_font(13)   # 提示条

# ---------------------------------------------------------------------------
# 招式页布局: 表格直接铺到屏幕底部(招式页不画底部提示条),
# 自动挑选"能塞下最多行"的最大字号, 保证小屏也能一页显示尽量多的招式。
# 小字屏(真机 wqy 字体偏高偏宽)会自动降到 12/11/10 号字。
# ---------------------------------------------------------------------------
MOVE_HEADER_Y = 30 if PORTRAIT else 26    # 表头起始 y
MOVE_BOTTOM = FB_HEIGHT - 2               # 表格下边界(贴近屏幕底)
MOVE_TARGET_ROWS = 13                     # 期望每页行数(尽量填满)
MOVE_FONT_SIZES = (13, 12, 11, 10)        # 依次尝试的字号


def _layout_move_table():
    """挑字号并算出 每页行数 / 行高 / 表格起始 y。返回 (font, size, row_h, rows, top)。"""
    best = None
    for size in MOVE_FONT_SIZES:
        f = spi_lcd.load_font(size)
        h = f.get_height()
        top = MOVE_HEADER_Y + h + 6      # 表头 + 分隔线 + 间距
        row_h = h + 1                    # 行距 = 字高 + 1px
        rows = max(1, (MOVE_BOTTOM - top) // row_h)
        best = (f, size, row_h, rows, top)
        if rows >= MOVE_TARGET_ROWS:
            break                        # 已达标, 用当前(尽量大的)字号
    return best


font_move, MOVE_FONT_SIZE, ROW_H, MOVES_PER_PAGE, MOVE_LIST_TOP = _layout_move_table()
print("招式表布局: %dx%d 字号 %d, 行距 %dpx, 每页 %d 行"
      % (FB_WIDTH, FB_HEIGHT, MOVE_FONT_SIZE, ROW_H, MOVES_PER_PAGE))


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------
if not os.path.exists(DATA_FILE):
    print("找不到数据文件: %s" % DATA_FILE)
    print("请先运行 crawl_pokemon_platinum.py 生成数据。")
    sys.exit(1)

with open(DATA_FILE, encoding="utf-8") as f:
    POKEMONS = json.load(f)
if not POKEMONS:
    print("数据文件为空。")
    sys.exit(1)

# 属性相克表(由 crawl_pokemon_platinum.py 生成); 缺失时跳过克制页
TYPE_CHART_FILE = os.path.join(BASE_DIR, "pokedex_data", "type_chart.json")
TYPE_CHART = None          # {攻击属性: {防御属性: 倍率}}
TYPE_ORDER = []            # 17 个属性顺序
if os.path.exists(TYPE_CHART_FILE):
    with open(TYPE_CHART_FILE, encoding="utf-8") as f:
        _chart = json.load(f)
    TYPE_CHART = _chart.get("attack") or {}
    TYPE_ORDER = _chart.get("types") or []
    print("属性相克表已加载: 第四世代规则, %d 属性" % len(TYPE_ORDER))
else:
    print("找不到属性相克表(type_chart.json), 不显示克制页。"
          "可运行 crawl_pokemon_platinum.py 生成。")

_img_cache = {}


def get_image(name_zh):
    """加载并缩放宝可梦图片(带缓存)。"""
    key = (name_zh, IMG_SIZE)
    if key in _img_cache:
        return _img_cache[key]
    path = os.path.join(IMG_DIR, name_zh + ".png")
    if not os.path.exists(path):
        return None
    try:
        img = pygame.image.load(path)
        if img.get_alpha() is None and img.get_bitsize() == 24:
            img = img.convert()
        else:
            img = img.convert_alpha()
        img = pygame.transform.smoothscale(img, (IMG_SIZE, IMG_SIZE))
    except Exception as e:
        print("图片加载失败 %s: %s" % (path, e))
        return None
    if len(_img_cache) > 8:  # 简单缓存上限
        _img_cache.clear()
    _img_cache[key] = img
    return img


def total_pages(p):
    """每只宝可梦的总页数: 1 页概览 + 招式分页 (+ 1 页属性克制)。"""
    pages = 1 + max(1, math.ceil(len(p["moves"]) / MOVES_PER_PAGE))
    if TYPE_CHART:
        pages += 1
    return pages


def type_matchups(p):
    """按本只宝可梦的属性计算相克关系(第四世代规则)。

    返回 (克制, 被克制, 抵抗, 免疫):
      克制   = 我方属性攻击这些属性效果绝佳(倍率 >= 2)
      被克制 = 这些属性攻击我方倍率 >= 2 (双属性倍率相乘)
      抵抗   = 倍率 < 1 且 > 0
      免疫   = 倍率 == 0
    """
    my_types = [t for t in p["types"] if t in TYPE_ORDER] or list(TYPE_ORDER)
    strong, weak, resist, immune = [], [], [], []
    for d in TYPE_ORDER:  # 克制: 我打别人
        if any(TYPE_CHART[t].get(d, 1.0) >= 2 for t in my_types):
            strong.append(d)
    for a in TYPE_ORDER:  # 别人打我(双属性倍率相乘)
        m = 1.0
        for t in my_types:
            m *= TYPE_CHART[a].get(t, 1.0)
        if m == 0:
            immune.append(a)
        elif m < 1:
            resist.append(a)
        elif m >= 2:
            weak.append(a)
    return strong, weak, resist, immune


def badge_width(name):
    """单个属性徽章占用的宽度(含右侧间隙)。"""
    return font_small.size(name)[0] + 10 + 5


def draw_badge_flow(names, x, y, max_w, max_rows=3):
    """从 (x, y) 开始流式绘制属性徽章, 自动换行。

    返回 (下一个 y, 未显示个数): 超过 max_rows 行时停止, 并返回剩余个数。
    """
    row_h = 23
    rows = 1
    shown = 0
    for n in names:
        if x + badge_width(n) - 5 > max_w:
            rows += 1
            if rows > max_rows:
                break
            x, y = 6, y + row_h
        x = draw_type_badge(x, y, n)
        shown += 1
    return y + row_h, len(names) - shown


# ---------------------------------------------------------------------------
# 页面绘制
# ---------------------------------------------------------------------------
def draw_top_bar(p, page, pages):
    pygame.draw.rect(screen, BAR_COLOR, (0, 0, FB_WIDTH, 24))
    t1 = font_small.render("#%03d %s" % (p["id"], p["name_zh"]), True, TEXT_COLOR)
    t2 = font_small.render("%d/%d" % (page + 1, pages), True, ACCENT_COLOR)
    screen.blit(t1, (8, 4))
    screen.blit(t2, (FB_WIDTH - t2.get_width() - 8, 4))


BACK_HINT = False  # True=浏览页底部提示"长按K3返回"(由 pokemon.py 主界面进入时置位)


def draw_bottom_bar():
    pygame.draw.rect(screen, BAR_COLOR, (0, FB_HEIGHT - 18, FB_WIDTH, 18))
    if BACK_HINT:
        text = "K1 翻页  K2 上一只  K3 下一只  长按K3 返回"
    else:
        text = "K1 下页   K2 上一只   K3 下一只"
    t = font_tiny.render(text, True, SUB_COLOR)
    screen.blit(t, ((FB_WIDTH - t.get_width()) // 2, FB_HEIGHT - 16))


def fit_text(text, font, max_w):
    """按像素宽度截断文字, 超出部分以省略号结尾。"""
    if font.size(text)[0] <= max_w:
        return text
    while text and font.size(text + "…")[0] > max_w:
        text = text[:-1]
    return (text + "…") if text else ""


def draw_type_badge(x, y, type_name):
    """属性色块徽章, 返回下一个 x 坐标。"""
    color = TYPE_COLORS.get(type_name, (120, 120, 120))
    text = font_small.render(type_name, True, (15, 15, 15))
    w, h = text.get_width() + 10, 19
    pygame.draw.rect(screen, color, (x, y, w, h), border_radius=4)
    screen.blit(text, (x + 5, y + 1))
    return x + w + 5


def draw_overview(p):
    """第 1 页: 概览。横屏=左图右信息, 竖屏=图上信息下。"""
    locs = p.get("platinum_locations") or []

    if PORTRAIT:
        # ---- 竖屏 240x320: 图片居中在上, 文字在下 ----
        img = get_image(p["name_zh"])
        ix = (FB_WIDTH - IMG_SIZE) // 2
        pygame.draw.rect(screen, PANEL_COLOR, (ix - 4, 28, IMG_SIZE + 8, IMG_SIZE + 8),
                         border_radius=6)
        if img:
            screen.blit(img, (ix, 32))
        else:
            t = font_small.render("无图片", True, SUB_COLOR)
            screen.blit(t, (FB_WIDTH // 2 - t.get_width() // 2, 70))

        # 名称(居中)
        def center_text(font, text, color, y):
            t = font.render(fit_text(text, font, FB_WIDTH - 12), True, color)
            screen.blit(t, (max(4, (FB_WIDTH - t.get_width()) // 2), y))

        center_text(font_mid, "#%03d" % p["id"], ACCENT_COLOR, IMG_SIZE + 38)
        center_text(font_big, p["name_zh"], TEXT_COLOR, IMG_SIZE + 60)
        center_text(font_small, p["name_en"], SUB_COLOR, IMG_SIZE + 92)

        # 属性徽章(居中)
        total_w = sum(font_small.size(tp)[0] + 10 + 5 for tp in p["types"]) - 5
        x = max(4, (FB_WIDTH - total_w) // 2)
        for tp in p["types"]:
            x = draw_type_badge(x, IMG_SIZE + 116, tp)

        # 获得方式
        center_text(font_mid, "- 白金版获得方式 -", WARN_COLOR, IMG_SIZE + 144)
        y = IMG_SIZE + 168
        if not locs:
            center_text(font_tiny, "无法自然获得(活动/传入)", SUB_COLOR, y)
        for loc in locs[:3]:
            line1 = fit_text(loc["location"], font_tiny, FB_WIDTH - 12)
            line2 = fit_text("- %s %s" % (loc["method"], loc["notes"]),
                             font_tiny, FB_WIDTH - 12)
            center_text(font_tiny, line1, TEXT_COLOR, y)
            y += 16
            if loc["method"] or loc["notes"]:
                center_text(font_tiny, line2, SUB_COLOR, y)
                y += 16
            if y > FB_HEIGHT - 26:
                break
    else:
        # ---- 横屏 320x240: 左图右信息 ----
        img = get_image(p["name_zh"])
        pygame.draw.rect(screen, PANEL_COLOR, (6, 30, 126, 126), border_radius=6)
        if img:
            screen.blit(img, (10, 34))
        else:
            t = font_small.render("无图片", True, SUB_COLOR)
            screen.blit(t, (70 - t.get_width() // 2, 90))

        # 编号
        t = font_mid.render("#%03d" % p["id"], True, ACCENT_COLOR)
        screen.blit(t, (6, 162))

        # 属性徽章(图下方)
        x = 6
        for tp in p["types"]:
            x = draw_type_badge(x, 186, tp)

        # 右侧: 名称
        tx = 142
        right_w = FB_WIDTH - tx - 6
        screen.blit(font_big.render(fit_text(p["name_zh"], font_big, right_w), True, TEXT_COLOR), (tx, 30))
        screen.blit(font_small.render(fit_text(p["name_en"], font_small, right_w), True, SUB_COLOR), (tx, 62))
        screen.blit(font_tiny.render(fit_text(p["name_ja"], font_tiny, right_w), True, SUB_COLOR), (tx, 82))

        # 获得方式(白金)
        screen.blit(font_mid.render("白金版获得方式", True, WARN_COLOR), (tx, 108))
        y = 132
        if not locs:
            txt = fit_text("无法自然获得(活动/传入)", font_tiny, right_w)
            screen.blit(font_tiny.render(txt, True, SUB_COLOR), (tx, y))
            y += 18
        for loc in locs[:4]:
            line1 = fit_text(loc["location"], font_tiny, right_w)
            line2 = fit_text("- %s %s" % (loc["method"], loc["notes"]), font_tiny, right_w)
            screen.blit(font_tiny.render(line1, True, TEXT_COLOR), (tx, y))
            y += 16
            if loc["method"] or loc["notes"]:
                screen.blit(font_tiny.render(line2, True, SUB_COLOR), (tx, y))
                y += 16
            if y > FB_HEIGHT - 40:
                break

    draw_top_bar(p, 0, total_pages(p))
    draw_bottom_bar()


# ---------------------------------------------------------------------------
# 招式表列宽: 属性列按"实际字体最宽属性名"自动撑开(避免"超能力"被截断),
# 招式列吃掉剩余宽度, 保证老设备上 wqy 字体也不会截字。
# 横屏 7 列, 竖屏去掉 命中/分类 压缩为 5 列。
# ---------------------------------------------------------------------------
_TYPE_COL_W = max(font_move.size(t)[0] for t in TYPE_COLORS) + 8   # 属性列宽
_TABLE_W = FB_WIDTH - 10                                            # 6..FB_WIDTH-4


def _build_move_cols():
    if PORTRAIT:
        fixed = [("等级", 30), (None, 0), ("属性", _TYPE_COL_W), ("威力", 32), ("PP", 24)]
        keys = ("level", "name", "type", "power", "pp")
        w = _TABLE_W - (30 + _TYPE_COL_W + 32 + 24)
    else:
        fixed = [("等级", 34), (None, 0), ("属性", _TYPE_COL_W), ("分类", 36),
                 ("威力", 32), ("命中", 32), ("PP", 24)]
        keys = ("level", "name", "type", "category", "power", "accuracy", "pp")
        w = _TABLE_W - (34 + _TYPE_COL_W + 36 + 32 + 32 + 24)
    cols = [(t, w if t is None else cw) for t, cw in fixed]
    # 第二列就是 招式, 用剩余宽度
    cols[1] = ("招式", w)
    return cols, keys


MOVE_COLS, MOVE_COL_KEYS = _build_move_cols()


def draw_moves(p, move_page):
    """第 2+ 页: 全屏招式表(横竖屏自适应, 铺到底部)。"""
    moves = p["moves"]
    start = move_page * MOVES_PER_PAGE
    chunk = moves[start:start + MOVES_PER_PAGE]
    cols, keys = MOVE_COLS, MOVE_COL_KEYS
    font = font_move

    # 表头
    x = 6
    y = MOVE_HEADER_Y
    for title, w in cols:
        screen.blit(font.render(title, True, ACCENT_COLOR), (x, y))
        x += w
    pygame.draw.line(screen, BAR_COLOR, (4, y + font.get_height() + 1),
                     (FB_WIDTH - 4, y + font.get_height() + 1), 1)

    # 数据行
    y = MOVE_LIST_TOP
    for i, mv in enumerate(chunk):
        # 隔行底色
        if i % 2 == 0:
            pygame.draw.rect(screen, PANEL_COLOR, (4, y, FB_WIDTH - 8, ROW_H))
        x = 6
        for (title, w), key in zip(cols, keys):
            val = mv[key]
            if key == "type":
                color = TYPE_COLORS.get(val, TEXT_COLOR)
                text = val                      # 属性列已按实际宽度撑开, 不再截断
            elif key == "category":
                color = (255, 170, 170) if val == "物理" else \
                        (170, 200, 255) if val == "特殊" else SUB_COLOR
                text = fit_text(val, font, w - 4)
            else:
                color = TEXT_COLOR
                text = fit_text(val, font, w - 4)
            screen.blit(font.render(text, True, color), (x, y))
            x += w
        y += ROW_H

    # 无数据提示
    if not chunk:
        t = font_small.render("这只宝可梦没有招式数据", True, SUB_COLOR)
        screen.blit(t, (FB_WIDTH // 2 - t.get_width() // 2, 100))

    draw_top_bar(p, 1 + move_page, total_pages(p))
    # 招式页不画底部提示条, 表格直接铺到屏幕底部


def draw_matchups(p):
    """最后一页: 属性克制关系(克制谁 / 被谁克制 / 抵抗 / 免疫)。"""
    strong, weak, resist, immune = type_matchups(p)
    pages = total_pages(p)

    # 标题带自己属性, 一眼看出计算依据
    t = font_mid.render("属性克制", True, TEXT_COLOR)
    screen.blit(t, (6, 30))
    x = 6 + t.get_width() + 8
    for tp in p["types"]:
        x = draw_type_badge(x, 30, tp)

    def section(label, color, names, y, max_rows=2):
        """画一个小节: 标签 + 徽章流。返回下一个 y。"""
        screen.blit(font_small.render(label, True, color), (6, y))
        y += 20
        if not names:
            screen.blit(font_tiny.render("无", True, SUB_COLOR), (10, y))
            return y + 18
        y, rest = draw_badge_flow(names, 6, y, FB_WIDTH - 6, max_rows=max_rows)
        if rest:
            t = font_tiny.render("+%d" % rest, True, SUB_COLOR)
            screen.blit(t, (FB_WIDTH - t.get_width() - 6, y - 19))
        return y

    y = 60
    y = section("克制(打这些效果绝佳)", ACCENT_COLOR, strong, y)
    y = section("被克制(挨打效果绝佳)", WARN_COLOR, weak, y + 2)
    y = section("抵抗(受伤减半)", SUB_COLOR, resist, y + 2)
    if immune:
        t = font_small.render("完全免疫: " + "、".join(immune), True, ACCENT_COLOR)
        screen.blit(t, (6, y + 2))

    draw_top_bar(p, pages - 1, pages)
    draw_bottom_bar()


def render(p, page):
    """绘制第 page 页(0=概览, 中间=招式页, 末页=属性克制)。"""
    screen.fill(BG_COLOR)
    if page == 0:
        draw_overview(p)
    elif TYPE_CHART and page == total_pages(p) - 1:
        draw_matchups(p)
    else:
        draw_moves(p, page - 1)
    return spi_lcd.present()


# ---------------------------------------------------------------------------
# GPIO 按键(参考 test_button.py)
# ---------------------------------------------------------------------------
BUTTONS = {"K1": 18, "K2": 23, "K3": 24}
gpio = None
try:
    import RPi.GPIO as GPIO  # noqa: E402

    GPIO.setmode(GPIO.BCM)
    for name, pin in BUTTONS.items():
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    gpio = GPIO
    print("GPIO 初始化完成: " + ", ".join("%s=GPIO%d" % (n, p) for n, p in BUTTONS.items()))
except (ImportError, Exception) as e:
    if not isinstance(e, ImportError):
        print("GPIO 初始化失败(%s)," % e, end=" ")
    print("进入键盘模拟模式: 按 1/2/3 代替 K1/K2/K3, Esc 退出。")


def poll_buttons():
    """返回本周期触发的按键列表(带按下沿检测 + 长按连发)。"""
    import time as _time

    now = _time.time()
    events = []
    if gpio is not None:
        for name, pin in BUTTONS.items():
            pressed = gpio.input(pin) == gpio.LOW
            st = _btn_state[name]
            if pressed and not st["down"]:
                st["down"], st["t0"], st["rep"] = True, now, False
                events.append(name)
            elif pressed and st["down"] and now - st["t0"] > 0.45:
                # 长按连发
                if now - st.get("last_rep", 0) > 0.15:
                    st["last_rep"] = now
                    st["rep"] = True
                    events.append(name)
            elif not pressed and st["down"]:
                st["down"] = False
    return events


_btn_state = {name: {"down": False, "t0": 0, "rep": False, "last_rep": 0} for name in BUTTONS}


def handle_key(event_key):
    """模拟模式键盘 -> 按键事件名。"""
    import pygame as _pg
    mapping = {_pg.K_1: "K1", _pg.K_2: "K2", _pg.K_3: "K3"}
    return mapping.get(event_key)


def handle_event(name, state, mon_list=None):
    """处理按键: 更新 (宝可梦索引, 页码) 状态。mon_list 缺省为全部。"""
    mon_list = POKEMONS if mon_list is None else mon_list
    if not mon_list:
        return
    p = mon_list[state["idx"]]
    pages = total_pages(p)
    if name == "K1":        # 下一页(本只内循环)
        state["page"] = (state["page"] + 1) % pages
    elif name == "K2":      # 上一只宝可梦
        state["idx"] = (state["idx"] - 1) % len(mon_list)
        state["page"] = 0
    elif name == "K3":      # 下一只宝可梦
        state["idx"] = (state["idx"] + 1) % len(mon_list)
        state["page"] = 0


# ---------------------------------------------------------------------------
# 浏览主循环: 可独立运行, 也可被 pokemon.py 当作"浏览页"调用
# ---------------------------------------------------------------------------
def _k3_down():
    """K3 当前是否被按住(GPIO 或 模拟键盘 '3')。"""
    if gpio is not None:
        return gpio.input(BUTTONS["K3"]) == gpio.LOW
    return pygame.key.get_pressed()[pygame.K_3]


def wait_release(name="K3", timeout=3.0):
    """等待按键物理松开并复位轮询状态。

    用于"长按返回"等场景: 若带着按住状态返回上层界面, 上层轮询会把
    长按连发事件误判为新按键(如 主界面把 K3 残留当作"确定"再次进入)。
    """
    if gpio is not None:
        t0 = time.time()
        while gpio.input(BUTTONS[name]) == gpio.LOW and time.time() - t0 < timeout:
            time.sleep(0.02)
    else:
        pygame.event.clear()          # 丢弃模拟模式下排队中的按键事件
    for st in _btn_state.values():
        st.update(down=False, t0=0, rep=False, last_rep=0)


def browse(mon_list=None, on_viewed=None, back_hold=0.8):
    """浏览模式主循环。

    参数:
      mon_list  : 允许浏览的宝可梦列表(缺省=全部); K2/K3 在此列表内切换
      on_viewed : 每次展示某只宝可梦时的回调 on_viewed(pokemon)
      back_hold : K3 按住超过该秒数返回(调用方); 短按 K3 仍是"下一只"

    返回: "back"=长按K3返回; "quit"=窗口关闭/Esc。

    独立运行(python show_pokemon.py)时, "back"/"quit" 都直接退出程序。
    """
    global BACK_HINT
    mon_list = list(POKEMONS if mon_list is None else mon_list)
    if not mon_list:
        return "quit"
    from_menu = on_viewed is not None
    BACK_HINT = from_menu

    state = {"idx": 0, "page": 0}
    k3_t0 = [None]          # K3 按下时刻(自行处理 短按/长按)

    def cur():
        return mon_list[state["idx"]]

    def redraw():
        r = render(cur(), state["page"])
        if on_viewed:
            on_viewed(cur())
        return r

    running = redraw()
    clock = pygame.time.Clock()
    while running:
        now = time.time()
        if gpio is None:
            # 模拟模式: 键盘事件
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_q):
                        running = False
                    elif event.key == pygame.K_3:
                        if k3_t0[0] is None:
                            k3_t0[0] = now
                    else:
                        name = handle_key(event.key)
                        if name:
                            handle_event(name, state, mon_list)
                            running = redraw()
            clock.tick(30)
        else:
            # 真机: GPIO 轮询(K3 事件交由长按检测处理)
            for name in poll_buttons():
                if name == "K3":
                    if k3_t0[0] is None:
                        k3_t0[0] = now
                    continue
                handle_event(name, state, mon_list)
                running = redraw()
            clock.tick(60)

        # K3 短按=下一只 / 长按=返回
        if k3_t0[0] is not None:
            if _k3_down() and now - k3_t0[0] >= back_hold:
                wait_release("K3")     # 等 K3 松开再返回, 防止主界面误判为"确定"
                return "back"
            if not _k3_down():
                handle_event("K3", state, mon_list)
                running = redraw()
                k3_t0[0] = None

    return "quit"


def run_screenshots():
    """截图模式(本机布局验证, 不进入主循环)。"""
    samples = [(0, 0), (0, 1), (2, 1), (106, 0)]
    if TYPE_CHART:
        samples.append((5, total_pages(POKEMONS[5]) - 1))     # 克制页(单属性)
        samples.append((7, total_pages(POKEMONS[7]) - 1))     # 克制页(双属性)
    for i, (idx, page) in enumerate(samples):
        render(POKEMONS[idx], page)
        out = os.path.join(BASE_DIR, "_shot_%d.png" % i)
        pygame.image.save(screen, out)
        print("已保存:", out)


def main():
    """独立运行入口: 浏览全部宝可梦。"""
    print("共 %d 只宝可梦。开始浏览..." % len(POKEMONS))
    try:
        browse()
    except KeyboardInterrupt:
        print("\n退出图鉴浏览器。")
    finally:
        if gpio is not None:
            gpio.cleanup()
        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    if "--screenshot" in sys.argv:
        run_screenshots()
    else:
        main()
