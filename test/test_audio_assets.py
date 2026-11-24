"""全项目音频接入的回归测试（不需要真实 pygame，只验证文件与接线约定）。

覆盖需求：
  1. 每个功能的音效文件都在自己目录、不混放
  2. 10 个功能都有 welcome.ogg
  3. 三个转盘音互不相同
  4. 各朗读文本 100% 命中预生成音频
  5. 每个游戏都在 spi_lcd.init() 前 prepare()，且接了 welcome/按键音
  6. 粘猴不额外加按键音
  7. 诗词选项朗读覆盖（选项一/二/三 + 值）
  8. 幸运转盘/骰子对决结果朗读覆盖
  9. 宠物 8 种动作各有独立音效
  10. 粘猴进入游戏后 K1 位置显示“开始”
  11. 转盘/骰子接了结果朗读，诗词接了连播
"""
import hashlib
import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys_path_added = False


def abs_path(relative):
    return os.path.join(ROOT, relative)


class AudioAssetsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sys
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)

    def pregen(self, text, directory):
        from common import tts
        return tts.pregen_path(text, abs_path(directory))

    def covered(self, text, directory):
        path = self.pregen(text, directory)
        return os.path.exists(path) and os.path.getsize(path) > 44

    def test_common_sfx_present(self):
        for name in ("button", "correct", "wrong"):
            path = abs_path(os.path.join("common", "media", name + ".ogg"))
            self.assertTrue(os.path.exists(path), "缺公共音效: " + path)

    def test_every_game_has_welcome_in_own_dir(self):
        games = ("Riddles", "Poetry Quest", "Pokemon", "Brain Challenge", "Quick Duel",
                 "Lucky Wheel", "Magic", "Virtual Pet", "Werewolf",
                 os.path.join("Mini Games", "Sticky Monkey"))
        for game in games:
            path = abs_path(os.path.join(game, "media", "welcome.ogg"))
            self.assertTrue(os.path.exists(path), "缺欢迎语: " + path)

    def test_wheel_sounds_are_distinct(self):
        wheels = ("Quick Duel", "Lucky Wheel", "Magic")
        hashes = []
        for game in wheels:
            path = abs_path(os.path.join(game, "media", "wheel.ogg"))
            self.assertTrue(os.path.exists(path), "缺转盘音: " + path)
            with open(path, "rb") as source:
                hashes.append(hashlib.md5(source.read()).hexdigest())
        self.assertEqual(len(set(hashes)), 3, "三个转盘音不能相同")

    def test_magic_wheel_tick_follows_scroll(self):
        path = abs_path(os.path.join("Magic", "media", "wheel_tick.ogg"))
        self.assertTrue(os.path.exists(path), "缺占卜屋逐格转盘音: " + path)
        self.assertGreater(os.path.getsize(path), 44)
        with open(abs_path("Magic/Magic.py"), encoding="utf-8") as source:
            code = source.read()
        self.assertIn('"wheel_tick"', code)
        self.assertNotIn('sound.loop_start("wheel")', code)

    def test_riddles_speech_coverage(self):
        with open(abs_path("Riddles/riddles.json"), encoding="utf-8") as source:
            bank = json.load(source)
        for entry in bank:
            for text in ("请听题。" + entry.get("q", "").strip(),
                         "答案是。" + entry.get("a", "").strip()):
                self.assertTrue(self.covered(text, "Riddles/media/tts"),
                                "脑筋急转弯朗读缺失: " + text)

    def test_pokemon_name_coverage(self):
        with open(abs_path("Pokemon/pokedex_data/pokemon_platinum.json"), encoding="utf-8") as source:
            bank = json.load(source)
        for entry in bank:
            name = str(entry.get("name_zh", "")).strip()
            if name:
                self.assertTrue(self.covered(name, "Pokemon/media/tts"),
                                "宝可梦名字音频缺失: " + name)

    def test_children_poetry_speech_coverage(self):
        with open(abs_path("Poetry Quest/data/children_poetry.json"), encoding="utf-8") as source:
            works = json.load(source)
        for work in works:
            stem = work.get("stem", "")
            prompts = ["请听题。“%s”的下一句是？" % stem, "请听题。“%s”是谁写的？" % stem]
            if work.get("genre", "").endswith("词"):
                prompts.append("请听题。“%s”的词牌是？" % stem)
            else:
                prompts.append("请听题。“%s”出自哪首诗？" % stem)
            answers = ["答案是。" + str(work.get(field, "")).strip()
                       for field in ("following", "author", "title")]
            for text in prompts + answers:
                if text.strip():
                    self.assertTrue(self.covered(text, "Poetry Quest/media/tts"),
                                    "诗词朗读缺失: " + text)

    def test_each_game_prepares_audio_before_display_init(self):
        games = {
            "Riddles/Riddles.py": "脑筋急转弯",
            "Poetry Quest/poetry.py": "诗词大赛",
            "Pokemon/show_pokemon.py": "宝可梦图鉴",
            "Brain Challenge/brain_challenge.py": "头脑挑战",
            "Quick Duel/quick_duel.py": "骰子对决",
            "Lucky Wheel/lucky_wheel.py": "幸运转盘",
            "Magic/Magic.py": "星愿占卜屋",
            "Virtual Pet/virtual_pet.py": "宠物乐园",
            "Werewolf/werewolf.py": "狼人杀",
            os.path.join("Mini Games", "Sticky Monkey", "sticky_monkey.py"): "粘猴",
        }
        for relative, name in games.items():
            with open(abs_path(relative), encoding="utf-8") as source:
                lines = source.read().splitlines()
            prepare = init = -1
            for index, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if prepare < 0 and ("audio_output.prepare()" in stripped
                                    or stripped.startswith("audio.prepare()")):
                    prepare = index
                if init < 0 and "spi_lcd.init()" in stripped:
                    init = index
            self.assertGreaterEqual(prepare, 0, name + " 未声明 audio.prepare()")
            if init >= 0:
                self.assertLess(prepare, init, name + " 的 prepare 晚于 spi_lcd.init()")

    def test_button_sound_wiring(self):
        # 九个游戏接了按键音；粘猴只用自带音效
        for relative in ("Riddles/Riddles.py", "Poetry Quest/poetry.py", "Pokemon/pokemon.py",
                         "Brain Challenge/brain_challenge.py", "Quick Duel/quick_duel.py",
                         "Lucky Wheel/lucky_wheel.py", "Magic/Magic.py",
                         "Virtual Pet/virtual_pet.py", "Werewolf/werewolf.py"):
            with open(abs_path(relative), encoding="utf-8") as source:
                text = source.read()
            self.assertIn("sound.button()", text, relative + " 未接按键音")
        with open(abs_path("Mini Games/Sticky Monkey/sticky_monkey.py"), encoding="utf-8") as source:
            monkey = source.read()
        self.assertNotIn("sound.button()", monkey, "粘猴不应额外加按键音")

    def test_poetry_options_coverage(self):
        """每个可能的选项值 × 三个位置都要有音频。"""
        with open(abs_path("Poetry Quest/data/children_poetry.json"), encoding="utf-8") as source:
            works = json.load(source)
        values = set()
        for work in works:
            for field in ("following", "author", "title"):
                value = str(work.get(field, "")).strip()
                if value:
                    values.add(value)
        prefixes = ("选项一，", "选项二，", "选项三，")
        for value in values:
            for prefix in prefixes:
                self.assertTrue(self.covered(prefix + value, "Poetry Quest/media/tts"),
                                "诗词选项朗读缺失: " + prefix + value)

    def test_wheel_and_duel_result_coverage(self):
        """两个转盘的每种可能结果都要能朗读。"""
        import ast

        def task_texts(relative, variable):
            with open(abs_path(relative), encoding="utf-8") as source:
                tree = ast.parse(source.read())
            for node in tree.body:
                if isinstance(node, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == variable for t in node.targets):
                    table = ast.literal_eval(node.value)
                    return [str(task).strip()
                            for entry in table for task in entry[2] if str(task).strip()]
            return []

        for relative, variable, directory in (
                ("Lucky Wheel/lucky_wheel.py", "GAMES", "Lucky Wheel/media/tts"),
                ("Quick Duel/quick_duel.py", "CHALLENGES", "Quick Duel/media/tts")):
            texts = task_texts(relative, variable)
            self.assertTrue(texts, relative + " 未提取到结果文本")
            for text in texts:
                self.assertTrue(self.covered(text, directory),
                                "%s 结果朗读缺失: %s" % (relative, text))

    def test_pet_actions_have_distinct_sounds(self):
        names = ("feed", "play", "wash", "sleep", "pat", "medicine", "explore", "skill")
        hashes = set()
        for name in names:
            path = abs_path(os.path.join("Virtual Pet", "media", "act_%s.ogg" % name))
            self.assertTrue(os.path.exists(path), "缺宠物动作音效: " + path)
            with open(path, "rb") as source:
                hashes.add(hashlib.md5(source.read()).hexdigest())
        self.assertEqual(len(hashes), len(names), "8 种宠物动作音效应互不相同")

    def test_result_and_sequence_wiring(self):
        """幸运转盘/骰子对决接了结果朗读，诗词接了连播。"""
        for relative in ("Lucky Wheel/lucky_wheel.py", "Quick Duel/quick_duel.py"):
            with open(abs_path(relative), encoding="utf-8") as source:
                text = source.read()
            self.assertIn("speaker.speak(", text, relative + " 未接结果朗读")
            self.assertIn("spoken_result", text, relative + " 未做结果去重")
        with open(abs_path("Poetry Quest/poetry.py"), encoding="utf-8") as source:
            poetry = source.read()
        self.assertIn("speak_sequence", poetry, "诗词未接选项连播")
        self.assertIn("SPEAK_OPTION_PREFIX", poetry, "诗词缺选项前缀")

    def test_monkey_k1_shows_start(self):
        with open(abs_path("Mini Games/Sticky Monkey/sticky_monkey.py"), encoding="utf-8") as source:
            text = source.read()
        self.assertIn('"ready": "开始"', text, "粘猴进入游戏后 K1 位置应显示“开始”")


if __name__ == "__main__":
    unittest.main()
