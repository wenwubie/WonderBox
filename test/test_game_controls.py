import importlib
import os
import random
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "Lucky Wheel"))
sys.path.insert(0, os.path.join(ROOT_DIR, "Quick Duel"))
sys.path.insert(0, os.path.join(ROOT_DIR, "Magic"))

import lucky_wheel
import quick_duel


class SimulatedHoldTests(unittest.TestCase):
	def setUp(self):
		self.now = [0.0]
		self.hold = lucky_wheel.spi_lcd.SimulatedHold("K3", "BACK", 0.8, clock=lambda: self.now[0])
		self.pygame_patch = patch.object(lucky_wheel.spi_lcd, "_pygame", pygame)
		self.pygame_patch.start()
		self.addCleanup(self.pygame_patch.stop)

	def test_keyboard_short_and_long_press_are_exclusive(self):
		down = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_3)
		up = pygame.event.Event(pygame.KEYUP, key=pygame.K_3)
		self.assertIsNone(self.hold.process_event(down, "K3"))
		self.now[0] = 0.2
		self.assertEqual(self.hold.process_event(up, None), "K3")
		self.assertIsNone(self.hold.process_event(down, "K3"))
		self.now[0] = 1.1
		self.assertEqual(self.hold.poll(), "BACK")
		self.assertIsNone(self.hold.poll())
		self.assertIsNone(self.hold.process_event(up, None))

	def test_mouse_release_after_threshold_and_other_input(self):
		down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(10, 10))
		up = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(10, 10))
		other = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1)
		self.assertEqual(self.hold.process_event(other, "K1"), "K1")
		self.assertIsNone(self.hold.process_event(down, "K3"))
		self.now[0] = 1.0
		self.assertEqual(self.hold.process_event(up, None), "BACK")
		self.assertIsNone(self.hold.process_event(up, None))

	def test_losing_focus_cancels_pending_press(self):
		down = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_3)
		up = pygame.event.Event(pygame.KEYUP, key=pygame.K_3)
		lost = pygame.event.Event(pygame.WINDOWFOCUSLOST)
		self.assertIsNone(self.hold.process_event(down, "K3"))
		self.assertIsNone(self.hold.process_event(lost, None))
		self.now[0] = 1.0
		self.assertIsNone(self.hold.poll())
		self.assertIsNone(self.hold.process_event(up, None))


class LuckyWheelControlTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		pygame.init()

	def test_k3_starts_stops_and_restarts_the_wheel(self):
		wheel = lucky_wheel.LuckyWheel(random.Random(1))
		wheel.handle_action("K1")
		self.assertEqual(wheel.phase, "ready")
		wheel.handle_action("K3")
		self.assertEqual(wheel.phase, "spinning")
		wheel.handle_action("K3")
		self.assertEqual(wheel.phase, "slowing")
		wheel.update(wheel.stop_duration)
		self.assertEqual(wheel.phase, "result")
		previous_task = wheel.task
		wheel.handle_action("K1")
		self.assertNotEqual(wheel.task, previous_task)
		wheel.handle_action("K3")
		self.assertEqual(wheel.phase, "spinning")

	def test_all_tasks_are_distinct_and_fit_both_orientations(self):
		for size in ((240, 320), (320, 240)):
			with patch.object(lucky_wheel.spi_lcd, "_pygame", pygame):
				display = lucky_wheel.WheelDisplay(pygame.Surface(size))
			for label, _, tasks in lucky_wheel.GAMES:
				self.assertGreaterEqual(len(tasks), 16)
				self.assertEqual(len(tasks), len(set(tasks)))
				for task in tasks:
					with self.subTest(size=size, category=label, task=task):
						lines = lucky_wheel.wrap_text(task, display.body_font, display.info_rect.width - 24)
						self.assertTrue(lines)
						self.assertTrue(all(display.body_font.size(line)[0] <= display.info_rect.width - 24
											for line in lines))
						bottom = 30 + (len(lines) - 1) * (display.body_font.get_linesize() + 1)
						bottom += display.body_font.get_height()
						self.assertLessEqual(bottom, display.info_rect.height - 4)

	def test_change_task_can_reach_every_other_task(self):
		wheel = lucky_wheel.LuckyWheel(random.Random(7))
		wheel.phase = "result"
		wheel.rng = Mock()
		for category, (_, _, tasks) in enumerate(lucky_wheel.GAMES):
			wheel.selected = category
			for previous in range(len(tasks)):
				chosen = set()
				for random_index in range(len(tasks) - 1):
					wheel.task = previous
					wheel.rng.randrange.return_value = random_index
					wheel.handle_action("K1")
					chosen.add(wheel.task)
				self.assertEqual(chosen, set(range(len(tasks))) - {previous})

	def test_button_labels_match_available_actions(self):
		with patch.object(lucky_wheel.spi_lcd, "_pygame", pygame):
			display = lucky_wheel.WheelDisplay(pygame.Surface((240, 320)))
		wheel = lucky_wheel.LuckyWheel(random.Random(2))
		with patch.object(display, "button_font", wraps=display.button_font) as font:
			for phase, expected in (("ready", ("换题", "无功能", "开始")),
									("spinning", ("换题", "无功能", "停下")),
									("slowing", ("换题", "无功能", "停下")),
									("result", ("换题", "无功能", "再转"))):
				with self.subTest(phase=phase):
					wheel.phase = phase
					font.reset_mock()
					display.draw_buttons(wheel)
					self.assertEqual(tuple(call.args[0] for call in font.render.call_args_list), expected)
					self.assertEqual(font.render.call_args_list[1].args[2], (83, 92, 89))

	def test_simulated_k3_hold_quits_without_stopping_the_wheel(self):
		pygame.display.set_mode((480, 640))
		screen = pygame.Surface((240, 320))
		now = [0.0]
		hold = lucky_wheel.spi_lcd.SimulatedHold("K3", "QUIT", 1.0, clock=lambda: now[0])
		wheel = lucky_wheel.LuckyWheel(random.Random(5))
		with patch.object(lucky_wheel.spi_lcd, "_pygame", pygame):
			display = lucky_wheel.WheelDisplay(screen)
		rect = display.buttons[2]
		position = (rect.centerx * 2, rect.centery * 2)
		down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=position)
		up = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=position)
		events = iter(((0.0, [down, up]), (0.1, [down]), (1.2, [])))
		frames = []

		def next_events():
			now[0], batch = next(events)
			return batch

		with patch.object(lucky_wheel.spi_lcd, "_pygame", pygame), \
			 patch.object(lucky_wheel.spi_lcd, "is_simulate", return_value=True), \
			 patch.object(lucky_wheel.spi_lcd, "init", return_value=screen), \
			 patch.object(lucky_wheel.spi_lcd, "SimulatedHold", return_value=hold), \
			 patch.object(lucky_wheel, "LuckyWheel", return_value=wheel), \
			 patch.object(lucky_wheel.WheelDisplay, "draw", side_effect=lambda display, game: frames.append(game.phase),
					  autospec=True), \
			 patch.object(lucky_wheel, "present_frame"), patch.object(pygame.display, "set_caption"), \
			 patch.object(pygame.event, "get", side_effect=next_events), \
			 patch.object(pygame.time, "Clock") as clock, patch.object(pygame, "quit"), patch("builtins.print"):
			clock.return_value.tick.return_value = 0
			lucky_wheel.main()
		self.assertEqual(frames, ["spinning", "spinning"])
		self.assertEqual(wheel.phase, "spinning")


class DuelControlTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		pygame.init()

	def test_player_buttons_and_k3_challenge_return(self):
		game = quick_duel.DuelGame(random.Random(3))
		game.handle_action("K3")
		self.assertEqual(game.view, "dice")
		for action in ("K1", "K2", "K1", "K2"):
			game.handle_action(action)
		self.assertEqual([die.phase for die in game.dice], ["locked", "locked"])
		game.dice[0].value, game.dice[1].value = 1, 6
		game.handle_action("K3")
		self.assertEqual(game.view, "wheel")
		game.handle_action("K1")
		self.assertEqual(game.wheel.phase, "spinning")
		game.handle_action("K2")
		self.assertEqual(game.wheel.phase, "slowing")
		game.handle_action("K3")
		self.assertEqual(game.view, "dice")
		self.assertEqual(game.round_number, 2)

	def test_button_labels_match_dice_and_wheel_actions(self):
		with patch.object(lucky_wheel.spi_lcd, "_pygame", pygame):
			display = quick_duel.DuelDisplay(pygame.Surface((240, 320)))
		game = quick_duel.DuelGame(random.Random(4))
		with patch.object(display, "centered") as centered:
			display.draw_buttons(game)
			self.assertEqual([call.args[0] for call in centered.call_args_list], ["开始", "开始", "挑战"])
			self.assertEqual(centered.call_args_list[2].args[2], (83, 92, 89))
			for action in ("K1", "K2", "K1", "K2"):
				game.handle_action(action)
			game.dice[0].value, game.dice[1].value = 1, 6
			centered.reset_mock()
			display.draw_buttons(game)
			self.assertEqual([call.args[0] for call in centered.call_args_list], ["锁定", "锁定", "挑战"])
			self.assertEqual(centered.call_args_list[0].args[2], (83, 92, 89))
			game.handle_action("K3")
			centered.reset_mock()
			display.draw_buttons(game)
			self.assertEqual([call.args[0] for call in centered.call_args_list], ["开始", "停下", "返回"])
			self.assertEqual(centered.call_args_list[1].args[2], (83, 92, 89))

	def test_gpio_long_k3_is_a_back_action(self):
		now = [0.0]
		levels = {pin: 1 for pin in lucky_wheel.BUTTON_PINS.values()}
		gpio = SimpleNamespace(BCM=1, IN=2, PUD_UP=3, LOW=0, input=levels.__getitem__,
							   setmode=Mock(), setup=Mock(), cleanup=Mock())
		buttons = quick_duel.DuelGPIOButtons(gpio, clock=lambda: now[0])
		levels[24] = 0
		self.assertEqual(buttons.poll(), [])
		now[0] = 0.05
		self.assertEqual(buttons.poll(), [])
		now[0] = 1.1
		self.assertEqual(buttons.poll(), ["BACK"])
		levels[24] = 1
		now[0] = 1.2
		buttons.poll()
		now[0] = 1.25
		self.assertEqual(buttons.poll(), [])

	def test_simulated_long_k3_returns_from_challenge(self):
		pygame.display.set_mode((480, 640))
		screen = pygame.Surface((240, 320))
		now = [0.0]
		hold = lucky_wheel.spi_lcd.SimulatedHold("K3", "BACK", 1.0, clock=lambda: now[0])
		game = quick_duel.DuelGame(random.Random(6))
		game.view = "wheel"
		game.loser = 1
		game.wheel = quick_duel.ChallengeWheel(game.rng)
		with patch.object(lucky_wheel.spi_lcd, "_pygame", pygame):
			display = quick_duel.DuelDisplay(screen)
		rect = display.buttons[2]
		position = (rect.centerx * 2, rect.centery * 2)
		down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=position)
		up = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=position)
		events = iter(((0.0, [down]), (1.1, []), (1.2, [up]),
					   (1.3, [pygame.event.Event(pygame.QUIT)])))
		frames = []

		def next_events():
			now[0], batch = next(events)
			return batch

		with patch.object(quick_duel.spi_lcd, "_pygame", pygame), \
			 patch.object(quick_duel.spi_lcd, "is_simulate", return_value=True), \
			 patch.object(quick_duel.spi_lcd, "init", return_value=screen), \
			 patch.object(quick_duel.spi_lcd, "SimulatedHold", return_value=hold), \
			 patch.object(quick_duel, "DuelGame", return_value=game), \
			 patch.object(quick_duel.DuelDisplay, "draw", side_effect=lambda display, current: frames.append(current.view),
					  autospec=True), \
			 patch.object(quick_duel, "present_frame"), patch.object(pygame.display, "set_caption"), \
			 patch.object(pygame.event, "get", side_effect=next_events), \
			 patch.object(pygame.time, "Clock") as clock, patch.object(pygame, "quit"), patch("builtins.print"):
			clock.return_value.tick.return_value = 0
			quick_duel.main()
		self.assertEqual(frames, ["wheel", "dice", "dice"])
		self.assertEqual(game.round_number, 2)


class MagicControlTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		pygame.init()
		pygame.display.set_mode((480, 640))
		with patch.object(lucky_wheel.spi_lcd, "_pygame", pygame), \
			 patch.object(lucky_wheel.spi_lcd, "is_simulate", return_value=True), \
			 patch.object(lucky_wheel.spi_lcd, "init", return_value=pygame.Surface((240, 320))):
			cls.magic = importlib.import_module("Magic")

	def test_k3_confirms_and_returns_from_each_view(self):
		magic = self.magic
		state = {"view": "home", "menu": 0}
		magic.handle_action("K2", state)
		self.assertEqual(state["menu"], 1)
		magic.handle_action("K3", state)
		self.assertEqual(state["view"], "zodiac")
		magic.handle_action("K3", state)
		self.assertEqual(state["view"], "home")
		magic.handle_action("K1", state)
		magic.handle_action("K3", state)
		self.assertEqual(state["view"], "shuffle")
		magic.handle_action("K3", state)
		self.assertEqual(state["view"], "home")
		state.update({"view": "result", "mode": "love", "love_page": 0})
		magic.handle_action("K1", state)
		self.assertEqual(state["love_page"], 1)
		magic.handle_action("K2", state)
		self.assertEqual(state["view"], "shuffle")
		state["view"] = "result"
		magic.handle_action("K3", state)
		self.assertEqual(state["view"], "home")

	def test_footer_labels_and_refresh_match_actions(self):
		magic = self.magic
		with patch.object(magic, "draw_footer") as footer:
			magic.draw_home(0)
			footer.assert_called_with(("上一项", "下一项", "开始"))
			magic.draw_shuffle("daily", 0, magic.DAILY_CARDS[0], 0, magic.SPIN_DURATION, 10)
			footer.assert_called_with(("翻页", "再抽", "返回"), True, (False, False, True))
			magic.draw_result("daily", magic.DAILY_CARDS[0])
			footer.assert_called_with(("翻页", "再抽", "返回"), True, (False, True, True))
			magic.draw_result("love", magic.TAROT[0], 0)
			footer.assert_called_with(("下一页", "再抽", "返回"))
			magic.draw_zodiac(0, 0, 0)
			self.assertEqual(footer.call_args.args[0][1:], ("下星座", "返回"))
		with patch.object(magic.spi_lcd, "present", return_value=True) as present:
			self.assertTrue(magic.render({"view": "home", "menu": 0}))
		present.assert_called_once_with(poll_events=False)

	def test_disabled_footer_buttons_are_gray_and_ignore_actions(self):
		magic = self.magic
		for dark in (False, True):
			with self.subTest(dark=dark), patch.object(magic, "font_small", wraps=magic.font_small) as font:
				magic.draw_footer(("翻页", "再抽", "返回"), dark, (False, False, True))
				self.assertEqual([call.args[0] for call in font.render.call_args_list], ["翻页", "再抽", "返回"])
				self.assertEqual(font.render.call_args_list[0].args[2], magic.DISABLED_TEXT)
				rect = magic.footer_button_rects()[0]
				self.assertEqual(magic.screen.get_at((rect.left + 4, rect.centery))[:3], magic.DISABLED_BG)
		state = {"view": "shuffle"}
		for action in ("K1", "K2"):
			magic.handle_action(action, state)
			self.assertEqual(state, {"view": "shuffle"})
		state = {"view": "result", "mode": "daily"}
		magic.handle_action("K1", state)
		self.assertEqual(state, {"view": "result", "mode": "daily"})

	def test_shuffle_moves_slowly_and_stops_on_selected_card(self):
		magic = self.magic
		for mode, cards in (("daily", magic.DAILY_CARDS), ("love", magic.TAROT)):
			for selected in (0, len(cards) - 1):
				for direction in (-1, 1):
					for steps in (4, 6):
						with self.subTest(mode=mode, selected=selected, direction=direction, steps=steps), \
								patch.object(magic.random, "randrange", return_value=selected), \
								patch.object(magic.random, "choice", return_value=direction), \
								patch.object(magic.random, "randint", return_value=steps):
							state = {}
							magic.start_draw(state, mode)
							start = state["scroll_start"]
							duration = state["spin_duration"]
							position = magic.card_scroll_position(start, direction, steps, 0.5, duration)
							self.assertLess(abs(position - start), 0.6)
							end = magic.card_scroll_position(start, direction, steps, duration, duration)
							self.assertEqual(round(end) % len(cards), selected)
							self.assertEqual(state["card"], cards[selected])

	def test_wheel_tracks_the_slower_card_motion_in_both_orientations(self):
		magic = self.magic
		for width, height in ((240, 320), (320, 240)):
			with self.subTest(width=width, height=height), \
					patch.multiple(magic, WIDTH=width, HEIGHT=height, PORTRAIT=height > width,
								   screen=pygame.Surface((width, height))), \
					patch.object(magic, "draw_oracle_wheel") as wheel:
				positions = [magic.card_scroll_position(0, 1, 6, elapsed, magic.SPIN_DURATION)
							 for elapsed in (0, 0.5)]
				for elapsed, position in zip((0, 0.5), positions):
					magic.draw_shuffle("love", elapsed, magic.TAROT[0], position, magic.SPIN_DURATION, 6)
				angles = [call.args[2] for call in wheel.call_args_list]
				radius = wheel.call_args.args[1]
				spacing = (72 if height > width else 62) + 8
				self.assertAlmostEqual(angles[1] - angles[0], (positions[1] - positions[0]) * spacing / radius)
				self.assertLess(abs(angles[1] - angles[0]), 1.4)

	def test_reveal_waits_for_slower_card_animation(self):
		magic = self.magic
		reveal_start = magic.SPIN_DURATION + magic.SPIN_SETTLE_SECONDS
		with patch.object(magic, "draw_tarot_face") as face:
			magic.draw_shuffle("daily", reveal_start + 0.82, magic.DAILY_CARDS[0],
							   0, magic.SPIN_DURATION, 0)
			face.assert_not_called()
			magic.draw_shuffle("daily", reveal_start + magic.CARD_REVEAL_SECONDS,
							   magic.DAILY_CARDS[0], 0, magic.SPIN_DURATION, 0)
			face.assert_called_once()

	def test_result_waits_until_revealed_card_has_been_shown(self):
		magic = self.magic
		down = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_3)
		up = pygame.event.Event(pygame.KEYUP, key=pygame.K_3)
		quit_event = pygame.event.Event(pygame.QUIT)
		events = iter(([down, up], [], [], [], [], [], [quit_event]))
		frames = []

		def capture(state):
			frames.append((state["view"], state["elapsed"]))
			return True

		with patch.object(magic.spi_lcd, "_pygame", pygame), \
				patch.object(magic.spi_lcd, "is_simulate", return_value=True), \
				patch.object(magic, "gpio", None), patch.object(magic, "setup_gpio"), \
				patch.object(magic, "render", side_effect=capture), \
				patch.object(pygame.event, "get", side_effect=lambda: next(events)), \
				patch.object(pygame.time, "Clock") as clock, \
				patch.object(pygame, "quit"), patch("builtins.print"):
			clock.return_value.tick.side_effect = (0, 10000, 250, 1400, 390, 20, 0)
			magic.main()
		clock.return_value.tick.assert_called_with(magic.FRAME_RATE)
		self.assertEqual(magic.FRAME_RATE, 20)
		self.assertEqual([view for view, elapsed in frames],
						 ["shuffle", "shuffle", "shuffle", "shuffle", "shuffle", "result"])
		self.assertLess(frames[-2][1], magic.SPIN_DURATION + magic.SPIN_SETTLE_SECONDS +
						magic.CARD_REVEAL_SECONDS + magic.CARD_REVEAL_HOLD_SECONDS)

	def test_magic_wheel_tick_slows_down_with_the_wheel(self):
		magic = self.magic
		elapsed_holder = {"value": 0.0}
		ticks = []

		class FakeSFX:
			def __init__(self, *args, **kwargs):
				pass

			def welcome(self):
				pass

			def button(self):
				pass

			def play(self, name):
				if name == "wheel_tick":
					ticks.append(elapsed_holder["value"])

			def loop_start(self, name):
				raise AssertionError("占卜屋不应使用固定速率循环音")

			def loop_stop(self):
				pass

			def close(self):
				pass

		down = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_3)
		up = pygame.event.Event(pygame.KEYUP, key=pygame.K_3)
		quit_event = pygame.event.Event(pygame.QUIT)
		events = iter([[down, up]] + [[] for _ in range(180)] + [[quit_event]])

		def capture(state):
			elapsed_holder["value"] = state["elapsed"]
			return True

		with patch.object(magic.spi_lcd, "_pygame", pygame), \
				patch.object(magic.spi_lcd, "is_simulate", return_value=True), \
				patch.object(magic, "setup_gpio", return_value=None), \
				patch.object(magic.sfx_helper, "SFX", FakeSFX), \
				patch.object(magic, "render", side_effect=capture), \
				patch.object(pygame.event, "get", side_effect=lambda: next(events, [])), \
				patch.object(pygame.time, "Clock") as clock, \
				patch.object(pygame, "quit"), patch("builtins.print"):
			clock.return_value.tick.return_value = 50
			magic.main()

		self.assertGreater(len(ticks), 8)
		first_gap = ticks[1] - ticks[0]
		last_gap = ticks[-1] - ticks[-2]
		self.assertGreater(last_gap, first_gap * 3)

	def test_magic_palette_keeps_text_readable_on_dark_surfaces(self):
		magic = self.magic
		def luminance(color):
			channels = [channel / 255.0 for channel in color]
			linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
					  for channel in channels]
			return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

		for foreground, background in ((magic.INK, magic.BG), (magic.INK, magic.PANEL),
									   (magic.INK, magic.PANEL_SELECTED), (magic.MUTED, magic.PANEL_SELECTED),
									   (magic.GOLD, magic.PANEL_SELECTED),
									   (magic.MYSTIC_TEXT, magic.MYSTIC_BG),
									   (magic.MYSTIC_MUTED, magic.MYSTIC_PANEL),
									   (magic.DISABLED_TEXT, magic.DISABLED_BG)):
			with self.subTest(foreground=foreground, background=background):
				lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
				self.assertGreaterEqual((lighter + 0.05) / (darker + 0.05), 4.5)

		for draw in (lambda: magic.draw_home(0), lambda: magic.draw_zodiac(0, 0, 0),
					 lambda: magic.draw_shuffle("love", 0, magic.TAROT[0], 0, magic.SPIN_DURATION, 4),
					 lambda: magic.draw_love_result(magic.TAROT[0], 0)):
			draw()
			self.assertIn(magic.screen.get_at((0, 0))[:3], (magic.BG, magic.PANEL))

	def test_gpio_k3_short_press_and_long_press_are_exclusive(self):
		magic = self.magic
		now = [0.0]
		levels = {pin: 1 for pin in magic.BUTTONS.values()}
		gpio = SimpleNamespace(LOW=0, input=levels.__getitem__)
		states = {name: {"down": False, "since": 0.0, "long": False} for name in magic.BUTTONS}
		with patch.object(magic, "gpio", gpio), patch.object(magic, "button_state", states), \
			 patch.object(magic.time, "monotonic", side_effect=lambda: now[0]):
			levels[24] = 0
			self.assertEqual(magic.poll_gpio(), [])
			now[0] = 0.1
			levels[24] = 1
			self.assertEqual(magic.poll_gpio(), ["K3"])
			levels[24] = 0
			self.assertEqual(magic.poll_gpio(), [])
			now[0] = 1.0
			self.assertEqual(magic.poll_gpio(), ["BACK"])
			levels[24] = 1
			self.assertEqual(magic.poll_gpio(), [])

	def test_simulated_mouse_hold_returns_without_triggering_short_press(self):
		magic = self.magic
		now = [0.0]
		hold = magic.spi_lcd.SimulatedHold("K3", "BACK", 0.8, clock=lambda: now[0])
		second, third = magic.footer_button_rects()[1:]
		second_pos = (second.centerx * 2, second.centery * 2)
		third_pos = (third.centerx * 2, third.centery * 2)
		second_down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=second_pos)
		third_down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=third_pos)
		third_up = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=third_pos)
		events = iter(((0.0, [second_down]), (0.1, [third_down, third_up]),
					   (0.2, [third_down]), (1.1, []), (1.2, [third_up]),
					   (1.3, [pygame.event.Event(pygame.QUIT)])))
		frames = []

		def next_events():
			now[0], batch = next(events)
			return batch

		def capture(state):
			frames.append((state["view"], state["menu"]))
			return True

		with patch.object(magic.spi_lcd, "_pygame", pygame), \
			 patch.object(magic.spi_lcd, "is_simulate", return_value=True), \
			 patch.object(magic.spi_lcd, "SimulatedHold", return_value=hold), \
			 patch.object(magic, "gpio", None), patch.object(magic, "setup_gpio"), \
			 patch.object(magic, "render", side_effect=capture), \
			 patch.object(pygame.event, "get", side_effect=next_events), \
			 patch.object(pygame.time, "Clock"), patch.object(pygame, "quit"), patch("builtins.print"):
			magic.main()
		self.assertEqual(frames, [("home", 1), ("zodiac", 1), ("zodiac", 1),
								  ("home", 1), ("home", 1)])


if __name__ == "__main__":
	unittest.main()