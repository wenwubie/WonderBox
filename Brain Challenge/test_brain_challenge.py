from contextlib import redirect_stdout
import io
import json
import os
import random
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import pygame

import brain_challenge as brain


class QuestionTests(unittest.TestCase):
	def test_each_round_uses_distinct_categories(self):
		history = brain.QuestionHistory()
		rng = random.Random(41)
		families = {(question.category, question.prompt, tuple(sorted(question.visual))):
					question.family or question.category
					for group in brain.QUESTION_BANK.values() for question in group}
		for round_number in range(40):
			questions = brain.build_questions(rng, history)
			with self.subTest(round=round_number + 1):
				self.assertEqual(len(questions), brain.QUESTIONS_PER_GAME)
				self.assertEqual(len({question.category for question in questions}), brain.QUESTIONS_PER_GAME)
				question_families = {families[(question.category, question.prompt, tuple(sorted(question.visual)))]
									 for question in questions}
				self.assertEqual(len(question_families), brain.QUESTIONS_PER_GAME)

	def test_shared_question_formats_are_not_repeated_in_a_round(self):
		def find(category, prompt):
			return next(question for question in brain.QUESTION_BANK[category] if question.prompt == prompt)

		pairs = (
			(("动脑筋", "今天周一，明天是周几？"), ("时间日历", "今天周日，再过2天是？")),
			(("算一算", "1 + 1 = ？"), ("动脑筋", "比5大2的数是几？")),
			(("算一算", "3 - 1 = ？"), ("动脑筋", "4支笔拿走1支，还剩几支？")),
			(("小常识", "向北的相反方向是？"), ("方向空间", "面向北，转身后面向哪边？")),
			(("动脑筋", "一根绳剪一刀，分成几段？"), ("逻辑推理", "一根绳子剪两刀，最多几段？")),
			(("小常识", "红灯亮时应该怎么做？"), ("安全守护", "过马路时红灯亮了应？")),
			(("小常识", "过马路应走哪里？"), ("安全守护", "过马路应优先走哪里？")),
			(("小常识", "吃东西前要先做什么？"), ("安全守护", "吃东西前应该做什么？")),
			(("小常识", "水结冰后是什么？"), ("科学发现", "水受冷变成冰称为？")),
		)
		for first_info, second_info in pairs:
			first = find(*first_info)
			second = find(*second_info)
			with self.subTest(first=first.prompt, second=second.prompt):
				self.assertTrue(first.family)
				self.assertEqual(first.family, second.family)
				other_categories = [category for category in brain.QUESTION_BANK
									if category not in (first.category, second.category)][:2]
				fillers = [brain.QUESTION_BANK[category][0] for category in other_categories]
				for seed in range(20):
					selected = brain.QuestionHistory().select(random.Random(seed), [first, second, *fillers], 3)
					self.assertEqual(len(selected), 3)
					self.assertFalse(first in selected and second in selected)

	def test_round_includes_more_question_types(self):
		new_categories = {"词语乐园", "时间日历", "方向空间", "逻辑推理", "科学发现", "自然地理", "安全守护"}
		self.assertTrue(new_categories.issubset(brain.QUESTION_BANK))
		observed_categories = set()
		for seed in range(20):
			questions = brain.build_questions(random.Random(seed))
			categories = {question.category for question in questions}
			self.assertEqual(len(questions), brain.QUESTIONS_PER_GAME)
			self.assertEqual(len(categories), brain.QUESTIONS_PER_GAME)
			self.assertGreaterEqual(len(new_categories.intersection(categories)), 5)
			observed_categories.update(categories)
		self.assertTrue(new_categories.issubset(observed_categories))

	def test_new_categories_remain_varied_across_many_games(self):
		new_categories = {"词语乐园", "时间日历", "方向空间", "逻辑推理", "科学发现", "自然地理", "安全守护"}
		history = brain.QuestionHistory()
		rng = random.Random(41)
		for block in range(9):
			observed_categories = set()
			for _ in range(20):
				observed_categories.update(question.category for question in brain.build_questions(rng, history))
			with self.subTest(games="%d-%d" % (block * 20 + 1, (block + 1) * 20)):
				self.assertTrue(new_categories.issubset(observed_categories))

	def test_new_question_examples_have_correct_answers(self):
		examples = (
			("词语乐园", "“高兴”的近义词是？", "开心"),
			("词语乐园", "“高”的反义词是？", "矮"),
			("时间日历", "钟表12时，过1小时是？", "1时"),
			("时间日历", "今天周日，再过2天是？", "周二"),
			("方向空间", "面向北，右转后面向哪边？", "东"),
			("方向空间", "向东走1步，再向北走1步，在起点哪边？", "东北"),
			("方向空间", "向西走2步，再向南走1步，在起点哪边？", "西南"),
			("方向空间", "笔在橡皮的上边，橡皮在笔的哪边？", "下"),
			("逻辑推理", "小明比小红高，小红比小华高，谁最高？", "小明"),
			("科学发现", "地球绕着哪颗恒星运行？", "太阳"),
			("自然地理", "中国的首都是哪里？", "北京"),
			("安全守护", "在中国遇到火灾可拨打？", "119"),
		)
		for category, prompt, answer in examples:
			with self.subTest(category=category, prompt=prompt):
				matches = [spec for spec in brain.QUESTION_BANK[category] if spec.prompt == prompt]
				self.assertEqual(len(matches), 1)
				self.assertEqual(matches[0].correct, answer)

	def test_generated_time_and_direction_answers(self):
		days = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
		for spec in brain.QUESTION_BANK["时间日历"]:
			with self.subTest(prompt=spec.prompt):
				clock = re.fullmatch(r"钟表(\d+)时，(过|往前拨)(\d+)小时是？", spec.prompt)
				half_hour = re.fullmatch(r"(\d+)时30分，过半小时是？", spec.prompt)
				calendar = re.fullmatch(r"今天(周.)，再过(\d+)天是？", spec.prompt)
				if clock:
					offset = int(clock[3]) * (1 if clock[2] == "过" else -1)
					answer = "%d时" % ((int(clock[1]) - 1 + offset) % 12 + 1)
				elif half_hour:
					answer = "%d时整" % (int(half_hour[1]) % 12 + 1)
				else:
					self.assertIsNotNone(calendar)
					answer = days[(days.index(calendar[1]) + int(calendar[2])) % 7]
				self.assertEqual(spec.correct, answer)
		vectors = {"东": (1, 0), "西": (-1, 0), "北": (0, 1), "南": (0, -1)}
		clockwise = ("北", "东", "南", "西")
		offsets = {"左转": -1, "右转": 1, "转身": 2}
		opposites = {"左": "右", "右": "左", "上": "下", "下": "上"}
		for spec in brain.QUESTION_BANK["方向空间"]:
			with self.subTest(prompt=spec.prompt):
				turn = re.fullmatch(r"面向([东南西北])，(左转|右转|转身)后面向哪边？", spec.prompt)
				twice = re.fullmatch(r"面向([东南西北])，先(左转|右转)再(左转|右转)，面向哪边？", spec.prompt)
				walk = re.fullmatch(r"向([东南西北])走(\d+)步，再向([东南西北])走(\d+)步，在起点哪边？", spec.prompt)
				position = re.fullmatch(r"(.+)在(.+)的([左右上下])边，(.+)在(.+)的哪边？", spec.prompt)
				if turn:
					answer = clockwise[(clockwise.index(turn[1]) + offsets[turn[2]]) % 4]
				elif twice:
					answer = clockwise[(clockwise.index(twice[1]) + offsets[twice[2]] + offsets[twice[3]]) % 4]
				elif walk:
					first = vectors[walk[1]]
					second = vectors[walk[3]]
					x = first[0] * int(walk[2]) + second[0] * int(walk[4])
					y = first[1] * int(walk[2]) + second[1] * int(walk[4])
					answer = ("东" if x > 0 else "西" if x < 0 else "")
					answer += ("北" if y > 0 else "南" if y < 0 else "")
				else:
					self.assertIsNotNone(position)
					self.assertEqual((position[1], position[2]), (position[5], position[4]))
					answer = opposites[position[3]]
				self.assertEqual(spec.correct, answer)

	def test_generated_logic_ordering_answers(self):
		patterns = (
			r"(.+?)比(.+?)高，(.+?)比(.+?)高，(谁最高|谁最矮)？",
			r"(.+?)在(.+?)前面，(.+?)在(.+?)前面，(三人中谁最前|三人中谁最后)？",
			r"(.+?)比(.+?)早到，(.+?)比(.+?)早到，(谁最早到|谁最晚到)？",
		)
		checked = 0
		for spec in brain.QUESTION_BANK["逻辑推理"]:
			match = next((match for pattern in patterns if (match := re.fullmatch(pattern, spec.prompt))), None)
			if match:
				with self.subTest(prompt=spec.prompt):
					self.assertEqual(match[2], match[3])
					answer = match[4] if match[5] in ("谁最矮", "三人中谁最后", "谁最晚到") else match[1]
					self.assertEqual(spec.correct, answer)
					self.assertEqual({spec.correct, *spec.wrong_choices}, {match[1], match[2], match[4]})
				checked += 1
		self.assertEqual(checked, 108)

	def test_bank_has_at_least_thousand_distinct_questions(self):
		questions = [question for group in brain.QUESTION_BANK.values() for question in group]
		self.assertGreaterEqual(len(questions), 1000)
		self.assertEqual(len({question.identity for question in questions}), len(questions))
		for category, group in brain.QUESTION_BANK.items():
			with self.subTest(category=category):
				self.assertGreaterEqual(len(group), 40)
		for question in questions:
			if question.wrong_choices:
				self.assertEqual(len({question.correct, *question.wrong_choices}), 3)

	def test_generated_answers_match_every_question(self):
		shapes = {prompt: shape for shape, prompt in brain.VISUAL_SHAPES}
		groups = {"%s属于哪一类？" % item: category
				  for category, items in brain.FACT_GROUPS for item in items}
		days = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
		for category, group in brain.QUESTION_BANK.items():
			for question in group:
				if category == "算一算":
					match = re.fullmatch(r"(\d+) ([+-]) (\d+) = ？", question.prompt)
					self.assertIsNotNone(match)
					first, second = int(match[1]), int(match[3])
					answer = first + second if match[2] == "+" else first - second
					self.assertEqual(int(question.correct), answer)
				elif category == "找规律":
					parts = question.prompt.split("、")
					numbers = [int(value) for value in parts if value != "？"]
					if parts[-1] != "？":
						answer = (numbers[-1] + numbers[1]) // 2
					elif len(numbers) == 3:
						answer = numbers[-1] * 2 - numbers[-2]
					else:
						self.assertEqual(numbers[:2], numbers[2:4])
						answer = numbers[-2]
					self.assertEqual(int(question.correct), answer)
				elif category == "看图形":
					self.assertEqual(int(question.correct), question.visual.count(shapes[question.prompt]))
					self.assertEqual(len(set(question.visual)), 2)
				elif question.prompt in groups:
					self.assertEqual(question.correct, groups[question.prompt])
				elif category == "小常识":
					match = re.fullmatch(r"(\d+)月的([上下])个月是？", question.prompt)
					if match:
						direction = 1 if match[2] == "下" else -1
						answer = (int(match[1]) - 1 + direction) % 12 + 1
						self.assertEqual(question.correct, "%d月" % answer)
				elif category == "动脑筋":
					match = re.fullmatch(r"今天(周.)，(明天|昨天)是周几？", question.prompt)
					if match:
						direction = 1 if match[2] == "明天" else -1
						self.assertEqual(question.correct, days[(days.index(match[1]) + direction) % 7])
					elif not question.wrong_choices:
						prompt = question.prompt
						match = re.fullmatch(r"排队第(\d+)位，前面有几人？", prompt)
						if match:
							answer = int(match[1]) - 1
						else:
							match = re.fullmatch(r"(\d+)人排队，排第(\d+)，后面几人？", prompt)
							if match:
								answer = int(match[1]) - int(match[2])
							else:
								match = re.fullmatch(r"比(\d+)([大小])(\d+)的数是几？", prompt)
								if match:
									difference = int(match[3]) if match[2] == "大" else -int(match[3])
									answer = int(match[1]) + difference
								else:
									match = re.fullmatch(r"(\d+)盒(?:积木|贴纸|糖果)，每盒(\d+)[块张颗]，共几[块张颗]？", prompt)
									if match:
										answer = int(match[1]) * int(match[2])
									else:
										match = re.fullmatch(r"(\d+)[块张颗](?:积木|贴纸|糖果)平均分(\d+)人，每人几[块张颗]？", prompt)
										self.assertIsNotNone(match)
										self.assertEqual(int(match[1]) % int(match[2]), 0)
										answer = int(match[1]) // int(match[2])
						self.assertEqual(int(question.correct), answer)

	def test_history_avoids_repeats_across_games_and_restarts(self):
		with tempfile.TemporaryDirectory() as directory:
			path = os.path.join(directory, "history.json")
			history = brain.QuestionHistory(path)
			game = brain.BrainGame(random.Random(41), history=history)
			seen = set()
			for index in range(100):
				if index:
					game.start()
				identities = {(question.category, question.prompt, question.choices[question.answer],
								   tuple(sorted(question.visual))) for question in game.questions}
				self.assertEqual(len(identities), brain.QUESTIONS_PER_GAME)
				self.assertFalse(seen.intersection(identities))
				seen.update(identities)
			reloaded = brain.QuestionHistory(path)
			game = brain.BrainGame(random.Random(92), history=reloaded)
			identities = {(question.category, question.prompt, question.choices[question.answer],
							   tuple(sorted(question.visual))) for question in game.questions}
			self.assertFalse(seen.intersection(identities))

	def test_history_prefers_distinct_categories_over_unseen_questions(self):
		history = brain.QuestionHistory()
		unseen = [brain.QuestionSpec("新题", str(index), str(index)) for index in range(2)]
		old = brain.QuestionSpec("旧题", "看过", "答案")
		history.seen[old.identity] = 1
		history.counter = 1
		selected = history.select(random.Random(41), [old, *unseen], 2)
		self.assertIn(old, selected)
		self.assertEqual({question.category for question in selected}, {"新题", "旧题"})
		remaining = next(question for question in unseen if question not in selected)
		self.assertEqual(history.select(random.Random(41), [old, *unseen], 1), [remaining])

	def test_selection_falls_back_when_unique_types_are_unavailable(self):
		candidates = [
			brain.QuestionSpec("一类", "第一题", "答案", family="同题型"),
			brain.QuestionSpec("一类", "第二题", "答案", family="同题型"),
			brain.QuestionSpec("另一类", "第三题", "答案", family="同题型"),
		]
		selected = brain.QuestionHistory().select(random.Random(41), candidates, 3)
		self.assertEqual(set(selected), set(candidates))

	def test_existing_history_prioritizes_new_question_types(self):
		history = brain.QuestionHistory()
		original_categories = ("算一算", "找规律", "看图形", "小常识", "动脑筋")
		old_questions = [question for category in original_categories for question in brain.QUESTION_BANK[category]]
		history.seen = {question.identity: index for index, question in enumerate(old_questions, 1)}
		history.counter = len(history.seen)
		questions = brain.build_questions(random.Random(41), history)
		self.assertEqual(len(questions), brain.QUESTIONS_PER_GAME)
		self.assertEqual(len({question.category for question in questions}), brain.QUESTIONS_PER_GAME)
		new_categories = set(brain.QUESTION_BANK) - set(original_categories)
		self.assertTrue(new_categories.issubset({question.category for question in questions}))
		self.assertEqual(len(history.seen), len(old_questions) + len(new_categories))

	def test_corrupt_history_is_replaced(self):
		with tempfile.TemporaryDirectory() as directory:
			path = os.path.join(directory, "history.json")
			with open(path, "w", encoding="utf-8") as output:
				output.write("{")
			history = brain.QuestionHistory(path)
			brain.BrainGame(random.Random(41), history=history)
			with open(path, encoding="utf-8") as source:
				self.assertEqual(len(json.load(source)["seen"]), brain.QUESTIONS_PER_GAME)

	def test_unwritable_history_keeps_in_memory_deduplication(self):
		with tempfile.TemporaryDirectory() as directory:
			path = os.path.join(directory, "history.json")
			history = brain.QuestionHistory(path)
			with patch.object(brain.os, "replace", side_effect=PermissionError), \
					patch.object(brain.time, "sleep"), redirect_stdout(io.StringIO()) as output:
				game = brain.BrainGame(random.Random(41), history=history)
				first = {(question.category, question.prompt, tuple(sorted(question.visual)))
						 for question in game.questions}
				game.start()
				second = {(question.category, question.prompt, tuple(sorted(question.visual)))
						  for question in game.questions}
			self.assertFalse(first.intersection(second))
			self.assertEqual(output.getvalue().count("题目历史无法保存"), 1)
			self.assertEqual(os.listdir(directory), [])

	def test_history_retries_temporary_access_error(self):
		with tempfile.TemporaryDirectory() as directory:
			path = os.path.join(directory, "history.json")
			history = brain.QuestionHistory(path)
			original_replace = brain.os.replace
			attempts = []

			def replace(source, destination):
				attempts.append(source)
				if len(attempts) < 3:
					raise PermissionError("temporary lock")
				original_replace(source, destination)

			with patch.object(brain.os, "replace", side_effect=replace), patch.object(brain.time, "sleep"):
				brain.BrainGame(random.Random(41), history=history)
			self.assertEqual(len(attempts), 3)
			self.assertFalse(history.warned)
			with open(path, encoding="utf-8") as source:
				self.assertEqual(len(json.load(source)["seen"]), brain.QUESTIONS_PER_GAME)

	def test_random_questions_have_valid_answers(self):
		answer_positions = set()
		for seed in range(100):
			questions = brain.build_questions(random.Random(seed))
			self.assertEqual(len(questions), brain.QUESTIONS_PER_GAME)
			self.assertEqual(len({question.category for question in questions}), brain.QUESTIONS_PER_GAME)
			self.assertEqual(len({(question.category, question.prompt, question.visual)
								  for question in questions}), brain.QUESTIONS_PER_GAME)
			for question in questions:
				self.assertEqual(len(set(question.choices)), 3)
				self.assertIn(question.answer, range(3))
				answer_positions.add(question.answer)
				if question.category == "算一算":
					match = re.fullmatch(r"(\d+) ([+-]) (\d+) = ？", question.prompt)
					self.assertIsNotNone(match)
					first, operation, second = int(match[1]), match[2], int(match[3])
					answer = first + second if operation == "+" else first - second
					self.assertEqual(int(question.choices[question.answer]), answer)
				elif question.category == "找规律":
					parts = question.prompt.split("、")
					values = [int(value) for value in parts if value != "？"]
					if parts[-1] != "？":
						answer = (values[-1] + values[1]) // 2
					elif len(values) == 3:
						answer = values[-1] + values[-1] - values[-2]
					else:
						answer = values[-2]
					self.assertEqual(int(question.choices[question.answer]), answer)
				elif question.category == "看图形":
					shape = dict((prompt, shape) for shape, prompt in brain.VISUAL_SHAPES)[question.prompt]
					self.assertEqual(int(question.choices[question.answer]), question.visual.count(shape))
					self.assertGreater(len(question.visual), question.visual.count(shape))
		self.assertEqual(answer_positions, {0, 1, 2})


class BrainDisplayTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		pygame.font.init()

	def test_all_questions_fit_both_screen_orientations(self):
		for size in ((320, 240), (240, 320)):
			with patch.object(brain.spi_lcd, "_pygame", pygame):
				display = brain.BrainDisplay(pygame.Surface(size))
			for group in brain.QUESTION_BANK.values():
				for spec in group:
					with self.subTest(size=size, prompt=spec.prompt, visual=spec.visual):
						prompt_rect = display.prompt_rect if spec.visual else display.prompt_rect.union(display.visual_rect)
						fits = False
						for font in display.prompt_fonts:
							lines = brain.wrap_text(spec.prompt, font, prompt_rect.width - font.size("？")[0])
							if (len(lines) * font.get_linesize() <= prompt_rect.height and
									all(font.size(line)[0] <= prompt_rect.width for line in lines) and
									all(not line.startswith(("，", "。", "？", "！", "、")) for line in lines)):
								fits = True
								break
						self.assertTrue(fits)
						for choice in (spec.correct, *spec.wrong_choices):
							font, lines = display.layout_option(choice, display.options[0])
							self.assertLessEqual(len(lines) * font.get_linesize(), display.options[0].height - 4)
							self.assertTrue(all(font.size(line)[0] <= display.options[0].width - 40 for line in lines))

	def test_new_categories_render_on_both_screen_orientations(self):
		for size in ((320, 240), (240, 320)):
			with patch.object(brain.spi_lcd, "_pygame", pygame):
				display = brain.BrainDisplay(pygame.Surface(size))
			for category, group in brain.QUESTION_BANK.items():
				spec = max(group, key=lambda question: max(map(len, (question.correct, *question.wrong_choices))))
				choices = (spec.correct, *spec.wrong_choices) if spec.wrong_choices else (spec.correct, "1", "2")
				question = brain.Question(category, spec.prompt, choices, 0, spec.visual)
				game = SimpleNamespace(index=0, questions=[question], phase="answer", active_player=0,
									   elapsed=0, question=question)
				with self.subTest(size=size, category=category):
					display.draw(game)

	def test_disabled_buttons_keep_their_labels(self):
		with patch.object(brain.spi_lcd, "_pygame", pygame):
			display = brain.BrainDisplay(pygame.Surface((240, 320)))
		cases = (("ready", ("选1", "选2", "开始"), (False, False, True)),
				 ("answer", ("选1", "选2", "选3"), (True, True, True)),
				 ("feedback", ("选1", "选2", "选3"), (False, False, False)),
				 ("finished", ("选1", "选2", "再玩"), (False, False, True)))
		with patch.object(display, "centered") as centered:
			for phase, labels, enabled in cases:
				with self.subTest(phase=phase):
					centered.reset_mock()
					display.draw_buttons(SimpleNamespace(phase=phase))
					self.assertEqual(tuple(call.args[0] for call in centered.call_args_list), labels)
					for call, active in zip(centered.call_args_list, enabled):
						self.assertEqual(call.args[2], brain.PAPER if active else (83, 92, 89))


class BrainGameTests(unittest.TestCase):
	def setUp(self):
		self.game = brain.BrainGame(random.Random(41))

	def start_player(self):
		self.assertEqual(self.game.phase, "ready")
		self.game.handle_action("K3")
		self.assertEqual(self.game.phase, "answer")

	def play_player(self, correct_count, seconds):
		self.start_player()
		questions = []
		for index in range(brain.QUESTIONS_PER_GAME):
			self.assertEqual(self.game.index, index)
			question = self.game.question
			questions.append(question)
			self.game.update(seconds)
			choice = question.answer if index < correct_count else (question.answer + 1) % 3
			self.game.handle_action(brain.BUTTON_ACTIONS[choice])
			self.assertEqual(self.game.phase, "feedback")
			self.game.update(brain.FEEDBACK_SECONDS)
		return questions

	def test_players_answer_same_questions_in_order(self):
		first_questions = self.play_player(7, 1.23)
		self.assertEqual(self.game.phase, "ready")
		self.assertEqual(self.game.active_player, 1)
		self.assertEqual(self.game.scores, [7, 0])
		self.assertEqual(self.game.times, [1230, 0])
		self.game.update(60.0)
		self.assertEqual(self.game.phase, "ready")
		second_questions = self.play_player(6, 0.5)
		self.assertEqual(first_questions, second_questions)
		self.assertEqual(self.game.phase, "finished")
		self.assertEqual(self.game.scores, [7, 6])
		self.assertEqual(self.game.times, [1230, 500])
		self.assertEqual(self.game.winner, 0)
		self.game.handle_action("K3")
		self.assertEqual(self.game.phase, "ready")
		self.assertEqual(self.game.active_player, 0)
		self.assertEqual(self.game.index, 0)
		self.assertEqual(self.game.scores, [0, 0])
		self.assertEqual(self.game.times, [0, 0])

	def test_equal_scores_are_decided_by_total_time(self):
		self.play_player(6, 1.23)
		self.play_player(6, 1.21)
		self.assertEqual(self.game.scores, [6, 6])
		self.assertEqual(self.game.times, [1230, 1210])
		self.assertEqual(self.game.winner, 1)

	def test_start_requires_k3(self):
		self.game.handle_action("K1")
		self.game.handle_action("K2")
		self.assertEqual(self.game.phase, "ready")
		self.game.handle_action("K3")
		self.assertEqual(self.game.phase, "answer")

	def test_k3_short_press_records_the_press_time(self):
		self.start_player()
		self.game.update(1.23)
		self.game.handle_action("K3_DOWN")
		self.game.update(0.5)
		self.assertEqual(self.game.phase, "answer")
		self.assertEqual(self.game.answers[0], [])
		self.game.handle_action("K3")
		self.assertEqual(self.game.answers[0][0].choice, 2)
		self.assertEqual(self.game.answers[0][0].elapsed_centiseconds, 123)

	def test_k3_hold_does_not_timeout_or_submit_an_answer(self):
		self.start_player()
		self.game.update(brain.QUESTION_SECONDS - 0.1)
		self.game.handle_action("K3_DOWN")
		self.game.update(1.1)
		self.assertEqual(self.game.phase, "answer")
		self.assertEqual(self.game.answers[0], [])

	def test_k3_release_does_not_answer_after_another_choice(self):
		self.start_player()
		self.game.handle_action("K3_DOWN")
		self.game.handle_action("K1")
		self.game.update(brain.FEEDBACK_SECONDS)
		self.game.handle_action("K3")
		self.assertEqual(self.game.phase, "answer")
		self.assertEqual(len(self.game.answers[0]), 1)

	def test_simulated_k3_short_long_and_focus_loss_in_main_loop(self):
		pygame.font.init()
		for outcome in ("short", "long", "focus"):
			with self.subTest(outcome=outcome):
				game = brain.BrainGame(random.Random(41), brain.QuestionHistory())
				screen = pygame.Surface((240, 320))
				window = pygame.Surface((480, 640))
				now = [0.0]
				hold = brain.spi_lcd.SimulatedHold("K3", "QUIT", 1.0, clock=lambda: now[0])
				with patch.object(brain.spi_lcd, "_pygame", pygame):
					display = brain.BrainDisplay(screen)
				rect = display.options[2]
				position = (rect.centerx * 2, rect.centery * 2)
				key_down = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_3)
				key_up = pygame.event.Event(pygame.KEYUP, key=pygame.K_3)
				mouse_down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=position)
				mouse_up = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=position)
				if outcome == "long":
					tail = [(1.2, [])]
				elif outcome == "focus":
					tail = [(0.2, [pygame.event.Event(pygame.WINDOWFOCUSLOST)]), (0.3, [])]
				else:
					tail = [(0.3, [mouse_up])]
				events = iter([(0.0, [key_down, key_up]), (0.1, [mouse_down]), *tail,
							   (1.3, [pygame.event.Event(pygame.QUIT)])])

				def next_events():
					now[0], batch = next(events)
					return batch

				with patch.object(brain.spi_lcd, "_pygame", pygame), \
					 patch.object(brain.spi_lcd, "is_simulate", return_value=True), \
					 patch.object(brain.spi_lcd, "init", return_value=screen), \
					 patch.object(brain.spi_lcd, "SimulatedHold", return_value=hold), \
					 patch.object(brain, "BrainGame", return_value=game), \
					 patch.object(brain, "QuestionHistory", return_value=object()), \
					 patch.object(brain.BrainDisplay, "draw"), patch.object(brain, "present_frame"), \
					 patch.object(pygame.display, "get_surface", return_value=window), \
					 patch.object(pygame.display, "set_caption"), \
					 patch.object(pygame.event, "get", side_effect=next_events), \
					 patch.object(pygame.time, "Clock") as clock, \
					 patch.object(pygame, "quit"), patch("builtins.print"):
					clock.return_value.tick.side_effect = [0, 1230, 200, 30000, 0]
					brain.main()
				if outcome == "long":
					self.assertEqual(game.answers[0], [])
					self.assertAlmostEqual(game.elapsed, 1.23)
				elif outcome == "focus":
					self.assertIsNone(game.answers[0][0].choice)
					self.assertIsNone(game.k3_pending)
				else:
					self.assertEqual(game.answers[0][0].choice, 2)
					self.assertEqual(game.answers[0][0].elapsed_centiseconds, 123)

	def test_equal_scores_and_time_are_tied(self):
		self.play_player(5, 1.0)
		self.play_player(5, 1.0)
		self.assertEqual(self.game.scores, [5, 5])
		self.assertEqual(self.game.times, [1000, 1000])
		self.assertIsNone(self.game.winner)

	def test_timeout_counts_as_wrong_and_records_full_limit(self):
		self.start_player()
		self.game.update(brain.QUESTION_SECONDS - 0.01)
		self.assertEqual(self.game.phase, "answer")
		self.game.update(0.02)
		self.assertEqual(self.game.phase, "feedback")
		record = self.game.answers[0][0]
		self.assertIsNone(record.choice)
		self.assertFalse(record.correct)
		self.assertEqual(record.elapsed_centiseconds, round(brain.QUESTION_SECONDS * 100))
		self.game.handle_action(brain.BUTTON_ACTIONS[self.game.question.answer])
		self.assertEqual(len(self.game.answers[0]), 1)
		self.game.update(brain.FEEDBACK_SECONDS)
		self.assertEqual(self.game.index, 1)
		self.assertEqual(self.game.elapsed, 0.0)
		self.assertEqual(self.game.phase, "answer")

	def test_waiting_and_feedback_do_not_count_as_answer_time(self):
		self.game.update(60.0)
		self.assertEqual(self.game.elapsed, 0.0)
		self.start_player()
		self.game.update(1.23)
		self.game.handle_action(brain.BUTTON_ACTIONS[self.game.question.answer])
		self.game.update(brain.FEEDBACK_SECONDS - 0.01)
		self.game.handle_action("K3")
		self.assertEqual(self.game.times, [123, 0])
		self.assertEqual(len(self.game.answers[0]), 1)
		self.assertEqual(self.game.phase, "feedback")
		self.game.update(0.02)
		self.assertEqual(self.game.phase, "answer")
		self.assertEqual(self.game.elapsed, 0.0)

	def test_mouse_can_select_answer(self):
		display = SimpleNamespace(
			width=240, height=320,
			buttons=[pygame.Rect(7 + index * 75, 288, 70, 26) for index in range(3)],
			scores=[pygame.Rect(9, 35, 82, 24), pygame.Rect(149, 35, 82, 24)],
			options=[pygame.Rect(9, 158 + index * 35, 222, 31) for index in range(3)],
		)
		window = pygame.Surface((480, 640))
		with patch.object(pygame.display, "get_surface", return_value=window):
			self.start_player()
			option = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(200, 488))
			self.assertEqual(brain.action_from_event(option, display, self.game), "K3")


class TimedGPIOButtonsTests(unittest.TestCase):
	def setUp(self):
		self.now = [0.0]
		self.levels = {pin: 1 for pin in brain.wheel_support.BUTTON_PINS.values()}
		self.gpio = SimpleNamespace(
			BCM="BCM", IN="IN", PUD_UP="PUD_UP", LOW=0,
			setmode=Mock(), setup=Mock(), input=self.levels.__getitem__, cleanup=Mock(),
		)
		self.buttons = brain.TimedGPIOButtons(self.gpio, clock=lambda: self.now[0])

	def debounce(self):
		self.now[0] += brain.wheel_support.DEBOUNCE_SECONDS + 0.001

	def test_choices_preserve_k3_press_and_release(self):
		for action, pin in brain.wheel_support.BUTTON_PINS.items():
			with self.subTest(action=action):
				self.levels[pin] = self.gpio.LOW
				self.assertEqual(self.buttons.poll(), [])
				self.debounce()
				self.assertEqual(self.buttons.poll(), ["K3_DOWN" if action == "K3" else action])
				self.assertEqual(self.buttons.poll(), [])
				self.levels[pin] = 1
				self.assertEqual(self.buttons.poll(), [])
				self.debounce()
				self.assertEqual(self.buttons.poll(), ["K3"] if action == "K3" else [])
		self.buttons.cleanup()
		self.gpio.cleanup.assert_called_once_with(list(brain.wheel_support.BUTTON_PINS.values()))

	def test_long_press_k3_quits_without_a_second_choice(self):
		pin = brain.wheel_support.BUTTON_PINS["K3"]
		self.levels[pin] = self.gpio.LOW
		self.assertEqual(self.buttons.poll(), [])
		self.debounce()
		self.assertEqual(self.buttons.poll(), ["K3_DOWN"])
		self.now[0] += brain.wheel_support.QUIT_HOLD_SECONDS + 0.01
		self.assertEqual(self.buttons.poll(), ["QUIT"])
		self.assertEqual(self.buttons.poll(), [])
		self.levels[pin] = 1
		self.assertEqual(self.buttons.poll(), [])
		self.debounce()
		self.assertEqual(self.buttons.poll(), [])


if __name__ == "__main__":
	unittest.main()