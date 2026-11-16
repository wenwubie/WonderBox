"""适合小朋友一起玩的幸运转盘。"""

import importlib
import math
import os
import random
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(BASE_DIR))
from common import spi_lcd
from common import ui_theme

import pygame


GAMES = (
	("节奏", (255, 190, 87), (
		"一人拍两下节奏，大家一起学一学。",
		"轮流拍出节奏，其他人跟着拍。",
		"大家先轻拍两下，再一起拍三下。",
		"每人加一个拍手动作，连起来试一试。",
		"拍一下、停一下，再拍两下。",
		"用手指轻点四下，大家一起跟着点。",
		"轮流轻拍膝盖，接成一段节奏。",
		"用手指点出三下长短不同的节奏。",
		"一人数到三，大家一起拍一下手。",
		"拍两下手，再轻轻点一下脚尖。",
		"轮流说一个词，把它拍成节奏。",
		"一人拍慢一点，大家跟着慢慢拍。",
		"拍一下手，再左右各挥一次手。",
		"大家轻拍三下，最后安静一秒。",
		"一人拍两下，下一人接着拍三下。",
		"用手指轻点手心，模仿下雨的声音。",
	)),
	("动作", (248, 132, 119), (
		"一人做个小动作，大家像照镜子一样跟着做。",
		"轮流摆个有趣的姿势，大家一起模仿。",
		"用手画一个大圆，再画一个小圆。",
		"跟着领头的人慢慢伸展，换人再试。",
		"用手臂做翅膀，原地轻轻飞一飞。",
		"用手指画一颗星，再画一颗心。",
		"做一个开心表情，让大家猜一猜。",
		"慢慢抬起双手，像花儿一样打开。",
		"用双手做个望远镜，看看四周。",
		"伸出一只手，假装接住一片雪花。",
		"用动作表示刷牙，大家猜猜是什么。",
		"假装抱起一个大西瓜，再轻轻放下。",
		"和伙伴一起做一个相同的手势。",
		"用手指比一只小鸟，轻轻飞一飞。",
		"学一学小树随风摇摆的样子。",
		"双肩轻轻画个圈，再换个方向。",
	)),
	("故事", (181, 152, 218), (
		"每人接一句话，一起编一个开心的故事。",
		"想一个神奇的地方，轮流说说那里有什么。",
		"轮流说一个词，把它们编成有趣的一句话。",
		"选一个小主角，大家接力讲一次冒险。",
		"故事从一个会说话的盒子开始。",
		"想一想，小主角今天发现了什么？",
		"给故事加一位新朋友，说说它是谁。",
		"轮流说一句，编一场雨后的旅行。",
		"想一个小难题，大家一起编解决办法。",
		"说一个声音，把它加进故事里。",
		"给故事选一个季节，再说说天气。",
		"编一个温暖的结尾，送给故事主角。",
		"想象一封神秘来信，猜猜里面写了什么。",
		"选一样日用品，让它成为故事主角。",
		"轮流说一个地点，编成一条旅行路线。",
		"大家给故事取一个有趣的名字。",
	)),
	("寻找", (103, 189, 199), (
		"用眼睛找一找，有什么红色的东西？",
		"找一个圆圆的东西，告诉大家它在哪里。",
		"看一看，找出一样让你觉得漂亮的东西。",
		"找一个喜欢的颜色，大家说说看到了什么。",
		"找一找，有什么蓝色的东西？",
		"看看周围，有什么是方方的？",
		"找一个柔软的东西，告诉大家是什么。",
		"找一找，有什么东西上面有数字？",
		"看一看，哪里有一条长长的线？",
		"找一个小小的东西，用手指给大家看。",
		"找出两样颜色一样的东西。",
		"找一个有图案的东西，说说图案是什么。",
		"看看周围，有什么东西可以打开？",
		"找一个你觉得像星星的形状。",
		"说一种颜色，大家一起用眼睛找一找。",
		"找一找，有什么东西比手掌还小？",
	)),
	("想象", (141, 197, 138), (
		"想象一辆神奇的车，轮流说说它有什么本领。",
		"假装在画画，大家猜猜画的是什么。",
		"想象一顶魔法帽，轮流说说它能做什么。",
		"大家一起想一个新游戏，给它起个名字。",
		"想象一双会飞的鞋，你想去哪里？",
		"如果能和云朵聊天，你会说什么？",
		"设计一种新水果，说说它的味道。",
		"想象一座糖果城，里面有什么？",
		"给自己发明一个有趣的小超能力。",
		"想象一把神奇雨伞，它能做什么？",
		"如果小树会说话，它会说什么？",
		"设计一艘小船，说说它要去哪里。",
		"想象一个彩色星球，说说它的样子。",
		"给一朵花起名字，想想它会唱什么。",
		"假装收到一份神秘礼物，猜猜是什么。",
		"想一个会动的房子，说说它去哪儿。",
	)),
	("友爱", (246, 155, 181), (
		"和身边的人挥挥手，一起说声你好。",
		"轮流说一句让人开心的话，也可以笑一笑。",
		"告诉大家一件今天开心的小事。",
		"一起用手比一个心，送给在场的伙伴。",
		"对伙伴说一句谢谢，也可以点点头。",
		"轮流说说，喜欢和大家一起玩什么。",
		"说一个欣赏伙伴的地方。",
		"一起给今天的游戏起个队名。",
		"做一个友好的手势，大家一起学。",
		"轮流说一件愿意和伙伴分享的事。",
		"一起为自己和伙伴鼓鼓掌。",
		"问问伙伴喜欢什么颜色，听听回答。",
		"说一句鼓励的话，送给在场的伙伴。",
		"一起商量下次想玩的小游戏。",
		"对大家微笑，或者轻轻挥挥手。",
		"说说今天最喜欢的游戏环节。",
	)),
)

SECTOR_ANGLE = 360.0 / len(GAMES)


class LuckyWheel:
	def __init__(self, rng=None):
		self.rng = rng if rng is not None else random.Random()
		self.angle = self.rng.uniform(0.0, 360.0)
		self.phase = "ready"
		self.speed = 0.0
		self.stop_angle = 0.0
		self.stop_speed = 0.0
		self.stop_elapsed = 0.0
		self.stop_duration = 0.0
		self.selected = None
		self.task = None

	def handle_action(self, action):
		if action == "K3" and self.phase in ("ready", "result"):
			self.speed = self.rng.uniform(240.0, 300.0)
			self.phase = "spinning"
			self.selected = None
			self.task = None
		elif action == "K3" and self.phase == "spinning":
			self.phase = "slowing"
			self.stop_angle = self.angle
			self.stop_speed = self.speed
			self.stop_elapsed = 0.0
			self.stop_duration = self.rng.uniform(2.8, 4.0)
		elif action == "K1" and self.phase == "result":
			task_count = len(GAMES[self.selected][2])
			next_task = self.rng.randrange(task_count - 1)
			self.task = next_task + (next_task >= self.task)

	def update(self, elapsed):
		elapsed = max(0.0, elapsed)
		if self.phase == "spinning":
			self.angle = (self.angle + self.speed * elapsed) % 360.0
		elif self.phase == "slowing":
			self.stop_elapsed = min(self.stop_elapsed + elapsed, self.stop_duration)
			progress = self.stop_elapsed / self.stop_duration
			distance = self.stop_speed * self.stop_duration * (1.0 - (1.0 - progress) ** 3) / 3.0
			self.angle = (self.stop_angle + distance) % 360.0
			self.speed = self.stop_speed * (1.0 - progress) ** 2
			if progress >= 1.0:
				self.phase = "result"
				self.selected = int((-self.angle % 360.0) // SECTOR_ANGLE)
				self.task = self.rng.randrange(len(GAMES[self.selected][2]))


BACKGROUND = None  # 占位, 下方按全局风格填充
INK = None
MUTED = None
PAPER = None
OUTLINE = None
CORAL = (226, 100, 88)   # 固定暖色(警示/返回), 不随风格变
TEAL = None
YELLOW = (255, 205, 99)  # 固定金色(转盘高亮)


def apply_theme():
    """按全局界面风格刷新配色(common/ui_theme.py)。"""
    global BACKGROUND, INK, MUTED, PAPER, OUTLINE, TEAL
    st = ui_theme.style()
    BACKGROUND = st["bg"]
    INK = st["text"]
    MUTED = st["sub"]
    PAPER = st["panel"]
    OUTLINE = st["deco"]
    TEAL = st["accent"]


apply_theme()


def point_on_wheel(center, radius, angle):
	radians = math.radians(angle)
	return (round(center[0] + math.sin(radians) * radius),
			round(center[1] - math.cos(radians) * radius))


def wrap_text(text, font, max_width):
	lines = []
	line = ""
	for character in text:
		if character == "\n":
			lines.append(line)
			line = ""
		elif line and font.size(line + character)[0] > max_width:
			if character in "，。！？；：、" and len(line) > 1:
				lines.append(line[:-1])
				line = line[-1] + character
			else:
				lines.append(line)
				line = character
		else:
			line += character
	if line:
		lines.append(line)
	return lines


class WheelDisplay:
	def __init__(self, screen):
		self.screen = screen
		self.width, self.height = screen.get_size()
		self.portrait = self.height > self.width
		self.title_font = spi_lcd.load_font(21)
		self.heading_font = spi_lcd.load_font(16)
		self.body_font = spi_lcd.load_font(13 if self.portrait else 14)
		self.wheel_font = spi_lcd.load_font(14)
		self.button_font = spi_lcd.load_font(12)
		self.small_font = spi_lcd.load_font(11)
		if self.portrait:
			self.center = (self.width // 2, 128)
			self.radius = 76
			self.info_rect = pygame.Rect(12, 214, self.width - 24, 68)
		else:
			self.center = (85, 124)
			self.radius = 72
			self.info_rect = pygame.Rect(171, 52, self.width - 183, 146)
		margin, gap, button_height = 7, 5, 22
		button_width = (self.width - margin * 2 - gap * 2) // 3
		self.buttons = [pygame.Rect(margin + index * (button_width + gap),
									self.height - button_height - 5, button_width, button_height)
						for index in range(3)]

	def text(self, value, font, color, position):
		image = font.render(value, True, color)
		self.screen.blit(image, position)
		return image.get_rect(topleft=position)

	def draw_header(self):
		self.text("幸运转盘", self.title_font, INK, (12, 7))
		tag = pygame.Rect(self.width - 62, 9, 50, 20)
		tag_fill = (255, 231, 173)
		pygame.draw.rect(self.screen, tag_fill, tag, border_radius=6)
		image = self.small_font.render("一起玩", True, ui_theme.pick(tag_fill, INK))
		self.screen.blit(image, image.get_rect(center=tag.center))
		pygame.draw.line(self.screen, OUTLINE, (12, 36), (self.width - 12, 36))

	def draw_symbol(self, label, position, color=None):
		x, y = position
		color = INK if color is None else color
		if label == "节奏":
			pygame.draw.circle(self.screen, INK, (x - 4, y + 3), 2)
			pygame.draw.circle(self.screen, INK, (x + 3, y + 1), 2)
			pygame.draw.line(self.screen, INK, (x - 2, y + 3), (x - 2, y - 5), 2)
			pygame.draw.line(self.screen, INK, (x + 5, y + 1), (x + 5, y - 6), 2)
			pygame.draw.line(self.screen, INK, (x - 2, y - 5), (x + 5, y - 6), 2)
		elif label == "动作":
			pygame.draw.circle(self.screen, INK, (x, y - 5), 2)
			pygame.draw.line(self.screen, INK, (x, y - 2), (x, y + 3), 2)
			pygame.draw.line(self.screen, INK, (x - 5, y - 1), (x + 5, y - 1), 2)
			pygame.draw.lines(self.screen, INK, False, [(x - 4, y + 7), (x, y + 3),
													   (x + 4, y + 7)], 2)
		elif label == "故事":
			pygame.draw.lines(self.screen, INK, False, [(x, y + 5), (x - 6, y + 2),
														(x - 6, y - 5), (x, y - 3),
														(x + 6, y - 5), (x + 6, y + 2),
														(x, y + 5)], 1)
			pygame.draw.line(self.screen, INK, (x, y - 3), (x, y + 5))
		elif label == "寻找":
			pygame.draw.circle(self.screen, INK, (x - 1, y - 2), 4, 2)
			pygame.draw.line(self.screen, INK, (x + 2, y + 1), (x + 6, y + 5), 2)
		elif label == "想象":
			pygame.draw.circle(self.screen, INK, (x, y - 3), 4, 2)
			pygame.draw.line(self.screen, INK, (x - 2, y + 2), (x + 2, y + 2), 2)
			pygame.draw.line(self.screen, INK, (x - 1, y + 5), (x + 1, y + 5), 2)
		else:
			pygame.draw.circle(self.screen, INK, (x - 3, y - 2), 3)
			pygame.draw.circle(self.screen, INK, (x + 3, y - 2), 3)
			pygame.draw.polygon(self.screen, INK, [(x - 6, y), (x + 6, y), (x, y + 6)])

	def draw_wheel(self, wheel):
		center = self.center
		radius = self.radius
		pygame.draw.circle(self.screen, (201, 218, 207), (center[0], center[1] + 3), radius + 4)
		pygame.draw.circle(self.screen, PAPER, center, radius + 4)
		for index, (label, color, _) in enumerate(GAMES):
			start = wheel.angle + index * SECTOR_ANGLE
			points = [center] + [point_on_wheel(center, radius, start + SECTOR_ANGLE * step / 20)
								 for step in range(21)]
			pygame.draw.polygon(self.screen, color, points)
		for index, (label, color, _) in enumerate(GAMES):
			start = wheel.angle + index * SECTOR_ANGLE
			pygame.draw.line(self.screen, PAPER, center, point_on_wheel(center, radius, start), 2)
			position = point_on_wheel(center, radius * 0.65, start + SECTOR_ANGLE / 2)
			# 扇区底色固定, 文字/符号颜色按扇区亮度自适应
			label_color = ui_theme.pick(color, INK)
			self.draw_symbol(label, (position[0], position[1] - 8), label_color)
			image = self.wheel_font.render(label, True, label_color)
			self.screen.blit(image, image.get_rect(center=(position[0], position[1] + 7)))
		pygame.draw.circle(self.screen, PAPER, center, 16)
		pygame.draw.circle(self.screen, (225, 175, 74), center, 16, 1)
		star = [point_on_wheel(center, 10 if index % 2 == 0 else 4,
							   wheel.angle + index * 36) for index in range(10)]
		pygame.draw.polygon(self.screen, YELLOW, star)
		top = center[1] - radius
		pointer = [(center[0] - 8, top - 11), (center[0] + 8, top - 11),
				   (center[0], top + 8)]
		pygame.draw.polygon(self.screen, PAPER, pointer, 4)
		pygame.draw.polygon(self.screen, CORAL, pointer)

	def draw_info(self, wheel):
		rect = self.info_rect
		pygame.draw.rect(self.screen, PAPER, rect, border_radius=7)
		pygame.draw.rect(self.screen, OUTLINE, rect, 1, border_radius=7)
		if wheel.phase == "result":
			label, color, tasks = GAMES[wheel.selected]
			heading = label + "游戏"
			body = tasks[wheel.task]
		elif wheel.phase == "spinning":
			color, heading, body = TEAL, "好运转起来", "大家一起期待吧！"
		elif wheel.phase == "slowing":
			color, heading, body = CORAL, "马上揭晓", "大家一起期待吧！"
		else:
			color, heading, body = TEAL, "今天玩什么？", "和小伙伴一起玩！"
		pygame.draw.rect(self.screen, color, (rect.x + 10, rect.y + 11, 4, 15), border_radius=2)
		self.text(heading, self.heading_font, INK, (rect.x + 20, rect.y + 8))
		text_y = rect.y + 30
		for line in wrap_text(body, self.body_font, rect.width - 24):
			self.text(line, self.body_font, INK, (rect.x + 12, text_y))
			text_y += self.body_font.get_linesize() + 1

	def draw_buttons(self, wheel):
		if wheel.phase == "result":
			labels, enabled = ("换题", "无功能", "再转"), (True, False, True)
		elif wheel.phase == "ready":
			labels, enabled = ("换题", "无功能", "开始"), (False, False, True)
		elif wheel.phase == "spinning":
			labels, enabled = ("换题", "无功能", "停下"), (False, False, True)
		else:
			labels, enabled = ("换题", "无功能", "停下"), (False, False, False)
		colors = ((248, 169, 138), (124, 202, 190), (255, 211, 117))
		for index, rect in enumerate(self.buttons):
			color = colors[index] if enabled[index] else (229, 235, 230)
			text_color = ui_theme.pick(color, INK) if enabled[index] else (83, 92, 89)
			pygame.draw.rect(self.screen, color, rect, border_radius=5)
			image = self.button_font.render(labels[index], True, text_color)
			self.screen.blit(image, image.get_rect(center=rect.center))

	def draw(self, wheel):
		self.screen.fill(BACKGROUND)
		self.draw_header()
		self.draw_wheel(wheel)
		self.draw_info(wheel)
		self.draw_buttons(wheel)


BUTTON_PINS = {"K1": 18, "K2": 23, "K3": 24}
DEBOUNCE_SECONDS = 0.035
QUIT_HOLD_SECONDS = 1.0


class GPIOButtons:
	def __init__(self, gpio, clock=time.monotonic):
		self.gpio = gpio
		self.clock = clock
		try:
			gpio.setmode(gpio.BCM)
			for pin in BUTTON_PINS.values():
				gpio.setup(pin, gpio.IN, pull_up_down=gpio.PUD_UP)
		except Exception:
			gpio.cleanup()
			raise
		self.states = {name: {"raw": False, "down": False, "changed": clock(),
							  "since": 0.0, "long": False} for name in BUTTON_PINS}

	def poll(self):
		now = self.clock()
		actions = []
		for name, pin in BUTTON_PINS.items():
			state = self.states[name]
			pressed = self.gpio.input(pin) == self.gpio.LOW
			if pressed != state["raw"]:
				state["raw"] = pressed
				state["changed"] = now
			if pressed != state["down"] and now - state["changed"] >= DEBOUNCE_SECONDS:
				state["down"] = pressed
				if pressed:
					state["since"] = now
					state["long"] = False
					if name != "K3":
						actions.append(name)
				elif name == "K3" and not state["long"]:
					actions.append("K3")
			if (name == "K3" and pressed and state["down"] and not state["long"]
					and now - state["since"] >= QUIT_HOLD_SECONDS):
				state["long"] = True
				actions.append("QUIT")
		return actions

	def cleanup(self):
		self.gpio.cleanup(list(BUTTON_PINS.values()))


def event_action(event, display):
	if event.type == pygame.QUIT:
		return "QUIT"
	if event.type == pygame.KEYDOWN:
		if event.key in (pygame.K_ESCAPE, pygame.K_q, pygame.K_BACKSPACE):
			return "QUIT"
		return {pygame.K_1: "K1", pygame.K_2: "K2", pygame.K_3: "K3",
				pygame.K_KP1: "K1", pygame.K_KP2: "K2", pygame.K_KP3: "K3"}.get(event.key)
	if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
		window = pygame.display.get_surface()
		if window is not None:
			position = (event.pos[0] * display.width / window.get_width(),
						event.pos[1] * display.height / window.get_height())
			for name, rect in zip(("K1", "K2", "K3"), display.buttons):
				if rect.collidepoint(position):
					return name
	return None


def present_frame(screen):
	if spi_lcd.is_simulate():
		window = pygame.display.get_surface()
		pygame.transform.scale(screen, window.get_size(), window)
		pygame.display.flip()
	else:
		spi_lcd.present()


def main():
	if spi_lcd.is_simulate():
		spi_lcd.WINDOW_SCALE = 2
		if "--landscape" in sys.argv:
			os.environ["POKEMON_PORTRAIT"] = "0"
		elif "--portrait" in sys.argv:
			os.environ["POKEMON_PORTRAIT"] = "1"
		else:
			os.environ.setdefault("POKEMON_PORTRAIT", "1")
	screen = spi_lcd.init()
	buttons = None
	try:
		if not spi_lcd.is_simulate():
			try:
				gpio = importlib.import_module("RPi.GPIO")
				buttons = GPIOButtons(gpio)
			except Exception as error:
				raise RuntimeError("GPIO 初始化失败，请检查 RPi.GPIO 和按键连接。") from error
		else:
			pygame.display.set_caption("幸运转盘")
		display = WheelDisplay(screen)
		wheel = LuckyWheel()
		hold = spi_lcd.SimulatedHold("K3", "QUIT", QUIT_HOLD_SECONDS)
		clock = pygame.time.Clock()
		running = True
		exit_hint = "按 Esc 退出" if buttons is None else "长按 K3 退出"
		print("幸运转盘已启动：K3 开始和停下，K1 换题；%s。" % exit_hint)
		while running:
			elapsed = clock.tick(30) / 1000.0
			if buttons is None:
				actions = [hold.process_event(event, event_action(event, display))
						   for event in pygame.event.get()]
				actions.append(hold.poll())
			else:
				actions = buttons.poll()
			for action in actions:
				if action == "QUIT":
					running = False
					break
				wheel.handle_action(action)
			if not running:
				break
			wheel.update(elapsed)
			display.draw(wheel)
			present_frame(screen)
	finally:
		if buttons is not None:
			buttons.cleanup()
		pygame.quit()


if __name__ == "__main__":
	main()
