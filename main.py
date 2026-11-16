"""Wonder Box 奇趣宝盒的游戏入口。"""

from dataclasses import dataclass
import glob
import importlib
import os
import subprocess
import sys
import time

from common import spi_lcd

import pygame


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT_DIR, "Lucky Wheel"))
from lucky_wheel import BUTTON_PINS, GPIOButtons, QUIT_HOLD_SECONDS


@dataclass(frozen=True)
class Game:
    name: str
    description: str
    path: str
    icon: str
    color: tuple[int, int, int]


GAMES = (
    Game("宝可梦图鉴", "图鉴探索", "Pokemon/pokemon.py", "pokemon", (224, 95, 78)),
    Game("头脑挑战", "双人答题", "Brain Challenge/brain_challenge.py", "brain", (66, 153, 139)),
    Game("脑筋急转弯", "趣味问答", "Riddles/Riddles.py", "riddle", (225, 165, 55)),
    Game("骰子对决", "双人对战", "Quick Duel/quick_duel.py", "dice", (89, 143, 206)),
    Game("幸运转盘", "一起玩耍", "Lucky Wheel/lucky_wheel.py", "wheel", (230, 129, 95)),
    Game("星愿占卜屋", "星座占卜", "Magic/Magic.py", "magic", (172, 125, 176)),
    Game("诗词大赛", "唐诗宋词", "Poetry Quest/poetry.py", "poetry", (186, 91, 73)),
    Game("宠物乐园", "萌宠养成", "Virtual Pet/virtual_pet.py", "pet", (87, 158, 120)),
)


class LauncherState:
    def __init__(self, show_declaration=False):
        self.selected = 0
        self.confirming_power = False
        self.power_selected = 0
        self.notice = ""
        self.show_declaration = show_declaration

    def handle_action(self, action):
        if self.show_declaration:
            return "ACCEPT_DECLARATION" if action == "K3" else None
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
            self.selected = (self.selected + (-1 if action == "K1" else 1)) % len(GAMES)
            self.notice = ""
        elif action == "K3":
            return "LAUNCH"
        elif action and action.startswith("GAME_"):
            index = int(action[5:])
            if 0 <= index < len(GAMES):
                self.selected = index
                return "LAUNCH"
        return None


BACKGROUND = (46, 64, 60)      # 深灰绿底, 与象牙色卡片拉开层次
PAPER = (246, 244, 236)        # 象牙色卡片
INK = (52, 70, 68)
MUTED = (108, 130, 124)
TEAL = (74, 145, 135)
LINE = (188, 205, 196)
CORAL = (204, 103, 90)
LIGHT = (228, 235, 229)        # 深底上的正文浅色
LIGHT_TEAL = (138, 194, 182)   # 深底上的强调浅色
LIGHT_MUTED = (160, 180, 173)  # 深底上的次要文字
DARK_LINE = (92, 114, 106)     # 深底上的分隔线
FOOTER_BG = (56, 76, 69)       # 底部按键栏(深色)
DECLARATION_LINES = ("此宝盒仅允许我或我的朋友", "文怡然、文焕然、", "欧泽轩、欧阳沐希使用，", "否则将大祸临头")


class LauncherDisplay:
    def __init__(self, screen):
        self.screen = screen
        self.width, self.height = screen.get_size()
        self.portrait = self.height > self.width
        self.brand_font = spi_lcd.load_font(19 if self.portrait else 17)
        self.brand_font.set_bold(True)
        self.chinese_font = spi_lcd.load_font(14 if self.portrait else 13)
        self.name_fonts = [spi_lcd.load_font(size) for size in (14, 13, 12, 11)]
        self.small_font = spi_lcd.load_font(11)
        self.button_font = spi_lcd.load_font(13)
        self.dialog_font = spi_lcd.load_font(19)
        self.declaration_font = spi_lcd.load_font(16 if self.portrait else 15)
        self.icon_font = spi_lcd.load_font(19)
        self.section_y = 62 if self.portrait else 49
        self.footer_top = self.height - 27
        top, gap, margin = self.section_y + 20, 6, 10
        width = (self.width - 2 * margin - gap) // 2
        rows = (len(GAMES) + 1) // 2
        height = (self.footer_top - top - 4 - (rows - 1) * gap) // rows
        self.game_rects = [pygame.Rect(margin + (index % 2) * (width + gap),
                                      top + (index // 2) * (height + gap), width, height)
                           for index in range(len(GAMES))]
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

    def draw_footer(self, confirming, declaration=False):
        pygame.draw.rect(self.screen, FOOTER_BG, (0, self.footer_top, self.width, 27))
        labels = (("", "", "确认") if declaration else
                  ("切换", "切换", "确认") if confirming else ("上一项", "下一项", "进入"))
        for label, rect in zip(labels, self.buttons):
            if label:
                self.centered(label, self.button_font, LIGHT_TEAL, rect.center)

    def draw(self, state):
        self.screen.fill(BACKGROUND)
        for dot_y in range(10, self.footer_top, 24):
            for dot_x in range(12, self.width, 24):
                pygame.draw.circle(self.screen, (62, 82, 74), (dot_x, dot_y), 1)
        size = 38 if self.portrait else 32
        self.draw_logo(10, 7, size)
        self.text("Wonder Box", self.brand_font, LIGHT, (size + 17, 7))
        self.text("奇趣宝盒", self.chinese_font, LIGHT_TEAL, (size + 18, 30 if self.portrait else 27))
        pygame.draw.line(self.screen, DARK_LINE, (10, self.section_y - 6), (self.width - 10, self.section_y - 6))
        if state.show_declaration:
            self.draw_declaration()
            self.draw_footer(False, declaration=True)
            return
        self.text(state.notice or "全部游戏", self.small_font,
                  (230, 132, 116) if state.notice else LIGHT_MUTED,
                  (11, self.section_y))
        count = "%02d / %02d" % (state.selected + 1, len(GAMES))
        count_image = self.small_font.render(count, True, LIGHT_TEAL)
        self.screen.blit(count_image, (self.width - count_image.get_width() - 11, self.section_y))
        for index, (game, rect) in enumerate(zip(GAMES, self.game_rects)):
            selected = index == state.selected
            pygame.draw.rect(self.screen, (217, 235, 226) if selected else PAPER, rect, border_radius=6)
            pygame.draw.rect(self.screen, TEAL if selected else LINE, rect, 2 if selected else 1, border_radius=6)
            icon = pygame.Rect(rect.x + 7, rect.centery - 13, 26, 26)
            self.draw_icon(game, icon)
            text_x = icon.right + 5
            text_width = rect.right - text_x - 4
            font = next((font for font in self.name_fonts if font.size(game.name)[0] <= text_width
                         and font.get_height() + self.small_font.get_height() <= rect.height - 4),
                        self.name_fonts[-1])
            text_y = rect.centery - (font.get_height() + self.small_font.get_height()) // 2
            self.text(game.name, font, INK, (text_x, text_y))
            self.text(game.description, self.small_font, MUTED, (text_x, text_y + font.get_height()))
        if state.confirming_power:
            self.draw_power_dialog(state)
        self.draw_footer(state.confirming_power)

    def draw_declaration(self):
        self.centered("使用声明", self.dialog_font, LIGHT, (self.width // 2, self.section_y + 12))
        line_gap = 24 if self.portrait else 22
        for index, line in enumerate(DECLARATION_LINES):
            color = (230, 132, 116) if index == len(DECLARATION_LINES) - 1 else LIGHT
            self.centered(line, self.declaration_font, color,
                          (self.width // 2, self.section_y + 40 + index * line_gap))
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
            color = (234, 214, 208) if selected and index == 1 else \
                    (212, 228, 219) if selected else (240, 240, 234)
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
        for action, rect in zip(("K1", "K2", "K3"), display.buttons):
            if rect.collidepoint(position):
                return action
        if state.confirming_power:
            for action, rect in zip(("POWER_CANCEL", "POWER_CONFIRM"), display.power_buttons):
                if rect.collidepoint(position):
                    return action
        else:
            for index, rect in enumerate(display.game_rects):
                if rect.collidepoint(position):
                    return "GAME_%d" % index
    return None


class LauncherApp:
    def __init__(self):
        self.state = LauncherState(show_declaration=True)
        self.screen = None
        self.display = None
        self.buttons = None
        self.hold = None
        self.clock = None
        self.simulate = True
        self.release_gate = False
        self.running = True

    def open(self, after_game=False):
        self.screen = spi_lcd.init()
        self.simulate = spi_lcd.is_simulate()
        self.display = LauncherDisplay(self.screen)
        self.hold = spi_lcd.SimulatedHold("K3", "POWER", QUIT_HOLD_SECONDS)
        self.clock = pygame.time.Clock()
        self.release_gate = False
        if self.simulate:
            pygame.display.set_caption("Wonder Box 奇趣宝盒")
        else:
            try:
                gpio = importlib.import_module("RPi.GPIO")
                self.buttons = GPIOButtons(gpio)
                self.release_gate = after_game
            except Exception as error:
                raise RuntimeError("GPIO 初始化失败，请检查 RPi.GPIO 和按键连接。") from error

    def close(self):
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
                state = self.buttons.states["K3"]
                gpio = self.buttons.gpio
                if (not state["raw"] and not state["down"]
                        and gpio.input(BUTTON_PINS["K3"]) != gpio.LOW):
                    self.release_gate = False
            return ["POWER" if action == "QUIT" else action for action in actions]
        actions = []
        for event in pygame.event.get():
            action = self.hold.process_event(event, event_action(event, self.display, self.state))
            if action:
                actions.append(action)
        action = self.hold.poll()
        if action:
            actions.append(action)
        return actions

    def play(self):
        game = GAMES[self.state.selected]
        simulate, portrait = self.simulate, self.display.portrait
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

    def run(self):
        while self.running:
            self.display.draw(self.state)
            if not spi_lcd.present(poll_events=False):
                break
            for action in self.poll_actions():
                if action == "EXIT":
                    self.running = False
                    break
                result = self.state.handle_action(action)
                if result == "ACCEPT_DECLARATION":
                    self.accept_declaration()
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
    app = LauncherApp()
    print("Wonder Box 奇趣宝盒: K1/K2 选择，K3 进入；长按 K3 打开关机确认。")
    try:
        app.open()
        app.run()
    finally:
        app.close()


if __name__ == "__main__":
    main()