"""Offline Werewolf moderator console."""

import math
import os
from pathlib import Path
import random
import sys
import time

import pygame

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import spi_lcd
from common.button_input import GPIOButtons, QUIT_HOLD_SECONDS


ROLE_NAMES = {"wolf": "狼人", "seer": "预言家", "witch": "女巫",
			  "guard": "守卫", "villager": "村民"}
ROLE_SKILLS = {
	"wolf": "每晚与狼队选择一名袭击目标",
	"seer": "每晚查验一名玩家的阵营",
	"witch": "解药救人，毒药淘汰，各限一次",
	"guard": "每晚守护一人，防止狼袭",
	"villager": "无夜间技能，白天讨论和投票",
}
BOARDS = {
	6: (2, 1, 0, 0, 3), 7: (2, 1, 1, 0, 3), 8: (2, 1, 1, 1, 3),
	9: (3, 1, 1, 1, 3), 10: (3, 1, 1, 1, 4),
	11: (3, 1, 1, 1, 5), 12: (4, 1, 1, 1, 5),
}
REVEAL_SECONDS = 3
MIN_REVEAL_SECONDS = 1
MAX_REVEAL_SECONDS = 10
SETUP_DURATION_INDEX = len(ROLE_NAMES) + 1
SETUP_CONFIRM_INDEX = len(ROLE_NAMES) + 2
WOLF_SECONDS = 10
NIGHT_ACTIONS = {"狼人请睁眼": "wolf", "预言家请睁眼": "seer",
				 "守卫请睁眼": "guard", "女巫请睁眼": "save", "女巫：确认用毒": "poison"}
ACTION_NAMES = {"wolf": "狼袭", "guard": "守护", "seer": "查验", "save": "解药", "poison": "毒药"}
NIGHT_ROLES = (
	("guard", (
		("守卫请睁眼", ("守卫请睁眼，指定守护目标。",),
			 ("按 K3 标记确认守护目标。", "不能守自己。")),
	)),
	("wolf", (
		("狼人请睁眼", ("狼人请睁眼，共同指定袭击目标。",),
		 ("全队一致后按 K3 标记目标。", "10 秒内未确认则空刀。")),
	)),
	("seer", (
		("预言家请睁眼", ("预言家请睁眼，指定查验对象。",),
		 ("按 K1 登记查验对象并查看阵营。", "只向预言家比手势，不要出声。",
		  "拇指向上＝好人，向下＝狼人。")),
	)),
	("witch", (
		("女巫请睁眼", ("女巫请睁眼，是否救狼袭目标？",),
			 ("有解药时，静默指出狼袭目标。", "首夜可自救；之后不能自救。",
		  "女巫拇指向上＝救；摇头＝不救。", "按 K1 查看药量并登记。")),
		("女巫：确认用毒", ("女巫请指定毒杀目标。",),
		 ("已救人或已用毒：不念，直接继续。", "指向一名其他存活玩家＝用毒。",
		  "摇头＝不用。", "按 K1 查看药量并登记。")),
	)),
)


class WerewolfGame:
	def __init__(self, rng=None, clock=time.monotonic):
		self.rng = rng if rng is not None else random.SystemRandom()
		self.clock = clock
		self.reveal_seconds = REVEAL_SECONDS
		self.preset = min(BOARDS)
		self.lineup = dict(zip(ROLE_NAMES, BOARDS[self.preset]))
		self.reset()

	def reset(self):
		self.phase = "setup"
		self.setup_index = 0
		self.editing_lineup = False
		self.roles = []
		self.player = 1
		self.deadline = 0
		self.round = 0
		self.alive = set()
		self.history = []
		self.pending = set()
		self.index = 0
		self.cues = []
		self.night_records = {}
		self.round_history = {}
		self.wolf_deadline = None
		self.record_index = 0
		self.record_advances = False
		self.log_round = 0
		self.interrupted_phase = None
		self.interrupt_started = None
		self.winner = None
		self.last_words_player = None

	@property
	def count(self):
		return sum(self.lineup.values())

	@property
	def lineup_error(self):
		if not min(BOARDS) <= self.count <= max(BOARDS):
			return "总人数须为 6 至 12 人"
		if not 0 < self.lineup["wolf"] < self.count - self.lineup["wolf"]:
			return "至少 1 名狼人，且狼人少于好人"
		return ""

	def configure(self, action, step):
		confirm = SETUP_CONFIRM_INDEX
		if action == f"SETUP_{confirm}" and self.editing_lineup and self.setup_index != 0:
			self.editing_lineup = False
		if self.editing_lineup:
			if action == "K3":
				if self.setup_index == 0:
					self.lineup = dict(zip(ROLE_NAMES, BOARDS[self.preset]))
				self.editing_lineup = False
			elif step and self.setup_index == 0:
				self.preset = max(min(BOARDS), min(max(BOARDS), self.preset + step))
			elif step and self.setup_index == SETUP_DURATION_INDEX:
				self.reveal_seconds = max(MIN_REVEAL_SECONDS,
								  min(MAX_REVEAL_SECONDS, self.reveal_seconds + step))
			elif step:
				role = tuple(ROLE_NAMES)[self.setup_index - 1]
				self.lineup[role] = max(0, min(max(BOARDS), self.lineup[role] + step))
			return
		if step:
			self.setup_index = (self.setup_index + step) % (confirm + 1)
			return
		if action and action.startswith("SETUP_"):
			self.setup_index = int(action.removeprefix("SETUP_"))
			action = "K3"
		if action == "K3":
			if self.setup_index != confirm:
				self.editing_lineup = True
			elif not self.lineup_error:
				self.roles = [role for role, count in self.lineup.items() for _ in range(count)]
				self.rng.shuffle(self.roles)
				self.alive = set(range(1, self.count + 1))
				self.phase = "draw"

	@property
	def revealed_role(self):
		if self.phase == "reveal" and self.clock() < self.deadline:
			return self.roles[self.player - 1]
		return None

	@property
	def choices(self):
		return sorted(self.alive) + [None]

	def tick(self):
		if self.phase == "reveal" and self.clock() >= self.deadline:
			self.player += 1
			self.phase = "handoff" if self.player > self.count else "draw"

	def start_night(self):
		self.round += 1
		self.phase = "night"
		self.index = 0
		self.last_words_player = None
		self.night_records[self.round] = {}
		self.round_history.setdefault(self.round, {})
		self.wolf_deadline = None
		self.record_advances = False
		self.cues = [("天黑请闭眼", ("天黑请闭眼，保持安静。", "请只向主持人做手势，不出声。"),
					  ("出局玩家不再睁眼或行动。", "同身份多人共选目标、共享次数。", "行动结果先记下，天亮统一登记。"))]
		living_roles = {self.roles[player - 1] for player in self.alive}
		for role, instructions in NIGHT_ROLES:
			if role in living_roles:
				if role == "witch" and self.previous_dose("save") and self.previous_dose("poison"):
					continue
				self.cues.extend(instructions)
				close = ROLE_NAMES[role] + "请闭眼"
				self.cues.append((close, (close + "。",), ("确认闭眼后继续。",)))
		self.cues.append(("天亮请睁眼", ("天亮了，所有玩家请睁眼。",),
						  ("狼袭被守护或解药抵消：不出局。", "毒药目标出局，不受守护影响。",
						   "死亡名单已按行动自动计算。", "核对后继续，只公布出局号码。")))

	@property
	def night_action(self):
		return NIGHT_ACTIONS.get(self.cues[self.index][0])

	@property
	def night_record(self):
		return self.night_records[self.round]

	@property
	def wolf_seconds(self):
		return max(0, math.ceil(self.wolf_deadline - self.clock())) if self.wolf_deadline is not None else 0

	def move_night(self, index):
		self.index = index
		if self.night_action == "wolf" and self.wolf_deadline is None:
			self.wolf_deadline = self.clock() + WOLF_SECONDS

	def previous_dose(self, action):
		return next(((round_number, targets[action]) for round_number, targets in self.night_records.items()
					 if round_number < self.round and targets.get(action)), None)

	def record_targets(self):
		action = self.night_action
		if action == "wolf":
			if action in self.night_record:
				return []
			return sorted(self.alive)
		if action == "guard":
			guard = next((player for player in sorted(self.alive)
						  if self.roles[player - 1] == "guard"), None)
			return [player for player in sorted(self.alive) if player != guard]
		if action == "seer":
			return [player for player in sorted(self.alive) if self.roles[player - 1] != "seer"]
		if self.previous_dose(action):
			return []
		other = "poison" if action == "save" else "save"
		if self.night_record.get(other):
			return []
		if action == "save":
			target = self.night_record.get("wolf")
			can_save_self = self.round == 1
			return [target] if target in self.alive and (can_save_self or self.roles[target - 1] != "witch") else []
		return [player for player in sorted(self.alive) if self.roles[player - 1] != "witch"]

	def recorded_result(self, kind, round_number):
		record = self.night_records[round_number]
		target = record.get(kind)
		if target:
			result = f"{target}号"
			if kind == "seer":
				result += " · 狼人" if self.roles[target - 1] == "wolf" else " · 好人"
			return result
		if kind == "wolf" and kind in record:
			return "空刀"
		return "未使用" if kind in ("save", "poison") else "未登记"

	def handle_night_record(self, action, step):
		kind = self.night_action
		choices = [None, *self.record_targets()]
		if step:
			self.record_index = (self.record_index + step) % len(choices)
		elif action and action.startswith("RECORD_"):
			player = int(action.removeprefix("RECORD_")) or None
			if player in choices:
				self.record_index = choices.index(player)
		elif action == "K3":
			if self.record_index < len(choices) and (len(choices) > 1 or kind in ("wolf", "guard", "seer")):
				self.night_record[kind] = choices[self.record_index]
			self.phase = "night"
			if self.record_advances:
				self.record_advances = False
				self.move_night(self.index + 1)

	def enter_deaths(self, phase):
		self.phase = phase
		self.pending.clear()
		self.index = 0

	def resolve_night_deaths(self):
		record = self.night_record
		wolf_target = record.get("wolf")
		guard_target = record.get("guard")
		saved_target = record.get("save")
		deaths = set()
		if wolf_target in self.alive and wolf_target != guard_target and wolf_target != saved_target:
			deaths.add(wolf_target)
		poison_target = record.get("poison")
		if poison_target in self.alive:
			deaths.add(poison_target)
		self.pending = deaths
		self.phase = "night_deaths"
		self.index = len(self.alive)

	def night_death_reasons(self):
		record = self.night_record
		reasons = {}
		wolf_target = record.get("wolf")
		if (wolf_target in self.pending and wolf_target != record.get("guard")
				and wolf_target != record.get("save")):
			reasons[wolf_target] = "狼袭"
		poison_target = record.get("poison")
		if poison_target in self.pending:
			reasons[poison_target] = "狼袭、毒杀" if poison_target in reasons else "毒杀"
		return reasons

	def confirm_deaths(self):
		phase = self.phase
		deaths = tuple(sorted(self.pending))
		self.alive.difference_update(self.pending)
		self.history.append((self.round, phase, deaths))
		record = self.round_history.setdefault(self.round, {})
		record[phase] = deaths
		record["actions"] = dict(self.night_records.get(self.round, {}))
		record["alive"] = tuple(sorted(self.alive))
		self.pending.clear()
		wolves = sum(self.roles[player - 1] == "wolf" for player in self.alive)
		if wolves == 0:
			self.winner = "good"
		elif wolves >= len(self.alive) - wolves:
			self.winner = "wolf"
		if phase == "vote_deaths" and deaths:
			self.last_words_player = deaths[0]
			self.phase = "last_words"
			return
		if self.winner:
			self.phase = "finished"
		elif self.phase == "night_deaths":
			self.phase = "discuss"
		else:
			self.start_night()

	def handle(self, action):
		phase = self.phase
		step = {"K1": -1, "K2": 1}.get(action, 0)
		if action == "EXIT":
			return "EXIT"
		if action == "BACK":
			if phase == "setup" and self.editing_lineup:
				if self.setup_index == 0:
					self.editing_lineup = False
				return None
			if phase == "interrupt_confirm":
				self.cancel_interrupt()
				return None
			if phase != "setup":
				self.interrupted_phase = phase
				self.interrupt_started = self.clock()
				self.phase = "interrupt_confirm"
			return None

		if phase == "interrupt_confirm":
			if action in ("K1", "K2"):
				self.cancel_interrupt()
			elif action == "K3":
				self.reset()
		elif phase == "setup":
			self.configure(action, step)
		elif phase == "draw" and action == "K3":
			self.deadline = self.clock() + self.reveal_seconds
			self.phase = "reveal"
		elif phase == "handoff" and action == "K3":
			self.start_night()
		elif phase == "night":
			if action == "K1":
				self.phase = "roster"
			elif action == "K2":
				self.log_round = self.round
				self.phase = "night_log"
			elif action == "K3":
				if (self.night_action in ("save", "poison")
						and not self.record_targets()):
					self.move_night(self.index + 1)
				elif self.night_action:
					self.record_advances = True
					self.record_index = 0
					self.phase = "night_record"
				elif self.index == len(self.cues) - 1:
					self.resolve_night_deaths()
				else:
					self.move_night(self.index + 1)
		elif phase == "night_record":
			self.handle_night_record(action, step)
		elif phase == "roster":
			if action == "K3":
				self.phase = "night"
			elif action == "K1":
				self.phase = "roster"
			elif action == "K2":
				self.log_round = self.round
				self.phase = "night_log"
		elif phase == "night_log":
			if action == "K1":
				self.phase = "roster"
			elif action == "K2":
				self.phase = "night_log"
			elif action == "K3":
				self.phase = "night"
		elif phase == "round_summary":
			if step:
				self.log_round = max(1, min(self.round, self.log_round + step))
			elif action == "K3":
				self.phase = "finished"
		elif phase == "last_words" and action == "K3":
			if self.winner:
				self.phase = "finished"
			else:
				self.start_night()
		elif phase in ("night_deaths", "vote_deaths"):
			choices = self.choices
			if step:
				self.index = (self.index + step) % len(choices)
			elif action == "DEATH_CONFIRM":
				self.confirm_deaths()
			elif action and action.startswith("DEATH_"):
				player = int(action.removeprefix("DEATH_"))
				if player in self.alive:
					self.index = choices.index(player)
					if phase != "vote_deaths" or player in self.pending or not self.pending:
						self.pending.symmetric_difference_update({player})
			elif action == "K3":
				player = choices[self.index]
				if player is None:
					self.confirm_deaths()
				elif phase != "vote_deaths" or player in self.pending or not self.pending:
					self.pending.symmetric_difference_update({player})
		elif phase == "discuss" and action == "K3":
			self.phase = "vote"
		elif phase == "vote" and action == "K3":
			self.enter_deaths("vote_deaths")
		elif phase == "finished":
			if action == "K1":
				self.log_round = 1
				self.phase = "round_summary"
			elif action == "K3":
				self.reset()
		return None

	def cancel_interrupt(self):
		elapsed = self.clock() - self.interrupt_started
		if self.interrupted_phase == "reveal":
			self.deadline += elapsed
		if self.wolf_deadline is not None and "wolf" not in self.night_record:
			self.wolf_deadline += elapsed
		self.phase = self.interrupted_phase
		self.interrupted_phase = None
		self.interrupt_started = None


class WerewolfDisplay:
	BG = (24, 34, 32)
	PANEL = (39, 54, 48)
	PAPER = (250, 243, 218)
	MUTED = (190, 207, 195)
	GOLD = (251, 204, 117)
	RED = (255, 158, 144)

	def __init__(self, screen):
		self.screen = screen
		self.width, self.height = screen.get_size()
		self.fonts = {size: spi_lcd.load_font(size) for size in (9, 10, 12, 14, 17, 26, 34)}
		edges = [8 + index * (self.width - 16) // 3 for index in range(4)]
		self.buttons = [pygame.Rect(edges[index] + 2, self.height - 42,
									edges[index + 1] - edges[index] - 4, 34)
						for index in range(3)]
		self.labels = ("", "", "")
		self.setup_rows = []
		self.death_rows = {}

	def text(self, value, size, color, y, x=None):
		font = self.fonts[size]
		limit = self.width - 32
		if font.size(value)[0] > limit:
			for smaller in reversed(tuple(self.fonts)):
				if smaller < size and self.fonts[smaller].size(value)[0] <= limit:
					font = self.fonts[smaller]
					break
		image = font.render(value, True, color)
		self.screen.blit(image, image.get_rect(center=(self.width // 2 if x is None else x, y)))

	def moon(self):
		center = (self.width - 27, 24)
		pygame.draw.circle(self.screen, self.GOLD, center, 11)
		pygame.draw.circle(self.screen, self.BG, (center[0] + 5, center[1] - 4), 9)
		pygame.draw.circle(self.screen, self.MUTED, (center[0] - 15, center[1] - 9), 2)

	def role_icon(self, role, center, size):
		colors = {"wolf": self.RED, "seer": (199, 178, 246), "witch": (150, 223, 181),
				  "guard": (161, 206, 251), "villager": self.GOLD}
		color = colors[role]
		pygame.draw.circle(self.screen, self.PANEL, center, size)
		def point(x, y):
			return center[0] + round(x * size / 10), center[1] + round(y * size / 10)

		def polygon(points, ink=color):
			pygame.draw.polygon(self.screen, ink, [point(*pair) for pair in points])

		if role == "wolf":
			polygon(((-7, -7), (-2, -4), (2, -4), (7, -7), (6, 2), (0, 7), (-6, 2)))
			for offset in (-3, 3):
				pygame.draw.circle(self.screen, self.BG, point(offset, 0), max(1, size // 9))
		elif role == "seer":
			polygon(((-8, 0), (-4, -4), (4, -4), (8, 0), (4, 4), (-4, 4)))
			pygame.draw.circle(self.screen, self.BG, center, max(1, size // 4))
		elif role == "witch":
			polygon(((-3, -7), (3, -7), (2, -5), (2, -2), (6, 3), (4, 7),
					 (-4, 7), (-6, 3), (-2, -2), (-2, -5)))
			pygame.draw.line(self.screen, self.BG, point(-3, 3), point(3, 3), max(1, size // 9))
		elif role == "guard":
			polygon(((-6, -6), (0, -7), (6, -6), (5, 2), (0, 7), (-5, 2)))
			pygame.draw.line(self.screen, self.BG, point(0, -5), point(0, 4), max(1, size // 9))
		else:
			polygon(((-7, 0), (0, -7), (7, 0), (5, 0), (5, 6), (-5, 6), (-5, 0)))
			pygame.draw.line(self.screen, self.BG, point(0, 6), point(0, 2), max(1, size // 6))

	def draw_setup(self, game):
		preview = game.editing_lineup and game.setup_index == 0
		counts = BOARDS[game.preset] if preview else game.lineup.values()
		self.text(f"{'推荐' if preview else '合计'} {sum(counts)} 人", 14, self.GOLD, 24)
		rows = [("推荐配板", f"{game.preset} 人", None)]
		rows.extend((name, str(count), role) for (role, name), count in zip(ROLE_NAMES.items(), counts))
		rows.append(("身份显示", f"{game.reveal_seconds} 秒", None))
		rows.append(("确认开局", "", None))
		row_height = min(28, (self.height - 114) // len(rows))
		top = 45 + max(0, (self.height - 114 - row_height * len(rows)) // 2)
		for index, (name, value, role) in enumerate(rows):
			rect = pygame.Rect(10, top + index * row_height, self.width - 20, row_height - 1)
			self.setup_rows.append(rect)
			selected = index == game.setup_index
			if selected:
				pygame.draw.rect(self.screen, self.PANEL, rect, border_radius=5)
				pygame.draw.rect(self.screen, self.GOLD, rect, 1, border_radius=5)
			if role:
				self.role_icon(role, (29, rect.centery), min(11, rect.height // 2))
			color = self.GOLD if selected else self.PAPER
			self.text(name, 14, color, rect.centery, 81)
			if value:
				if selected and game.editing_lineup:
					value = (f"-   {game.reveal_seconds}秒   +" if index == SETUP_DURATION_INDEX
							 else f"-   {value}   +")
				self.text(value, 14, color, rect.centery, rect.right - 42)
		if not preview and game.lineup_error:
			self.text(game.lineup_error, 14, self.RED, self.height - 54)
		if preview:
			return ("减一人", "加一人", "应用推荐")
		if game.editing_lineup:
			return ("减少", "增加", "完成")
		command = ("" if game.lineup_error else "开局") if game.setup_index == len(rows) - 1 else "调整"
		return ("上一项", "下一项", command)

	def player_grid(self, count, bottom):
		top = 47
		row_count = (count + 1) // 2
		row_height = min(32, (bottom - top) // row_count)
		width = (self.width - 26) // 2
		for index in range(count):
			row, column = divmod(index, 2)
			yield pygame.Rect(10 + column * (width + 6), top + row * row_height, width, row_height - 1)

	def draw_death_list(self, game):
		title = "夜间阵亡" if game.phase == "night_deaths" else "白天放逐"
		self.text(f"第{game.round}轮 · {title} · 主持人", 14, self.GOLD, 24)
		death_reasons = game.night_death_reasons() if game.phase == "night_deaths" else {}
		action_labels = {"wolf": "狼袭", "guard": "守护", "seer": "查验",
					 "save": "解药", "poison": "毒药"}
		actions_by_player = {}
		if game.phase == "night_deaths":
			for action, label in action_labels.items():
				player = game.night_record.get(action)
				if player:
					actions_by_player.setdefault(player, []).append(label)
		current = game.choices[game.index]
		confirm = pygame.Rect(10, self.buttons[2].top - 22, self.width - 20, 18)
		for player, rect in enumerate(self.player_grid(game.count, confirm.top - 2), 1):
			alive = player in game.alive
			marked = player in game.pending
			pygame.draw.rect(self.screen, self.PANEL, rect, border_radius=4)
			if player == current:
				pygame.draw.rect(self.screen, self.GOLD, rect, 1, border_radius=4)
			if alive:
				self.death_rows[f"DEATH_{player}"] = rect
				box = pygame.Rect(rect.left + 6, rect.centery - 5, 10, 10)
				pygame.draw.rect(self.screen, self.RED if marked else self.MUTED, box, 0 if marked else 1)
				if marked:
					pygame.draw.lines(self.screen, self.BG, False,
									  [(box.left + 2, box.top + 5), (box.left + 4, box.top + 7),
									   (box.left + 8, box.top + 2)])
			role = ROLE_NAMES[game.roles[player - 1]]
			name_x = rect.centerx + 7
			self.text(f"{player}号 {role}", 12, self.PAPER if alive else self.MUTED, rect.centery - 6, name_x)
			status = death_reasons.get(player, "已勾选") if marked else "存活" if alive else "已出局"
			actions = actions_by_player.get(player, ())
			if marked and status in actions:
				actions = tuple(action for action in actions if action != status)
			if actions:
				status = f"{status}·{'/'.join(actions)}"
			self.text(status, 9 if actions else 10,
				  self.RED if marked or not alive else self.GOLD if actions else self.MUTED,
				  rect.centery + 6, rect.centerx + 1 if actions else name_x)
		self.death_rows["DEATH_CONFIRM"] = confirm
		pygame.draw.rect(self.screen, self.PANEL, confirm, border_radius=4)
		if current is None:
			pygame.draw.rect(self.screen, self.GOLD, confirm, 1, border_radius=4)
		self.text(f"确认登记 · 已选 {len(game.pending)} 人", 12, self.PAPER, confirm.centery)
		command = "确认" if current is None else "取消勾选" if current in game.pending else "勾选"
		return ("上一项", "下一项", command)

	def draw_roster(self, game):
		finished = game.phase == "finished"
		if finished:
			title = "好人阵营胜利" if game.winner == "good" else "狼人阵营胜利"
		else:
			title = "身份名单 · 主持人"
		self.text(title, 14, self.RED if game.winner == "wolf" else self.GOLD, 24)
		deaths = {player: (round_number, phase) for round_number, phase, players in game.history
				  for player in players}
		for player, (role, rect) in enumerate(zip(game.roles, self.player_grid(game.count, self.height - 44)), 1):
			pygame.draw.rect(self.screen, self.PANEL, rect, border_radius=4)
			self.role_icon(role, (rect.left + 13, rect.centery), 9)
			status, color = "存活", self.MUTED
			if player in deaths:
				round_number, phase = deaths[player]
				cause = "夜间阵亡" if phase == "night_deaths" else "投票放逐"
				status, color = f"第{round_number}轮 {cause}", self.RED
			name_x = rect.centerx + 10
			self.text(f"{player}号 {ROLE_NAMES[role]}", 12, self.PAPER, rect.centery - 6, name_x)
			self.text(status, 10, color, rect.centery + 6, name_x)
		return ("复盘", "", "新一局") if finished else ("身份名单", "夜间记录", "返回")

	def draw_night_record(self, game):
		kind = game.night_action
		self.text(f"{ACTION_NAMES[kind]}登记 · 仅主持人", 14, self.GOLD, 24)
		bottom = self.buttons[2].top
		targets = game.record_targets()
		selected = targets[game.record_index - 1] if 0 < game.record_index <= len(targets) else None
		if targets:
			for player, rect in zip(targets, self.player_grid(len(targets), bottom - 53)):
				pygame.draw.rect(self.screen, self.PANEL, rect, border_radius=4)
				if player == selected:
					pygame.draw.rect(self.screen, self.GOLD, rect, 1, border_radius=4)
				role = ROLE_NAMES[game.roles[player - 1]]
				self.text(f"{player}号 {role}", 12, self.PAPER, rect.centery, rect.centerx)
				self.death_rows[f"RECORD_{player}"] = rect
			clear = pygame.Rect(10, bottom - 51, self.width - 20, 17)
			pygame.draw.rect(self.screen, self.PANEL, clear, border_radius=4)
			if selected is None:
				pygame.draw.rect(self.screen, self.GOLD, clear, 1, border_radius=4)
			self.text("不守护" if kind == "guard" else "不查验" if kind == "seer" else
					  "不用药" if kind in ("save", "poison") else "空刀",
					  12, self.PAPER, clear.centery)
			self.death_rows["RECORD_0"] = clear
		status = f"已登记：{game.recorded_result(kind, game.round)}"
		if kind == "wolf" and kind not in game.night_record:
			status = "请选择狼袭目标或空刀"
		elif kind in ("save", "poison"):
			previous = game.previous_dose(kind)
			if previous:
				round_number, player = previous
				status = f"已用：第{round_number}轮 · {player}号"
			elif not targets and not game.night_record.get(kind):
				status = "本轮不可用 · 药尚未使用"
		if kind == "save" and targets:
			self.text(f"狼袭目标：{targets[0]}号", 12, self.PAPER, bottom - 24)
		elif kind == "seer" and selected:
			alignment = "狼人" if game.roles[selected - 1] == "wolf" else "好人"
			self.text(f"{selected}号 · {alignment}", 12, self.GOLD, bottom - 24)
		self.text(status, 12, self.MUTED, bottom - 10)
		return ("上一项", "下一项", "确认") if targets else ("", "", "返回")

	def draw_night_log(self, game):
		self.text(f"第{game.log_round}轮 · 夜间记录", 17, self.GOLD, 24)
		self.text("仅主持人看 · 不念", 12, self.MUTED, 57)
		for index, (kind, label) in enumerate(ACTION_NAMES.items()):
			self.text(f"{label}：{game.recorded_result(kind, game.log_round)}", 14, self.PAPER, 86 + index * 24)
		return ("身份名单", "夜间记录", "返回")

	def draw_round_summary(self, game):
		record = game.round_history[game.log_round]
		self.text(f"第{game.log_round}轮 · 对局复盘", 17, self.GOLD, 24)
		self.text("仅主持人看 · 不念", 10, self.MUTED, 45)
		result = lambda kind: game.recorded_result(kind, game.log_round)
		self.text(f"守护 {result('guard')} · 狼袭 {result('wolf')} · 查验 {result('seer')}",
				  10, self.PAPER, 62)
		self.text(f"解药 {result('save')} · 毒药 {result('poison')}", 10, self.PAPER, 76)
		night_dead = set(record.get("night_deaths", ()))
		vote_dead = set(record.get("vote_deaths", ()))
		alive = set(record.get("alive", ()))
		top = 88
		bottom = self.buttons[2].top - 2
		row_height = max(1, (bottom - top) // ((game.count + 1) // 2))
		column_width = (self.width - 26) // 2
		for player, role in enumerate(game.roles, 1):
			row, column = divmod(player - 1, 2)
			rect = pygame.Rect(10 + column * (column_width + 6), top + row * row_height,
							  column_width, row_height - 1)
			pygame.draw.rect(self.screen, self.PANEL, rect, border_radius=3)
			if player in night_dead:
				status, color = "夜间出局", self.RED
			elif player in vote_dead:
				status, color = "投票放逐", self.RED
			elif player in alive:
				status, color = "存活", self.MUTED
			else:
				status, color = "此前出局", self.MUTED
			self.text(f"{player}号 {ROLE_NAMES[role]} · {status}", 10, color, rect.centery, rect.centerx)
		return ("上一轮" if game.log_round > 1 else "",
				"下一轮" if game.log_round < game.round else "", "返回结算")

	def draw_script(self, eyebrow, title, spoken, private):
		self.text(eyebrow, 12, self.MUTED, 54)
		self.text(title, 17, self.PAPER, 72)
		y = 91
		for label, lines, color in (("仅主持人看 · 不念", private, self.MUTED),
								  ("请念给玩家听", spoken, self.GOLD)):
			pygame.draw.rect(self.screen, self.PANEL, (10, y - 7, self.width - 20, 14), border_radius=4)
			self.text(label, 12, color, y)
			for line in lines:
				y += 14
				self.text(line, 12, self.PAPER, y)
			y += 17

	def draw(self, game):
		phase = game.phase
		self.screen.fill(self.BG)
		self.moon()
		list_page = phase in ("roster", "finished", "night_deaths", "vote_deaths", "night_record", "night_log",
						  "round_summary")
		if not list_page:
			self.text("狼人杀", 17, self.PAPER, 24, 44)
			if game.round:
				self.text(f"第 {game.round} 轮", 14, self.MUTED, 24)
		pygame.draw.line(self.screen, self.PANEL, (10, 43), (self.width - 10, 43))
		middle = (45 + self.height - 47) // 2
		eyebrow, title, detail, note = "", "", "", ""
		labels = ("", "", "")
		wolves_alive = sum(game.roles[player - 1] == "wolf" for player in game.alive)
		good_alive = len(game.alive) - wolves_alive
		accent = self.GOLD
		role_icon = None
		self.setup_rows.clear()
		self.death_rows.clear()
		if phase == "setup":
			labels = self.draw_setup(game)
		elif phase in ("draw", "reveal"):
			eyebrow = f"身份抽取   {game.player} / {game.count}"
			role = game.revealed_role
			if role is not None:
				role_icon = role
				title = ROLE_NAMES[role]
				accent = self.RED if role == "wolf" else self.GOLD
				detail = "狼人阵营" if role == "wolf" else "好人阵营"
				note = f"{max(0, math.ceil(game.deadline - game.clock()))} 秒后隐藏"
			elif phase == "reveal":
				title = "身份已隐藏"
			else:
				title, labels = f"请 {game.player} 号抽取", ("", "", "抽取")
		elif phase == "handoff":
			eyebrow = f"身份发放完成   {game.count} / {game.count}"
			title, labels = "请交回主持人", ("", "", "开始")
		elif phase == "night":
			title, spoken, private = game.cues[game.index]
			if game.night_action == "wolf" and "wolf" not in game.night_record:
				title += f" · {game.wolf_seconds} 秒" if game.wolf_seconds else " · 讨论结束，请登记"
			labels = ("身份名单", "夜间记录", "继续")
		elif phase == "night_record":
			labels = self.draw_night_record(game)
		elif phase == "night_log":
			labels = self.draw_night_log(game)
		elif phase == "round_summary":
			labels = self.draw_round_summary(game)
		elif phase in ("roster", "finished"):
			labels = self.draw_roster(game)
		elif phase in ("night_deaths", "vote_deaths"):
			labels = self.draw_death_list(game)
		elif phase == "discuss":
			dead = game.history[-1][2]
			eyebrow = "白天流程"
			title = "请开始讨论"
			spoken = ("昨夜平安。" if not dead else "昨夜出局：" + "、".join(map(str, dead)),
				  "请存活玩家按号码轮流发言。")
			private = (("不透露袭击是否发生或是否被救。" if not dead else "不公布身份和死因。"),
					   f"未结束：好人{good_alive}人，狼人{wolves_alive}人。",
					   "讨论结束后，再发起投票。")
			labels = ("", "", "开始投票")
		elif phase == "vote":
			eyebrow, title = "白天流程", "请投票放逐"
			spoken = ("我倒数三声，存活玩家同时指人。", "每人一票，可以弃票。")
			private = ("最高票者出局，平票只对并列者重投。", "再平票或全员弃票：空选确认。",
					   "记下出局号码，再登记结果。")
			labels = ("", "", "登记结果")
		elif phase == "last_words":
			eyebrow = "白天流程"
			role = ROLE_NAMES[game.roles[game.last_words_player - 1]]
			title = f"{game.last_words_player}号 {role}发表遗言"
			spoken = (f"请 {game.last_words_player} 号玩家发表遗言。",)
			result = (f"已结束：{'好人' if game.winner == 'good' else '狼人'}阵营胜利，遗言后结算。"
					  if game.winner else f"未结束：好人{good_alive}人，狼人{wolves_alive}人。")
			private = ("仅被放逐玩家发表遗言。", result, "结束后按 K3 继续。")
			labels = ("", "", "遗言结束")
		elif phase == "interrupt_confirm":
			eyebrow, title = "确认中断", "本局将中断"
			detail = "确认后回到角色配置"
			note = "取消则继续当前游戏"
			labels = ("继续本局", "", "确认中断")

		if phase == "night":
			self.draw_script(f"夜间流程   {game.index + 1} / {len(game.cues)}", title, spoken, private)
		elif phase in ("discuss", "vote", "last_words"):
			self.draw_script(eyebrow, title, spoken, private)
		elif phase == "interrupt_confirm":
			self.text(eyebrow, 14, self.RED, middle - 54)
			self.text(title, 26, self.GOLD, middle - 15)
			self.text(detail, 14, self.PAPER, middle + 23)
			self.text(note, 12, self.MUTED, middle + 48)
		elif phase != "setup" and not list_page:
			if role_icon:
				self.text(eyebrow, 14, self.MUTED, middle - 61)
				self.role_icon(role_icon, (self.width // 2, middle - 35), 16)
				self.text(title, 26, accent, middle - 5)
				self.text(detail, 12, self.MUTED, middle + 18)
				self.text(ROLE_SKILLS[role_icon], 14, self.PAPER, middle + 40)
				self.text(note, 14, self.MUTED, middle + 62)
			else:
				self.text(eyebrow, 14, self.MUTED, middle - 54)
				self.text(title, 26, accent, middle - 15)
				self.text(detail, 17, self.PAPER, middle + 23)
				self.text(note, 14, self.MUTED, middle + 48)
		self.labels = labels
		for index, (rect, label) in enumerate(zip(self.buttons, labels)):
			if label:
				border = self.GOLD if index == 2 else self.PANEL
				pygame.draw.rect(self.screen, self.PANEL, rect, border_radius=6)
				pygame.draw.rect(self.screen, border, rect, 1, border_radius=6)
				self.text(label, 14, self.PAPER, rect.centery, rect.centerx)


def event_action(event, display):
	if event.type == pygame.QUIT:
		return "EXIT"
	if event.type == pygame.KEYDOWN:
		if event.key in (pygame.K_ESCAPE, pygame.K_q):
			return "EXIT"
		if event.key == pygame.K_BACKSPACE:
			return "BACK"
		return {pygame.K_1: "K1", pygame.K_KP1: "K1", pygame.K_LEFT: "K1",
				pygame.K_2: "K2", pygame.K_KP2: "K2", pygame.K_RIGHT: "K2",
				pygame.K_3: "K3", pygame.K_KP3: "K3", pygame.K_RETURN: "K3"}.get(event.key)
	point = spi_lcd.mouse_position(event)
	if point is not None:
		for index, rect in enumerate(display.setup_rows):
			if rect.collidepoint(point):
				return f"SETUP_{index}"
		for action, rect in display.death_rows.items():
			if rect.collidepoint(point):
				return action
		for index, (button, label) in enumerate(zip(display.buttons, display.labels), 1):
			if label and button.collidepoint(point):
				return f"K{index}"
	return None


def main():
	for arg, key, value in (("--sim", "POKEMON_SIMULATE", "1"), ("--spi", "POKEMON_SIMULATE", "0"),
							("--portrait", "POKEMON_PORTRAIT", "1"), ("--landscape", "POKEMON_PORTRAIT", "0")):
		if arg in sys.argv:
			os.environ[key] = value
	screen = spi_lcd.init()
	buttons = None
	try:
		if spi_lcd.is_simulate():
			pygame.display.set_caption("狼人杀 · 主持人")
		else:
			import RPi.GPIO as gpio
			buttons = GPIOButtons(gpio, long_action="BACK")
		hold = spi_lcd.SimulatedHold("K3", "BACK", QUIT_HOLD_SECONDS)
		game = WerewolfGame()
		display = WerewolfDisplay(screen)
		clock = pygame.time.Clock()
		while True:
			display.draw(game)
			if not spi_lcd.present(poll_events=False):
				return
			clock.tick(30)
			if buttons is None:
				actions = [hold.process_event(event, event_action(event, display)) for event in pygame.event.get()]
				actions.append(hold.poll())
			else:
				actions = buttons.poll()
			for action in actions:
				previous = game.phase
				if game.handle(action) == "EXIT":
					return
				if game.phase != previous:
					break
			game.tick()
	finally:
		if buttons is not None:
			buttons.cleanup()
		pygame.quit()


if __name__ == "__main__":
	main()
