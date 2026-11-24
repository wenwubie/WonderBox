# -*- coding: utf-8 -*-
"""全局界面风格 —— 主界面与所有子游戏共用。

风格选择入口在 main.py 主界面的"设置"里, 选择结果持久化到项目根目录
settings.json; 各子游戏启动时调用 ui_theme.style() 取当前风格配色,
整个宝盒界面风格统一。

风格字典的 key 约定(各界面按语义取用, 缺谁补谁):
    bg        页面背景
    panel     卡片/面板底色
    panel_hi  选中卡片/高亮面板
    text      面板上的正文色
    sub       面板上的次要文字
    accent    主强调色(按钮/选中框)
    title     标题/品牌强调色
    deco      分隔线/描边/装饰
    hint_bg   底部提示条背景
"""
import json
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_FILE = os.path.join(ROOT_DIR, "settings.json")
DEFAULT_STYLE = "宝盒"

# 界面风格(可自由增删, 名称会出现在设置项里)
STYLES = {
    "宝盒": {
        "bg": (46, 64, 60), "panel": (246, 244, 236), "panel_hi": (217, 235, 226),
        "text": (52, 70, 68), "sub": (108, 130, 124),
        "accent": (74, 145, 135), "title": (84, 160, 148),
        "deco": (188, 205, 196), "hint_bg": (56, 76, 69),
    },
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
        "deco": (246, 178, 200), "hint_bg": (250, 196, 212),
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


def _luminance(color):
    r, g, b = color[:3]
    return 0.299 * r + 0.587 * g + 0.114 * b


def readable(bg, light=(243, 246, 242), dark=(38, 48, 46)):
    """返回在指定背景上可读的文字颜色。"""
    return light if _luminance(bg) < 128 else dark


def pick(bg, color, tolerance=40):
    """color 与背景对比足够时返回 color, 否则退回可读色。"""
    if abs(_luminance(bg) - _luminance(color)) >= tolerance:
        return color
    return readable(bg)


def shift(color, amount=30):
    """把颜色向白(底色深时)或黑(底色浅时)方向偏移, 派生装饰色。"""
    if _luminance(color) < 128:
        return tuple(min(255, v + amount) for v in color[:3])
    return tuple(max(0, v - amount) for v in color[:3])


def style_name():
    """当前全局风格名(读 settings.json, 失败回默认)。"""
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        name = data.get("style") if isinstance(data, dict) else None
    except Exception:
        name = None
    return name if name in STYLES else DEFAULT_STYLE


def set_style(name):
    """保存全局风格(立即持久化, 保留音量/语音等其它设置)。"""
    if name not in STYLES:
        return
    from common import sound_settings
    sound_settings.update({"style": name})


def style():
    """当前风格字典(不要修改返回值)。"""
    return STYLES[style_name()]


def palette():
    """当前风格 + 背景可读派生色。

    text_bg / sub_bg / title_bg: 保证画在 bg 上可读的文字色,
    line_bg: 比 bg 略亮(或略暗)的分隔线色。
    供"深底浅卡"类界面(如主界面)直接取用。
    """
    st = dict(style())
    bg = st["bg"]
    st["text_bg"] = pick(bg, st["text"])
    st["sub_bg"] = pick(bg, st["sub"])
    st["title_bg"] = pick(bg, st["title"])
    st["line_bg"] = shift(bg, 18)
    return st
