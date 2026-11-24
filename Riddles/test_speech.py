"""脑筋急转弯朗读文案触发的单元测试。"""
import os
import random
import tempfile
import unittest

import Riddles as riddles


class SpeechTests(unittest.TestCase):
	def setUp(self):
		self.bank = [("题目甲？", "答案甲"), ("题目乙？", "答案乙")]

	def make_app(self, directory):
		history = riddles.RiddleHistory(os.path.join(directory, "h.json"))
		return riddles.RiddleApp(self.bank, history, random.Random(1))

	def test_menu_is_silent(self):
		with tempfile.TemporaryDirectory() as directory:
			app = self.make_app(directory)
			self.assertEqual(app.speech(), (None, ""))

	def test_question_then_answer_then_next(self):
		with tempfile.TemporaryDirectory() as directory:
			app = self.make_app(directory)
			app.handle_action("K3")  # 进入“全部题目”
			key_q, text_q = app.speech()
			self.assertEqual(key_q[0], "question")
			self.assertEqual(text_q, riddles.SPEAK_QUESTION_PREFIX + app.game.current[0])
			question_key = key_q

			# 同一状态在多帧里保持稳定，不重复朗读
			self.assertEqual(app.speech(), (key_q, text_q))

			app.handle_action("K3")  # 揭晓答案
			key_a, text_a = app.speech()
			self.assertEqual(key_a[0], "answer")
			self.assertEqual(text_a, riddles.SPEAK_ANSWER_PREFIX + app.game.current[1])
			self.assertNotEqual(key_a, question_key)

			app.handle_action("K2")  # 下一题
			key_n, text_n = app.speech()
			self.assertEqual(key_n[0], "question")
			self.assertNotEqual(key_n, key_a)
			self.assertEqual(text_n, riddles.SPEAK_QUESTION_PREFIX + app.game.current[0])

	def test_previous_question_replays_its_own_text(self):
		with tempfile.TemporaryDirectory() as directory:
			app = self.make_app(directory)
			app.handle_action("K3")
			first = app.speech()
			app.handle_action("K2")
			second = app.speech()
			app.handle_action("K1")  # 回看上一题
			self.assertEqual(app.speech(), first)
			self.assertNotEqual(app.speech(), second)

	def test_returning_to_menu_stops_speech(self):
		with tempfile.TemporaryDirectory() as directory:
			app = self.make_app(directory)
			app.handle_action("K3")
			self.assertIsNotNone(app.speech()[0])
			app.handle_action("MENU")
			self.assertEqual(app.speech(), (None, ""))

	def test_prefetch_contains_current_answer_and_next_question(self):
		"""预取文本必须覆盖接下来可能朗读的内容，且与 speech 文本一致。"""
		with tempfile.TemporaryDirectory() as directory:
			app = self.make_app(directory)
			self.assertEqual(app.prefetch_texts(), [])  # 菜单无需预取
			app.handle_action("K3")  # 进入全部题目
			_, question_text = app.speech()
			ahead = app.prefetch_texts()
			# 当前答案在预取列表里，文本格式与揭晓后 speech 一致
			current_answer = riddles.SPEAK_ANSWER_PREFIX + app.game.current[1]
			self.assertIn(current_answer, ahead)
			self.assertNotIn(question_text, ahead)  # 当前题目已朗读，无需再预取
			# 下一题题目也在预取列表
			app.handle_action("K2")
			_, next_question_text = app.speech()
			self.assertIn(next_question_text, ahead)

	def test_prefetch_empty_at_end(self):
		with tempfile.TemporaryDirectory() as directory:
			app = self.make_app(directory)
			app.handle_action("K3")
			app.handle_action("K2")  # 第二题(最后一题)
			app.handle_action("K2")  # 到末尾
			self.assertTrue(app.game.at_end)
			self.assertEqual(app.prefetch_texts(), [])

	def test_all_speech_texts_covers_whole_bank(self):
		"""整库预热文本必须是每题的题目+答案，且顺序固定。"""
		texts = riddles.all_speech_texts(self.bank)
		self.assertEqual(len(texts), 2 * len(self.bank))
		self.assertEqual(texts[0], riddles.SPEAK_QUESTION_PREFIX + "题目甲？")
		self.assertEqual(texts[1], riddles.SPEAK_ANSWER_PREFIX + "答案甲")
		self.assertEqual(texts[2], riddles.SPEAK_QUESTION_PREFIX + "题目乙？")

	def test_prefetch_covers_next_questions_for_fast_press(self):
		"""连按“下一题”时后续多题文本都在预取窗口内。"""
		bank = [("题目%d？" % i, "答案%d" % i) for i in range(10)]
		app = riddles.RiddleApp(bank, riddles.RiddleHistory(None), random.Random(1))
		app.handle_action("K3")
		ahead = app.prefetch_texts()
		text_q, text_a = app.game.current
		self.assertIn(riddles.SPEAK_ANSWER_PREFIX + text_a, ahead)
		# 窗口内后续题目的题目文本也都在
		for offset in range(1, riddles.PREFETCH_LOOKAHEAD + 1):
			next_q = bank[app.game.order[app.game.position + offset]][0]
			self.assertIn(riddles.SPEAK_QUESTION_PREFIX + next_q, ahead)


if __name__ == "__main__":
	unittest.main()
