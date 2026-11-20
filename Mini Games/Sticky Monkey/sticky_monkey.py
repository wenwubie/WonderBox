"""按住蓄力搭桥、让猴子走到下一座平台。"""

import importlib
import json
import math
import os
import random
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(os.path.dirname(BASE_DIR))
ASSET_DIR = os.path.join(BASE_DIR, "assets")
BEST_RECORD_PATH = os.path.join(BASE_DIR, "best_score.json")
sys.path.insert(0, ROOT_DIR)

from common import spi_lcd
from common.button_input import BUTTON_PINS, DEBOUNCE_SECONDS, GPIOButtons, QUIT_HOLD_SECONDS

import pygame


BACKGROUND = (21, 51, 35)
PAPER = (255, 248, 224)
INK = (50, 55, 39)
GOLD = (255, 194, 73)
CAMERA_PLAYER_SCREEN_RATIO = 0.34


def load_best_record(path=BEST_RECORD_PATH):
	try:
		with open(path, "r", encoding="utf-8") as source:
			data = json.load(source)
		candidates = data.get("records") if isinstance(data, dict) else None
		if not isinstance(candidates, list):
			candidates = [data] if isinstance(data, dict) else []
		records = []
		for candidate in candidates:
			if not isinstance(candidate, dict):
				continue
			try:
				score = max(0, int(candidate.get("score", candidate.get("best_score", 0))))
			except (ValueError, TypeError, OverflowError):
				continue
			if score:
				recorded_at = candidate.get("recorded_at", "")
				records.append((score, recorded_at if isinstance(recorded_at, str) else ""))
		return max(records, default=(0, ""), key=lambda record: record[0])
	except (OSError, ValueError, TypeError, OverflowError):
		return 0, ""


def save_best_record(score, recorded_at=None, path=BEST_RECORD_PATH):
	path = os.fspath(path)
	temporary_path = path + ".tmp"
	try:
		score = max(0, int(score))
		best_score, best_time = load_best_record(path)
		if score <= best_score:
			return best_score, best_time
		recorded_at = recorded_at or datetime.now().astimezone().isoformat(timespec="seconds")
		with open(temporary_path, "w", encoding="utf-8") as destination:
			json.dump({"score": score, "recorded_at": recorded_at}, destination)
		os.replace(temporary_path, path)
		return score, recorded_at
	except (OSError, ValueError, TypeError, OverflowError):
		try:
			os.remove(temporary_path)
		except OSError:
			pass
		return None


def format_best_time(recorded_at):
	if not recorded_at:
		return ""
	try:
		return datetime.fromisoformat(recorded_at).astimezone().strftime("%Y-%m-%d %H:%M")
	except ValueError:
		return recorded_at


def present_frame(screen):
	if spi_lcd.is_simulate():
		window = pygame.display.get_surface()
		pygame.transform.scale(screen, window.get_size(), window)
		pygame.display.flip()
	else:
		spi_lcd.present()


class StickMonkeyGame:
	def __init__(self, width, height, rng=None, best_score=0, best_time=""):
		self.width = width
		self.height = height
		self.rng = rng or random.Random()
		self.scale_x = width / 1080
		self.scale_y = height / 1920
		self.player_width = max(1, round(162 * self.scale_x))
		self.ground_y = round(1030 * self.scale_y)
		self.state = "title"
		self.score = 0
		self.best_score = max(0, int(best_score))
		self.best_time = best_time
		self.camera_x = 0.0
		self.player_x = 0.0
		self.player_y = float(self.ground_y)
		self.hold_time = 0.0
		self.stick_length = 0.0
		self.bridge_elapsed = 0.0
		self.walk_start = 0.0
		self.walk_end_x = 0.0
		self.walk_is_success = False
		self.fall_speed = 0.0
		self.fall_elapsed = 0.0
		self.reset_round("title")

	def reset_round(self, state="ready"):
		self.score = 0
		self.camera_x = 0.0
		self.base_x = 460 * self.scale_x
		self.base_width = 160 * self.scale_x
		self.player_x = 570 * self.scale_x
		self.player_y = float(self.ground_y)
		self.hold_time = 0.0
		self.stick_length = 0.0
		self.bridge_elapsed = 0.0
		self.walk_end_x = 0.0
		self.walk_is_success = False
		self.fall_speed = 0.0
		self.fall_elapsed = 0.0
		self.state = state
		self.make_target()

	def make_target(self):
		self.target_gap = self.rng.uniform(220 * self.scale_x, 420 * self.scale_x)
		self.target_x = self.base_x + self.base_width + self.target_gap
		self.target_width = 160 * self.scale_x

	@property
	def bridge_is_safe(self):
		gap = self.target_x - (self.base_x + self.base_width)
		return gap <= self.stick_length <= gap + self.target_width

	def press(self):
		if self.state in ("title", "game_over"):
			self.reset_round("ready")
			return
		if self.state == "ready":
			self.hold_time = 0.0
			self.stick_length = 0.0
			self.state = "charging"

	def release(self):
		if self.state == "charging":
			self.state = "bridge"
			self.bridge_elapsed = 0.0

	def update(self, elapsed):
		elapsed = max(0.0, min(elapsed, 0.1))
		if self.state == "charging":
			self.hold_time += elapsed
			self.stick_length = min(self.width * 1.25, self.hold_time * self.width * 0.82)
		elif self.state == "bridge":
			self.bridge_elapsed += elapsed
			if self.bridge_elapsed >= 0.28:
				self.walk_is_success = self.bridge_is_safe
				self.walk_start = self.player_x
				self.walk_end_x = (self.target_x + self.target_width - self.player_width * 0.55
							   if self.walk_is_success
							   else self.base_x + self.base_width + self.stick_length)
				self.state = "walking"
		elif self.state == "walking":
			self.player_x += self.width * 0.92 * elapsed
			self.camera_x = max(self.camera_x,
								self.player_x - self.width * CAMERA_PLAYER_SCREEN_RATIO, 0.0)
			if self.player_x >= self.walk_end_x:
				self.player_x = self.walk_end_x
				if not self.walk_is_success:
					self.state = "falling"
					self.fall_speed = 0.0
					self.fall_elapsed = 0.0
					return
				self.score += 1
				self.base_x = self.target_x
				self.base_width = self.target_width
				self.camera_x = max(0.0, self.player_x - self.width * CAMERA_PLAYER_SCREEN_RATIO)
				self.make_target()
				self.stick_length = 0.0
				self.state = "ready"
		elif self.state == "falling":
			self.fall_elapsed += elapsed
			self.fall_speed += self.height * 1.8 * elapsed
			self.player_y += self.fall_speed * elapsed
			if self.fall_elapsed >= 0.8:
				self.state = "game_over"

	def world_to_screen(self, x):
		return round(x - self.camera_x)


class StickyMonkeyDisplay:
	def __init__(self, screen):
		self.screen = screen
		self.width, self.height = screen.get_size()
		self.portrait = self.height > self.width
		self.scale_x = self.width / 1080
		self.scale_y = self.height / 1920
		self.ground_y = round(1030 * self.scale_y)
		self.title_font = self.load_font(27 if self.height > self.width else 23)
		self.score_font = self.load_font(22)
		self.panel_font = self.load_font(max(9, round(28 * min(self.scale_x, self.scale_y))))
		self.record_time_font = self.load_font(max(7, round(14 * min(self.scale_x, self.scale_y))))
		self.body_font = self.load_font(15)
		self.small_font = self.load_font(12)
		self.backgrounds = [self.load_image("background-sheet%d.png" % index)
						for index in range(6)]
		self.backgrounds = [pygame.transform.smoothscale(image, screen.get_size())
						for image in self.backgrounds]
		self.logo = self.load_image("gamelogo-sheet0.png")
		self.platform_sheet = self.load_image("platform_1-sheet0.png")
		self.platform_frames = [self.platform_sheet.subsurface(rect).copy() for rect in (
			(1, 1, 182, 1024), (185, 1, 170, 1024),
			(357, 1, 160, 1024), (519, 1, 160, 1024),
			(681, 1, 160, 1024), (843, 1, 160, 1024))]
		self.player_sheet = self.load_image("player-sheet0.png")
		self.player_frames = {
			"idle": [self.player_sheet.subsurface(rect).copy() for rect in (
				(1783, 647, 242, 297), (1783, 946, 242, 297),
				(1783, 1245, 242, 297), (805, 1279, 242, 297),
				(1049, 1279, 242, 297), (1293, 1279, 242, 297),
				(1537, 1279, 242, 297), (1, 1286, 242, 297),
				(245, 1286, 242, 297), (1783, 647, 242, 297))],
			"walk": [self.player_sheet.subsurface(rect).copy() for rect in (
				(1, 1, 324, 321), (327, 1, 324, 321), (653, 1, 324, 321),
				(979, 1, 324, 321), (1305, 1, 324, 321), (1631, 1, 324, 321),
				(1, 324, 324, 321), (327, 324, 324, 321), (653, 324, 324, 321),
				(979, 324, 324, 321), (1305, 324, 324, 321), (1631, 324, 324, 321),
				(1, 647, 324, 321), (327, 647, 324, 321), (653, 647, 324, 321),
				(1305, 324, 324, 321), (979, 324, 324, 321), (1, 1, 324, 321))],
			"fall": [self.player_sheet.subsurface(rect).copy() for rect in (
				(979, 647, 266, 314), (1247, 647, 266, 314), (1515, 647, 266, 314),
				(979, 963, 266, 314), (1247, 963, 266, 314), (1515, 963, 266, 314),
				(1, 970, 266, 314), (269, 970, 266, 314),
				(537, 970, 266, 314), (979, 647, 266, 314))]}
		self.monkey = self.load_image("monkey-sheet0.png")
		self.sunrays = self.load_image("sunrays-sheet0.png")
		self.stick = self.load_image("stick-sheet0.png")
		self.play_button = self.load_image("buttonplay-sheet0.png")
		self.restart_button = self.load_image("buttonrestart-sheet0.png")
		self.game_over_text = self.load_image("textgameover-sheet0.png")
		self.score_frame = self.load_image("framescore-sheet0.png")
		self.best_frame = self.load_image("framebestscore-sheet0.png")
		self.pillar_cache = {}
		self.return_button_rect = None

	def load_font(self, size):
		try:
			return spi_lcd.load_font(size)
		except RuntimeError:
			return pygame.font.Font(None, size)

	def load_image(self, name):
		return pygame.image.load(os.path.join(ASSET_DIR, name)).convert_alpha()

	def text(self, value, font, color, center):
		image = font.render(value, True, color)
		self.screen.blit(image, image.get_rect(center=center))

	def draw_platform(self, game, world_x, variant):
		x = game.world_to_screen(world_x)
		pillar_width = max(1, round(160 * self.scale_x))
		pillar_height = max(1, round(1024 * self.scale_y))
		if x + pillar_width < 0 or x > self.width:
			return
		key = (variant, pillar_width, pillar_height)
		image = self.pillar_cache.get(key)
		if image is None:
			image = pygame.transform.scale(self.platform_frames[variant],
										   (pillar_width, pillar_height))
			self.pillar_cache[key] = image
		self.screen.blit(image, (x, self.ground_y))

	def draw_monkey(self, game, now):
		animation = "walk" if game.state == "walking" else "fall" if game.state == "falling" else "idle"
		fps = {"idle": 18, "walk": 34, "fall": 18}[animation]
		frames = self.player_frames[animation]
		image = frames[int(now * fps) % len(frames)]
		frame_height = {"idle": 198, "walk": 160, "fall": 191}[animation]
		size = (max(1, round(162 * self.scale_x)), max(1, round(frame_height * self.scale_y)))
		image = pygame.transform.smoothscale(image, size)
		rect = image.get_rect(midbottom=(game.world_to_screen(game.player_x), round(game.player_y)))
		self.screen.blit(image, rect)

	def draw_stick(self, game):
		if game.state not in ("charging", "bridge", "walking", "falling"):
			return
		root_x = game.world_to_screen(game.base_x + game.base_width)
		root_y = self.ground_y
		if game.state == "charging":
			angle = 0.0
			length = game.stick_length
		elif game.state == "bridge":
			progress = min(1.0, game.bridge_elapsed / 0.28)
			angle = progress * math.pi / 2
			length = game.stick_length
		else:
			angle = math.pi / 2
			length = game.stick_length
		if length < 2:
			return
		thickness = max(1, round(20 * self.scale_x))
		image = pygame.transform.scale(self.stick, (thickness, max(1, round(length))))
		image = pygame.transform.rotate(image, -math.degrees(angle))
		center = (round(root_x + length * 0.5 * math.sin(angle)),
				  round(root_y - length * 0.5 * math.cos(angle)))
		self.screen.blit(image, image.get_rect(center=center))

	def draw_score_panels(self, game):
		score_size = (max(1, round(256 * self.scale_x)),
					 max(1, round(256 * self.scale_y)))
		best_size = (max(1, round(518 * self.scale_x)),
					 max(1, round(255 * self.scale_y)))
		gap = round(20 * self.scale_x)
		left = (self.width - score_size[0] - gap - best_size[0]) // 2
		top = round(180 * self.scale_y) - max(score_size[1], best_size[1]) // 2
		self.screen.blit(pygame.transform.smoothscale(self.score_frame, score_size), (left, top))
		best_left = left + score_size[0] + gap
		self.screen.blit(pygame.transform.smoothscale(self.best_frame, best_size), (best_left, top))
		self.text("%d" % game.score, self.panel_font, INK,
				  (left + score_size[0] // 2, top + round(187 * self.scale_y)))
		self.text("%d" % game.best_score, self.panel_font, INK,
				  (best_left + best_size[0] // 2, top + round(187 * self.scale_y)))
		recorded_at = format_best_time(game.best_time)
		if recorded_at:
			self.text(recorded_at, self.record_time_font, INK,
					  (best_left + best_size[0] // 2, top + round(229 * self.scale_y)))

	def draw(self, game, now):
		self.return_button_rect = None
		background_index = 2 if game.state == "title" else 0
		self.screen.fill(BACKGROUND)
		self.screen.blit(self.backgrounds[background_index], (0, 0))
		if game.state == "title":
			rays_size = max(1, round(760 * self.scale_x))
			rays = pygame.transform.smoothscale(self.sunrays, (rays_size, rays_size))
			rays = pygame.transform.rotate(rays, now * 2 % 360)
			self.screen.blit(rays, rays.get_rect(center=(self.width // 2,
												 round(620 * self.scale_y))))
			logo_width = min(self.width - 30, round(840 * self.scale_x))
			logo_height = round(logo_width * self.logo.get_height() / self.logo.get_width())
			logo = pygame.transform.smoothscale(self.logo, (logo_width, logo_height))
			self.screen.blit(logo, logo.get_rect(center=(self.width // 2,
												 round(500 * self.scale_y))))
			monkey_size = (max(1, round(250 * self.scale_x)), max(1, round(320 * self.scale_y)))
			monkey = pygame.transform.smoothscale(self.monkey, monkey_size)
			self.screen.blit(monkey, monkey.get_rect(center=(self.width // 2,
												  round(1120 * self.scale_y))))
			button_size = max(1, round(230 * self.scale_x))
			button = pygame.transform.smoothscale(self.play_button, (button_size, button_size))
			self.screen.blit(button, button.get_rect(center=(self.width // 2,
												 round(1580 * self.scale_y))))
			self.text("BEST  %d" % game.best_score, self.score_font, INK,
					  (self.width // 2, round(1320 * self.scale_y)))
			recorded_at = format_best_time(game.best_time)
			if recorded_at:
				self.text(recorded_at, self.small_font, INK,
						  (self.width // 2, round(1380 * self.scale_y)))
		else:
			self.draw_platform(game, game.base_x, game.score % 6)
			self.draw_platform(game, game.target_x, (game.score + 1) % 6)
			self.draw_stick(game)
			self.draw_monkey(game, now)
			self.draw_score_panels(game)
		if game.state == "game_over":
			text_width = max(1, round(700 * self.scale_x))
			text_height = round(text_width * self.game_over_text.get_height()
								/ self.game_over_text.get_width())
			text_image = pygame.transform.smoothscale(self.game_over_text,
												 (text_width, text_height))
			self.screen.blit(text_image, text_image.get_rect(center=(self.width // 2,
													 round(700 * self.scale_y))))
			self.text("%d" % game.score, self.title_font, PAPER,
				  (self.width // 2, round(1050 * self.scale_y)))
			restart_size = max(1, round(190 * self.scale_x))
			restart = pygame.transform.smoothscale(self.restart_button,
												 (restart_size, restart_size))
			self.screen.blit(restart, restart.get_rect(center=(self.width // 2,
												   round(1400 * self.scale_y))))
		action_hint = {
			"title": "开始",
			"ready": "蓄力",
			"charging": "松开",
			"game_over": "重来",
		}.get(game.state)
		hint_y = self.height - max(12, round(25 * self.scale_y))
		if action_hint:
			self.text(action_hint, self.small_font, PAPER,
					  (max(28, round(60 * self.scale_x)), hint_y))
		if game.state != "title":
			return_center = (self.width - max(28, round(60 * self.scale_x)), hint_y)
			return_size = self.small_font.size("返回")
			self.return_button_rect = pygame.Rect((0, 0), return_size).inflate(12, 12)
			self.return_button_rect.center = return_center
			self.text("返回", self.small_font, PAPER, return_center)


def key_action(event, display=None):
	if event.type == pygame.KEYDOWN:
		if event.key in (pygame.K_ESCAPE, pygame.K_q, pygame.K_BACKSPACE):
			return "RETURN"
		if event.key in (pygame.K_1, pygame.K_KP1, pygame.K_UP, pygame.K_SPACE):
			return "K1_DOWN"
		if event.key in (pygame.K_3, pygame.K_KP3, pygame.K_RETURN):
			return "K3_DOWN"
	if event.type == pygame.KEYUP:
		if event.key in (pygame.K_1, pygame.K_KP1, pygame.K_UP, pygame.K_SPACE):
			return "K1_UP"
	if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
		position = spi_lcd.mouse_position(event)
		if (display is not None and display.return_button_rect is not None
				and position is not None and display.return_button_rect.collidepoint(position)):
			return "K3_DOWN"
		return "K1_DOWN"
	if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
		return "K1_UP"
	return None


def main():
	if spi_lcd.is_simulate():
		spi_lcd.WINDOW_SCALE = 2
		if "--landscape" in sys.argv:
			os.environ["POKEMON_PORTRAIT"] = "0"
		elif "--portrait" in sys.argv:
			os.environ["POKEMON_PORTRAIT"] = "1"
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
			pygame.display.set_caption("粘猴")
		display = StickyMonkeyDisplay(screen)
		best_score, best_time = load_best_record()
		game = StickMonkeyGame(*screen.get_size(), best_score=best_score, best_time=best_time)
		hold = spi_lcd.SimulatedHold("K3", "HOLD_K3", QUIT_HOLD_SECONDS)
		clock = pygame.time.Clock()
		running = True
		key_held = False
		print("粘猴已启动：按住蓄力搭桥，松开后猴子前进；返回游戏菜单。")
		while running:
			elapsed = clock.tick(30) / 1000.0
			if buttons is None:
				for event in pygame.event.get():
					if event.type == pygame.QUIT:
						running = False
						break
					action = key_action(event, display)
					if action == "K1_DOWN" and not key_held:
						key_held = True
						game.press()
					elif action == "K1_UP" and key_held:
						key_held = False
						game.release()
					if action in ("K3_DOWN", "RETURN"):
						if action == "K3_DOWN":
							action = hold.process_event(event, "K3")
						else:
							running = False
					if action in ("K3", "RETURN"):
						running = False
					elif event.type in (pygame.KEYUP, pygame.MOUSEBUTTONUP, pygame.WINDOWFOCUSLOST):
						action = hold.process_event(event, None)
						if action in ("K3", "RETURN"):
							running = False
				if not running:
					break
			else:
				actions = buttons.poll()
				is_down = buttons.states["K1"]["down"]
				if is_down and not key_held:
					key_held = True
					game.press()
				elif not is_down and key_held:
					key_held = False
					game.release()
				if "K3" in actions:
					running = False
			if not running:
				break
			previous_state = game.state
			game.update(elapsed)
			if (previous_state != "game_over" and game.state == "game_over"
					and game.score > game.best_score):
				record = save_best_record(game.score)
				if record is None:
					print("最高纪录保存失败。")
				else:
					game.best_score, game.best_time = record
			display.draw(game, pygame.time.get_ticks() / 1000.0)
			present_frame(screen)
	finally:
		if buttons is not None:
			buttons.cleanup()
		pygame.quit()


if __name__ == "__main__":
	main()
