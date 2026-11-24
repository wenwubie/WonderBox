"""Wonder Box 奇趣宝盒的游戏入口。"""

from dataclasses import dataclass
import glob
import importlib
import math
import os
import subprocess
import sys
import time

from common import audio as audio_output, sfx as sfx_helper, sound_settings
from common import spi_lcd
from common import ui_theme
from common.button_input import BUTTON_PINS, GPIOButtons, QUIT_HOLD_SECONDS

import pygame


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
K3_KEYS = (pygame.K_3, pygame.K_KP3, pygame.K_RETURN, pygame.K_KP_ENTER)


@dataclass(frozen=True)
class Game:
    name: str
    description: str
    path: str
    icon: str
    color: tuple[int, int, int]


@dataclass(frozen=True)
class GameCategory:
    name: str
    description: str
    directory: str
    icon: str
    color: tuple[int, int, int]
    games: tuple[Game, ...]

    def as_game(self):
        return Game(self.name, self.description, self.directory, self.icon, self.color)


GAMES = (
    Game("宝可梦图鉴", "图鉴探索", "Pokemon/pokemon.py", "pokemon", (224, 95, 78)),
    Game("头脑挑战", "双人答题", "Brain Challenge/brain_challenge.py", "brain", (66, 153, 139)),
    Game("脑筋急转弯", "趣味问答", "Riddles/Riddles.py", "riddle", (225, 165, 55)),
    Game("骰子对决", "双人对战", "Quick Duel/quick_duel.py", "dice", (89, 143, 206)),
    Game("幸运转盘", "一起玩耍", "Lucky Wheel/lucky_wheel.py", "wheel", (230, 129, 95)),
    Game("星愿占卜屋", "星座占卜", "Magic/Magic.py", "magic", (172, 125, 176)),
    Game("诗词大赛", "唐诗宋词", "Poetry Quest/poetry.py", "poetry", (186, 91, 73)),
    Game("宠物乐园", "萌宠养成", "Virtual Pet/virtual_pet.py", "pet", (87, 158, 120)),
    Game("狼人杀", "主持人助手", "Werewolf/werewolf.py", "werewolf", (73, 110, 97)),
    Game("粘猴", "搭桥闯关", "Mini Games/Sticky Monkey/sticky_monkey.py", "monkey", (126, 177, 82)),
)

GAME_CATEGORIES = (
    GameCategory("小游戏", "1 款游戏", "Mini Games", "minigames", (126, 177, 82), (GAMES[-1],)),
)
CATEGORIZED_PATHS = {game.path for category in GAME_CATEGORIES for game in category.games}
DIRECT_GAMES = tuple(game for game in GAMES if game.path not in CATEGORIZED_PATHS)
HOME_GAMES = DIRECT_GAMES + tuple(category.as_game() for category in GAME_CATEGORIES)
MINI_GAMES_HOME_INDEX = len(DIRECT_GAMES)

# 设置页条目：(键, 名称)。风格由 ui_theme 管理，其余由 sound_settings 管理。
SETTINGS_ITEMS = (
    ("style", "界面风格"),
    ("sfx_volume", "按键音量"),
    ("voice_volume", "语音音量"),
    ("voice_enabled", "语音提示"),
)


class LauncherState:
    def __init__(self, show_declaration=False):
        self.selected = 0
        self.confirming_power = False
        self.power_selected = 0
        self.notice = ""
        self.show_declaration = show_declaration
        self.show_settings = False
        self.settings_selection = 0
        self.settings_editing = False
        self.show_category = None
        self.return_selection = MINI_GAMES_HOME_INDEX

    @property
    def visible_games(self):
        if self.show_category is None:
            return HOME_GAMES
        return GAME_CATEGORIES[self.show_category].games

    @property
    def settings_index(self):
        return len(HOME_GAMES)

    @property
    def selected_game(self):
        if self.show_category is not None:
            category_games = GAME_CATEGORIES[self.show_category].games
            return category_games[self.selected] if self.selected < len(category_games) else None
        return DIRECT_GAMES[self.selected] if self.selected < len(DIRECT_GAMES) else None

    def select_visible(self, index):
        if self.show_category is None:
            if index < len(DIRECT_GAMES):
                self.selected = index
                return "LAUNCH"
            category_index = index - len(DIRECT_GAMES)
            if 0 <= category_index < len(GAME_CATEGORIES):
                self.return_selection = index
                self.show_category = category_index
                self.selected = 0
                return "OPEN_CATEGORY"
            return None

        category = GAME_CATEGORIES[self.show_category]
        if index < len(category.games):
            self.selected = index
            return "LAUNCH"
        return None

    def handle_action(self, action):
        if self.show_declaration:
            if action == "POWER":
                return "EXIT"
            return "ACCEPT_DECLARATION" if action == "K3" else None
        if self.show_settings:
            count = len(SETTINGS_ITEMS)
            if action == "POWER":  # 长按 K3 直接返回主界面
                self.settings_editing = False
                return "CLOSE_SETTINGS"
            if self.settings_editing:
                if action == "K1":
                    return "SETTING_STEP_DOWN"
                if action == "K2":
                    return "SETTING_STEP_UP"
                if action == "K3":
                    self.settings_editing = False
                    return None
                return None
            # 浏览模式：K1/K2 切换设置项，K3 进入调节
            if action == "K1":
                self.settings_selection = (self.settings_selection - 1) % count
                return None
            if action == "K2":
                self.settings_selection = (self.settings_selection + 1) % count
                return None
            if action == "K3":
                self.settings_editing = True
                return None
            if action and action.startswith("SELECT_"):
                index = int(action[-1:])
                if 0 <= index < count:
                    self.settings_selection = index
                    self.settings_editing = True
                return None
            return None
        if action == "BACK" and self.show_category is not None:
            self.show_category = None
            self.selected = self.return_selection
            return "CLOSE_CATEGORY"
        if action == "POWER":
            self.confirming_power = not self.confirming_power
            self.power_selected = 0
            self.notice = ""
        elif self.confirming_power:
            if action in ("K1", "K2"):
                self.power_selected = 1 - self.power_selected
            elif action == "POWER_CANCEL":
                self.confirming_power = False
            elif action == "POWER_CONFIRM":
                return "SHUTDOWN"
            elif action == "K3":
                if self.power_selected == 1:
                    return "SHUTDOWN"
                self.confirming_power = False
        elif action in ("K1", "K2"):
            item_count = len(self.visible_games)
            if self.show_category is None:
                item_count += 1
            self.selected = (self.selected + (-1 if action == "K1" else 1)) % item_count
            self.notice = ""
        elif action == "K3":
            if self.show_category is None and self.selected == self.settings_index:
                return "SETTINGS"
            return self.select_visible(self.selected)
        elif action and action.startswith("GAME_"):
            index = int(action[5:])
            if self.show_category is None and index == self.settings_index:
                self.selected = index
                return "SETTINGS"
            if 0 <= index < len(self.visible_games):
                self.selected = index
                return self.select_visible(index)
        return None


def apply_theme():
    """按当前全局风格刷新主界面配色; 在设置里切换风格后再次调用即时生效。"""
    global BACKGROUND, PAPER, SELECTED, INK, MUTED, TEAL, LINE, CORAL, \
        LIGHT, LIGHT_TEAL, LIGHT_MUTED, DARK_LINE, FOOTER_BG
    p = ui_theme.palette()
    BACKGROUND = p["bg"]       # 页面背景
    PAPER = p["panel"]         # 卡片
    SELECTED = p["panel_hi"]   # 选中卡片
    INK = p["text"]            # 卡片上的正文
    MUTED = p["sub"]           # 卡片上的次要文字
    TEAL = p["accent"]         # 主强调(选中框/按钮)
    LINE = p["deco"]           # 卡片描边
    CORAL = ui_theme.pick(BACKGROUND, (232, 116, 100))  # 警示/危险色
    LIGHT = p["text_bg"]       # 背景上的正文
    LIGHT_TEAL = p["title_bg"]  # 背景上的强调
    LIGHT_MUTED = p["sub_bg"]  # 背景上的次要文字
    DARK_LINE = p["line_bg"]   # 背景上的分隔线/装饰点
    FOOTER_BG = p["hint_bg"]   # 底部按键栏


apply_theme()
# 按屏幕方向分行: 竖屏 240px 窄, 拆成 8 行; 横屏 320px 宽, 保持原 5 行。
DECLARATION_LINES = {
    True: (
        "此宝盒由文武天尊",
        "耗时七七四十九天,",
        "花费九九八十一万亿",
        "Token，打造而成。",
        "仅允许文武天尊或他的好朋友",
        "文怡然、文焕然、欧泽轩、",
        "欧阳沐希使用，",
        "否则将大祸临头！切记切记！",
    ),
    False: (
        "此宝盒由文武天尊耗时七七四十九天,",
        "花费九九八十一万亿Token，打造而成。",
        "仅允许文武天尊或他的好朋友",
        "文怡然、文焕然、欧泽轩、欧阳沐希使用，",
        "否则将大祸临头！切记切记！",
    ),
}


class LauncherDisplay:
    def __init__(self, screen):
        self.screen = screen
        self.width, self.height = screen.get_size()
        self.portrait = self.height > self.width
        self.brand_font = spi_lcd.load_font(19 if self.portrait else 17)
        self.brand_font.set_bold(True)
        self.chinese_font = spi_lcd.load_font(14 if self.portrait else 13)
        self.name_fonts = [spi_lcd.load_font(size) for size in (15, 14, 13, 12, 11, 10)]
        self.small_font = spi_lcd.load_font(12)
        self.button_font = spi_lcd.load_font(13)
        self.dialog_font = spi_lcd.load_font(19)
        self.declaration_font = spi_lcd.load_font(16 if self.portrait else 14)
        self.icon_font = spi_lcd.load_font(19)
        self.section_y = 62 if self.portrait else 49
        self.footer_top = self.height - 27
        top, gap, margin = self.section_y + 20, 6, 10
        columns = 2 if self.portrait else 3
        width = (self.width - 2 * margin - (columns - 1) * gap) // columns
        rows = (len(GAMES) + columns - 1) // columns
        height = (self.footer_top - top - 4 - (rows - 1) * gap) // rows  # 全部高度给游戏卡片
        self.game_rects = [pygame.Rect(margin + (index % columns) * (width + gap),
                          top + (index // columns) * (height + gap), width, height)
                           for index in range(len(GAMES))]
        self.home_game_rects = self.game_rects.copy()
        # 设置: 主界面右上角的小齿轮(与"奇趣宝盒"文字行平行对齐)
        subtitle_y = 30 if self.portrait else 27
        gear_size = 22
        self.settings_rect = pygame.Rect(
            self.width - gear_size - 10,
            subtitle_y + (self.chinese_font.get_height() - gear_size) // 2,
            gear_size, gear_size)
        self.buttons = [pygame.Rect(index * self.width // 3, self.footer_top,
                                    (index + 1) * self.width // 3 - index * self.width // 3, 27)
                        for index in range(3)]
        dialog_width = min(self.width - 24, 230)
        dialog_height = 150
        self.dialog = pygame.Rect((self.width - dialog_width) // 2,
                                  (self.footer_top - dialog_height) // 2,
                                  dialog_width, dialog_height)
        button_width = (dialog_width - 36) // 2
        self.power_buttons = [pygame.Rect(self.dialog.x + 12 + index * (button_width + 12),
                                          self.dialog.bottom - 45, button_width, 32)
                              for index in range(2)]
        self.declaration_button = pygame.Rect((self.width - 112) // 2, self.footer_top - 42, 112, 32)

    def text(self, value, font, color, position):
        image = font.render(value, True, color)
        self.screen.blit(image, position)
        return image.get_rect(topleft=position)

    def centered(self, value, font, color, center):
        image = font.render(value, True, color)
        self.screen.blit(image, image.get_rect(center=center))

    def draw_logo(self, origin_x, origin_y, size):
        def point(percent_x, percent_y):
            return (origin_x + round(size * percent_x / 100),
                origin_y + round(size * percent_y / 100))

        gold = (255, 206, 93)
        outline = (94, 77, 60)
        left = (point(25, 48), point(50, 59), point(50, 97), point(25, 86))
        right = (point(50, 59), point(75, 48), point(75, 86), point(50, 97))
        rim = (point(25, 48), point(50, 36), point(75, 48), point(50, 59))
        opening = (point(30, 48), point(50, 40), point(70, 48), point(50, 55))
        pygame.draw.polygon(self.screen, (226, 105, 88), left)
        pygame.draw.polygon(self.screen, (49, 151, 139), right)
        pygame.draw.polygon(self.screen, outline, left, 1)
        pygame.draw.polygon(self.screen, outline, right, 1)
        pygame.draw.polygon(self.screen, gold, rim)
        pygame.draw.polygon(self.screen, (31, 74, 68), opening)
        pygame.draw.lines(self.screen, gold, False, (point(28, 58), point(50, 67), point(72, 58)),
                  max(1, size // 24))
        for color, start, tip in (((190, 131, 43), (47, 42), (41, 32)),
                                  ((190, 131, 43), (50, 42), (50, 29)),
                                  (TEAL, (53, 42), (60, 32))):
            pygame.draw.line(self.screen, color, point(*start), point(*tip), max(1, size // 55))
        for color, center in ((gold, (40, 23)), (CORAL, (59, 28)), (TEAL, (36, 30))):
            pygame.draw.circle(self.screen, color, point(*center), max(1, size // 80))
        pygame.draw.polygon(self.screen, gold, (point(50, 2), point(55, 9),
                                                point(50, 16), point(45, 9)))
        pygame.draw.circle(self.screen, CORAL, point(31, 18), max(1, size // 24))
        pygame.draw.polygon(self.screen, TEAL, (point(69, 16), point(74, 21),
                                                point(69, 26), point(64, 21)))
        for center_x, center_y in ((25, 30), (77, 30)):
            pygame.draw.line(self.screen, CORAL, point(center_x - 3, center_y),
                             point(center_x + 3, center_y), 1)
            pygame.draw.line(self.screen, CORAL, point(center_x, center_y - 3),
                             point(center_x, center_y + 3), 1)

    def draw_icon(self, game, rect):
        pygame.draw.rect(self.screen, game.color, rect, border_radius=6)
        center = rect.center
        if game.icon == "pokemon":
            pygame.draw.circle(self.screen, PAPER, center, 9)
            pygame.draw.arc(self.screen, (190, 62, 54), (center[0] - 9, center[1] - 9, 18, 18), 0, 3.14, 8)
            pygame.draw.line(self.screen, INK, (center[0] - 9, center[1]), (center[0] + 9, center[1]), 2)
            pygame.draw.circle(self.screen, PAPER, center, 3)
            pygame.draw.circle(self.screen, INK, center, 3, 1)
        elif game.icon == "brain":
            for dx, dy in ((-4, -4), (4, -4), (-6, 2), (6, 2), (-3, 6), (3, 6)):
                pygame.draw.circle(self.screen, PAPER, (center[0] + dx, center[1] + dy), 4, 2)
            pygame.draw.line(self.screen, PAPER, (center[0], center[1] - 8), (center[0], center[1] + 8), 2)
        elif game.icon == "riddle":
            self.centered("?", self.icon_font, PAPER, center)
        elif game.icon == "dice":
            die = pygame.Rect(center[0] - 8, center[1] - 8, 16, 16)
            pygame.draw.rect(self.screen, PAPER, die, border_radius=3)
            for dx, dy in ((-4, -4), (0, 0), (4, 4)):
                pygame.draw.circle(self.screen, game.color, (center[0] + dx, center[1] + dy), 2)
        elif game.icon == "wheel":
            for points, color in (
                    ((center, (center[0], center[1] - 9), (center[0] + 9, center[1])), PAPER),
                    ((center, (center[0] + 9, center[1]), (center[0], center[1] + 9)), (255, 213, 105)),
                    ((center, (center[0], center[1] + 9), (center[0] - 9, center[1])), (118, 205, 190)),
                    ((center, (center[0] - 9, center[1]), (center[0], center[1] - 9)), (246, 183, 162))):
                pygame.draw.polygon(self.screen, color, points)
            pygame.draw.circle(self.screen, PAPER, center, 9, 1)
        elif game.icon == "magic":
            pygame.draw.circle(self.screen, PAPER, (center[0] - 2, center[1]), 8)
            pygame.draw.circle(self.screen, game.color, (center[0] + 2, center[1] - 3), 7)
            pygame.draw.line(self.screen, (255, 222, 129), (center[0] + 6, center[1] - 8),
                             (center[0] + 6, center[1] - 2), 2)
            pygame.draw.line(self.screen, (255, 222, 129), (center[0] + 3, center[1] - 5),
                             (center[0] + 9, center[1] - 5), 2)
        elif game.icon == "poetry":
            book = pygame.Rect(center[0] - 7, center[1] - 8, 14, 16)
            pygame.draw.rect(self.screen, PAPER, book, border_radius=2)
            pygame.draw.line(self.screen, game.color, (center[0] - 3, center[1] - 4),
                             (center[0] + 3, center[1] - 4), 1)
            pygame.draw.line(self.screen, game.color, (center[0] - 3, center[1]),
                             (center[0] + 3, center[1]), 1)
            pygame.draw.line(self.screen, game.color, (center[0] - 3, center[1] + 4),
                             (center[0] + 1, center[1] + 4), 1)
        elif game.icon == "pet":
            pygame.draw.ellipse(self.screen, PAPER, (center[0] - 7, center[1], 14, 10))
            for dx, dy in ((-7, -4), (-2, -7), (3, -7), (8, -4)):
                pygame.draw.circle(self.screen, PAPER, (center[0] + dx, center[1] + dy), 3)
        elif game.icon == "werewolf":
            x, y = center
            points = ((x - 9, y - 9), (x - 3, y - 5), (x + 3, y - 5), (x + 9, y - 9),
                      (x + 8, y + 3), (x, y + 9), (x - 8, y + 3))
            pygame.draw.polygon(self.screen, PAPER, points)
            for dx in (-4, 4):
                pygame.draw.circle(self.screen, game.color, (x + dx, y), 1)
            pygame.draw.circle(self.screen, game.color, (x, y + 5), 2)
        elif game.icon == "monkey":
            pygame.draw.circle(self.screen, (112, 67, 39), center, 10)
            pygame.draw.circle(self.screen, (255, 220, 167), (center[0] + 2, center[1] + 2), 7)
            pygame.draw.circle(self.screen, PAPER, (center[0] - 2, center[1] - 2), 2)
            pygame.draw.circle(self.screen, PAPER, (center[0] + 4, center[1] - 2), 2)
            pygame.draw.line(self.screen, (244, 181, 79), (center[0] - 9, center[1] + 8),
                             (center[0] + 10, center[1] + 8), 2)
        elif game.icon == "minigames":
            for dx, dy, color in ((-5, -4, PAPER), (4, 3, (255, 213, 105))):
                tile = pygame.Rect(center[0] + dx - 5, center[1] + dy - 5, 10, 10)
                pygame.draw.rect(self.screen, color, tile, border_radius=2)
                pygame.draw.rect(self.screen, INK, tile, 1, border_radius=2)
        elif game.icon == "back":
            pygame.draw.line(self.screen, PAPER, (center[0] + 7, center[1]),
                             (center[0] - 7, center[1]), 2)
            pygame.draw.line(self.screen, PAPER, (center[0] - 7, center[1]),
                             (center[0] - 1, center[1] - 6), 2)
            pygame.draw.line(self.screen, PAPER, (center[0] - 7, center[1]),
                             (center[0] - 1, center[1] + 6), 2)

    def draw_footer(self, confirming, declaration=False, settings=False,
                    settings_editing=False):
        pygame.draw.rect(self.screen, FOOTER_BG, (0, self.footer_top, self.width, 27))
        labels = (("", "", "确认") if declaration else
                  ("上一项", "下一项", "调整") if settings and not settings_editing else
                  ("减小", "增大", "确认") if settings else
                  ("切换", "切换", "确认") if confirming else ("上一项", "下一项", "进入"))
        for label, rect in zip(labels, self.buttons):
            if label:
                self.centered(label, self.button_font, LIGHT_TEAL, rect.center)

    def draw(self, state):
        self.screen.fill(BACKGROUND)
        if state.show_settings:
            self.draw_settings_page(state)
            self.draw_footer(False, settings=True, settings_editing=state.settings_editing)
            return
        for dot_y in range(10, self.footer_top, 24):
            for dot_x in range(12, self.width, 24):
                pygame.draw.circle(self.screen, DARK_LINE, (dot_x, dot_y), 1)
        size = 38 if self.portrait else 32
        self.draw_logo(10, 7, size)
        self.text("Wonder Box", self.brand_font, LIGHT, (size + 17, 7))
        self.text("奇趣宝盒", self.chinese_font, LIGHT_TEAL, (size + 18, 30 if self.portrait else 27))
        pygame.draw.line(self.screen, DARK_LINE, (10, self.section_y - 6),
                         (self.settings_rect.left - 8, self.section_y - 6))
        if state.show_declaration:
            self.draw_declaration()
            self.draw_footer(False, declaration=True)
            return
        if state.show_category is None:
            self.game_rects = self.home_game_rects
        else:
            entries_count = len(state.visible_games)
            margin, gap = 16, 10
            top = self.section_y + 28
            width = self.width - margin * 2
            available_height = self.footer_top - top
            height = min(54, (available_height - gap * (entries_count - 1)) // entries_count)
            total_height = height * entries_count + gap * (entries_count - 1)
            first_y = top + (available_height - total_height) // 2
            self.game_rects = [pygame.Rect(margin, first_y + index * (height + gap), width, height)
                               for index in range(entries_count)]
        if state.show_category is None:
            section_title = "界面风格 · 设置" if state.selected == state.settings_index else "全部游戏"
            entries = state.visible_games
            count_total = len(entries) + 1
        else:
            section_title = GAME_CATEGORIES[state.show_category].name
            entries = state.visible_games
            count_total = len(entries)
        self.text(state.notice or section_title,
                  self.small_font, CORAL if state.notice else LIGHT_MUTED, (11, self.section_y))
        count = "%02d / %02d" % (state.selected + 1, count_total)
        count_image = self.small_font.render(count, True, LIGHT_TEAL)
        self.screen.blit(count_image, (self.width - count_image.get_width() - 11, self.section_y))
        for index, (game, rect) in enumerate(zip(entries, self.game_rects)):
            selected = index == state.selected
            pygame.draw.rect(self.screen, SELECTED if selected else PAPER, rect, border_radius=6)
            pygame.draw.rect(self.screen, TEAL if selected else LINE, rect, 2 if selected else 1, border_radius=6)
            chip = min(28, rect.height - 4)
            icon = pygame.Rect(rect.x + 7, rect.centery - chip // 2, chip, chip)
            self.draw_icon(game, icon)
            text_x = icon.right + 5
            text_width = rect.right - text_x - 4
            font = next((font for font in self.name_fonts if font.size(game.name)[0] <= text_width
                         and font.get_height() + self.small_font.get_height() <= rect.height - 4),
                        self.name_fonts[-1])
            text_y = rect.centery - (font.get_height() + self.small_font.get_height()) // 2
            self.text(game.name, font, INK, (text_x, text_y))
            self.text(game.description, self.small_font, MUTED, (text_x, text_y + font.get_height()))
        if state.show_category is None:
            self.draw_gear(self.settings_rect, state.selected == state.settings_index)
        if state.confirming_power:
            self.draw_power_dialog(state)
        self.draw_footer(state.confirming_power)

    def draw_launching(self, state, game_name):
        self.draw(state)
        shade = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        shade.fill((15, 31, 37, 156))
        self.screen.blit(shade, (0, 0))
        width, height = min(self.width - 32, 220), 86
        panel = pygame.Rect((self.width - width) // 2, (self.footer_top - height) // 2,
                            width, height)
        pygame.draw.rect(self.screen, PAPER, panel, border_radius=7)
        pygame.draw.rect(self.screen, TEAL, panel, 2, border_radius=7)
        self.centered("正在进入", self.dialog_font, INK, (panel.centerx, panel.y + 27))
        self.centered(game_name, self.small_font, MUTED, (panel.centerx, panel.y + 60))

    def draw_gear(self, rect, selected):
        """主界面右上角的设置齿轮(齿盘+8齿+中心孔), 尺寸随 rect 自适应。"""
        if selected:
            pygame.draw.rect(self.screen, SELECTED, rect, border_radius=5)
            pygame.draw.rect(self.screen, TEAL, rect, 2, border_radius=5)
            color, backdrop = INK, SELECTED
        else:
            color, backdrop = LIGHT_MUTED, BACKGROUND
        center = rect.center
        scale = rect.width / 28.0
        body = round(9 * scale)
        hole = max(2, round(3 * scale))
        tooth = round(12 * scale)
        width = max(2, round(3 * scale))
        teeth = 8
        pygame.draw.circle(self.screen, color, center, body)      # 齿盘主体
        for index in range(teeth):                                # 均匀分布的齿
            angle = math.pi * 2 * index / teeth
            dx, dy = math.cos(angle), math.sin(angle)
            start = (round(center[0] + dx * (body - 2 * scale)), round(center[1] + dy * (body - 2 * scale)))
            end = (round(center[0] + dx * tooth), round(center[1] + dy * tooth))
            pygame.draw.line(self.screen, color, start, end, width)
        pygame.draw.circle(self.screen, backdrop, center, hole)   # 中心孔露出底色

    def setting_value(self, key):
        """设置项当前显示值。"""
        if key == "style":
            return ui_theme.style_name()
        if key == "voice_enabled":
            return "开" if sound_settings.voice_enabled() else "关"
        return "%d%%" % sound_settings.settings()[key]

    def draw_settings_page(self, state):
        self.text("Wonder Box", self.brand_font, LIGHT, (10, 7))
        self.text("设置", self.chinese_font, LIGHT_TEAL, (11, 30 if self.portrait else 27))
        pygame.draw.line(self.screen, DARK_LINE, (10, self.section_y - 6), (self.width - 10, self.section_y - 6))

        top = self.section_y + 6
        bottom = self.footer_top - (24 if self.portrait else 22)
        count = len(SETTINGS_ITEMS)
        gap = 5
        row_height = (bottom - top - gap * (count - 1)) // count
        self.setting_rows = []
        for index, (key, label) in enumerate(SETTINGS_ITEMS):
            rect = pygame.Rect(12, top + index * (row_height + gap),
                               self.width - 24, row_height)
            self.setting_rows.append(rect)
            selected = index == state.settings_selection
            pygame.draw.rect(self.screen, SELECTED if selected else PAPER, rect, border_radius=6)
            pygame.draw.rect(self.screen, TEAL if selected else LINE,
                             rect, 2 if selected else 1, border_radius=6)
            text_y = rect.centery - self.small_font.get_height() // 2
            self.text(label, self.small_font, INK if selected else MUTED, (rect.x + 10, text_y))
            value = self.setting_value(key)
            image = self.small_font.render(value, True, TEAL if selected else MUTED)
            self.screen.blit(image, image.get_rect(midright=(rect.right - 10, rect.centery)))
            if selected:
                marker = ("K1 减 / K2 加 / K3 确认" if state.settings_editing
                          else "K3 调节 · 长按 K3 退出设置")
                hint_y = bottom + 2  # 固定在行区下方预留条，避免被其它卡片遮住
                if hint_y + self.small_font.get_height() <= self.footer_top:
                    self.centered(marker, self.small_font, LIGHT_MUTED,
                                  (self.width // 2, hint_y + self.small_font.get_height() // 2))

    def draw_declaration(self):
        self.centered("使用声明", self.dialog_font, LIGHT, (self.width // 2, self.section_y + 12))
        lines = DECLARATION_LINES[self.portrait]
        line_gap = 19 if self.portrait else 18
        first_y = self.section_y + (38 if self.portrait else 37)
        for index, line in enumerate(lines):
            color = CORAL if index == len(lines) - 1 else LIGHT
            self.centered(line, self.declaration_font, color,
                          (self.width // 2, first_y + index * line_gap))
        pygame.draw.rect(self.screen, TEAL, self.declaration_button, border_radius=5)
        self.centered("知道了", self.button_font, PAPER, self.declaration_button.center)

    def draw_power_dialog(self, state):
        shade = pygame.Surface((self.width, self.footer_top), pygame.SRCALPHA)
        shade.fill((24, 48, 47, 175))
        self.screen.blit(shade, (0, 0))
        pygame.draw.rect(self.screen, PAPER, self.dialog, border_radius=7)
        pygame.draw.rect(self.screen, LINE, self.dialog, 1, border_radius=7)
        self.centered("确定关机？", self.dialog_font, INK, (self.dialog.centerx, self.dialog.y + 32))
        self.centered("将关闭奇趣宝盒", self.small_font, MUTED, (self.dialog.centerx, self.dialog.y + 60))
        for index, (label, rect) in enumerate(zip(("取消", "关机"), self.power_buttons)):
            selected = index == state.power_selected
            color = SELECTED if selected else PAPER
            pygame.draw.rect(self.screen, color, rect, border_radius=5)
            pygame.draw.rect(self.screen, CORAL if selected and index == 1 else TEAL if selected else LINE,
                             rect, 2 if selected else 1, border_radius=5)
            self.centered(label, self.button_font, CORAL if index == 1 else INK, rect.center)


def launch_game(game, simulate, portrait):
    environment = os.environ.copy()
    environment["POKEMON_SIMULATE"] = "1" if simulate else "0"
    environment["POKEMON_PORTRAIT"] = "1" if portrait else "0"
    command = [sys.executable, os.path.join(ROOT_DIR, game.path),
               "--sim" if simulate else "--spi",
               "--portrait" if portrait else "--landscape"]
    return subprocess.run(command, cwd=ROOT_DIR, env=environment, check=False).returncode


def blank_screen(screen):
    """关机前把 SPI 屏彻底刷成全黑（三重保险）。

    1. pygame 画布 fill 黑色并 present 刷一帧;
    2. 绕过 pygame 直接把 /dev/fb1 清零(即使上面一步失败也生效);
    3. fbtft 注册了 backlight 时写 fb blank, 直接熄灭背光。
    """
    try:
        screen.fill((0, 0, 0))
        spi_lcd.present(poll_events=False)
    except (RuntimeError, pygame.error):
        pass
    time.sleep(0.2)  # 等 SPI 传输真正落到面板上再发关机命令
    try:
        with open(spi_lcd.FB_DEV, "wb") as f:
            f.write(bytes(spi_lcd.FB_WIDTH * spi_lcd.FB_HEIGHT * 2))
    except OSError:
        pass
    for path in glob.glob("/sys/class/graphics/fb*/blank"):
        try:
            with open(path, "w") as f:
                f.write("4")  # FB_BLANK_POWERDOWN: 熄屏并关背光
        except OSError:
            pass


def request_shutdown(screen, simulate):
    if simulate:
        return False, "模拟模式不会关机"
    try:
        blank_screen(screen)  # 先把屏幕刷成全黑, 再发关机命令
        command = ["shutdown", "-h", "now"]
        if not (hasattr(os, "geteuid") and os.geteuid() == 0):
            command = ["sudo", "-n"] + command
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, RuntimeError, subprocess.SubprocessError, pygame.error) as error:
        print("关机失败:", error)
        return False, "关机失败"
    if result.returncode != 0:
        print("关机失败:", result.stderr.strip())
        return False, "关机失败"
    return True, ""


def event_action(event, display, state):
    if event.type == pygame.QUIT:
        return "EXIT"
    if event.type == pygame.KEYDOWN:
        if event.key in (pygame.K_ESCAPE, pygame.K_q, pygame.K_BACKSPACE):
            return "POWER_CANCEL" if state.confirming_power else "EXIT"
        return {pygame.K_1: "K1", pygame.K_KP1: "K1", pygame.K_UP: "K1", pygame.K_LEFT: "K1",
                pygame.K_2: "K2", pygame.K_KP2: "K2", pygame.K_DOWN: "K2", pygame.K_RIGHT: "K2",
                pygame.K_3: "K3", pygame.K_KP3: "K3", pygame.K_RETURN: "K3", pygame.K_KP_ENTER: "K3"}.get(event.key)
    if event.type == pygame.MOUSEBUTTONDOWN:
        position = spi_lcd.mouse_position(event)
        if position is None:
            return None
        if state.show_declaration:
            if display.declaration_button.collidepoint(position) or display.buttons[2].collidepoint(position):
                return "K3"
            return None
        if state.show_settings:
            for index, rect in enumerate(getattr(display, "setting_rows", [])):
                if rect.collidepoint(position):
                    return "SELECT_%d" % index
            for action, rect in zip(("K1", "K2", "K3"), display.buttons):
                if rect.collidepoint(position):
                    return action
            return None
        for action, rect in zip(("K1", "K2", "K3"), display.buttons):
            if rect.collidepoint(position):
                return action
        if state.confirming_power:
            for action, rect in zip(("POWER_CANCEL", "POWER_CONFIRM"), display.power_buttons):
                if rect.collidepoint(position):
                    return action
        else:
            for index, rect in enumerate(display.game_rects[:len(state.visible_games)]):
                if rect.collidepoint(position):
                    return "GAME_%d" % index
            if state.show_category is None and display.settings_rect.collidepoint(position):
                return "GAME_%d" % state.settings_index
    return None


class LauncherApp:
    def __init__(self):
        self.state = LauncherState(show_declaration=True)
        self.screen = None
        self.display = None
        self.buttons = None
        self.hold = None
        self.clock = None
        self.sound = None  # 主界面按键音；open() 里创建（需 mixer 已就绪）
        self.simulate = True
        self.release_gate = False
        self.running = True

    def open(self, after_game=False):
        self.screen = spi_lcd.init()
        self.simulate = spi_lcd.is_simulate()
        apply_theme()
        self.display = LauncherDisplay(self.screen)
        self.hold = spi_lcd.SimulatedHold("K3", "POWER", QUIT_HOLD_SECONDS)
        self.clock = pygame.time.Clock()
        self.sound = sfx_helper.SFX(sfx_helper.game_media(__file__))
        self.release_gate = False
        if self.simulate:
            pygame.display.set_caption("Wonder Box 奇趣宝盒")
            if after_game:
                self.hold.block_held(pygame, K3_KEYS)
        else:
            try:
                gpio = importlib.import_module("RPi.GPIO")
                self.buttons = GPIOButtons(gpio)
                self.release_gate = after_game
            except Exception as error:
                raise RuntimeError("GPIO 初始化失败，请检查 RPi.GPIO 和按键连接。") from error

    def close(self):
        try:
            if self.sound is not None:
                self.sound.close()
        finally:
            try:
                if self.buttons is not None:
                    self.buttons.cleanup()
                    self.buttons = None
            finally:
                pygame.quit()

    def poll_actions(self):
        if self.buttons is not None:
            actions = self.buttons.poll()
            if self.release_gate:
                actions = [action for action in actions if action not in ("K3", "QUIT")]
                if self.buttons.is_released("K3"):
                    self.release_gate = False
            actions = ["POWER" if action == "QUIT" else action for action in actions]
            if self.state.show_category is not None:
                actions = ["BACK" if action == "POWER" else action for action in actions]
            return actions
        actions = []
        for event in pygame.event.get():
            action = self.hold.process_event(event, event_action(event, self.display, self.state))
            if action:
                actions.append(action)
        action = self.hold.poll()
        if action:
            actions.append(action)
        if self.state.show_category is not None:
            actions = ["BACK" if action == "POWER" else action for action in actions]
        return actions

    def play(self):
        game = self.state.selected_game
        if game is None:
            return
        simulate, portrait = self.simulate, self.display.portrait
        if game.name == "诗词大赛":
            self.display.draw_launching(self.state, game.name)
            spi_lcd.present(poll_events=False)
        self.close()
        notice = ""
        try:
            if launch_game(game, simulate, portrait) != 0:
                notice = "游戏异常退出"
        except (OSError, subprocess.SubprocessError) as error:
            print("游戏启动失败:", error)
            notice = "游戏启动失败"
        finally:
            self.open(after_game=True)
        self.state.notice = notice

    def accept_declaration(self):
        self.state.show_declaration = False

    def cycle_style(self, direction):
        names = ui_theme.STYLE_NAMES
        index = (names.index(ui_theme.style_name()) + direction) % len(names)
        ui_theme.set_style(names[index])  # 立即持久化
        apply_theme()

    def step_setting(self, direction):
        """调节当前选中的设置项；风格/开关切换，音量按步长增减。"""
        key = SETTINGS_ITEMS[self.state.settings_selection][0]
        if key == "style":
            self.cycle_style(direction)
        elif key == "voice_enabled":
            sound_settings.toggle_voice()
        else:
            sound_settings.step(key, direction)

    def run(self):
        while self.running:
            self.display.draw(self.state)
            if not spi_lcd.present(poll_events=False):
                break
            for action in self.poll_actions():
                if self.sound is not None and sfx_helper.is_press(action):
                    self.sound.button()  # 主界面每次短按都有按键音
                if action == "EXIT":
                    self.running = False
                    break
                result = self.state.handle_action(action)
                if result == "EXIT":
                    self.running = False
                    break
                if result == "ACCEPT_DECLARATION":
                    self.accept_declaration()
                    break
                if result == "SETTINGS":
                    self.state.show_settings = True
                    self.state.settings_editing = False
                    break
                if result == "CLOSE_SETTINGS":
                    self.state.show_settings = False
                    self.state.settings_editing = False
                    break
                if result in ("OPEN_CATEGORY", "CLOSE_CATEGORY"):
                    break
                if result == "SETTING_STEP_DOWN":
                    self.step_setting(-1)
                    break
                if result == "SETTING_STEP_UP":
                    self.step_setting(1)
                    break
                if result == "LAUNCH":
                    self.play()
                    break
                if result == "SHUTDOWN":
                    shutdown, notice = request_shutdown(self.screen, self.simulate)
                    self.state.confirming_power = False
                    self.state.notice = notice
                    if shutdown:
                        self.running = False
                    break
            if self.running:
                self.clock.tick(30)


def main():
    if "--landscape" in sys.argv:
        os.environ["POKEMON_PORTRAIT"] = "0"
    elif "--portrait" in sys.argv:
        os.environ["POKEMON_PORTRAIT"] = "1"
    else:
        os.environ.setdefault("POKEMON_PORTRAIT", "1")
    audio_output.prepare()  # 主界面要出按键音，必须在 spi_lcd.init() 前声明
    app = LauncherApp()
    print("Wonder Box 奇趣宝盒: K1/K2 选择，K3 进入；长按 K3 打开关机确认。")
    try:
        app.open()
        app.run()
    finally:
        app.close()


if __name__ == "__main__":
    main()