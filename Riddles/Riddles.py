"""适合小朋友的脑筋急转弯。"""

import importlib
import json
import os
import random
import sys
import tempfile
import time
import unicodedata


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, "riddles.json")
ROOT_DIR = os.path.dirname(BASE_DIR)
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "Lucky Wheel"))
wheel_support = importlib.import_module("lucky_wheel")
event_action = wheel_support.event_action
present_frame = wheel_support.present_frame
spi_lcd = wheel_support.spi_lcd

from common import audio as audio_output
from common import sfx as sfx_helper
from common import tts
from common import ui_theme

import pygame


# 朗读文案前缀：题目念“请听题”，答案用语音提示内容
SPEAK_QUESTION_PREFIX = "请听题。"
SPEAK_ANSWER_PREFIX = "答案是。"

# 预取窗口：当前题答案 + 后续 N 题的题目/答案。连按“下一题”也命中缓存。
PREFETCH_LOOKAHEAD = 6


class GPIOButtons(wheel_support.GPIOButtons):
	def poll(self):
		return ["HOLD_K3" if action == "QUIT" else action for action in super().poll()]


def question_key(question):
	text = unicodedata.normalize("NFKC", question).casefold()
	return "".join(character for character in text
				   if not character.isspace() and not unicodedata.category(character).startswith("P"))


def all_speech_texts(riddles):
	"""整库朗读文本（题目+答案），供空闲预热后台慢慢合成落盘。"""
	texts = []
	for question, answer in riddles:
		texts.append(SPEAK_QUESTION_PREFIX + question)
		texts.append(SPEAK_ANSWER_PREFIX + answer)
	return texts


def load_riddles(path=DATA_PATH):
	with open(path, encoding="utf-8") as source:
		data = json.load(source)
	if not isinstance(data, list):
		raise ValueError("题库格式错误：应为题目列表")
	riddles = []
	keys = set()
	for entry in data:
		if not isinstance(entry, dict):
			continue
		question, answer = entry.get("q"), entry.get("a")
		if not isinstance(question, str) or not isinstance(answer, str):
			continue
		question, answer = question.strip(), answer.strip()
		key = question_key(question)
		if not key or not answer or key in keys:
			continue
		keys.add(key)
		riddles.append((question, answer))
	if not riddles:
		raise ValueError("题库没有有效题目")
	return riddles


def default_history_path():
	if os.name == "nt":
		directory = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
	else:
		directory = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
	return os.path.join(directory, "WonderBox", "riddles_history.json")


class RiddleHistory:
	def __init__(self, path=None):
		self.path = path
		self.seen = set()
		self.answered = set()
		self.last = None
		self.warned = False
		if path is not None:
			try:
				with open(path, encoding="utf-8") as source:
					data = json.load(source)
				if isinstance(data, dict):
					entries = data.get("seen", [])
					if isinstance(entries, list):
						self.seen = {entry for entry in entries if isinstance(entry, str)}
					answered = data.get("answered")
					if isinstance(answered, list):
						self.answered = {entry for entry in answered if isinstance(entry, str)}
					elif "answered" not in data:
						self.answered = self.seen.copy()
					last = data.get("last")
					if isinstance(last, str) and last in self.seen:
						self.last = last
			except (OSError, ValueError):
				pass

	def record(self, question):
		self.last = question_key(question)
		self.seen.add(self.last)
		self.save()

	def mark_answered(self, question):
		key = question_key(question)
		if key not in self.answered:
			self.answered.add(key)
			self.save()

	def reset(self):
		previous = self.seen, self.answered, self.last
		self.seen, self.answered, self.last = set(), set(), None
		if self.save():
			return True
		self.seen, self.answered, self.last = previous
		return False

	def save(self):
		if self.path is None:
			return True
		temporary_path = None
		try:
			directory = os.path.dirname(os.path.abspath(self.path))
			os.makedirs(directory, exist_ok=True)
			with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=directory, delete=False) as output:
				temporary_path = output.name
				json.dump({"seen": sorted(self.seen), "answered": sorted(self.answered),
						   "last": self.last}, output, ensure_ascii=False)
			for attempt in range(4):
				try:
					os.replace(temporary_path, self.path)
					break
				except PermissionError:
					if attempt == 3:
						raise
					time.sleep(0.02 * (2 ** attempt))
			self.warned = False
			return True
		except OSError:
			if temporary_path is not None:
				try:
					os.remove(temporary_path)
				except OSError:
					pass
			if not self.warned:
				print("题目记录无法保存；本次使用中仍会避免重复。")
				self.warned = True
			return False


class RiddleGame:
	def __init__(self, riddles, rng=None, history=None, mode=None):
		unique = {}
		for question, answer in riddles:
			key = question_key(question)
			if key and answer.strip():
				unique.setdefault(key, (question.strip(), answer.strip()))
		self.riddles = tuple(unique.values())
		if not self.riddles:
			raise ValueError("题库为空")
		self.keys = {question_key(question) for question, _ in self.riddles}
		self.rng = rng if rng is not None else random.Random()
		self.history = history if history is not None else RiddleHistory()
		if mode not in (None, "all", "unanswered", "answered"):
			raise ValueError("未知的题目分类")
		self.mode = mode
		self.order = []
		for index, (question, _) in enumerate(self.riddles):
			key = question_key(question)
			if mode is None and key in self.history.seen:
				continue
			if mode == "unanswered" and key in self.history.answered:
				continue
			if mode == "answered" and key not in self.history.answered:
				continue
			self.order.append(index)
		self.rng.shuffle(self.order)
		if mode in ("all", "unanswered"):
			self.order.sort(key=lambda index: question_key(self.riddles[index][0]) in self.history.seen)
		if mode in ("all", "unanswered") and len(self.order) > 1:
			first = question_key(self.riddles[self.order[0]][0])
			if first in self.history.seen and first == self.history.last:
				self.order[0], self.order[1] = self.order[1], self.order[0]
		self.position = 0 if self.order else -1
		self.furthest = self.position
		self.at_end = not self.order
		self.revealed = False
		if self.order:
			self.record_current()

	@property
	def current(self):
		return self.riddles[self.order[self.position]] if self.position >= 0 else None

	def upcoming_texts(self):
		"""按优先级返回接下来可能朗读的文本（含前缀），供后台预取。

		题目顺序 self.order 在开局已 shuffle 确定，因此当前题答案、下一题
		题目/答案都可预知。趁用户读题/听当前朗读的间隙提前合成，按键时
		speak() 直接命中缓存秒播，消除现场合成的等待。
		"""
		if self.at_end or self.position < 0 or not self.order:
			return []
		texts = []
		question, answer = self.riddles[self.order[self.position]]
		texts.append(SPEAK_ANSWER_PREFIX + answer)  # 用户随时可能按 K3 看答案
		# 后续若干题的题目/答案都预取，连按“下一题”不用等现场合成
		for offset in range(1, PREFETCH_LOOKAHEAD + 1):
			index = self.position + offset
			if index >= len(self.order):
				break
			next_question, next_answer = self.riddles[self.order[index]]
			texts.append(SPEAK_QUESTION_PREFIX + next_question)
			texts.append(SPEAK_ANSWER_PREFIX + next_answer)
		return texts

	def record_current(self):
		if (self.mode == "all" and question_key(self.current[0]) in self.history.seen
				and self.keys <= self.history.seen):
			self.history.seen.clear()
		self.history.record(self.current[0])

	def restart(self):
		last = self.history.last
		self.order = list(range(len(self.riddles)))
		self.rng.shuffle(self.order)
		if len(self.order) > 1 and question_key(self.riddles[self.order[0]][0]) == last:
			self.order[0], self.order[1] = self.order[1], self.order[0]
		self.position = 0
		self.furthest = 0
		self.at_end = False
		self.revealed = False
		self.history.seen.clear()
		self.history.record(self.current[0])

	def handle_action(self, action):
		if action == "K3":
			if self.at_end and self.mode is None:
				self.restart()
			elif not self.at_end:
				self.revealed = True
				self.history.mark_answered(self.current[0])
		elif action == "K1":
			if self.at_end and self.position >= 0:
				self.at_end = False
			elif self.position > 0:
				self.position -= 1
			else:
				return
			self.revealed = False
		elif action == "K2":
			if not self.at_end and self.position + 1 < len(self.order):
				self.position += 1
				if self.position > self.furthest:
					self.furthest = self.position
					self.record_current()
			elif not self.at_end:
				self.at_end = True
			self.revealed = False


class RiddleApp:
	OPTIONS = (("all", "全部题目"), ("unanswered", "未答过"),
			   ("answered", "已答过"), ("reset", "重置进度"))

	def __init__(self, riddles, history=None, rng=None):
		self.riddles = tuple(riddles)
		self.keys = {question_key(question) for question, _ in self.riddles}
		self.history = history if history is not None else RiddleHistory()
		self.rng = rng if rng is not None else random.Random()
		self.selection = 0
		self.notice = ""
		self.confirm_reset = False
		self.game = None

	def counts(self):
		answered = len(self.keys & self.history.answered)
		return {"all": len(self.keys), "unanswered": len(self.keys) - answered, "answered": answered}

	def handle_action(self, action):
		if action == "MENU":
			self.game = None
			self.notice = ""
			self.confirm_reset = False
			return
		if self.game is not None:
			if action == "K3" and self.game.at_end:
				self.game = None
			else:
				self.game.handle_action(action)
			return
		if self.confirm_reset:
			if action in ("K1", "K2"):
				self.confirm_reset = False
				self.notice = ""
			elif action == "K3":
				self.confirm_reset = False
				self.notice = "进度已重置" if self.history.reset() else "重置失败，记录未改变"
			return
		if action in ("K1", "K2"):
			step = -1 if action == "K1" else 1
			self.selection = (self.selection + step) % len(self.OPTIONS)
			self.notice = ""
		elif action in ("SELECT_0", "SELECT_1", "SELECT_2", "SELECT_3"):
			self.selection = int(action[-1])
			self.notice = ""
		elif action == "K3":
			mode, _ = self.OPTIONS[self.selection]
			if mode == "reset":
				self.confirm_reset = True
				self.notice = ""
				return
			if not self.counts()[mode]:
				self.notice = "还没有已答过的题" if mode == "answered" else "没有未答过的题啦"
				return
			self.game = RiddleGame(self.riddles, self.rng, self.history, mode=mode)
			self.notice = ""

	def speech(self):
		"""返回当前应朗读的 (标识, 文本)；菜单或题组结束返回 (None, "")。

		标识随题目和“是否揭晓”变化，调用方只在标识变化时朗读，
		避免同一题在多帧里被反复朗读；返回菜单后标识归零。
		"""
		game = self.game
		if game is None or game.at_end or game.current is None:
			return None, ""
		question, answer = game.current
		key = question_key(question)
		if game.revealed:
			return ("answer", key), SPEAK_ANSWER_PREFIX + answer
		return ("question", key), SPEAK_QUESTION_PREFIX + question

	def prefetch_texts(self):
		"""返回当前可预知的后续朗读文本（供后台预取，不朗读）。"""
		game = self.game
		return game.upcoming_texts() if game is not None else []


_st = ui_theme.style()  # 全局界面风格
BACKGROUND = _st["bg"]
PAPER = _st["panel"]
INK = _st["text"]
MUTED = _st["sub"]
TEAL = _st["accent"]
CORAL = (224, 102, 91)  # 固定暖色(警示)
YELLOW = (255, 204, 93)  # 固定金色(奖励)
ANSWER_HIDDEN = (255, 243, 200)
ANSWER_SHOWN = (216, 241, 230)
OUTLINE = _st["deco"]


def wrap_text(text, font, max_width):
	lines = []
	line = ""
	for character in text:
		if character == "\n":
			lines.append(line)
			line = ""
		elif line and font.size(line + character)[0] > max_width:
			if (character in "，。！？；：、）】》”" and len(line) > 1
					and font.size(line[-1] + character)[0] <= max_width):
				lines.append(line[:-1])
				line = line[-1] + character
			else:
				lines.append(line)
				line = character.lstrip()
		else:
			line += character
	if line or not lines:
		lines.append(line)
	return lines


class RiddleDisplay:
	def __init__(self, screen):
		self.screen = screen
		self.width, self.height = screen.get_size()
		self.portrait = self.height > self.width
		self.fonts = {}
		margin = 12
		self.menu_button = pygame.Rect(self.width - 32, 7, 24, 28)
		button_gap = 6
		button_width = (self.width - margin * 2 - button_gap * 2) // 3
		button_top = self.height - 39
		self.buttons = [pygame.Rect(margin + index * (button_width + button_gap), button_top,
									button_width, 29) for index in range(3)]
		menu_top = 55 if self.portrait else 46
		menu_gap = 7 if self.portrait else 5
		self.menu_bottom = button_top - 25
		row_height = (self.menu_bottom - menu_top - menu_gap * 3) // 4
		self.menu_rows = [pygame.Rect(margin, menu_top + index * (row_height + menu_gap),
									 self.width - margin * 2, row_height) for index in range(4)]
		answer_height = 65 if self.portrait else 48
		self.answer_rect = pygame.Rect(margin, button_top - 8 - answer_height,
									  self.width - margin * 2, answer_height)
		question_top = 49 if self.portrait else 43
		self.question_rect = pygame.Rect(margin, question_top, self.width - margin * 2,
										 self.answer_rect.top - question_top - 8)
		self.question_text_rect = pygame.Rect(self.question_rect.x + 12, self.question_rect.y + 32,
												self.question_rect.width - 24, self.question_rect.height - 40)
		self.answer_text_rect = pygame.Rect(self.answer_rect.x + 43, self.answer_rect.y + 5,
											  self.answer_rect.width - 54, self.answer_rect.height - 10)

	def font(self, size):
		if size not in self.fonts:
			self.fonts[size] = spi_lcd.load_font(size)
		return self.fonts[size]

	def fit_text(self, text, rect, max_size):
		for size in range(max_size, 7, -1):
			font = self.font(size)
			lines = wrap_text(text, font, rect.width)
			if (len(lines) * font.get_linesize() <= rect.height
					and all(font.size(line)[0] <= rect.width for line in lines)):
				return font, lines
		return font, lines

	def draw_fitted(self, text, rect, color, max_size):
		font, lines = self.fit_text(text, rect, max_size)
		top = rect.centery - len(lines) * font.get_linesize() // 2
		for line in lines:
			image = font.render(line, True, color)
			self.screen.blit(image, image.get_rect(midtop=(rect.centerx, top)))
			top += font.get_linesize()

	def draw_header(self, game, show_menu=False):
		center = (27, 24)
		pygame.draw.circle(self.screen, (255, 230, 160), center, 18)
		pygame.draw.circle(self.screen, YELLOW, center, 13)
		pygame.draw.circle(self.screen, CORAL, center, 13, 1)
		pygame.draw.circle(self.screen, INK, (23, 22), 1)
		pygame.draw.circle(self.screen, INK, (31, 22), 1)
		pygame.draw.arc(self.screen, INK, (22, 23, 10, 7), 3.4, 6.0, 1)
		title = self.font(20).render("脑筋急转弯", True, INK)
		self.screen.blit(title, (49, 12))
		progress = "%d/%d" % (len(game.keys & game.history.answered), len(game.keys))
		image = self.font(12).render(progress, True, TEAL)
		right = self.menu_button.left - 5 if show_menu else self.width - 12
		if not show_menu or not self.portrait:
			self.screen.blit(image, image.get_rect(topright=(right, 16)))
		if show_menu:
			rect = self.menu_button
			pygame.draw.rect(self.screen, ANSWER_SHOWN, rect, border_radius=6)
			icon_color = ui_theme.pick(ANSWER_SHOWN, TEAL)
			pygame.draw.lines(self.screen, icon_color, False,
							  [(rect.x + 5, rect.y + 13), (rect.centerx, rect.y + 7),
							   (rect.right - 5, rect.y + 13)], 2)
			pygame.draw.rect(self.screen, icon_color, (rect.x + 7, rect.y + 13, 10, 8), 2)

	def draw_question(self, game):
		rect = self.question_rect
		pygame.draw.rect(self.screen, PAPER, rect, border_radius=8)
		pygame.draw.rect(self.screen, OUTLINE, rect, 1, border_radius=8)
		pygame.draw.circle(self.screen, TEAL, (rect.x + 17, rect.y + 17), 10)
		letter = self.font(13).render("Q", True, ui_theme.pick(TEAL, PAPER))
		self.screen.blit(letter, letter.get_rect(center=(rect.x + 17, rect.y + 17)))
		label_text = dict(RiddleApp.OPTIONS).get(game.mode, "转转脑袋")
		label = self.font(13).render(label_text, True, TEAL)
		self.screen.blit(label, (rect.x + 32, rect.y + 9))
		if game.history.warned:
			warning = self.font(12).render("记录未保存", True, CORAL)
			self.screen.blit(warning, warning.get_rect(topright=(rect.right - 10, rect.y + 10)))
		else:
			pygame.draw.circle(self.screen, CORAL, (rect.right - 20, rect.y + 14), 3)
			pygame.draw.circle(self.screen, YELLOW, (rect.right - 12, rect.y + 21), 2)
		question = "这组题目看完啦！" if game.at_end else game.current[0]
		self.draw_fitted(question, self.question_text_rect, INK, 23 if self.portrait else 21)

	def draw_answer(self, game):
		rect = self.answer_rect
		color = ANSWER_SHOWN if game.revealed else ANSWER_HIDDEN
		pygame.draw.rect(self.screen, color, rect, border_radius=7)
		pygame.draw.circle(self.screen, CORAL, (rect.x + 21, rect.centery), 12)
		letter = self.font(15).render("A", True, ui_theme.pick(CORAL, PAPER))
		self.screen.blit(letter, letter.get_rect(center=(rect.x + 21, rect.centery)))
		if game.at_end:
			answer = "再选一组继续玩！" if game.mode is not None else "休息一下，再来一轮！"
		elif game.revealed:
			answer = game.current[1]
		else:
			answer = "答案藏起来啦"
		# 答案卡底色是固定浅色, 文字颜色按底色自适应
		self.draw_fitted(answer, self.answer_text_rect,
						 ui_theme.pick(color, INK if game.revealed else MUTED),
						 18 if self.portrait else 17)

	def draw_buttons(self, game):
		previous = game.position > 0 or (game.at_end and game.position >= 0)
		if game.at_end:
			labels = ("上题", "下题", "菜单" if game.mode is not None else "再玩")
			enabled = (previous, False, True)
		else:
			labels = ("上题", "下题", "答案")
			enabled = (previous, True, not game.revealed)
		self.draw_control_buttons(labels, enabled)

	def draw_control_buttons(self, labels, enabled):
		colors = ((248, 167, 146), (115, 199, 183), (255, 208, 112))
		for index, rect in enumerate(self.buttons):
			color = colors[index] if enabled[index] else (218, 228, 222)
			text_color = ui_theme.pick(color, INK) if enabled[index] else (83, 92, 89)
			pygame.draw.rect(self.screen, color, rect, border_radius=6)
			image = self.font(13).render(labels[index], True, text_color)
			self.screen.blit(image, image.get_rect(center=rect.center))

	def draw(self, game):
		self.screen.fill(BACKGROUND)
		self.draw_header(game, show_menu=game.mode is not None)
		self.draw_question(game)
		self.draw_answer(game)
		self.draw_buttons(game)

	def draw_menu(self, app):
		self.screen.fill(BACKGROUND)
		self.draw_header(app)
		if app.confirm_reset:
			self.draw_fitted("确定重置答题进度吗？", self.question_text_rect, INK,
							 22 if self.portrait else 20)
			self.draw_fitted("已答过和已看记录将清空", self.answer_rect, CORAL, 15)
			self.draw_control_buttons(("取消", "取消", "确认"), (True, True, True))
			return
		counts = app.counts()
		colors = (CORAL, TEAL, (201, 151, 59), MUTED)
		icons = ("全", "新", "答", "重")
		for index, (mode, label) in enumerate(app.OPTIONS):
			rect = self.menu_rows[index]
			selected = index == app.selection
			fill = ANSWER_SHOWN if selected else PAPER
			pygame.draw.rect(self.screen, fill, rect, border_radius=7)
			pygame.draw.rect(self.screen, TEAL if selected else OUTLINE, rect, 2 if selected else 1,
							 border_radius=7)
			center = (rect.x + 22, rect.centery)
			pygame.draw.circle(self.screen, colors[index], center, min(13, rect.height // 2 - 2))
			icon = self.font(13).render(icons[index], True, ui_theme.readable(colors[index]))
			self.screen.blit(icon, icon.get_rect(center=center))
			image = self.font(18).render(label, True, ui_theme.pick(fill, INK))
			self.screen.blit(image, image.get_rect(midleft=(rect.x + 44, rect.centery)))
			count_text = "清除记录" if mode == "reset" else "%d 题" % counts[mode]
			count = self.font(14).render(count_text, True,
										 ui_theme.pick(fill, TEAL) if selected else MUTED)
			self.screen.blit(count, count.get_rect(midright=(rect.right - 12, rect.centery)))
		notice = app.notice or ("记录未保存" if app.history.warned else "")
		if notice:
			rect = pygame.Rect(12, self.menu_bottom, self.width - 24,
							   self.buttons[0].top - self.menu_bottom)
			self.draw_fitted(notice, rect, CORAL, 13)
		self.draw_control_buttons(("上选", "下选", "确定"), (True, True, True))


def riddle_event_action(event, display, app):
	if event.type == pygame.KEYDOWN and event.key == pygame.K_BACKSPACE:
		return "MENU"
	if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
		window = pygame.display.get_surface()
		if window is not None:
			position = (event.pos[0] * display.width / window.get_width(),
						event.pos[1] * display.height / window.get_height())
			if app.game is not None and display.menu_button.collidepoint(position):
				return "MENU"
			if app.game is None and not app.confirm_reset:
				for index, rect in enumerate(display.menu_rows):
					if rect.collidepoint(position):
						return "SELECT_%d" % index
	return event_action(event, display)


def main():
	# 必须在 spi_lcd.init()/pygame.init() 之前声明需要声音：让显示层跳过
	# dummy 音频驱动，朗读音频由 pygame 的同一音频设备播放（预生成 ogg，无需 piper）。
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
	speaker = tts.Speaker()
	sound = sfx_helper.SFX(sfx_helper.game_media(__file__))
	spoken = None
	try:
		if not spi_lcd.is_simulate():
			try:
				gpio = importlib.import_module("RPi.GPIO")
				buttons = GPIOButtons(gpio)
			except Exception as error:
				raise RuntimeError("GPIO 初始化失败，请检查 RPi.GPIO 和按键连接。") from error
		else:
			pygame.display.set_caption("脑筋急转弯")
		display = RiddleDisplay(screen)
		riddles = load_riddles()
		app = RiddleApp(riddles, history=RiddleHistory(default_history_path()))
		sound.welcome()  # 从主界面进入时的语音欢迎
		hold = spi_lcd.SimulatedHold("K3", "HOLD_K3", wheel_support.QUIT_HOLD_SECONDS)
		clock = pygame.time.Clock()
		running = True
		print("脑筋急转弯已启动：K1/K2 选择，K3 确认或显示答案；长按 K3 返回菜单，菜单中长按退出。")
		while running:
			clock.tick(30)
			if buttons is None:
				actions = [hold.process_event(event, riddle_event_action(event, display, app))
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
				if action == "HOLD_K3":
					if app.confirm_reset or (app.game is not None and app.game.at_end):
						continue
					if app.game is None:
						running = False
						break
					app.handle_action("MENU")
					break
				app.handle_action(action)
			if running:
				if app.game is None:
					display.draw_menu(app)
				else:
					display.draw(app.game)
				# 题目或答案状态变化时才朗读，同一题不会在多帧里反复念
				key, text = app.speech()
				if key is not None and key != spoken:
					spoken = key
					if text:
						speaker.speak(text)  # 本地 ogg，命中即播、零延迟
				elif key is None:
					spoken = None
				present_frame(screen)
	finally:
		sound.close()
		speaker.close()
		if buttons is not None:
			buttons.cleanup()
		pygame.quit()


if __name__ == "__main__":
	main()
