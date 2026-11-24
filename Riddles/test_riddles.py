import json
import os
import random
import tempfile
import unittest
from unittest.mock import Mock, patch

import pygame

import Riddles as riddles


class RiddleGameTests(unittest.TestCase):
	def setUp(self):
		self.bank = [("题目%d？" % index, "答案%d" % index) for index in range(7)]

	def test_filters_track_revealed_answers_across_restarts(self):
		with tempfile.TemporaryDirectory() as directory:
			path = os.path.join(directory, "history.json")
			history = riddles.RiddleHistory(path)
			game = riddles.RiddleGame(self.bank, random.Random(1), history, mode="unanswered")
			skipped = game.current
			game.handle_action("K2")
			answered = game.current
			game.handle_action("K3")

			restored = riddles.RiddleHistory(path)
			self.assertNotIn(riddles.question_key(skipped[0]), restored.answered)
			self.assertIn(riddles.question_key(answered[0]), restored.answered)
			unanswered = riddles.RiddleGame(self.bank, random.Random(2), restored, mode="unanswered")
			unanswered_questions = {unanswered.riddles[index] for index in unanswered.order}
			self.assertIn(skipped, unanswered_questions)
			self.assertNotIn(answered, unanswered_questions)
			replay = riddles.RiddleGame(self.bank, random.Random(3), restored, mode="answered")
			self.assertEqual({replay.riddles[index] for index in replay.order}, {answered})

	def test_legacy_history_is_preserved_as_answered(self):
		with tempfile.TemporaryDirectory() as directory:
			path = os.path.join(directory, "history.json")
			old_keys = [riddles.question_key(question) for question, _ in self.bank[:2]]
			with open(path, "w", encoding="utf-8") as output:
				json.dump({"seen": old_keys, "last": old_keys[-1]}, output)
			history = riddles.RiddleHistory(path)
			self.assertEqual(history.answered, set(old_keys))
			history.record(self.bank[2][0])
			restored = riddles.RiddleHistory(path)
			self.assertEqual(restored.answered, set(old_keys))
			self.assertIn(riddles.question_key(self.bank[2][0]), restored.seen)

	def test_all_mode_cycles_across_restarts_without_clearing_answers(self):
		with tempfile.TemporaryDirectory() as directory:
			path = os.path.join(directory, "history.json")
			questions = []
			for seed in range(len(self.bank) * 2):
				history = riddles.RiddleHistory(path)
				game = riddles.RiddleGame(self.bank, random.Random(seed), history, mode="all")
				questions.append(game.current)
				game.handle_action("K3")
			self.assertEqual(len(set(questions[:len(self.bank)])), len(self.bank))
			self.assertEqual(len(set(questions[len(self.bank):])), len(self.bank))
			self.assertNotEqual(questions[len(self.bank) - 1], questions[len(self.bank)])
			self.assertEqual(len(riddles.RiddleHistory(path).answered), len(self.bank))

	def test_reveal_and_navigation(self):
		game = riddles.RiddleGame(self.bank, random.Random(12))
		first = game.current
		self.assertFalse(game.revealed)
		game.handle_action("K3")
		self.assertTrue(game.revealed)
		game.handle_action("K2")
		self.assertNotEqual(first, game.current)
		self.assertFalse(game.revealed)
		game.handle_action("K1")
		self.assertEqual(first, game.current)
		self.assertFalse(game.revealed)

	def test_draws_are_unique_and_restart_is_explicit(self):
		game = riddles.RiddleGame(self.bank, random.Random(12))
		questions = [game.current]
		for _ in range(len(self.bank) - 1):
			game.handle_action("K2")
			questions.append(game.current)
		self.assertEqual(len(set(questions)), len(self.bank))
		last = game.current
		game.handle_action("K2")
		self.assertTrue(game.at_end)
		game.handle_action("K1")
		self.assertFalse(game.at_end)
		self.assertEqual(last, game.current)
		game.handle_action("K2")
		self.assertTrue(game.at_end)
		game.handle_action("K3")
		self.assertFalse(game.at_end)
		self.assertNotEqual(last, game.current)

	def test_history_prevents_repeats_across_launches(self):
		with tempfile.TemporaryDirectory() as directory:
			path = os.path.join(directory, "history.json")
			first = riddles.RiddleGame(self.bank, random.Random(1), riddles.RiddleHistory(path))
			seen = {first.current}
			first.handle_action("K2")
			seen.add(first.current)
			second = riddles.RiddleGame(self.bank, random.Random(2), riddles.RiddleHistory(path))
			while not second.at_end:
				self.assertNotIn(second.current, seen)
				seen.add(second.current)
				second.handle_action("K2")
			self.assertEqual(len(seen), len(self.bank))
			third = riddles.RiddleGame(self.bank, random.Random(3), riddles.RiddleHistory(path))
			self.assertTrue(third.at_end)
			self.assertIsNone(third.current)
			third.handle_action("K3")
			self.assertFalse(third.at_end)
			self.assertIsNotNone(third.current)

	def test_corrupt_history_and_duplicate_questions(self):
		with tempfile.TemporaryDirectory() as directory:
			path = os.path.join(directory, "history.json")
			with open(path, "w", encoding="utf-8") as output:
				output.write("invalid json")
			game = riddles.RiddleGame([("同一道题？", "一"), ("同一道题?", "二")],
									  random.Random(1), riddles.RiddleHistory(path))
			self.assertEqual(len(game.riddles), 1)
			with open(path, encoding="utf-8") as source:
				self.assertEqual(len(json.load(source)["seen"]), 1)

	def test_unwritable_history_keeps_in_memory_order(self):
		with tempfile.TemporaryDirectory() as directory:
			blocker = os.path.join(directory, "not_a_directory")
			with open(blocker, "w", encoding="utf-8") as output:
				output.write("x")
			history = riddles.RiddleHistory(os.path.join(blocker, "history.json"))
			with patch("builtins.print") as output:
				game = riddles.RiddleGame(self.bank, random.Random(1), history)
				first = game.current
				game.handle_action("K2")
				self.assertNotEqual(first, game.current)
				self.assertEqual(len(history.seen), 2)
				output.assert_called_once()

	def test_history_retries_transient_replace_failure(self):
		with tempfile.TemporaryDirectory() as directory:
			path = os.path.join(directory, "history.json")
			replace = os.replace
			calls = []

			def flaky_replace(source, destination):
				calls.append((source, destination))
				if len(calls) == 1:
					raise PermissionError("temporarily locked")
				replace(source, destination)

			with patch.object(riddles.os, "replace", side_effect=flaky_replace), \
				 patch.object(riddles.time, "sleep"):
				history = riddles.RiddleHistory(path)
				history.record("题目？")
			self.assertEqual(len(calls), 2)
			self.assertFalse(history.warned)
			self.assertIn(riddles.question_key("题目？"), riddles.RiddleHistory(path).seen)

	def test_full_bank_does_not_repeat_across_restarts(self):
		bank = riddles.load_riddles()
		with tempfile.TemporaryDirectory() as directory:
			path = os.path.join(directory, "history.json")
			seen = set()
			for seed in range(len(bank)):
				game = riddles.RiddleGame(bank, random.Random(seed), riddles.RiddleHistory(path))
				self.assertFalse(game.at_end)
				self.assertNotIn(game.current[0], seen)
				seen.add(game.current[0])
			self.assertEqual(len(seen), len(bank))
			exhausted = riddles.RiddleGame(bank, random.Random(123), riddles.RiddleHistory(path))
			self.assertTrue(exhausted.at_end)


class RiddleMenuTests(unittest.TestCase):
	def setUp(self):
		self.bank = [("题目%d？" % index, "答案%d" % index) for index in range(3)]

	def test_menu_filters_and_returns_without_resetting_history(self):
		history = riddles.RiddleHistory()
		history.record(self.bank[0][0])
		history.mark_answered(self.bank[0][0])
		app = riddles.RiddleApp(self.bank, history, random.Random(1))
		self.assertEqual(app.counts(), {"all": 3, "unanswered": 2, "answered": 1})
		self.assertIsNone(app.game)
		app.handle_action("K2")
		app.handle_action("K3")
		self.assertEqual(app.game.mode, "unanswered")
		self.assertNotEqual(app.game.current, self.bank[0])
		app.handle_action("K3")
		app.handle_action("MENU")
		self.assertIsNone(app.game)
		self.assertEqual(app.counts(), {"all": 3, "unanswered": 1, "answered": 2})
		app.handle_action("K2")
		app.handle_action("K3")
		self.assertEqual(app.game.mode, "answered")
		self.assertIn(riddles.question_key(app.game.current[0]), history.answered)

	def test_empty_category_and_exhaustion_return_to_menu(self):
		history = riddles.RiddleHistory()
		app = riddles.RiddleApp(self.bank, history, random.Random(2))
		app.handle_action("K2")
		app.handle_action("K2")
		app.handle_action("K3")
		self.assertIsNone(app.game)
		self.assertTrue(app.notice)
		app.handle_action("K2")
		app.handle_action("K2")
		app.handle_action("K3")
		for _ in self.bank:
			app.handle_action("K3")
			app.handle_action("K2")
		self.assertTrue(app.game.at_end)
		app.handle_action("K3")
		self.assertIsNone(app.game)
		self.assertEqual(app.counts(), {"all": 3, "unanswered": 0, "answered": 3})
		app.handle_action("K2")
		app.handle_action("K3")
		self.assertIsNone(app.game)
		self.assertTrue(app.notice)
		self.assertEqual(len(history.answered), 3)

	def test_reset_requires_confirmation_and_survives_restart(self):
		with tempfile.TemporaryDirectory() as directory:
			path = os.path.join(directory, "history.json")
			history = riddles.RiddleHistory(path)
			history.record(self.bank[0][0])
			history.mark_answered(self.bank[0][0])
			history.record(self.bank[1][0])
			app = riddles.RiddleApp(self.bank, history, random.Random(3))
			app.handle_action("K1")
			self.assertEqual(app.OPTIONS[app.selection][0], "reset")
			app.handle_action("K3")
			self.assertTrue(app.confirm_reset)
			self.assertEqual(len(riddles.RiddleHistory(path).answered), 1)
			app.handle_action("K1")
			self.assertFalse(app.confirm_reset)
			self.assertEqual(app.counts()["answered"], 1)
			app.handle_action("K3")
			app.handle_action("K3")
			self.assertFalse(app.confirm_reset)
			self.assertEqual(app.counts(), {"all": 3, "unanswered": 3, "answered": 0})
			restored = riddles.RiddleHistory(path)
			self.assertEqual(restored.seen, set())
			self.assertEqual(restored.answered, set())
			self.assertIsNone(restored.last)

	def test_failed_reset_keeps_existing_progress(self):
		with tempfile.TemporaryDirectory() as directory:
			path = os.path.join(directory, "history.json")
			history = riddles.RiddleHistory(path)
			history.record(self.bank[0][0])
			history.mark_answered(self.bank[0][0])
			app = riddles.RiddleApp(self.bank, history, random.Random(4))
			app.handle_action("K1")
			app.handle_action("K3")
			with patch.object(riddles.os, "replace", side_effect=OSError("unwritable")), \
				 patch("builtins.print"):
				app.handle_action("K3")
			self.assertEqual(app.counts()["answered"], 1)
			self.assertIn("失败", app.notice)
			self.assertEqual(len(riddles.RiddleHistory(path).answered), 1)


class RiddleBankTests(unittest.TestCase):
	def test_packaged_bank_is_unique_and_readable(self):
		bank = riddles.load_riddles()
		self.assertEqual(len(bank), 500)
		with open(riddles.DATA_PATH, encoding="utf-8") as source:
			self.assertEqual(len(bank), len(json.load(source)))
		self.assertEqual(len({riddles.question_key(question) for question, _ in bank}), len(bank))
		for question, answer in bank:
			with self.subTest(question=question):
				self.assertTrue(question and answer)
				# 题库来自《激发无限潜能的500个脑筋急转弯游戏》原文，
				# 个别题目/答案较长；显示端 fit_text 会自动缩放适配（见布局测试）。
				self.assertLessEqual(len(question), 130)
				self.assertLessEqual(len(answer), 60)

	def test_loader_skips_invalid_and_duplicate_records(self):
		with tempfile.TemporaryDirectory() as directory:
			path = os.path.join(directory, "bank.json")
			with open(path, "w", encoding="utf-8") as output:
				json.dump([{"q": "问题？", "a": "答案"}, {"q": "问题?", "a": "重复"},
						   {"q": "", "a": "无题"}, {"q": "无答案", "a": ""}, 3], output)
			self.assertEqual(riddles.load_riddles(path), [("问题？", "答案")])


class RiddleDisplayTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		pygame.font.init()
		riddles.spi_lcd._pygame = pygame

	def test_all_questions_and_answers_fit_both_orientations(self):
		for size in ((240, 320), (320, 240)):
			display = riddles.RiddleDisplay(pygame.Surface(size))
			for question, answer in riddles.load_riddles():
				for text, rect, max_size in ((question, display.question_text_rect, 23 if display.portrait else 21),
											 (answer, display.answer_text_rect, 18 if display.portrait else 17)):
					with self.subTest(size=size, text=text):
						font, lines = display.fit_text(text, rect, max_size)
						self.assertLessEqual(len(lines) * font.get_linesize(), rect.height)
						self.assertTrue(all(font.size(line)[0] <= rect.width for line in lines))

	def test_answer_is_only_rendered_after_reveal(self):
		game = riddles.RiddleGame([("一条题目？", "秘密答案")], random.Random(1))
		for size in ((240, 320), (320, 240)):
			display = riddles.RiddleDisplay(pygame.Surface(size))
			with patch.object(display, "draw_fitted", wraps=display.draw_fitted) as draw:
				game.revealed = False
				display.draw(game)
				self.assertNotIn("秘密答案", [call.args[0] for call in draw.call_args_list])
				draw.reset_mock()
				game.handle_action("K3")
				display.draw(game)
				self.assertIn("秘密答案", [call.args[0] for call in draw.call_args_list])

	def test_keyboard_and_scaled_mouse_controls(self):
		display = riddles.RiddleDisplay(pygame.Surface((240, 320)))
		for key, action in ((pygame.K_1, "K1"), (pygame.K_2, "K2"), (pygame.K_3, "K3"),
							(pygame.K_ESCAPE, "QUIT")):
			self.assertEqual(riddles.event_action(pygame.event.Event(pygame.KEYDOWN, key=key), display), action)
		window = pygame.Surface((480, 640))
		with patch.object(pygame.display, "get_surface", return_value=window):
			for index, rect in enumerate(display.buttons):
				position = (rect.centerx * 2, rect.centery * 2)
				event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=position)
				self.assertEqual(riddles.event_action(event, display), "K%d" % (index + 1))

	def test_menu_mouse_selection_and_return_shortcuts(self):
		display = riddles.RiddleDisplay(pygame.Surface((240, 320)))
		app = riddles.RiddleApp([("题目？", "答案")], rng=random.Random(1))
		window = pygame.Surface((480, 640))
		back = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_BACKSPACE)
		self.assertEqual(riddles.riddle_event_action(back, display, app), "MENU")
		with patch.object(pygame.display, "get_surface", return_value=window):
			row = display.menu_rows[1]
			event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
									   pos=(row.centerx * 2, row.centery * 2))
			app.handle_action(riddles.riddle_event_action(event, display, app))
			self.assertEqual(app.selection, 1)
			app.handle_action("K3")
			app.handle_action("K3")
			button = display.menu_button
			event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
									   pos=(button.centerx * 2, button.centery * 2))
			self.assertEqual(riddles.riddle_event_action(event, display, app), "MENU")
			app.handle_action("MENU")
			self.assertIsNone(app.game)
			self.assertEqual(app.counts()["answered"], 1)
			row = display.menu_rows[3]
			event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
									   pos=(row.centerx * 2, row.centery * 2))
			app.handle_action(riddles.riddle_event_action(event, display, app))
			self.assertEqual(app.selection, 3)
			app.handle_action("K3")
			self.assertTrue(app.confirm_reset)
			cancel = display.buttons[0]
			event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
									   pos=(cancel.centerx * 2, cancel.centery * 2))
			app.handle_action(riddles.riddle_event_action(event, display, app))
			self.assertFalse(app.confirm_reset)
			self.assertEqual(app.counts()["answered"], 1)
			app.handle_action("K3")
			confirm = display.buttons[2]
			event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
									   pos=(confirm.centerx * 2, confirm.centery * 2))
			app.handle_action(riddles.riddle_event_action(event, display, app))
			self.assertFalse(app.confirm_reset)
			self.assertEqual(app.counts()["answered"], 0)

	def test_menu_and_reset_confirmation_fit_both_orientations(self):
		app = riddles.RiddleApp(riddles.load_riddles())
		for size in ((240, 320), (320, 240)):
			display = riddles.RiddleDisplay(pygame.Surface(size))
			with self.subTest(size=size):
				self.assertEqual(len(display.menu_rows), len(app.OPTIONS))
				for index, rect in enumerate(display.menu_rows):
					self.assertGreaterEqual(rect.height, display.font(18).get_linesize())
					self.assertLessEqual(rect.bottom, display.buttons[0].top)
					if index:
						self.assertGreaterEqual(rect.top, display.menu_rows[index - 1].bottom)
				display.draw_menu(app)
				app.selection = 3
				app.handle_action("K3")
				display.draw_menu(app)
				for text, rect, maximum in (("确定重置答题进度吗？", display.question_text_rect, 22),
										 ("已答过和已看记录将清空", display.answer_rect, 15)):
					font, lines = display.fit_text(text, rect, maximum)
					self.assertLessEqual(len(lines) * font.get_linesize(), rect.height)
					self.assertTrue(all(font.size(line)[0] <= rect.width for line in lines))
				app.handle_action("K1")

	def test_disabled_controls_keep_their_labels(self):
		display = riddles.RiddleDisplay(pygame.Surface((240, 320)))
		app = riddles.RiddleApp([("题目？", "答案")], rng=random.Random(1))
		with patch.object(display, "draw_control_buttons") as buttons:
			display.draw_menu(app)
			buttons.assert_called_with(("上选", "下选", "确定"), (True, True, True))
			app.handle_action("K3")
			display.draw_buttons(app.game)
			buttons.assert_called_with(("上题", "下题", "答案"), (False, True, True))
			app.handle_action("K3")
			display.draw_buttons(app.game)
			buttons.assert_called_with(("上题", "下题", "答案"), (False, True, False))
			app.handle_action("K2")
			display.draw_buttons(app.game)
			buttons.assert_called_with(("上题", "下题", "菜单"), (True, False, True))

	def test_disabled_control_text_is_readable_gray(self):
		display = riddles.RiddleDisplay(pygame.Surface((240, 320)))
		with patch.object(display, "font") as font:
			font.return_value.render.return_value = pygame.Surface((1, 1))
			display.draw_control_buttons(("上题", "下题", "答案"), (False, True, False))
			self.assertEqual([call.args[2] for call in font.return_value.render.call_args_list],
							 [(83, 92, 89), riddles.INK, (83, 92, 89)])

	def test_simulated_k3_hold_returns_without_revealing(self):
		with tempfile.TemporaryDirectory() as directory:
			screen = pygame.Surface((240, 320))
			now = [0.0]
			hold = riddles.spi_lcd.SimulatedHold("K3", "HOLD_K3", 1.0, clock=lambda: now[0])
			down = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_3)
			up = pygame.event.Event(pygame.KEYUP, key=pygame.K_3)
			frames = []
			events = iter(((0.0, [down, up]), (0.1, [down]), (1.2, []),
						   (1.3, [up]), (1.4, [pygame.event.Event(pygame.QUIT)])))

			def next_events():
				now[0], batch = next(events)
				return batch

			def capture_game(display, game):
				frames.append(("game", game.revealed))

			def capture_menu(display, app):
				frames.append(("menu", app.counts()["answered"]))

			with patch.object(riddles.spi_lcd, "is_simulate", return_value=True), \
				 patch.object(riddles.spi_lcd, "init", return_value=screen), \
				 patch.object(riddles.spi_lcd, "SimulatedHold", return_value=hold), \
				 patch.object(riddles, "default_history_path", return_value=os.path.join(directory, "history.json")), \
				 patch.object(riddles, "present_frame"), \
				 patch.object(riddles.RiddleDisplay, "draw", capture_game), \
				 patch.object(riddles.RiddleDisplay, "draw_menu", capture_menu), \
				 patch.object(pygame.display, "set_caption"), \
				 patch.object(pygame.event, "get", side_effect=next_events), \
				 patch.object(pygame.time, "Clock"), \
				 patch.object(pygame, "quit"), patch("builtins.print"):
				riddles.main()
			self.assertEqual(frames, [("game", False), ("game", False), ("menu", 0), ("menu", 0)])

	def test_simulator_main_displays_reveals_and_navigates(self):
		with tempfile.TemporaryDirectory() as directory:
			path = os.path.join(directory, "history.json")
			screen = pygame.Surface((320, 240))
			frames = []
			original_draw = riddles.RiddleDisplay.draw
			original_menu = riddles.RiddleDisplay.draw_menu

			def capture(display, game):
				frames.append(("game", game.current, game.revealed))
				original_draw(display, game)

			def capture_menu(display, app):
				frames.append(("menu", app.selection, app.counts()))
				original_menu(display, app)

			events = [[], [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_3),
							  pygame.event.Event(pygame.KEYUP, key=pygame.K_3)],
					  [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_3),
					   pygame.event.Event(pygame.KEYUP, key=pygame.K_3)],
					  [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_2)],
					  [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1)],
					  [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_BACKSPACE)],
					  [pygame.event.Event(pygame.QUIT)]]
			with patch.object(riddles.sys, "argv", ["Riddles.py", "--landscape"]), \
				 patch.object(riddles.spi_lcd, "is_simulate", return_value=True), \
				 patch.object(riddles.spi_lcd, "init", return_value=screen), \
				 patch.object(riddles, "default_history_path", return_value=path), \
				 patch.object(riddles, "present_frame"), \
				 patch.object(riddles.RiddleDisplay, "draw", capture), \
				 patch.object(riddles.RiddleDisplay, "draw_menu", capture_menu), \
				 patch.object(pygame.display, "set_caption"), \
				 patch.object(pygame.event, "get", side_effect=events), \
				 patch.object(pygame.time, "Clock"), \
				 patch.object(pygame, "quit"), patch("builtins.print"):
				riddles.main()
			self.assertEqual(len(frames), 6)
			self.assertEqual(frames[0][0], "menu")
			self.assertEqual(frames[1][0], "game")
			self.assertFalse(frames[1][2])
			self.assertEqual(frames[1][1], frames[2][1])
			self.assertTrue(frames[2][2])
			self.assertNotEqual(frames[1][1], frames[3][1])
			self.assertFalse(frames[3][2])
			self.assertEqual(frames[1][1], frames[4][1])
			self.assertFalse(frames[4][2])
			self.assertEqual(frames[5][0], "menu")
			self.assertEqual(frames[5][2]["answered"], 1)
			with open(path, encoding="utf-8") as source:
				data = json.load(source)
				self.assertEqual(len(data["seen"]), 2)
				self.assertEqual(len(data["answered"]), 1)

	def test_hardware_main_uses_gpio_and_cleans_up(self):
		with tempfile.TemporaryDirectory() as directory:
			screen = pygame.Surface((240, 320))
			gpio = object()
			buttons = Mock()
			buttons.poll.side_effect = [[], ["K3"], ["K3"], ["K2"], ["QUIT"]]
			frames = []
			original_draw = riddles.RiddleDisplay.draw

			def capture(display, game):
				frames.append((game.current, game.revealed))
				original_draw(display, game)

			with patch.object(riddles.spi_lcd, "is_simulate", return_value=False), \
				 patch.object(riddles.spi_lcd, "init", return_value=screen), \
				 patch.object(riddles, "importlib") as importlib_mock, \
				 patch.object(riddles, "GPIOButtons", return_value=buttons) as gpio_buttons, \
				 patch.object(riddles, "default_history_path", return_value=os.path.join(directory, "history.json")), \
				 patch.object(riddles, "present_frame"), \
				 patch.object(riddles.RiddleDisplay, "draw", capture), \
				 patch.object(pygame.time, "Clock"), \
				 patch.object(pygame, "quit"), patch("builtins.print"):
				importlib_mock.import_module.return_value = gpio
				riddles.main()
			importlib_mock.import_module.assert_called_once_with("RPi.GPIO")
			gpio_buttons.assert_called_once_with(gpio)
			buttons.cleanup.assert_called_once()
			self.assertEqual(len(frames), 3)
			self.assertFalse(frames[0][1])
			self.assertTrue(frames[1][1])
			self.assertNotEqual(frames[0][0], frames[2][0])
			self.assertFalse(frames[2][1])


class GPIOButtonTests(unittest.TestCase):
	def test_short_and_long_k3_and_navigation_buttons(self):
		class FakeGPIO:
			BCM, IN, PUD_UP, LOW = 1, 2, 3, 0

			def __init__(self):
				self.values = {5: 1, 23: 1, 24: 1}
				self.cleaned = None

			def setmode(self, mode):
				self.mode = mode

			def setup(self, pin, mode, pull_up_down):
				pass

			def input(self, pin):
				return self.values[pin]

			def cleanup(self, pins=None):
				self.cleaned = pins

		gpio = FakeGPIO()
		now = [0.0]
		buttons = riddles.GPIOButtons(gpio, clock=lambda: now[0])
		gpio.values[24] = 0
		now[0] = 0.01
		self.assertEqual(buttons.poll(), [])
		now[0] = 0.06
		self.assertEqual(buttons.poll(), [])
		gpio.values[24] = 1
		now[0] = 0.10
		self.assertEqual(buttons.poll(), [])
		now[0] = 0.15
		self.assertEqual(buttons.poll(), ["K3"])
		gpio.values[24] = 0
		now[0] = 0.20
		buttons.poll()
		now[0] = 0.25
		buttons.poll()
		now[0] = 1.30
		self.assertEqual(buttons.poll(), ["HOLD_K3"])
		gpio.values[24] = 1
		now[0] = 1.40
		buttons.poll()
		now[0] = 1.45
		self.assertEqual(buttons.poll(), [])
		gpio.values[5] = gpio.values[23] = 0
		now[0] = 1.50
		buttons.poll()
		now[0] = 1.55
		self.assertEqual(buttons.poll(), ["K1", "K2"])
		gpio.values[5] = gpio.values[23] = 1
		now[0] = 1.60
		buttons.poll()
		now[0] = 1.65
		buttons.poll()
		gpio.values[5] = 0
		now[0] = 1.70
		buttons.poll()
		now[0] = 1.75
		self.assertEqual(buttons.poll(), ["K1"])
		now[0] = 2.80
		self.assertEqual(buttons.poll(), [])
		now[0] = 3.00
		self.assertEqual(buttons.poll(), [])
		buttons.cleanup()
		self.assertEqual(gpio.cleaned, [5, 23, 24])


if __name__ == "__main__":
	unittest.main()