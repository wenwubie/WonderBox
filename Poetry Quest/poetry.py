"""唐诗宋词三选一答题。"""

from dataclasses import dataclass
import importlib
import json
import os
from pathlib import Path
import random
import sqlite3
import sys

import pygame


ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "Lucky Wheel"))
from common import spi_lcd
from common import ui_theme
from lucky_wheel import GPIOButtons, QUIT_HOLD_SECONDS


DATA_FILE = Path(__file__).resolve().parent / "data" / "poetry.sqlite3"
CHILDREN_DATA_FILE = Path(__file__).resolve().parent / "data" / "children_poetry.json"
MODES = (("儿童诗词", None, False), ("经典名篇", None, True),
		 ("唐诗题库", "唐诗", False), ("宋词题库", "宋词", False),
		 ("混合题库", None, False))
CHILDREN_MODE = next(index for index, (name, _, _) in enumerate(MODES) if name == "儿童诗词")
CLASSIC_MODE = next(index for index, (_, _, classic) in enumerate(MODES) if classic)
QUESTION_KINDS = ("续句", "作者", "作品")
QUESTIONS_PER_GAME = 10


@dataclass(frozen=True)
class Question:
	kind: str
	prompt: str
	choices: tuple[str, str, str]
	answer: int
	explanation: str
	genre: str = ""


def make_question(kind, prompt, answer, alternatives, explanation, rng, genre=""):
	distinct = list(dict.fromkeys(choice for choice in alternatives if choice and choice != answer))
	if not answer or len(distinct) < 2:
		raise ValueError("题目需要一个答案和两个不同的干扰选项")
	choices = [answer, *rng.sample(distinct, 2)]
	rng.shuffle(choices)
	return Question(kind, prompt, tuple(choices), choices.index(answer), explanation, genre)


def make_catalog_question(kind, row, alternatives, rng):
	if kind == "续句":
		prompt, label = "“%s”的下一句是？" % row["stem"], "诗句接龙"
	elif kind == "作者":
		prompt, label = "“%s”是谁写的？" % row["stem"], "辨认作者"
	else:
		label = "辨认词牌" if row["genre"].endswith("词") else "辨认诗题"
		prompt = ("“%s”的词牌是？" if row["genre"].endswith("词")
				  else "“%s”出自哪首诗？") % row["stem"]
	explanation = "%s · 《%s》" % (row["author"], row["title"])
	return make_question(label, prompt, row["answer"], alternatives, explanation, rng, row["genre"])


def make_children_round(works, rng, count=QUESTIONS_PER_GAME):
	if count > len(works):
		raise ValueError("儿童诗词不足以组成一场比赛")
	children_kinds = ("续句", "续句", "续句", "作者", "作品")
	kinds = [children_kinds[index % len(children_kinds)] for index in range(count)]
	rng.shuffle(kinds)
	questions = []
	for kind, work in zip(kinds, rng.sample(works, count)):
		field = {"续句": "following", "作者": "author", "作品": "title"}[kind]
		answer = work[field]
		alternatives = [other[field] for other in works if kind != "作品" or
						other["genre"].endswith("词") == work["genre"].endswith("词")]
		if kind == "续句":
			matching = [option for option in alternatives if len(option) == len(answer)]
			if len(set(matching) - {answer}) >= 2:
				alternatives = matching
		questions.append(make_catalog_question(kind, dict(work, answer=answer), alternatives, rng))
	return questions


class PoetryBank:
	def __init__(self, path=DATA_FILE):
		path = Path(path).resolve()
		if not path.is_file():
			raise FileNotFoundError("诗词题库不存在: " + str(path))
		self.database = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
		self.database.row_factory = sqlite3.Row
		self.ranges = {}
		self.pools = {}
		self.loaded_option_groups = set()
		try:
			self.children_works = json.loads(CHILDREN_DATA_FILE.read_text(encoding="utf-8"))
			self.metadata = dict(self.database.execute("SELECT name, value FROM metadata"))
			self.work_counts = dict(self.database.execute("SELECT genre, COUNT(*) FROM works GROUP BY genre"))
		except Exception:
			self.database.close()
			raise

	def close(self):
		self.database.close()

	def filters(self, mode, kind):
		_, genre, classic = MODES[mode]
		conditions, parameters = ["kind = ?"], [kind]
		if genre:
			conditions.append("genre = ?")
			parameters.append(genre)
		if classic:
			conditions.append("classic = 1")
		return " AND ".join(conditions), parameters

	def option_pool(self, kind, genre, classic_only, length):
		group = (kind, genre, classic_only)
		if group not in self.loaded_option_groups:
			query = "SELECT answer FROM options WHERE kind = ? AND genre = ?"
			parameters = [kind, genre]
			if classic_only:
				query += " AND classic = 1"
			for row in self.database.execute(query, parameters):
				answer = row[0]
				self.pools.setdefault((*group, None), []).append(answer)
				if kind == "续句":
					self.pools.setdefault((*group, len(answer)), []).append(answer)
			self.loaded_option_groups.add(group)
		return self.pools.get((*group, length), ())

	def question(self, mode, kind, rng, used):
		where, parameters = self.filters(mode, kind)
		key = (mode, kind)
		if key not in self.ranges:
			bounds = self.database.execute("SELECT MIN(id), MAX(id) FROM questions WHERE " + where,
										   parameters).fetchone()
			self.ranges[key] = tuple(bounds)
		minimum, maximum = self.ranges[key]
		if minimum is None:
			raise ValueError("所选范围没有可用题目")
		_, _, classic = MODES[mode]
		for _ in range(256):
			target = rng.randint(minimum, maximum)
			row = self.database.execute(
				"SELECT q.genre, q.kind, q.stem, q.answer, w.author, w.title "
				"FROM questions AS q JOIN works AS w ON w.id = q.work_id "
				"WHERE q.id = (SELECT id FROM questions WHERE " + where +
				" AND id >= ? ORDER BY id LIMIT 1)", (*parameters, target)).fetchone()
			if row is None or row["stem"] in used:
				continue
			length = len(row["answer"]) if kind == "续句" else None
			pool = self.option_pool(kind, row["genre"], classic, length)
			if len(pool) < 3:
				pool = self.option_pool(kind, row["genre"], False, length)
			if len(pool) < 3:
				pool = self.option_pool(kind, row["genre"], False, None)
			if len(pool) < 3:
				continue
			alternatives = rng.sample(pool, min(12, len(pool)))
			question = make_catalog_question(kind, row, alternatives, rng)
			used.add(row["stem"])
			return question
		raise ValueError("无法生成足够的不重复题目")

	def make_round(self, mode, rng, count=QUESTIONS_PER_GAME):
		if mode == CHILDREN_MODE:
			return make_children_round(self.children_works, rng, count)
		kinds = [QUESTION_KINDS[index % len(QUESTION_KINDS)] for index in range(count)]
		rng.shuffle(kinds)
		used = set()
		return [self.question(mode, kind, rng, used) for kind in kinds]


class PoetryGame:
	def __init__(self, bank, rng=None):
		self.bank = bank
		self.rng = rng if rng is not None else random.Random()
		self.mode = 0
		self.phase = "menu"
		self.questions = []
		self.index = 0
		self.score = 0
		self.selected = None

	@property
	def question(self):
		return self.questions[self.index]

	def start(self):
		self.questions = self.bank.make_round(self.mode, self.rng)
		self.index = 0
		self.score = 0
		self.selected = None
		self.phase = "answer"

	def handle_action(self, action):
		if action == "BACK":
			if self.phase == "menu":
				return "EXIT"
			self.phase = "menu"
			return None
		if self.phase == "menu":
			if action in ("K1", "K2"):
				self.mode = (self.mode + (-1 if action == "K1" else 1)) % len(MODES)
			elif action == "K3":
				self.start()
			elif action and action.startswith("MODE_"):
				index = int(action[5:])
				if 0 <= index < len(MODES):
					self.mode = index
					self.start()
		elif self.phase == "answer" and action in ("K1", "K2", "K3"):
			self.selected = int(action[1:]) - 1
			self.score += self.selected == self.question.answer
			self.phase = "feedback"
		elif self.phase == "feedback" and action == "K3":
			if self.index + 1 == len(self.questions):
				self.phase = "summary"
			else:
				self.index += 1
				self.selected = None
				self.phase = "answer"
		elif self.phase == "summary":
			if action == "K1":
				self.phase = "menu"
			elif action == "K3":
				self.start()
		return None


_st = ui_theme.style()  # 全局界面风格
BACKGROUND = _st["bg"]
PAPER = _st["panel"]
INK = _st["text"]
MUTED = _st["sub"]
JADE = _st["accent"]
CORAL = (193, 81, 69)   # 固定暖色(错误/退出)
GOLD = (218, 164, 64)   # 固定金色(奖励)
LINE = _st["deco"]
DISABLED_BG = tuple((a + b) // 2 for a, b in zip(_st["bg"], _st["panel"]))
DISABLED_TEXT = _st["sub"]
BUTTON_COLORS = ((CORAL, PAPER), (JADE, PAPER), (GOLD, INK))


def wrap_text(text, font, max_width):
	lines, line = [], ""
	for character in text:
		if character == "\n":
			lines.append(line)
			line = ""
		elif line and font.size(line + character)[0] > max_width:
			if character in "，。！？；：、”》" and len(line) > 1:
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


class PoetryDisplay:
	def __init__(self, screen):
		self.screen = screen
		self.width, self.height = screen.get_size()
		self.portrait = self.height > self.width
		self.title_font = spi_lcd.load_font(20 if self.portrait else 18)
		self.mode_font = spi_lcd.load_font(15)
		self.small_font = spi_lcd.load_font(11)
		self.button_font = spi_lcd.load_font(12)
		self.score_font = spi_lcd.load_font(42)
		self.body_fonts = [spi_lcd.load_font(size) for size in (16, 15, 14, 13, 12, 11, 10)]
		self.option_fonts = [spi_lcd.load_font(size) for size in (15, 14, 13, 12, 11, 10)]
		self.footer_top = self.height - 27
		self.buttons = [pygame.Rect(index * self.width // 3, self.footer_top,
									(index + 1) * self.width // 3 - index * self.width // 3, 27)
						for index in range(3)]
		if self.portrait:
			self.modes = [pygame.Rect(12, 65 + index * 45, self.width - 24, 38)
						  for index in range(len(MODES))]
			self.prompt_rect = pygame.Rect(10, 52, self.width - 20, 72)
			self.options = [pygame.Rect(12, 132 + index * 43, self.width - 24, 36)
							for index in range(3)]
			self.feedback_rect = pygame.Rect(12, 262, self.width - 24, 27)
		else:
			mode_width = (self.width - 30) // 2
			self.modes = [pygame.Rect(10 + (index % 2) * (mode_width + 10),
									  53 + (index // 2) * 50, mode_width, 42)
						  for index in range(len(MODES))]
			self.prompt_rect = pygame.Rect(10, 48, 139, 131)
			self.options = [pygame.Rect(157, 48 + index * 46, self.width - 167, 40)
							for index in range(3)]
			self.feedback_rect = pygame.Rect(10, 184, self.width - 20, 27)

	def text(self, value, font, color, position):
		image = font.render(value, True, color)
		self.screen.blit(image, position)

	def centered(self, value, font, color, center):
		image = font.render(value, True, color)
		self.screen.blit(image, image.get_rect(center=center))

	def fit_one_line(self, text, fonts, width):
		for font in fonts:
			if font.size(text)[0] <= width:
				return font, text
		font = fonts[-1]
		while text and font.size(text + "…")[0] > width:
			text = text[:-1]
		return font, text + "…"

	def layout_prompt(self, text, rect):
		for font in self.body_fonts:
			lines = wrap_text(text, font, rect.width)
			if len(lines) * font.get_linesize() <= rect.height:
				return font, lines
		font = self.body_fonts[-1]
		return font, wrap_text(text, font, rect.width)[:max(1, rect.height // font.get_linesize())]

	def draw_header(self, game):
		self.text("诗词大赛", self.title_font, INK, (10, 7))
		if game is not None and game.phase in ("answer", "feedback"):
			status = "%d / %d" % (game.index + 1, len(game.questions))
		elif game is not None and game.phase == "summary":
			status = MODES[game.mode][0]
		else:
			status = "中华诗词"
		image = self.small_font.render(status, True, JADE)
		self.screen.blit(image, (self.width - image.get_width() - 10, 14))
		pygame.draw.line(self.screen, LINE, (10, 36), (self.width - 10, 36))

	def draw_footer(self, labels, enabled):
		pygame.draw.rect(self.screen, (218, 237, 227), (0, self.footer_top, self.width, 27))
		for index, (label, rect) in enumerate(zip(labels, self.buttons)):
			inset = rect.inflate(-5, -6)
			color, text_color = BUTTON_COLORS[index] if enabled[index] else (DISABLED_BG, DISABLED_TEXT)
			text_color = ui_theme.pick(color, text_color)
			pygame.draw.rect(self.screen, color, inset, border_radius=4)
			self.centered(label, self.button_font, text_color, inset.center)

	def draw_menu(self, game):
		metadata = game.bank.metadata
		counts = []
		for index, (_, genre, classic) in enumerate(MODES):
			if index == CHILDREN_MODE:
				counts.append(len(game.bank.children_works))
			elif classic:
				counts.append(int(metadata.get("classic_works", 0)))
			elif genre:
				counts.append(game.bank.work_counts.get(genre, 0))
			else:
				counts.append(int(metadata.get("works", 0)))
		for index, ((label, _, _), rect) in enumerate(zip(MODES, self.modes)):
			selected = index == game.mode
			fill = (218, 241, 226) if selected else PAPER
			pygame.draw.rect(self.screen, fill, rect, border_radius=6)
			pygame.draw.rect(self.screen, JADE if selected else LINE, rect, 2 if selected else 1, border_radius=6)
			pygame.draw.rect(self.screen, (JADE, CORAL, GOLD, (95, 137, 172), (112, 155, 83))[index],
							 (rect.x + 9, rect.y + 9, 5, rect.height - 18), border_radius=2)
			image = self.mode_font.render(label, True, ui_theme.pick(fill, INK))
			self.screen.blit(image, image.get_rect(midleft=(rect.x + 22, rect.centery)))
			count = self.small_font.render("%d 首" % counts[index], True, ui_theme.pick(fill, MUTED))
			self.screen.blit(count, count.get_rect(midright=(rect.right - 10, rect.centery)))
		self.draw_footer(("上一项", "下一项", "开始"), (True, True, True))

	def draw_question(self, game):
		question = game.question
		rect = self.prompt_rect
		pygame.draw.rect(self.screen, PAPER, rect, border_radius=6)
		pygame.draw.rect(self.screen, LINE, rect, 1, border_radius=6)
		self.text(question.genre + " · " + question.kind, self.small_font, JADE, (rect.x + 9, rect.y + 7))
		prompt_area = pygame.Rect(rect.x + 9, rect.y + 26, rect.width - 18, rect.height - 30)
		font, lines = self.layout_prompt(question.prompt, prompt_area)
		for index, line in enumerate(lines):
			self.text(line, font, INK, (prompt_area.x, prompt_area.y + index * font.get_linesize()))

		for index, option_rect in enumerate(self.options):
			correct = game.phase == "feedback" and index == question.answer
			incorrect = game.phase == "feedback" and index == game.selected and not correct
			color = (216, 241, 224) if correct else (252, 224, 218) if incorrect else PAPER
			border = JADE if correct else CORAL if incorrect else LINE
			pygame.draw.rect(self.screen, color, option_rect, border_radius=6)
			pygame.draw.rect(self.screen, border, option_rect, 2 if correct or incorrect else 1, border_radius=6)
			marker = pygame.Rect(option_rect.x + 7, option_rect.centery - 10, 20, 20)
			marker_color, marker_text = BUTTON_COLORS[index]
			marker_text = ui_theme.pick(marker_color, marker_text)
			pygame.draw.rect(self.screen, marker_color, marker, border_radius=4)
			self.centered(str(index + 1), self.button_font, marker_text, marker.center)
			font, label = self.fit_one_line(question.choices[index], self.option_fonts, option_rect.width - 38)
			image = font.render(label, True, ui_theme.pick(color, INK))
			self.screen.blit(image, image.get_rect(midleft=(option_rect.x + 33, option_rect.centery)))

		if game.phase == "feedback":
			feedback = "回答正确" if game.selected == question.answer else "正确答案：" + question.choices[question.answer]
			for index, text in enumerate((feedback, question.explanation)):
				font, text = self.fit_one_line(text, (self.small_font,), self.feedback_rect.width)
				self.text(text, font, JADE if index == 0 and game.selected == question.answer else INK,
						  (self.feedback_rect.x, self.feedback_rect.y + index * font.get_linesize()))
			self.draw_footer(("选1", "选2", "成绩" if game.index + 1 == len(game.questions) else "下一题"),
							 (False, False, True))
		else:
			self.draw_footer(("选1", "选2", "选3"), (True, True, True))

	def draw_summary(self, game):
		center = self.width // 2
		self.centered("本场成绩", self.mode_font, INK, (center, 67))
		self.centered("%d / %d" % (game.score, len(game.questions)), self.score_font, JADE,
					  (center, 122 if self.portrait else 108))
		self.centered(MODES[game.mode][0], self.small_font, MUTED,
					  (center, 166 if self.portrait else 150))
		self.draw_footer(("菜单", "无功能", "再玩"), (True, False, True))

	def draw_error(self):
		self.screen.fill(BACKGROUND)
		self.draw_header(None)
		self.centered("诗词题库不可用", self.mode_font, CORAL, (self.width // 2, self.height // 2 - 20))
		self.centered("请检查诗词数据文件", self.small_font, INK, (self.width // 2, self.height // 2 + 5))
		self.draw_footer(("无功能", "无功能", "返回"), (False, False, True))

	def draw(self, game):
		self.screen.fill(BACKGROUND)
		self.draw_header(game)
		if game.phase == "menu":
			self.draw_menu(game)
		elif game.phase in ("answer", "feedback"):
			self.draw_question(game)
		else:
			self.draw_summary(game)


def event_action(event, display, game):
	if event.type == pygame.QUIT:
		return "EXIT"
	if event.type == pygame.KEYDOWN:
		if event.key in (pygame.K_ESCAPE, pygame.K_q):
			return "EXIT"
		if event.key == pygame.K_BACKSPACE:
			return "BACK"
		return {pygame.K_1: "K1", pygame.K_2: "K2", pygame.K_3: "K3",
				pygame.K_KP1: "K1", pygame.K_KP2: "K2", pygame.K_KP3: "K3"}.get(event.key)
	position = spi_lcd.mouse_position(event)
	if position is None:
		return None
	for action, rect in zip(("K1", "K2", "K3"), display.buttons):
		if rect.collidepoint(position):
			return action
	if game is not None and game.phase == "menu":
		for index, rect in enumerate(display.modes):
			if rect.collidepoint(position):
				return "MODE_%d" % index
	elif game is not None and game.phase == "answer":
		for index, rect in enumerate(display.options):
			if rect.collidepoint(position):
				return "K%d" % (index + 1)
	return None


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
	buttons, bank = None, None
	try:
		if spi_lcd.is_simulate():
			pygame.display.set_caption("诗词大赛")
		else:
			try:
				buttons = GPIOButtons(importlib.import_module("RPi.GPIO"))
			except Exception as error:
				raise RuntimeError("GPIO 初始化失败，请检查 RPi.GPIO 和按键连接。") from error
		display = PoetryDisplay(screen)
		try:
			bank = PoetryBank()
			game = PoetryGame(bank)
		except (OSError, sqlite3.Error, ValueError) as error:
			print("诗词题库不可用:", error)
			game = None
		hold = spi_lcd.SimulatedHold("K3", "BACK", QUIT_HOLD_SECONDS)
		clock = pygame.time.Clock()
		running = True
		print("诗词大赛已启动：K1/K2/K3 选择，长按 K3 返回。")
		while running:
			clock.tick(30)
			if buttons is None:
				actions = [hold.process_event(event, event_action(event, display, game))
						   for event in pygame.event.get()]
				actions.append(hold.poll())
			else:
				actions = ["BACK" if action == "QUIT" else action for action in buttons.poll()]
			for action in actions:
				if action == "EXIT" or (game is None and action in ("BACK", "K3")):
					running = False
					break
				if game is not None and action:
					previous_phase = game.phase
					try:
						if game.handle_action(action) == "EXIT":
							running = False
							break
					except (sqlite3.Error, ValueError) as error:
						print("诗词题库读取失败:", error)
						game = None
						break
					if game.phase != previous_phase:
						break
			if not running:
				break
			if game is None:
				display.draw_error()
			else:
				display.draw(game)
			if not spi_lcd.present(poll_events=False):
				break
	finally:
		if bank is not None:
			bank.close()
		if buttons is not None:
			buttons.cleanup()
		pygame.quit()


if __name__ == "__main__":
	main()
