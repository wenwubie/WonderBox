import random
import json
from contextlib import closing
import io
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zlib

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

import build_corpus
import poetry


class PoetryQuestionTests(unittest.TestCase):
    def test_choices_are_distinct_and_answer_is_shuffled(self):
        positions = set()
        rng = random.Random(12)
        for _ in range(30):
            question = poetry.make_question("作者", "《静夜思》的作者是？", "李白",
                                            ("杜甫", "李白", "王维", "杜甫"), "李白", rng)
            self.assertEqual(len(set(question.choices)), 3)
            self.assertEqual(question.choices[question.answer], "李白")
            positions.add(question.answer)
        self.assertEqual(positions, {0, 1, 2})

    def test_requires_two_distinct_distractors(self):
        with self.assertRaises(ValueError):
            poetry.make_question("作者", "作者是？", "李白", ("杜甫", "杜甫"), "", random.Random(1))

    def test_downloader_retries_empty_data(self):
        responses = (io.BytesIO(b"[]"), io.BytesIO(b'[{"author":"test"}]'))
        with patch.object(build_corpus, "urlopen", side_effect=responses) as request:
            genre, path, records = build_corpus.download_json(("唐诗", "test.json"))
        self.assertEqual((genre, path, records), ("唐诗", "test.json", [{"author": "test"}]))
        self.assertEqual(request.call_count, 2)

    def test_build_writes_license_and_does_not_replace_an_existing_one(self):
        record = {"author": "王维", "title": "山居秋暝", "paragraphs": ["空山新雨后，天气晚来秋。"]}
        sources = (("唐诗", "fixture.json"),)
        converter = SimpleNamespace(OpenCC=lambda mode: SimpleNamespace(convert=lambda value: value))
        for existing_license in (False, True):
            with self.subTest(existing_license=existing_license), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "data" / "test.sqlite3"
                license_path = path.parent / "UPSTREAM_LICENSE.txt"
                if existing_license:
                    path.parent.mkdir()
                    license_path.write_bytes(b"existing license")
                with patch.object(sys, "argv", ["build_corpus.py", "--output", str(path)]), \
                        patch.dict(sys.modules, {"opencc": converter}), \
                        patch.object(build_corpus, "SOURCE_FILES", sources), \
                        patch.object(build_corpus, "POPULAR_FILES", ()), \
                        patch.object(build_corpus, "COMMON_VARIANTS", ()), \
                        patch.object(build_corpus, "download_json", return_value=("唐诗", "fixture.json", [record])), \
                        patch.object(build_corpus, "download_license", return_value=b"upstream license") as download, \
                        patch("builtins.print"):
                    build_corpus.main()
                self.assertTrue(path.is_file())
                self.assertEqual(license_path.read_bytes(), b"existing license" if existing_license else b"upstream license")
                self.assertEqual(download.call_count, 0 if existing_license else 1)

    def test_build_retains_original_works_and_rejects_ambiguous_stems(self):
        first = {"author": "李白", "title": "静夜思",
                 "paragraphs": ["床前明月光，疑是地上霜。"], "id": "first", "notes": ["原始注释"]}
        second = {"author": "杜甫", "title": "另一首诗",
                  "paragraphs": ["床前明月光，梦里见故乡。"]}
        third = {"author": "王维", "title": "山居秋暝",
                 "paragraphs": ["空山新雨后，天气晚来秋。"]}
        sources = [("唐诗", "demo.json", [first, second, third])]
        popular = [("唐诗", "popular.json", [first])]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite3"
            stats = build_corpus.build_database(path, sources, popular, lambda value: value)
            with closing(sqlite3.connect(path)) as database:
                original, classic = database.execute("SELECT original, classic FROM works WHERE author = ?",
                                                     ("李白",)).fetchone()
                rows = database.execute("SELECT kind, stem, answer FROM questions").fetchall()
            self.assertEqual(stats["tang"], 3)
            self.assertEqual(json.loads(zlib.decompress(original)), first)
            self.assertEqual(classic, 1)
            self.assertFalse(any(stem == "床前明月光" for _, stem, _ in rows))
            self.assertIn(("续句", "空山新雨后", "天气晚来秋"), rows)

    def test_common_version_is_added_without_replacing_the_historical_text(self):
        old_version = {"author": "李白", "title": "静夜思",
                       "paragraphs": ["床前看月光，疑是地上霜。", "举头望山月，低头思故乡。"]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite3"
            build_corpus.build_database(path, [("唐诗", "source.json", [old_version])],
                                        build_corpus.COMMON_VARIANTS, lambda value: value)
            with closing(sqlite3.connect(path)) as database:
                works = database.execute("SELECT paragraphs FROM works").fetchall()
                rows = database.execute("SELECT kind, stem, answer, classic FROM questions").fetchall()
            self.assertEqual(len(works), 2)
            self.assertIn(("续句", "床前明月光", "疑是地上霜", 1), rows)
            self.assertIn(("续句", "床前看月光", "疑是地上霜", 0), rows)

    def test_children_round_uses_familiar_works_and_correct_answers(self):
        path = Path(poetry.DATA_FILE).parent / "children_poetry.json"
        works = json.loads(path.read_text(encoding="utf-8"))
        by_stem = {work["stem"]: work for work in works}
        self.assertGreaterEqual(len(works), 60)
        self.assertEqual(len(by_stem), len(works))
        self.assertEqual(by_stem["鹅鹅鹅"]["following"], "曲项向天歌")
        self.assertEqual(by_stem["白日依山尽"]["author"], "王之涣")
        self.assertEqual(by_stem["小荷才露尖尖角"]["title"], "小池")
        self.assertEqual(by_stem["儿童散学归来早"]["following"], "忙趁东风放纸鸢")
        questions = poetry.make_children_round(works, random.Random(12))
        self.assertEqual(len(questions), poetry.QUESTIONS_PER_GAME)
        self.assertEqual(sum(question.kind == "诗句接龙" for question in questions), 6)
        self.assertEqual(len({question.prompt.split("”", 1)[0] for question in questions}), len(questions))
        for question in questions:
            stem = question.prompt.split("”", 1)[0].lstrip("“")
            work = by_stem[stem]
            field = {"诗句接龙": "following", "辨认作者": "author",
                     "辨认诗题": "title", "辨认词牌": "title"}[question.kind]
            self.assertEqual(question.choices[question.answer], work[field])
            self.assertEqual(len(set(question.choices)), 3)
            self.assertEqual(question.explanation, "%s · 《%s》" % (work["author"], work["title"]))

    def test_children_rounds_prefer_easy_questions_and_match_title_types(self):
        works = json.loads(poetry.CHILDREN_DATA_FILE.read_text(encoding="utf-8"))
        poem_titles = {work["title"] for work in works if not work["genre"].endswith("词")}
        lyric_titles = {work["title"] for work in works if work["genre"].endswith("词")}
        for seed in range(50):
            questions = poetry.make_children_round(works, random.Random(seed))
            with self.subTest(seed=seed):
                self.assertEqual(sum(question.kind == "诗句接龙" for question in questions), 6)
                self.assertEqual(sum(question.kind == "辨认作者" for question in questions), 2)
                for question in questions:
                    if question.kind == "辨认诗题":
                        self.assertTrue(set(question.choices).issubset(poem_titles))
                    elif question.kind == "辨认词牌":
                        self.assertTrue(set(question.choices).issubset(lyric_titles))


class PoetryBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bank = poetry.PoetryBank()

    @classmethod
    def tearDownClass(cls):
        cls.bank.close()

    def test_option_pools_are_loaded_on_demand(self):
        with closing(poetry.PoetryBank()) as bank:
            self.assertEqual(bank.pools, {})
            bank.question(poetry.CLASSIC_MODE, "续句", random.Random(1), set())
            self.assertTrue(bank.pools)

    def test_complete_corpus_and_familiar_version_are_available(self):
        self.assertGreaterEqual(int(self.bank.metadata["tang_records"]), 57000)
        self.assertGreaterEqual(int(self.bank.metadata["song_records"]), 21000)
        self.assertEqual(self.bank.work_counts, {"唐诗": 57613, "宋词": 21061})
        row = self.bank.database.execute(
            "SELECT answer, classic FROM questions WHERE kind = ? AND stem = ?",
            ("续句", "床前明月光")).fetchone()
        self.assertEqual(tuple(row), ("疑是地上霜", 1))

    def test_every_mode_generates_balanced_unique_questions(self):
        for mode, (_, genre, _) in enumerate(poetry.MODES):
            with self.subTest(mode=mode):
                questions = self.bank.make_round(mode, random.Random(100 + mode))
                self.assertEqual(len(questions), poetry.QUESTIONS_PER_GAME)
                self.assertEqual(len({question.prompt for question in questions}), len(questions))
                self.assertEqual(len({question.prompt.split("”", 1)[0] for question in questions}), len(questions))
                self.assertTrue({"诗句接龙", "辨认作者"}.issubset({question.kind for question in questions}))
                self.assertTrue({"辨认诗题", "辨认词牌"} & {question.kind for question in questions})
                for question in questions:
                    self.assertEqual(len(set(question.choices)), 3)
                    self.assertTrue(0 <= question.answer < 3)
                    self.assertTrue(question.explanation)
                    if genre:
                        self.assertEqual(question.genre, genre)
                    kind = {"诗句接龙": "续句", "辨认作者": "作者",
                            "辨认诗题": "作品", "辨认词牌": "作品"}[question.kind]
                    stem = question.prompt.split("”", 1)[0].lstrip("“")
                    if mode == poetry.CHILDREN_MODE:
                        work = next(work for work in self.bank.children_works if work["stem"] == stem)
                        answer = work[{"续句": "following", "作者": "author", "作品": "title"}[kind]]
                        self.assertEqual(question.choices[question.answer], answer)
                        continue
                    row = self.bank.database.execute(
                        "SELECT q.answer, q.classic, w.author, w.title FROM questions AS q "
                        "JOIN works AS w ON w.id = q.work_id WHERE q.kind = ? AND q.genre = ? AND q.stem = ?",
                        (kind, question.genre, stem)).fetchone()
                    self.assertEqual(question.choices[question.answer], row["answer"])
                    self.assertEqual(question.explanation, "%s · 《%s》" % (row["author"], row["title"]))
                    if mode == poetry.CLASSIC_MODE:
                        self.assertEqual(row["classic"], 1)

    def test_many_rounds_have_no_repeated_verses(self):
        for mode in range(len(poetry.MODES)):
            for seed in range(10):
                with self.subTest(mode=mode, seed=seed):
                    questions = self.bank.make_round(mode, random.Random(seed))
                    verses = [question.prompt.split("”", 1)[0] for question in questions]
                    self.assertEqual(len(set(verses)), poetry.QUESTIONS_PER_GAME)
                    self.assertTrue(all(len(set(question.choices)) == 3 for question in questions))


class PoetryGameTests(unittest.TestCase):
    def test_children_mode_runs_a_full_game_with_buttons(self):
        with closing(poetry.PoetryBank()) as bank:
            game = poetry.PoetryGame(bank, random.Random(42))
            self.assertEqual(game.mode, poetry.CHILDREN_MODE)
            self.assertEqual(poetry.MODES[game.mode][0], "儿童诗词")
            game.handle_action("K3")
            for index in range(poetry.QUESTIONS_PER_GAME):
                self.assertEqual((game.phase, game.index), ("answer", index))
                game.handle_action("K%d" % (game.question.answer + 1))
                self.assertEqual(game.phase, "feedback")
                game.handle_action("K3")
            self.assertEqual((game.phase, game.score), ("summary", poetry.QUESTIONS_PER_GAME))
            game.handle_action("K3")
            self.assertEqual((game.phase, game.score), ("answer", 0))
            game.handle_action("BACK")
            self.assertEqual(game.phase, "menu")
            self.assertEqual(game.handle_action("BACK"), "EXIT")

    def test_answer_feedback_summary_restart_and_back(self):
        question = poetry.make_question("作者", "作者是？", "李白", ("杜甫", "王维"), "李白", random.Random(3))
        bank = Mock()
        bank.make_round.return_value = [question, question]
        game = poetry.PoetryGame(bank, random.Random(4))
        game.handle_action("K2")
        self.assertEqual(game.mode, 1)
        game.handle_action("K3")
        self.assertEqual(game.phase, "answer")
        game.handle_action("K%d" % (question.answer + 1))
        self.assertEqual((game.phase, game.score), ("feedback", 1))
        game.handle_action("K1")
        self.assertEqual(game.phase, "feedback")
        game.handle_action("K3")
        game.handle_action("K%d" % ((question.answer + 1) % 3 + 1))
        self.assertEqual(game.score, 1)
        game.handle_action("K3")
        self.assertEqual(game.phase, "summary")
        game.handle_action("HOLD_K3")
        self.assertEqual(game.phase, "summary")
        game.handle_action("K3")
        self.assertEqual((game.phase, game.score), ("answer", 0))
        game.handle_action("BACK")
        self.assertEqual(game.phase, "menu")
        self.assertEqual(game.handle_action("BACK"), "EXIT")


class PoetryDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()

    def make_game(self, questions):
        bank = Mock()
        bank.metadata = {"classic_works": "647", "works": "78674"}
        bank.work_counts = {"唐诗": 57613, "宋词": 21061}
        bank.children_works = [None] * 77
        bank.make_round.return_value = questions
        return poetry.PoetryGame(bank, random.Random(1))

    def test_button_and_disabled_text_have_readable_contrast(self):
        def luminance(color):
            channels = [channel / 255.0 for channel in color]
            linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
                      for channel in channels]
            return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

        colors = poetry.BUTTON_COLORS + ((poetry.DISABLED_BG, poetry.DISABLED_TEXT),
                                         (poetry.BACKGROUND, poetry.JADE))
        for background, foreground in colors:
            with self.subTest(background=background, foreground=foreground):
                lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
                self.assertGreaterEqual((lighter + 0.05) / (darker + 0.05), 4.5)

    def test_questions_and_all_views_fit_both_orientations(self):
        with closing(poetry.PoetryBank()) as bank:
            questions = [question for mode in range(len(poetry.MODES))
                         for question in bank.make_round(mode, random.Random(40 + mode))]
        for size in ((240, 320), (320, 240)):
            with self.subTest(size=size), patch.object(poetry.spi_lcd, "_pygame", pygame):
                screen = pygame.Surface(size)
                display = poetry.PoetryDisplay(screen)
                game = self.make_game(questions)
                display.draw(game)
                self.assertTrue(all(screen.get_rect().contains(rect) for rect in display.modes + display.buttons))
                for index, rect in enumerate(display.modes):
                    self.assertLessEqual(rect.bottom, display.footer_top)
                    self.assertFalse(any(rect.colliderect(other) for other in display.modes[index + 1:]))
                game.start()
                for question in questions:
                    with self.subTest(size=size, prompt=question.prompt):
                        game.questions = [question]
                        game.index = 0
                        game.phase = "answer"
                        area = pygame.Rect(display.prompt_rect.x + 9, display.prompt_rect.y + 26,
                                           display.prompt_rect.width - 18, display.prompt_rect.height - 30)
                        font, lines = display.layout_prompt(question.prompt, area)
                        self.assertEqual("".join(lines), question.prompt)
                        self.assertLessEqual(len(lines) * font.get_linesize(), area.height)
                        self.assertTrue(all(font.size(line)[0] <= area.width for line in lines))
                        for rect, choice in zip(display.options, question.choices):
                            self.assertLessEqual(rect.bottom, display.feedback_rect.top)
                            font, label = display.fit_one_line(choice, display.option_fonts, rect.width - 38)
                            self.assertEqual(label, choice)
                            self.assertLessEqual(font.size(label)[0], rect.width - 38)
                        display.draw(game)
                        game.handle_action("K1")
                        display.draw(game)
                game.phase = "summary"
                display.draw(game)
                display.draw_error()
                self.assertLessEqual(display.feedback_rect.bottom, display.footer_top)

    def test_mode_counts_follow_reordered_menu(self):
        with patch.object(poetry.spi_lcd, "_pygame", pygame):
            display = poetry.PoetryDisplay(pygame.Surface((240, 320)))
        game = self.make_game([])
        counts = []
        display.small_font = SimpleNamespace(
            render=lambda text, *_args: counts.append(text) or pygame.Surface((10, 10)))
        display.draw_menu(game)
        self.assertEqual([mode[0] for mode in poetry.MODES],
                         ["儿童诗词", "经典名篇", "唐诗题库", "宋词题库", "混合题库"])
        self.assertEqual(counts, ["77 首", "647 首", "57613 首", "21061 首", "78674 首"])

    def test_all_children_poems_fit_both_orientations(self):
        works = json.loads(poetry.CHILDREN_DATA_FILE.read_text(encoding="utf-8"))
        for size in ((240, 320), (320, 240)):
            with self.subTest(size=size), patch.object(poetry.spi_lcd, "_pygame", pygame):
                display = poetry.PoetryDisplay(pygame.Surface(size))
                area = pygame.Rect(display.prompt_rect.x + 9, display.prompt_rect.y + 26,
                                   display.prompt_rect.width - 18, display.prompt_rect.height - 30)
                for work in works:
                    for kind, field in (("续句", "following"), ("作者", "author"), ("作品", "title")):
                        question = poetry.make_catalog_question(kind, dict(work, answer=work[field]),
                                                               ("其他选项一", "其他选项二"), random.Random(1))
                        font, lines = display.layout_prompt(question.prompt, area)
                        self.assertEqual("".join(lines), question.prompt)
                        self.assertLessEqual(len(lines) * font.get_linesize(), area.height)
                        self.assertTrue(all(font.size(line)[0] <= area.width for line in lines))
                        font, label = display.fit_one_line(work[field], display.option_fonts,
                                                          display.options[0].width - 38)
                        self.assertEqual(label, work[field])
                        self.assertLessEqual(font.size(label)[0], display.options[0].width - 38)

    def test_mouse_actions_work_only_in_simulation(self):
        pygame.display.set_mode((480, 640))
        with patch.object(poetry.spi_lcd, "_pygame", pygame), \
                patch.object(poetry.spi_lcd, "_simulate", True), \
                patch.object(poetry.spi_lcd, "FB_WIDTH", 240), \
                patch.object(poetry.spi_lcd, "FB_HEIGHT", 320):
            display = poetry.PoetryDisplay(pygame.Surface((240, 320)))
            question = poetry.make_question("作者", "作者是？", "李白", ("杜甫", "王维"), "李白", random.Random(3))
            game = self.make_game([question])
            rect = display.modes[poetry.CHILDREN_MODE]
            event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(rect.centerx * 2, rect.centery * 2))
            action = poetry.event_action(event, display, game)
            self.assertEqual(action, "MODE_%d" % poetry.CHILDREN_MODE)
            game.handle_action(action)
            self.assertEqual((game.mode, game.phase), (poetry.CHILDREN_MODE, "answer"))
            for index, rect in enumerate(display.options):
                event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                           pos=(rect.centerx * 2, rect.centery * 2))
                self.assertEqual(poetry.event_action(event, display, game), "K%d" % (index + 1))
            with patch.object(poetry.spi_lcd, "_simulate", False):
                self.assertIsNone(poetry.event_action(event, display, game))

    def test_long_k3_returns_without_answering(self):
        now = [0.0]
        hold = poetry.spi_lcd.SimulatedHold("K3", "BACK", 1.0, clock=lambda: now[0])
        question = poetry.make_question("作者", "作者是？", "李白", ("杜甫", "王维"), "李白", random.Random(3))
        with patch.object(poetry.spi_lcd, "_pygame", pygame):
            display = poetry.PoetryDisplay(pygame.Surface((240, 320)))
            game = self.make_game([question])
            game.start()
            down = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_3)
            up = pygame.event.Event(pygame.KEYUP, key=pygame.K_3)
            self.assertIsNone(hold.process_event(down, poetry.event_action(down, display, game)))
            now[0] = 1.1
            game.handle_action(hold.poll())
            self.assertEqual((game.phase, game.score), ("menu", 0))
            self.assertIsNone(hold.process_event(up, poetry.event_action(up, display, game)))

    def test_simulated_main_runs_a_complete_round_and_returns_to_menu(self):
        pygame.display.set_mode((480, 640))
        screen = pygame.Surface((240, 320))
        question = poetry.make_question("作者", "作者是？", "李白", ("杜甫", "王维"), "李白", random.Random(3))
        bank = Mock()
        bank.metadata = {"classic_works": "647", "tang_records": "57608", "song_records": "21053"}
        bank.make_round.return_value = [question, question]
        down = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_3)
        up = pygame.event.Event(pygame.KEYUP, key=pygame.K_3)
        answer = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1)
        back = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_BACKSPACE)
        quit_event = pygame.event.Event(pygame.QUIT)
        events = iter(([down, up], [answer], [down, up], [answer], [down, up], [back], [quit_event]))
        frames = []
        with patch.object(poetry.spi_lcd, "_pygame", pygame), \
                patch.object(poetry.spi_lcd, "is_simulate", return_value=True), \
                patch.object(poetry.spi_lcd, "init", return_value=screen), \
                patch.object(poetry.spi_lcd, "present", return_value=True) as present, \
                patch.object(poetry, "PoetryBank", return_value=bank), \
                patch.object(poetry.PoetryDisplay, "draw", autospec=True,
                             side_effect=lambda display, game: frames.append(game.phase)), \
                patch.object(pygame.event, "get", side_effect=lambda: next(events)), \
                patch.object(pygame.time, "Clock"), patch.object(pygame, "quit"), patch("builtins.print"):
            poetry.main()
        self.assertEqual(frames, ["answer", "feedback", "answer", "feedback", "summary", "menu"])
        self.assertEqual(present.call_count, len(frames))
        present.assert_called_with(poll_events=False)
        bank.close.assert_called_once()

    def test_missing_database_shows_error_until_return(self):
        pygame.display.set_mode((480, 640))
        screen = pygame.Surface((240, 320))
        down = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_3)
        up = pygame.event.Event(pygame.KEYUP, key=pygame.K_3)
        events = iter(([], [down, up]))
        with patch.object(poetry.spi_lcd, "_pygame", pygame), \
                patch.object(poetry.spi_lcd, "is_simulate", return_value=True), \
                patch.object(poetry.spi_lcd, "init", return_value=screen), \
                patch.object(poetry.spi_lcd, "present", return_value=True), \
                patch.object(poetry, "PoetryBank", side_effect=FileNotFoundError("missing")), \
                patch.object(poetry.PoetryDisplay, "draw_error", autospec=True) as error_screen, \
                patch.object(pygame.event, "get", side_effect=lambda: next(events)), \
                patch.object(pygame.time, "Clock"), patch.object(pygame, "quit"), patch("builtins.print"):
            poetry.main()
        error_screen.assert_called_once()

    def test_gpio_hold_returns_to_menu_then_exits(self):
        screen = pygame.Surface((240, 320))
        question = poetry.make_question("作者", "作者是？", "李白", ("杜甫", "王维"), "李白", random.Random(3))
        bank = Mock()
        bank.make_round.return_value = [question]
        buttons = Mock()
        buttons.poll.side_effect = (("K3",), ("K1",), ("QUIT",), ("QUIT",))
        frames = []
        importer = SimpleNamespace(import_module=Mock(return_value=Mock()))
        with patch.object(poetry.spi_lcd, "_pygame", pygame), \
                patch.object(poetry.spi_lcd, "is_simulate", return_value=False), \
                patch.object(poetry.spi_lcd, "init", return_value=screen), \
                patch.object(poetry.spi_lcd, "present", return_value=True) as present, \
                patch.object(poetry, "importlib", importer), patch.object(poetry, "GPIOButtons", return_value=buttons), \
                patch.object(poetry, "PoetryBank", return_value=bank), \
                patch.object(poetry.PoetryDisplay, "draw", autospec=True,
                             side_effect=lambda display, game: frames.append(game.phase)), \
                patch.object(pygame.time, "Clock"), patch.object(pygame, "quit"), patch("builtins.print"):
            poetry.main()
        self.assertEqual(frames, ["answer", "feedback", "menu"])
        present.assert_called_with(poll_events=False)
        buttons.cleanup.assert_called_once()
        bank.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()