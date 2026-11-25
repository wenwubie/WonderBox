"""双人骰子对决与趣味挑战转盘。"""

import importlib
import math
import os
import random
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "Lucky Wheel"))
wheel_support = importlib.import_module("lucky_wheel")
GPIOButtons = wheel_support.GPIOButtons
event_action = wheel_support.event_action
point_on_wheel = wheel_support.point_on_wheel
present_frame = wheel_support.present_frame
spi_lcd = wheel_support.spi_lcd
wrap_text = wheel_support.wrap_text

from common import audio as audio_output
from common import sfx as sfx_helper
from common import tts
from common import ui_theme

import pygame


CHALLENGES = (
	("拍拍", (255, 195, 74), (
		"轻轻拍手三下。", "拍拍肩膀两下。", "拍出一个小节奏。",
		"用手指轻轻敲三下。", "先拍一下，再拍两下。", "轻拍两下腿，再拍一下手。",
		"轻拍手心两下，再停一下。", "先慢拍三下，再快拍两下。", "用两根手指轻敲手心三下。",
		"左右手轮流拍拍膝盖。", "拍手两下，再挥挥手。", "用手指在掌心轻点两下。",
	)),
	("动作", (241, 125, 102), (
		"向对方挥挥手。", "用手画一个大圆。", "做一个有趣的姿势。",
		"轻轻伸伸双臂。", "摸摸自己的头。", "慢慢点头三下。",
		"用手画一个小三角。", "轻轻耸肩两下。", "两只手张开，再握拳。",
		"抬起一只手停三秒。", "用手指在空中画颗星。", "慢慢摆动双手两下。",
	)),
	("表情", (239, 150, 178), (
		"做一个开心的表情。", "做一个惊讶的表情。", "做一个眨眼的表情。",
		"做一个大大的微笑。", "鼓鼓脸颊。", "做一个困困的表情。",
		"皱一皱鼻子。", "做一个好奇的表情。", "噘起嘴巴三秒。",
		"把眉毛轻轻挑起来。", "做一个害羞的表情。", "做一个思考的表情。",
	)),
	("声音", (139, 191, 226), (
		"哼一句喜欢的歌。", "有节奏地说三声加油。", "轻轻说三遍你好。",
		"唱一句自己编的歌。", "说一句神奇的咒语。", "用轻轻的声音说早上好。",
		"轻声说一句谢谢。", "像机器人一样说你好。", "用不同的声音说再见。",
		"说出一个长长的哦。", "哼一个短短的旋律。", "用悄悄话说声加油。",
	)),
	("想象", (126, 202, 177), (
		"假装吹一个大泡泡。", "假装闻一朵小花。", "假装手里拿着魔法棒。",
		"假装捧着一颗小星星。", "假装画一个大太阳。", "假装戴一顶神奇的帽子。",
		"假装打开一把小雨伞。", "假装划一条小船。", "假装喝一杯果汁。",
		"假装乘坐一艘飞船。", "假装搭一座小房子。", "假装和云朵打招呼。",
	)),
	("找找", (181, 202, 121), (
		"找一找红色的东西。", "找一个圆圆的东西。", "找一找蓝色的东西。",
		"找一种自己喜欢的颜色。", "找一样小小的东西。", "找一个方方的东西。",
		"找一种浅色的东西。", "找一个长长的东西。", "找一样有图案的东西。",
		"找一个你喜欢的东西。", "找一找白色的东西。", "找一样你觉得漂亮的东西。",
	)),
	("夸夸", (246, 180, 118), (
		"对对方说一声你好。", "送对方一个微笑。", "对对方说一声加油。",
		"向对方点点头。", "送给对方一句祝福。", "用手画一颗心送给对方。",
		"对自己说一句我很棒。", "夸夸对方的好点子。", "谢谢对方陪你玩。",
		"说一句鼓励自己的话。", "对对方说很高兴见到你。", "微笑着送对方一个赞。",
	)),
	("小问", (177, 164, 220), (
		"说出一种喜欢的水果。", "说一个开心的词。", "说一个喜欢的颜色。",
		"给自己起个有趣的名字。", "说一件今天开心的小事。", "说一个想玩的游戏。",
		"说一个喜欢的季节。", "说一种喜欢的天气。", "说一个喜欢的数字。",
		"说一个喜欢的玩具。", "说一个想去的地方。", "说一个喜欢的运动。",
	)),
)

DIE_FACES = (
	(1, (0, 0, 1), (1, 0, 0), (0, 1, 0)),
	(6, (0, 0, -1), (-1, 0, 0), (0, 1, 0)),
	(2, (1, 0, 0), (0, 0, -1), (0, 1, 0)),
	(5, (-1, 0, 0), (0, 0, 1), (0, 1, 0)),
	(3, (0, 1, 0), (1, 0, 0), (0, 0, -1)),
	(4, (0, -1, 0), (1, 0, 0), (0, 0, 1)),
)
SECTOR_ANGLE = 360.0 / len(CHALLENGES)
POINTER_ANGLE = 90.0


def multiply_rotations(first, second):
	x1, y1, z1, w1 = first
	x2, y2, z2, w2 = second
	return (w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
			w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
			w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
			w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2)


def rotate_vector(rotation, vector):
	qx, qy, qz, qw = rotation
	x, y, z = vector
	tx = 2.0 * (qy * z - qz * y)
	ty = 2.0 * (qz * x - qx * z)
	tz = 2.0 * (qx * y - qy * x)
	return (x + qw * tx + qy * tz - qz * ty,
			y + qw * ty + qz * tx - qx * tz,
			z + qw * tz + qx * ty - qy * tx)


def facing_value(rotation):
	return max(DIE_FACES, key=lambda face: rotate_vector(rotation, face[1])[2])[0]


class Die:
	def __init__(self, rng):
		self.rng = rng
		self.phase = "ready"
		self.value = None
		self.rotation = (0.23, -0.29, 0.0, math.sqrt(1.0 - 0.23 ** 2 - 0.29 ** 2))
		self.axis = (1.0, 0.0, 0.0)
		self.speed = 0.0

	def press(self):
		if self.phase == "ready":
			first = self.rng.random()
			second = self.rng.random() * math.tau
			third = self.rng.random() * math.tau
			self.rotation = (math.sqrt(1.0 - first) * math.sin(second),
							 math.sqrt(1.0 - first) * math.cos(second),
							 math.sqrt(first) * math.sin(third),
							 math.sqrt(first) * math.cos(third))
			direction = self.rng.uniform(0.0, math.tau)
			depth = self.rng.uniform(-0.5, 0.5)
			length = math.sqrt(1.0 + depth * depth)
			self.axis = (math.cos(direction) / length, math.sin(direction) / length, depth / length)
			self.speed = self.rng.uniform(5.0, 8.0)
			self.phase = "rolling"
			self.value = facing_value(self.rotation)
		elif self.phase == "rolling":
			self.phase = "locked"

	def update(self, elapsed):
		if self.phase == "rolling":
			half_angle = max(0.0, elapsed) * self.speed / 2.0
			sine = math.sin(half_angle)
			step = tuple(component * sine for component in self.axis) + (math.cos(half_angle),)
			self.rotation = multiply_rotations(step, self.rotation)
			length = math.sqrt(sum(component * component for component in self.rotation))
			self.rotation = tuple(component / length for component in self.rotation)
			self.value = facing_value(self.rotation)


class ChallengeWheel:
	def __init__(self, rng, recent_challenges=None):
		self.rng = rng
		self.recent_challenges = recent_challenges if recent_challenges is not None else {}
		self.angle = rng.uniform(0.0, 360.0)
		self.phase = "ready"
		self.speed = 0.0
		self.stop_angle = 0.0
		self.stop_speed = 0.0
		self.stop_elapsed = 0.0
		self.stop_duration = 0.0
		self.selected = None
		self.task = None

	def handle_action(self, action):
		if action == "K1" and self.phase in ("ready", "result"):
			self.speed = self.rng.uniform(240.0, 300.0)
			self.phase = "spinning"
			self.selected = None
			self.task = None
		elif action == "K1" and self.phase == "spinning":
			self.phase = "slowing"
			self.stop_angle = self.angle
			self.stop_speed = self.speed
			self.stop_elapsed = 0.0
			self.stop_duration = self.rng.uniform(2.8, 4.0)

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
				self.selected = int(((POINTER_ANGLE - self.angle) % 360.0) // SECTOR_ANGLE)
				task_count = len(CHALLENGES[self.selected][2])
				previous = self.recent_challenges.get(self.selected)
				if previous is None or task_count == 1:
					self.task = self.rng.randrange(task_count)
				else:
					self.task = self.rng.randrange(task_count - 1)
					if self.task >= previous:
						self.task += 1
				self.recent_challenges[self.selected] = self.task


class DuelGame:
	def __init__(self, rng=None):
		self.rng = rng if rng is not None else random.Random()
		self.recent_challenges = {}
		self.round_number = 0
		self.new_round()

	def new_round(self):
		self.round_number += 1
		self.dice = [Die(self.rng), Die(self.rng)]
		self.view = "dice"
		self.loser = None
		self.wheel = None

	def handle_action(self, action):
		if self.view == "wheel":
			if action == "K2":
				self.new_round()
			elif action == "K1":
				self.wheel.handle_action(action)
		elif action in ("K1", "K2"):
			self.dice[0 if action == "K1" else 1].press()
		elif action == "K3" and all(die.phase == "locked" for die in self.dice):
			if self.dice[0].value == self.dice[1].value:
				self.new_round()
			else:
				self.loser = 1 if self.dice[0].value < self.dice[1].value else 2
				self.wheel = ChallengeWheel(self.rng, self.recent_challenges)
				self.view = "wheel"

	def update(self, elapsed):
		if self.view == "wheel":
			self.wheel.update(elapsed)
		else:
			for die in self.dice:
				die.update(elapsed)


class DuelGPIOButtons(GPIOButtons):
	def poll(self):
		return ["BACK" if action == "QUIT" else action for action in super().poll()]


_st = ui_theme.style()  # 全局界面风格
BACKGROUND = _st["bg"]
PAPER = _st["panel"]
INK = _st["text"]
MUTED = _st["sub"]
LINE = _st["deco"]
PLAYER_COLORS = ((210, 89, 72), (55, 119, 191))  # 双方识别色, 固定
PLAYER_BACKGROUNDS = ((255, 242, 235), (234, 244, 255))
RIM = (45, 70, 81)
GOLD = (255, 211, 88)

PIPS = {
	1: ((0, 0),),
	2: ((-1, -1), (1, 1)),
	3: ((-1, -1), (0, 0), (1, 1)),
	4: ((-1, -1), (1, -1), (-1, 1), (1, 1)),
	5: ((-1, -1), (1, -1), (0, 0), (-1, 1), (1, 1)),
	6: ((-1, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (1, 1)),
}
DIE_CAMERA_DISTANCE = 5.0
DIE_INNER_SIZE = 0.56
DIE_MID_SIZE = (DIE_INNER_SIZE + 2.0) / 3.0
DIE_MESH_STEPS = (-1.0, -DIE_MID_SIZE, -DIE_INNER_SIZE,
				  DIE_INNER_SIZE, DIE_MID_SIZE, 1.0)
DIE_PIP_SPACING = 0.36
DIE_PIP_CIRCLE = tuple((math.cos(index * math.tau / 12), math.sin(index * math.tau / 12))
					   for index in range(12))


def build_die_mesh():
	vertices = []
	vertex_normals = []
	patches = []
	step_count = len(DIE_MESH_STEPS)
	for _, normal, right, up in DIE_FACES:
		first_vertex = len(vertices)
		for horizontal in DIE_MESH_STEPS:
			for vertical in DIE_MESH_STEPS:
				point = tuple(normal[axis] + right[axis] * horizontal + up[axis] * vertical
							  for axis in range(3))
				inner = tuple(max(-DIE_INNER_SIZE, min(DIE_INNER_SIZE, value)) for value in point)
				offset = tuple(point[axis] - inner[axis] for axis in range(3))
				length = math.sqrt(sum(value * value for value in offset))
				vertex_normal = tuple(value / length for value in offset)
				vertices.append(tuple(inner[axis] + (1.0 - DIE_INNER_SIZE) * vertex_normal[axis]
									  for axis in range(3)))
				vertex_normals.append(vertex_normal)
		for horizontal in range(step_count - 1):
			for vertical in range(step_count - 1):
				indices = (first_vertex + horizontal * step_count + vertical,
						   first_vertex + (horizontal + 1) * step_count + vertical,
						   first_vertex + (horizontal + 1) * step_count + vertical + 1,
						   first_vertex + horizontal * step_count + vertical + 1)
				normal = tuple(sum(vertex_normals[index][axis] for index in indices)
							   for axis in range(3))
				length = math.sqrt(sum(value * value for value in normal))
				normal = tuple(value / length for value in normal)
				center = tuple(sum(vertices[index][axis] for index in indices) / 4.0
							   for axis in range(3))
				distance = sum(normal[axis] * center[axis] for axis in range(3))
				patches.append((indices, normal, distance))
	return tuple(vertices), tuple(patches)


DIE_VERTICES, DIE_PATCHES = build_die_mesh()


def project_die_vertex(point, center, scale):
	x, y, z = point
	perspective = DIE_CAMERA_DISTANCE / (DIE_CAMERA_DISTANCE - z)
	return (round(center[0] + x * scale * perspective),
			round(center[1] - y * scale * perspective))


def die_outline(points):
	ordered = sorted(set(points))

	def half_outline(sequence):
		outline = []
		for point in sequence:
			while len(outline) >= 2:
				first, second = outline[-2:]
				turn = ((second[0] - first[0]) * (point[1] - first[1]) -
						(second[1] - first[1]) * (point[0] - first[0]))
				if turn > 0:
					break
				outline.pop()
			outline.append(point)
		return outline

	return half_outline(ordered)[:-1] + half_outline(reversed(ordered))[:-1]


def project_die_point(normal, right, up, horizontal, vertical, center, scale):
	x = normal[0] + right[0] * horizontal + up[0] * vertical
	y = normal[1] + right[1] * horizontal + up[1] * vertical
	z = normal[2] + right[2] * horizontal + up[2] * vertical
	return project_die_vertex((x, y, z), center, scale)


class DuelDisplay:
	def __init__(self, screen):
		self.screen = screen
		self.width, self.height = screen.get_size()
		self.portrait = self.height > self.width
		self.title_font = spi_lcd.load_font(21)
		self.heading_font = spi_lcd.load_font(15)
		self.body_font = spi_lcd.load_font(13)
		self.wheel_font = spi_lcd.load_font(11)
		self.button_font = spi_lcd.load_font(12)
		self.small_font = spi_lcd.load_font(11)
		self.hub_font = spi_lcd.load_font(14)
		margin, gap, button_height = 7, 5, 23
		button_width = (self.width - margin * 2 - gap * 2) // 3
		self.buttons = [pygame.Rect(margin + index * (button_width + gap),
									self.height - button_height - 5, button_width, button_height)
					for index in range(3)]
		card_width = (self.width - 30) // 2
		card_top = 48 if self.portrait else 43
		card_height = 165 if self.portrait else 124
		self.die_size = 72 if self.portrait else 56
		self.die_offset = 88 if self.portrait else 64
		shadow_size = (self.die_size + 8, max(6, self.die_size // 6))
		self.die_shadow = pygame.Surface(shadow_size, pygame.SRCALPHA)
		pygame.draw.ellipse(self.die_shadow, (38, 58, 68, 42), self.die_shadow.get_rect())
		self.die_canvas_size = math.ceil(self.die_size * 1.3)
		self.die_canvas = pygame.Surface((self.die_canvas_size * 2, self.die_canvas_size * 2),
									 pygame.SRCALPHA)
		self.die_mask = pygame.Surface(self.die_canvas.get_size(), pygame.SRCALPHA)
		self.dice_rects = [pygame.Rect(10 + index * (card_width + 10), card_top,
									   card_width, card_height) for index in range(2)]
		self.result_rect = pygame.Rect(10, 222 if self.portrait else 174,
									   self.width - 20, 54 if self.portrait else 29)
		if self.portrait:
			self.wheel_center = (self.width // 2, 126)
			self.wheel_radius = 75
			self.challenge_rect = pygame.Rect(12, 216, self.width - 24, 66)
		else:
			self.wheel_center = (83, 123)
			self.wheel_radius = 68
			self.challenge_rect = pygame.Rect(178, 52, self.width - 190, 145)

	def text(self, value, font, color, position):
		image = font.render(value, True, color)
		self.screen.blit(image, position)
		return image.get_rect(topleft=position)

	def centered(self, value, font, color, center):
		image = font.render(value, True, color)
		self.screen.blit(image, image.get_rect(center=center))

	def draw_header(self, game):
		header_fill = (223, 237, 245)
		pygame.draw.rect(self.screen, header_fill, (0, 0, self.width, 37))
		title = "骰子对决" if game.view == "dice" else "挑战转盘"
		self.text(title, self.title_font, ui_theme.pick(header_fill, INK), (11, 6))
		badge = "第%d轮" % game.round_number if game.view == "dice" else "玩家%d" % game.loser
		image = self.small_font.render(badge, True, ui_theme.pick(GOLD, INK))
		badge_rect = image.get_rect(center=(self.width - 38, 18)).inflate(14, 8)
		pygame.draw.rect(self.screen, GOLD, badge_rect, border_radius=5)
		self.screen.blit(image, image.get_rect(center=badge_rect.center))

	def draw_die(self, die, center, size, color):
		shadow_rect = self.die_shadow.get_rect(center=(center[0], center[1] + round(size * 0.51)))
		self.screen.blit(self.die_shadow, shadow_rect)
		self.die_canvas.fill((0, 0, 0, 0))
		canvas_center = (self.die_canvas_size, self.die_canvas_size)
		scale = size * 0.62
		vertices = [rotate_vector(die.rotation, vertex) for vertex in DIE_VERTICES]
		projected = [project_die_vertex(vertex, canvas_center, scale) for vertex in vertices]
		outline = die_outline(projected)
		self.die_mask.fill((255, 255, 255, 0))
		pygame.draw.polygon(self.die_mask, (255, 255, 255, 255), outline)
		pygame.draw.polygon(self.die_canvas, (207, 208, 204), outline)
		patches = []
		for indices, normal, distance in DIE_PATCHES:
			normal = rotate_vector(die.rotation, normal)
			if normal[2] * DIE_CAMERA_DISTANCE <= distance:
				continue
			light = max(0.0, -0.35 * normal[0] + 0.55 * normal[1] + 0.76 * normal[2])
			brightness = min(1.0, 0.70 + 0.30 * light)
			face_color = tuple(round(component * brightness) for component in (255, 253, 248))
			depth = sum(vertices[index][2] for index in indices) / 4.0
			patches.append((depth, face_color, [projected[index] for index in indices]))
		patches.sort(key=lambda patch: patch[0])
		for _, face_color, points in patches:
			pygame.draw.polygon(self.die_canvas, face_color, points)
		faces = []
		for number, normal, right, up in DIE_FACES:
			transformed_normal = rotate_vector(die.rotation, normal)
			if transformed_normal[2] > 1.0 / DIE_CAMERA_DISTANCE:
				faces.append((number, transformed_normal, rotate_vector(die.rotation, right),
							  rotate_vector(die.rotation, up)))
		faces.sort(key=lambda face: face[1][2])
		front = facing_value(die.rotation)
		for number, normal, right, up in faces:
			light = max(0.0, -0.35 * normal[0] + 0.55 * normal[1] + 0.76 * normal[2])
			brightness = min(1.0, 0.70 + 0.30 * light)
			face_color = tuple(round(component * brightness) for component in (255, 253, 248))
			if die.value is None and number == front:
				question_position = project_die_point(normal, right, up, 0, 0, center, size * 0.31)
				continue
			pip_color = color if number == front else tuple(
				round(component * 0.65 + face_color[index] * 0.35)
				for index, component in enumerate(color))
			for horizontal, vertical in PIPS[number]:
				for radius, fill in ((0.16, tuple(round(component * 0.7) for component in pip_color)),
									 (0.12, pip_color)):
					points = [project_die_point(normal, right, up,
												   horizontal * DIE_PIP_SPACING + circle_x * radius,
												   vertical * DIE_PIP_SPACING + circle_y * radius,
											   canvas_center, scale)
							  for circle_x, circle_y in DIE_PIP_CIRCLE]
					pygame.draw.polygon(self.die_canvas, fill, points)
		self.die_canvas.blit(self.die_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
		image = pygame.transform.smoothscale(self.die_canvas, (self.die_canvas_size, self.die_canvas_size))
		self.screen.blit(image, image.get_rect(center=center))
		if die.value is None:
			self.centered("?", self.title_font, color, question_position)

	def draw_dice(self, game):
		for index, die in enumerate(game.dice):
			rect = self.dice_rects[index]
			color = PLAYER_COLORS[index]
			pygame.draw.rect(self.screen, PLAYER_BACKGROUNDS[index], rect, border_radius=8)
			pygame.draw.rect(self.screen, color, rect, 2, border_radius=8)
			self.centered("玩家 %d" % (index + 1), self.heading_font, color,
						  (rect.centerx, rect.y + 17))
			die_center = (rect.centerx, rect.y + self.die_offset)
			self.draw_die(die, die_center, self.die_size, color)
			status = "锁定 %d 点" % die.value if die.phase == "locked" else \
				{"ready": "准备", "rolling": "转动中"}[die.phase]
			self.centered(status, self.body_font, color, (rect.centerx, rect.bottom - 16))
		rect = self.result_rect
		pygame.draw.rect(self.screen, PAPER, rect, border_radius=7)
		pygame.draw.rect(self.screen, LINE, rect, 1, border_radius=7)
		if all(die.phase == "locked" for die in game.dice):
			if game.dice[0].value == game.dice[1].value:
				message, color = "平局，再来一局！", INK
			else:
				winner = 1 if game.dice[0].value > game.dice[1].value else 2
				message = "玩家%d获胜 · 玩家%d挑战" % (winner, 3 - winner)
				color = PLAYER_COLORS[winner - 1]
		else:
			message, color = "等待两位玩家", MUTED
		self.centered(message, self.heading_font, color, rect.center)

	def draw_challenge_wheel(self, game):
		wheel = game.wheel
		center, radius = self.wheel_center, self.wheel_radius
		pygame.draw.circle(self.screen, RIM, center, radius + 9)
		pygame.draw.circle(self.screen, (93, 124, 128), center, radius + 5)
		for index, (_, color, _) in enumerate(CHALLENGES):
			start = wheel.angle + index * SECTOR_ANGLE
			points = [center] + [point_on_wheel(center, radius, start + SECTOR_ANGLE * step / 15)
								 for step in range(16)]
			pygame.draw.polygon(self.screen, color, points)
		for index, (label, color, _) in enumerate(CHALLENGES):
			start = wheel.angle + index * SECTOR_ANGLE
			pygame.draw.line(self.screen, PAPER, center, point_on_wheel(center, radius, start), 1)
			position = point_on_wheel(center, radius * 0.68, start + SECTOR_ANGLE / 2)
			# 扇区底色固定, 文字颜色按扇区亮度自适应
			self.centered(label, self.wheel_font, ui_theme.pick(color, INK), position)
		for index in range(16):
			position = point_on_wheel(center, radius + 6, index * 22.5)
			active = (index + int(wheel.angle // 20)) % 2 == 0
			pygame.draw.circle(self.screen, GOLD if active else (255, 248, 218), position, 2)
		pygame.draw.circle(self.screen, RIM, center, 15)
		self.centered("GO", self.hub_font, ui_theme.readable(RIM), center)
		pointer = [(center[0] + radius + 13, center[1] - 8),
				   (center[0] + radius + 13, center[1] + 8),
				   (center[0] + radius - 4, center[1])]
		pygame.draw.polygon(self.screen, PAPER, pointer, 4)
		pygame.draw.polygon(self.screen, PLAYER_COLORS[0], pointer)

	def draw_challenge(self, game):
		wheel = game.wheel
		self.draw_challenge_wheel(game)
		rect = self.challenge_rect
		pygame.draw.rect(self.screen, PAPER, rect, border_radius=7)
		pygame.draw.rect(self.screen, LINE, rect, 1, border_radius=7)
		heading = "玩家%d的挑战" % game.loser
		self.text(heading, self.heading_font, PLAYER_COLORS[game.loser - 1], (rect.x + 10, rect.y + 8))
		if wheel.phase == "result":
			body = CHALLENGES[wheel.selected][2][wheel.task]
		elif wheel.phase == "spinning":
			body = "转起来！"
		elif wheel.phase == "slowing":
			body = "马上揭晓！"
		else:
			body = "准备好啦！"
		text_y = rect.y + 29
		for line in wrap_text(body, self.body_font, rect.width - 20):
			self.text(line, self.body_font, INK, (rect.x + 10, text_y))
			text_y += self.body_font.get_linesize() + 1

	def draw_buttons(self, game):
		if game.view == "dice":
			labels = []
			for die in game.dice:
				labels.append({"ready": "开始", "rolling": "停下", "locked": "锁定"}[die.phase])
			both_locked = all(die.phase == "locked" for die in game.dice)
			tie = both_locked and game.dice[0].value == game.dice[1].value
			labels.append("重掷" if tie else "挑战")
			enabled = (game.dice[0].phase != "locked", game.dice[1].phase != "locked", both_locked)
		else:
			wheel = game.wheel
			label = {"ready": "开始", "spinning": "停下", "slowing": "减速中",
					 "result": "再转"}[wheel.phase]
			labels = (label, "返回", "")
			enabled = (wheel.phase != "slowing", True, False)
		colors = ((251, 184, 164), (160, 200, 239), GOLD)
		for index, rect in enumerate(self.buttons):
			color = colors[index] if enabled[index] else (221, 229, 231)
			text_color = ui_theme.pick(color, INK) if enabled[index] else (83, 92, 89)
			pygame.draw.rect(self.screen, color, rect, border_radius=5)
			self.centered(labels[index], self.button_font, text_color, rect.center)

	def draw(self, game):
		self.screen.fill(BACKGROUND)
		self.draw_header(game)
		if game.view == "dice":
			self.draw_dice(game)
		else:
			self.draw_challenge(game)
		self.draw_buttons(game)


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
	last_text = None  # 最近一次朗读的挑战内容，长按 K2 原地重播
	try:
		if not spi_lcd.is_simulate():
			try:
				gpio = importlib.import_module("RPi.GPIO")
				buttons = DuelGPIOButtons(gpio, k2_long_action="REPLAY")
			except Exception as error:
				raise RuntimeError("GPIO 初始化失败，请检查 RPi.GPIO 和按键连接。") from error
		else:
			pygame.display.set_caption("骰子对决")
		display = DuelDisplay(screen)
		game = DuelGame()
		hold = spi_lcd.SimulatedHold("K3", "BACK", wheel_support.QUIT_HOLD_SECONDS,
								 k2_long_action="REPLAY")
		clock = pygame.time.Clock()
		running = True
		sound.welcome()
		print("骰子对决已启动：K1、K2 控制骰子，K3 进入挑战；轮盘中 K1 启动/停止，K2 返回，K3 无功能。")
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
				if action == "REPLAY":
					if last_text:
						speaker.speak(last_text)  # 原地重播，不新开一局
					continue
				if action == "QUIT":
					running = False
					break
				if action == "BACK":
					if game.view == "wheel":
						continue
					running = False
					break
				wheel_phase = getattr(game, "wheel", None).phase if getattr(game, "wheel", None) else None
				game.handle_action(action)
				# 轮盘开始转动 -> 循环转盘音；停下 -> 停止
				if getattr(game, "wheel", None):
					if game.wheel.phase == "spinning" and wheel_phase != "spinning":
						sound.loop_start("wheel")
					elif wheel_phase == "spinning" and game.wheel.phase != "spinning":
						sound.loop_stop()
			if not running:
				break
			game.update(elapsed)
			if getattr(game, "wheel", None) and game.wheel.phase == "result":
				sound.loop_stop()
				# 挑战转盘停下后朗读结果内容；新一局会重置为新的 key
				result_key = (id(game.wheel), game.wheel.selected, game.wheel.task)
				if result_key != spoken_result:
					spoken_result = result_key
					text = str(CHALLENGES[game.wheel.selected][2][game.wheel.task]).strip()
					if speaker.has(text):
						last_text = text
						speaker.speak(text)
			else:
				spoken_result = None
				last_text = None
			display.draw(game)
			present_frame(screen)
	finally:
		speaker.close()
		sound.close()
		if buttons is not None:
			buttons.cleanup()
		pygame.quit()


if __name__ == "__main__":
	main()
