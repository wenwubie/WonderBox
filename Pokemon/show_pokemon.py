# -*- coding: utf-8 -*-
"""SPI 屏宝可梦图鉴浏览器（第四世代 / 白金版）。

主界面入口: python pokemon.py  (菜单 / 浏览记录 / 设置, 推荐从主界面进入)
本文件也可独立运行: python show_pokemon.py 浏览设置中选中的世代。

布局: 320x240
    第 1 页(概览): 左边图片, 右边 编号/名称/属性/白金获得方式
    第 2+ 页(招式): 招式表行数自适应, 模拟模式保留底部按键提示
    末页(克制): 本只宝可梦的属性克制关系(克制/被克制/抵抗/免疫)

按键:
    K1 (GPIO5): 下一页
    K2 (GPIO23): 短按切换到上一只宝可梦; 长按 0.6 秒收藏/取消收藏当前宝可梦
    K3 (GPIO24): 切换到下一只宝可梦(长按返回)

收藏记录持久保存于 pokedex_data/favorites.json, 顶栏显示当前是否已收藏。

本机模拟模式: 键盘 1/2/3 代替 K1/K2/K3, Esc 退出。
截图模式: python show_pokemon.py --screenshot  (渲染两页样例存 PNG 后退出)
"""
import json
import math
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(BASE_DIR))

from common import spi_lcd
from common import ui_theme
from common.button_input import BUTTON_PINS as BUTTONS
from common import audio as audio_output
from common import sfx as sfx_helper
from common import tts

# 声明需要声音，须早于下方模块级 spi_lcd.init()
audio_output.prepare()

# ---------------------------------------------------------------------------
# 数据路径(相对本脚本所在目录)
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "pokedex_data", "pokemon_platinum.json")
IMG_DIR = os.path.join(BASE_DIR, "pokedex_data", "images")
SETTINGS_FILE = os.path.join(BASE_DIR, "pokedex_data", "settings.json")
FAVORITES_FILE = os.path.join(BASE_DIR, "pokedex_data", "favorites.json")
FAVORITE_HOLD_SECONDS = 0.6   # 长按 K2 收藏/取消收藏的秒数(短按仍是"上一只")

FB_WIDTH = spi_lcd.FB_WIDTH
FB_HEIGHT = spi_lcd.FB_HEIGHT
# ---------------------------------------------------------------------------
# 颜色(跟随全局界面风格, 见 common/ui_theme.py)
# ---------------------------------------------------------------------------
_theme = ui_theme.style()
BG_COLOR = _theme["bg"]
PANEL_COLOR = _theme["panel"]
BAR_COLOR = _theme["panel_hi"]
TEXT_COLOR = _theme["text"]
SUB_COLOR = _theme["sub"]
ACCENT_COLOR = _theme["accent"]
WARN_COLOR = _theme["title"]
ROW_BG = tuple((a + b) // 2 for a, b in zip(_theme["bg"], _theme["panel"]))  # 招式表隔行底色

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
# 招式页布局: 真机表格铺到底部, 模拟模式为按键提示预留空间,
# 自动挑选"能塞下最多行"的最大字号, 保证小屏也能一页显示尽量多的招式。
# 小字屏(真机 wqy 字体偏高偏宽)会自动降到 12/11/10 号字。
# ---------------------------------------------------------------------------
MOVE_HEADER_Y = 30 if PORTRAIT else 26    # 表头起始 y
MOVE_BOTTOM = FB_HEIGHT - (20 if spi_lcd.is_simulate() else 2)
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

GENERATION_RANGES = {1: (1, 151), 2: (152, 251), 3: (252, 386), 4: (387, 493)}


def normalize_generations(generations):
    if not isinstance(generations, list):
        return list(GENERATION_RANGES)
    selected = sorted({generation for generation in generations
                       if type(generation) is int and generation in GENERATION_RANGES})
    return selected if selected or not generations else list(GENERATION_RANGES)


def generation_pokemon(generations):
    generations = normalize_generations(generations)
    return [pokemon for pokemon in POKEMONS
            if any(start <= pokemon["id"] <= end
                   for generation, (start, end) in GENERATION_RANGES.items()
                   if generation in generations)]


def load_selected_generations():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as settings_file:
            settings = json.load(settings_file)
        generations = settings.get("generations") if isinstance(settings, dict) else None
    except (OSError, ValueError):
        generations = None
    return normalize_generations(generations)


# ---------------------------------------------------------------------------
# 收藏记录(持久化, 与"已发现"相互独立)
# ---------------------------------------------------------------------------
def load_favorites(path=None):
    """读取收藏的宝可梦 id 集合; 文件缺失/损坏时返回空集合, 并过滤无效 id。"""
    try:
        with open(path or FAVORITES_FILE, encoding="utf-8") as favorites_file:
            data = json.load(favorites_file)
        ids = set(data.get("ids", [])) if isinstance(data, dict) else set()
    except (OSError, ValueError, TypeError):
        ids = set()
    valid = {pokemon["id"] for pokemon in POKEMONS}
    return {value for value in ids if isinstance(value, int) and value in valid}


def save_favorites(ids, path=None):
    with open(path or FAVORITES_FILE, "w", encoding="utf-8") as favorites_file:
        json.dump({"ids": sorted(ids)}, favorites_file, ensure_ascii=False)


def is_favorite(pokemon, favorites):
    return pokemon["id"] in favorites


def toggle_favorite(pokemon, favorites):
    """原地切换收藏状态, 返回 (是否已收藏, 新的集合)。"""
    pid = pokemon["id"]
    if pid in favorites:
        favorites.remove(pid)
        return False, favorites
    favorites.add(pid)
    return True, favorites


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
def draw_heart_icon(cx, cy, size, color, hollow=False, background=None):
    """画收藏爱心(两个上圆弧 + 下尖角)。

    hollow=True 时用底色再画一圈稍小的爱心, 形成"未收藏"的空心描边效果。
    不依赖字体里的 ♥ 字符, 真机 wqy 字体也能正常显示。
    """
    def heart(fill, scale):
        r = size * scale / 2.0
        top = cy - r * 0.35
        pygame.draw.circle(screen, fill, (int(cx - r * 0.4), int(top)),
                           max(1, int(r * 0.5)))
        pygame.draw.circle(screen, fill, (int(cx + r * 0.4), int(top)),
                           max(1, int(r * 0.5)))
        pygame.draw.polygon(screen, fill, [(int(cx - r * 0.9), int(top)),
                                           (int(cx + r * 0.9), int(top)),
                                           (int(cx), int(cy + r * 0.95))])
    if hollow:
        heart(color, 1.0)
        heart(background or BAR_COLOR, 0.62)
    else:
        heart(color, 1.0)


def draw_top_bar(p, page, pages, favorites=None):
    pygame.draw.rect(screen, BAR_COLOR, (0, 0, FB_WIDTH, 24))
    t1 = font_small.render("#%03d %s" % (p["id"], p["name_zh"]), True, TEXT_COLOR)
    t2 = font_small.render("%d/%d" % (page + 1, pages), True, ACCENT_COLOR)
    screen.blit(t1, (8, 4))
    screen.blit(t2, (FB_WIDTH - t2.get_width() - 8, 4))

    # 收藏状态: 顶栏中央用"爱心图标 + 文字", 已收藏=实心亮色, 未收藏=空心
    # 并兼作操作提示。收藏一律用爱心表示, 与"已发现"的星星区分开。
    active = favorites if favorites is not None else _favorite_ids
    fav = is_favorite(p, active)
    label = "已收藏" if fav else "长按K2收藏"
    color = ACCENT_COLOR if fav else SUB_COLOR
    left_end = 8 + t1.get_width()
    right_start = FB_WIDTH - t2.get_width() - 8
    icon_w = 16
    label = fit_text(label, font_tiny, max(16, right_start - left_end - 8 - icon_w))
    tf = font_tiny.render(label, True, color)
    group_w = icon_w + tf.get_width()
    x = left_end + max(0, (right_start - left_end - group_w) // 2)
    draw_heart_icon(x + icon_w // 2, 12, 13, color, hollow=not fav)
    screen.blit(tf, (x + icon_w, 5))


_footer_button_rects = []
# 当前浏览会话的收藏 id 集合: browse() 会指向自己持有的 set,
# render()/draw_top_bar() 在不显式传 favorites 时读它, 保持 render(p, page) 两参兼容。
_favorite_ids = set()


def draw_bottom_bar():
    global _footer_button_rects
    pygame.draw.rect(screen, BAR_COLOR, (0, FB_HEIGHT - 18, FB_WIDTH, 18))
    buttons = (("K1", "翻页"), ("K2", "上一只"), ("K3", "下一只"))
    text = "    ".join(label for _, label in buttons)
    t = font_tiny.render(text, True, SUB_COLOR)
    y = FB_HEIGHT - 16
    screen.blit(t, ((FB_WIDTH - t.get_width()) // 2, y))
    _footer_button_rects = spi_lcd.text_button_rects(text, font_tiny, y, buttons)


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


def draw_overview(p, favorites=None):
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

    draw_top_bar(p, 0, total_pages(p), favorites)
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


def draw_moves(p, move_page, favorites=None):
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
        # 隔行底色(bg 与 panel 的混合, 保证深浅风格下都和文字有对比)
        if i % 2 == 0:
            pygame.draw.rect(screen, ROW_BG, (4, y, FB_WIDTH - 8, ROW_H))
        x = 6
        for (title, w), key in zip(cols, keys):
            val = mv[key]
            if key == "type":
                color = ui_theme.pick(ROW_BG, TYPE_COLORS.get(val, TEXT_COLOR))
                text = val                      # 属性列已按实际宽度撑开, 不再截断
            elif key == "category":
                color = (255, 170, 170) if val == "物理" else \
                        (170, 200, 255) if val == "特殊" else SUB_COLOR
                color = ui_theme.pick(ROW_BG, color)
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

    draw_top_bar(p, 1 + move_page, total_pages(p), favorites)
    if spi_lcd.is_simulate():
        draw_bottom_bar()


def draw_matchups(p, favorites=None):
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

    draw_top_bar(p, pages - 1, pages, favorites)
    draw_bottom_bar()


def render(p, page, favorites=None):
    """绘制第 page 页(0=概览, 中间=招式页, 末页=属性克制)。"""
    if favorites is None:
        favorites = _favorite_ids
    screen.fill(BG_COLOR)
    if page == 0:
        draw_overview(p, favorites)
    elif TYPE_CHART and page == total_pages(p) - 1:
        draw_matchups(p, favorites)
    else:
        draw_moves(p, page - 1, favorites)
    return spi_lcd.present(poll_events=False)


# ---------------------------------------------------------------------------
# GPIO 按键(参考 test_button.py)
# ---------------------------------------------------------------------------
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
def input_actions(mouse_action, hold=None, fav_hold=None):
    """采集一帧动作。

    hold     : K3 长按手势(短按 K3 / 长按 BACK)
    fav_hold : K2 长按手势(短按 K2 / 长按 FAVORITE); 长按期间会屏蔽
               poll_buttons 产生的 K2 连发, 避免误翻到上一只。
    """
    actions = []
    if gpio is not None:
        blocked = set()
        if hold is not None:
            blocked.add("K3")
        if fav_hold is not None:
            blocked.add("K2")
        actions = [name for name in poll_buttons() if name not in blocked]
        for gesture, key in ((hold, "K3"), (fav_hold, "K2")):
            if gesture is None:
                continue
            source = ("gpio", key)
            if gpio.input(BUTTONS[key]) == gpio.LOW:
                gesture.press(source)
                action = gesture.poll()
            else:
                action = gesture.release(source)
            if action:
                actions.append(action)
        return actions if spi_lcd.pump() else None

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            return None
        action = None
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_q):
                return None
            action = handle_key(event.key)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            action = mouse_action(event)
        # 两路长按手势不能串联覆盖: 按下事件交给"拥有该键"的手势(它可能吞掉
        # 短按), 松开事件则两路都跑 release, 取第一个有效结果。否则 K3 松开
        # 产生的 "K3" 会被 K2 手势的 release(None) 冲掉。
        if fav_hold is not None and action == "K2":
            action = fav_hold.process_event(event, action)
        elif hold is not None and action == "K3":
            action = hold.process_event(event, action)
        else:
            original = action
            action = None
            for gesture in (hold, fav_hold):
                if gesture is not None:
                    emitted = gesture.process_event(event, original)
                    if emitted and action is None:
                        action = emitted
            if action is None:
                action = original
        if action:
            actions.append(action)
    for gesture in (hold, fav_hold):
        if gesture is not None:
            action = gesture.poll()
            if action:
                actions.append(action)
    return actions


def browse(mon_list=None, on_viewed=None, back_hold=0.8, hold=None,
           favorites=None, fav_hold=None, favorites_file=None):
    """浏览模式主循环。

    参数:
      mon_list  : 允许浏览的宝可梦列表(缺省=全部); K2/K3 在此列表内切换
      on_viewed : 每次展示某只宝可梦时的回调 on_viewed(pokemon)
      back_hold : K3 按住超过该秒数返回(调用方); 短按 K3 仍是"下一只"
      favorites : 收藏 id 集合(原地修改并即时落盘); 缺省从 favorites.json 读取
      fav_hold  : K2 长按手势, 缺省用 SimulatedHold("K2", "FAVORITE", 0.6)
      favorites_file : 覆盖收藏文件路径(主界面传入, 便于与设置同目录/测试隔离)

    长按 K2 收藏/取消收藏当前宝可梦(短按 K2 仍是"上一只"), 顶栏显示收藏状态。

    返回: "back"=长按K3返回; "quit"=窗口关闭/Esc。

    独立运行(python show_pokemon.py)时, "back"/"quit" 都直接退出程序。
    """
    global _favorite_ids
    mon_list = list(POKEMONS if mon_list is None else mon_list)
    if not mon_list:
        return "quit"

    state = {"idx": 0, "page": 0}
    if hold is None:
        hold = spi_lcd.SimulatedHold("K3", "BACK", back_hold)
    if fav_hold is None:
        fav_hold = spi_lcd.SimulatedHold("K2", "FAVORITE", FAVORITE_HOLD_SECONDS)
    if favorites is None:
        favorites = load_favorites(favorites_file)
    _favorite_ids = favorites

    sound = sfx_helper.SFX(sfx_helper.game_media(__file__))
    speaker = tts.Speaker(pregen_dir=os.path.join(BASE_DIR, "media", "tts"))

    def cur():
        return mon_list[state["idx"]]

    def say_name():
        """朗读当前宝可梦名字（本地 ogg，命中即播）；返回是否真的播放。"""
        name = str(cur().get("name_zh", "")).strip()
        if name:
            return speaker.speak(name)
        return False

    def redraw():
        r = render(cur(), state["page"])
        if on_viewed:
            on_viewed(cur())
        return r

    running = redraw()
    say_name()  # 进入浏览时读第一只的名字
    clock = pygame.time.Clock()
    while running:
        actions = input_actions(
            lambda event: spi_lcd.button_from_mouse(event, _footer_button_rects),
            hold, fav_hold)
        if actions is None:
            break
        for action in actions:
            if sfx_helper.is_press(action):
                sound.button()  # 每次短按都有按键音反馈
            if action == "BACK":
                sound.close()
                return "back"
            if action == "FAVORITE":
                favored, favorites = toggle_favorite(cur(), favorites)
                save_favorites(favorites, favorites_file)
                sound.play("correct") if favored else sound.button()
                running = redraw()
                if not running:
                    break
                continue
            idx_before = state["idx"]
            handle_event(action, state, mon_list)
            if state["idx"] != idx_before:
                say_name()  # 切换宝可梦时读名字
            running = redraw()
            if not running:
                break
        clock.tick(30 if gpio is None else 60)

    sound.close()
    return "quit"


def run_screenshots():
    """截图模式(本机布局验证, 不进入主循环)。"""
    samples = [(0, 0), (0, 1), (2, 1), (106, 0)]
    if TYPE_CHART:
        samples.append((5, total_pages(POKEMONS[5]) - 1))     # 克制页(单属性)
        samples.append((7, total_pages(POKEMONS[7]) - 1))     # 克制页(双属性)
    for i, (idx, page) in enumerate(samples):
        # 第 1 张顺便演示"已收藏"顶栏状态
        render(POKEMONS[idx], page, {POKEMONS[0]["id"]} if i == 0 else set())
        out = os.path.join(BASE_DIR, "_shot_%d.png" % i)
        pygame.image.save(screen, out)
        print("已保存:", out)


def main():
    """独立运行入口: 浏览设置中选中的世代。"""
    monsters = generation_pokemon(load_selected_generations())
    print("共 %d 只宝可梦。模拟模式可点击底栏功能文字。" % len(monsters))
    try:
        if monsters:
            browse(monsters)
        else:
            print("没有选择宝可梦世代，请在主界面的设置中勾选。")
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
