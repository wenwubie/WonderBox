"""适合小朋友一起玩的幸运转盘。"""

import importlib
import math
import os
import random
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(BASE_DIR))
from common import spi_lcd
from common.button_input import BUTTON_PINS, DEBOUNCE_SECONDS, GPIOButtons, QUIT_HOLD_SECONDS
from common import audio as audio_output
from common import sfx as sfx_helper
from common import tts
from common import ui_theme

import pygame


GAMES = (
	("节奏", (255, 190, 87), (
		"听领头人拍“慢、快、快”，大家复拍两轮。",
		"拍两下膝盖、一下手，连做两轮不跟丢。",
		"每人加一拍，接成六拍节奏，再全员复现。",
		"拍四拍“轻、轻、重、停”，一起做两轮。",
		"领头人示范三拍，大家按原顺序复拍。",
		"拍两下、停一拍；下一人接三拍新节奏。",
		"用拍手和拍腿做三拍，让伙伴说出顺序。",
		"先拍一慢两快，再把快慢顺序倒过来。",
		"节奏从慢到快做四拍，再从快到慢收住。",
		"依次接拍，每人记住前面节奏并加一拍。",
		"一人拍节奏，大家复现后倒序再拍一次。",
		"按座位轮流拍一拍，接成八拍并保持稳定。",
		"看领队手指数拍，不出声地同步拍四拍。",
		"每人用两拍说名字，全员按节奏复述。",
		"模仿雨声：先轻点四下，再逐渐加快。",
		"全员轮做“拍手、拍腿、停”，连续三轮。",
	)),
	("动作", (248, 132, 119), (
		"记住领队三个动作，按原顺序完整模仿。",
		"右手摸左肩、左手摸右肩，再双手举高。",
		"用三步手势演出开门、找物、挥手，让人猜。",
		"站稳或坐好，双臂伸展、交叉抱肩、比心。",
		"领队做四个手势，下一人复现后再加一个。",
		"用表情和手势演出雨停天晴，伙伴说变化。",
		"两人隔空镜像做三个动作，然后交换领队。",
		"用动作演示日常流程，必须有开始和结束。",
		"听口令比圆形、三角形、直线，连续切换三轮。",
		"左右手交替比方向，连续四次不弄反。",
		"演一种动物，再加上它找食物的动作线索。",
		"一人摆造型，伙伴依次加入，最后定格三秒。",
		"不出声演天气变化，伙伴说出三个动作线索。",
		"按“举手、拍肩、摊掌、定格”做四拍动作。",
		"两人只用手臂拼出一个数字，大家猜是哪一个。",
		"记住伙伴三动作，按相反顺序做并说出来。",
	)),
	("故事", (181, 152, 218), (
		"接力编故事：加入主角、目标和意外，再想办法解决。",
		"从“门后有三声”开头，轮流续句并解释声音来源。",
		"每人给一个词，合成通顺句子，再扩成三句小故事。",
		"主角遇到难题，每人给一种办法，最后选个结局。",
		"轮流讲星球旅行，每人加入一个新地点和一个意外。",
		"给故事加位新朋友，用两句对话决定接下来的行动。",
		"轮流接一句，故事里必须出现会说话的日用品。",
		"编雨天旅行，每人加一种声音或气味，再接下一站。",
		"记住前文细节继续讲，不能重复名词，情节要连贯。",
		"让主角丢失又找回一件物品，说清寻找过程。",
		"轮流给出谜题线索，最后一人猜答案并说理由。",
		"分工讲开头、转折、结尾，三段情节要彼此衔接。",
		"主角面对选择，每人说一种后果，再决定结局。",
		"用雨伞、纸船、月亮编三句话，并说明它们的关系。",
		"一人先讲故事，大家各加一细节，最后复述所有细节。",
		"每人接一句编故事，不能用“后来”，最后起标题。",
	)),
	("寻找", (103, 189, 199), (
		"不移动物品，找两件同色物品，说出形状区别。",
		"找带数字的物品，读出数字并猜它的用途。",
		"找一种重复图案，指出重复次数或排列规律。",
		"找圆形和长方形各一件，说说它们的位置。",
		"只观察不拿取，找一件软物和一件硬物。",
		"找三种颜色的物品，从浅到深依次指出。",
		"找带文字的物品，说出第一个字和用途。",
		"观察十秒后转开视线，说出三件物品的位置。",
		"找有对称图案的物品，说出两边相同处。",
		"找视线范围内最小的物品，再说它旁边是什么。",
		"找一条线，说出它是直线、曲线还是折线。",
		"找两件同色但用途不同的物品，分别说用途。",
		"找三个圆形，按从大到小依次指出。",
		"找有盖子的容器，只观察并猜它装什么。",
		"观察十秒后闭眼，回忆并说出四种颜色。",
		"找个像字母或数字的形状，说出判断线索。",
	)),
	("想象", (141, 197, 138), (
		"设计一辆帮忙车：说三种功能和一条限制。",
		"发明新水果，描述颜色、味道和生长地点。",
		"设计漂浮图书馆，说出入口、规则和特别藏书。",
		"设计新星球：描述天气、地面和出行方式。",
		"给会说话的动物设目标、困难和解决办法。",
		"让雨伞有三种变形用途，选出最实用的一种。",
		"设计会移动的房子，说明目的地和出发准备。",
		"发明新乐器，说清演奏动作和它发出的声音。",
		"给普通物品一种超能力，再设定使用规则。",
		"设计手势小游戏，讲清目标、轮流方式和胜负条件。",
		"想象云朵商店，决定卖什么、怎样付款和店规。",
		"设计三种星球居民，并说明他们怎样合作。",
		"给无字地图加三个地标，推理宝藏可能在哪。",
		"发明解小麻烦的机器人，说明步骤和禁做事项。",
		"设计花园秘密入口，说明找法和入口后的景象。",
		"想象影子离开一天，决定它去哪和如何回来。",
	)),
	("友爱", (246, 155, 181), (
		"具体夸赞左边伙伴一件事，说说它怎样帮到大家。",
		"商量一件想合作的小事，轮流提出公平分工。",
		"分享今天的开心事；也可以选择跳过。",
		"请伙伴定一条规则，大家听后复述并确认。",
		"轮流说谢谢，并说清感谢对方哪件小事。",
		"一起取个队名，再说出它代表的共同特点。",
		"每人提一个下次想玩的活动，选出都能参加的。",
		"给伙伴一句鼓励，要针对他正在做的事。",
		"回想刚才游戏，说出每人一个贡献和一次默契。",
		"轮流问喜欢的游戏或颜色，并复述对方答案。",
		"一起设计三步合作挑战，给每人分配一个角色。",
		"合作完成四拍节奏，每轮换一位伙伴领拍。",
		"各说一件擅长的小事，找出两种能力如何互助。",
		"说出欣赏伙伴的一点和具体原因，不作比较。",
		"一起定一条让所有人玩得舒服的规则，再复述。",
		"选个共同小目标，每人认领一步并按顺序完成。",
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
	# 声明需要声音，须早于 pygame.init()
	audio_output.prepare()
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
	sound = sfx_helper.SFX(sfx_helper.game_media(__file__))
	speaker = tts.Speaker(pregen_dir=os.path.join(BASE_DIR, "media", "tts"))
	spoken_result = None
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
		sound.welcome()
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
				if sfx_helper.is_press(action):
					sound.button()
				if action == "QUIT":
					running = False
					break
				phase_before = wheel.phase
				wheel.handle_action(action)
				# 进入转动 -> 循环转盘音；停下 -> 停止
				if wheel.phase == "spinning" and phase_before != "spinning":
					sound.loop_start("wheel")
				elif phase_before == "spinning" and wheel.phase != "spinning":
					sound.loop_stop()
			if not running:
				break
			wheel.update(elapsed)
			if wheel.phase == "result":
				sound.loop_stop()
				# 转完后朗读结果内容；换题或再转会得到新的 key，重新朗读
				result_key = (wheel.selected, wheel.task)
				if result_key != spoken_result:
					spoken_result = result_key
					text = str(GAMES[wheel.selected][2][wheel.task]).strip()
					if speaker.has(text):
						speaker.speak(text)
			else:
				spoken_result = None
			display.draw(wheel)
			present_frame(screen)
	finally:
		speaker.close()
		sound.close()
		if buttons is not None:
			buttons.cleanup()
		pygame.quit()


if __name__ == "__main__":
	main()
