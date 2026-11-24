import json
import os
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(BASE_DIR))
sys.path.insert(0, BASE_DIR)

from common import spi_lcd

pygame.init()


def init_simulator():
    spi_lcd._simulate = True
    spi_lcd._pygame = pygame
    spi_lcd.FB_WIDTH, spi_lcd.FB_HEIGHT = 240, 320
    spi_lcd._window = pygame.display.set_mode((480, 640))
    spi_lcd._screen = pygame.Surface((240, 320))
    return spi_lcd._screen


with patch.object(spi_lcd, "init", side_effect=init_simulator), \
        patch.dict(sys.modules, {"RPi": None}):
    import pokemon


class PokemonInputTests(unittest.TestCase):
    def setUp(self):
        spi_lcd._simulate = True
        pygame.event.clear()

    def post_click(self, button_rects, button, release=True):
        rect = next(rect for name, rect in button_rects if name == button)
        window = pygame.display.get_surface()
        position = (rect.centerx * window.get_width() // pokemon.FB_WIDTH,
                    rect.centery * window.get_height() // pokemon.FB_HEIGHT)
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=position))
        if release:
            pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=position))

    def test_function_labels_map_to_simulated_buttons(self):
        labels = (("K1", "上一项"), ("K2", "下一项"), ("K3", "确定"))
        rects = spi_lcd.text_button_rects("上一项    下一项    确定", pokemon.sp.font_tiny, 300, labels)
        self.assertEqual([name for name, _ in rects], ["K1", "K2", "K3"])
        for name, rect in rects:
            self.assertGreaterEqual(rect.left, 0)
            self.assertLessEqual(rect.right, pokemon.FB_WIDTH)
            position = (rect.centerx * 2, rect.centery * 2)
            event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=position)
            self.assertEqual(spi_lcd.button_from_mouse(event, rects), name)

    def test_menu_hint_shows_function_names(self):
        buttons = (("K1", "上一项"), ("K2", "下一项"), ("K3", "确定"))
        with patch.object(pokemon.sp, "font_tiny", wraps=pokemon.sp.font_tiny) as font:
            pokemon.draw_hint(pokemon.STYLES["夜空"], buttons)
        self.assertEqual(font.render.call_args.args[0], "上一项    下一项    确定")
        self.assertEqual([name for name, _ in pokemon._hint_button_rects], ["K1", "K2", "K3"])

    def test_navigation_pages_use_the_same_descriptive_labels(self):
        style = pokemon.STYLES["夜空"]
        with patch.object(pokemon, "draw_hint") as hint:
            pokemon.draw_menu({"style": "夜空"}, 0, (10, 5, 5), 0)
            hint.assert_called_with(style, (("K1", "上一项"), ("K2", "下一项"), ("K3", "确定")))
            pokemon.draw_settings_page("夜空", 0, "正序", 0)
            hint.assert_called_with(style, (("K1", "上一项"), ("K2", "下一项"), ("K3", "切换")))
            pokemon.draw_generations_page("夜空", 0, {1}, 0)
            hint.assert_called_with(style, (("K1", "上一项"), ("K2", "下一项"), ("K3", "勾选")))

    def test_menu_clicks_reach_main_loop_after_display_refresh(self):
        selections = []
        draw_menu = pokemon.draw_menu

        def draw_and_click(settings, selected, counts, now):
            draw_menu(settings, selected, counts, now)
            selections.append(selected)
            if len(selections) <= 3:
                self.post_click(pokemon._hint_button_rects, ("K1", "K2", "K3")[len(selections) - 1])
            else:
                pygame.event.post(pygame.event.Event(pygame.QUIT))

        with patch.object(pokemon, "draw_menu", side_effect=draw_and_click), \
                patch.object(pokemon, "load_settings", return_value={"style": "夜空", "order": "正序"}), \
                patch.object(pokemon, "load_discovered", return_value=set()), \
                patch.object(pokemon, "save_discovered"), \
                patch.object(pokemon.sp, "gpio", None), \
                patch.object(pokemon.sp, "browse", return_value="back") as browse, \
                patch.object(pygame, "quit"):
            pokemon.main()

        self.assertEqual(selections[:3], [0, 3, 0])
        browse.assert_called_once()

    def test_menu_k3_hold_exits_without_opening_a_browser(self):
        now = [0.0]
        hold = spi_lcd.SimulatedHold("K3", "BACK", 0.8, clock=lambda: now[0])
        draw_menu = pokemon.draw_menu
        frames = 0

        def draw_and_hold(settings, selected, counts, current):
            nonlocal frames
            draw_menu(settings, selected, counts, current)
            now[0] = 0.0 if frames == 0 else 1.0
            if frames == 0:
                self.post_click(pokemon._hint_button_rects, "K3", release=False)
            frames += 1

        pygame.time.set_timer(pygame.QUIT, 2000, loops=1)
        try:
            with patch.object(pokemon, "draw_menu", side_effect=draw_and_hold), \
                    patch.object(pokemon, "load_settings", return_value={"style": "夜空", "order": "正序"}), \
                    patch.object(pokemon, "load_discovered", return_value=set()), \
                    patch.object(pokemon.sp, "gpio", None), \
                    patch.object(spi_lcd, "SimulatedHold", return_value=hold), \
                    patch.object(pokemon.sp, "browse") as browse, \
                    patch.object(pygame, "quit"):
                pokemon.main()
        finally:
            pygame.time.set_timer(pygame.QUIT, 0)
        self.assertEqual(frames, 2)
        browse.assert_not_called()

    def test_browser_clicks_change_pokemon_and_page_after_display_refresh(self):
        browser = pokemon.sp
        monsters = browser.POKEMONS[:3]
        rendered = []
        render = browser.render
        draw_footer = browser.draw_bottom_bar

        def draw_and_click():
            draw_footer()
            if len(rendered) <= 4:
                self.post_click(browser._footer_button_rects, ("K2", "K3", "K1", "K2")[len(rendered) - 1])

        def render_and_record(monster, page):
            rendered.append((monster["id"], page))
            result = render(monster, page)
            if len(rendered) >= 5:
                pygame.event.post(pygame.event.Event(pygame.QUIT))
            return result

        pygame.time.set_timer(pygame.QUIT, 1500, loops=1)
        try:
            with patch.object(browser, "gpio", None), \
                    patch.object(browser, "render", side_effect=render_and_record), \
                    patch.object(browser, "draw_bottom_bar", side_effect=draw_and_click):
                self.assertEqual(browser.browse(mon_list=monsters), "quit")
        finally:
            pygame.time.set_timer(pygame.QUIT, 0)

        self.assertEqual(rendered[:5], [
            (monsters[0]["id"], 0), (monsters[2]["id"], 0),
            (monsters[0]["id"], 0), (monsters[0]["id"], 1),
            (monsters[2]["id"], 0),
        ])

    def test_browser_footer_and_move_table_fit(self):
        browser = pokemon.sp
        with patch.object(browser, "font_tiny", wraps=browser.font_tiny) as font:
            browser.draw_bottom_bar()
        self.assertEqual(font.render.call_args.args[0], "翻页    上一只    下一只")
        for name in ("K1", "K2", "K3"):
            rect = next(rect for key, rect in browser._footer_button_rects if key == name)
            self.assertGreaterEqual(rect.left, 0)
            self.assertLessEqual(rect.right, browser.FB_WIDTH)
        self.assertLessEqual(browser.MOVE_LIST_TOP + browser.MOVES_PER_PAGE * browser.ROW_H,
                             browser.FB_HEIGHT - 18)

    def test_holding_mouse_on_k3_returns_without_changing_pokemon(self):
        browser = pokemon.sp
        monsters = browser.POKEMONS[:3]
        visited = []
        draw_footer = browser.draw_bottom_bar
        pressed = False

        def draw_and_hold():
            nonlocal pressed
            draw_footer()
            if not pressed:
                self.post_click(browser._footer_button_rects, "K3", release=False)
                pressed = True

        pygame.time.set_timer(pygame.QUIT, 750, loops=1)
        try:
            with patch.object(browser, "gpio", None), \
                    patch.object(browser, "draw_bottom_bar", side_effect=draw_and_hold):
                result = browser.browse(mon_list=monsters,
                                        on_viewed=lambda monster: visited.append(monster["id"]),
                                        back_hold=0.1)
        finally:
            pygame.time.set_timer(pygame.QUIT, 0)

        self.assertEqual(result, "back")
        self.assertEqual(visited, [monsters[0]["id"]])

    def test_keyboard_event_is_preserved_during_refresh(self):
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_2))
        self.assertTrue(spi_lcd.present(poll_events=False))
        actions = []
        self.assertTrue(pokemon.pump(actions.append))
        self.assertEqual(actions, ["K2"])

    def test_default_refresh_still_handles_quit(self):
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        self.assertFalse(spi_lcd.present())

    def test_real_display_refresh_still_flushes_framebuffer(self):
        with patch.object(spi_lcd, "_simulate", False), \
                patch.object(spi_lcd, "_flush_fb") as flush:
            self.assertTrue(spi_lcd.present(poll_events=False))
        flush.assert_called_once_with()

    def test_real_display_ignores_mouse_input(self):
        event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(20, 20))
        with patch.object(spi_lcd, "_simulate", False):
            self.assertIsNone(spi_lcd.button_from_mouse(event, [("K1", pygame.Rect(0, 0, 40, 40))]))

    def test_generation_boundaries_cover_all_pokemon(self):
        expected = ((1, 151, 1, 151), (2, 100, 152, 251),
                    (3, 135, 252, 386), (4, 107, 387, 493))
        for generation, count, first, last in expected:
            with self.subTest(generation=generation):
                monsters = pokemon.build_list("all", {"generations": [generation]}, set())
                self.assertEqual((len(monsters), monsters[0]["id"], monsters[-1]["id"]),
                                 (count, first, last))
        self.assertEqual(len(pokemon.build_list("all", {}, set())), 493)

    def test_generations_filter_counts_discovery_and_order(self):
        settings = {"generations": [2, 4], "order": "倒序"}
        discovered = {1, 152, 251, 252, 387, 493}
        self.assertEqual(pokemon.menu_counts(settings, discovered), (207, 203, 4))
        self.assertEqual([monster["id"] for monster in pokemon.build_list("found", settings, discovered)],
                         [493, 387, 251, 152])
        unseen = pokemon.build_list("unseen", settings, discovered)
        self.assertEqual(len(unseen), 203)
        self.assertTrue(all(monster["id"] not in discovered for monster in unseen))
        self.assertEqual(discovered, {1, 152, 251, 252, 387, 493})
        settings["order"] = "随机"
        self.assertEqual({monster["id"] for monster in pokemon.build_list("all", settings, discovered)},
                         {monster["id"] for monster in pokemon.generation_pokemon(settings)})
        self.assertEqual(pokemon.menu_counts({"generations": []}, discovered), (0, 0, 0))

    def test_generation_settings_are_backward_compatible_and_persistent(self):
        cases = (({}, [1, 2, 3, 4]), ({"generations": [4, 1, 1]}, [1, 4]),
                 ({"generations": []}, []), ({"generations": [True, "2", 5]}, [1, 2, 3, 4]),
                 ({"generations": "2"}, [1, 2, 3, 4]))
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "settings.json")
            with patch.object(pokemon, "SETTINGS_FILE", path), \
                    patch.object(pokemon.sp, "SETTINGS_FILE", path):
                for stored, expected in cases:
                    with self.subTest(stored=stored):
                        with open(path, "w", encoding="utf-8") as settings_file:
                            json.dump(stored, settings_file)
                        self.assertEqual(pokemon.load_settings()["generations"], expected)
                        self.assertEqual(pokemon.sp.load_selected_generations(), expected)
                settings = {"style": "森林", "order": "倒序", "generations": [1, 3]}
                pokemon.save_settings(settings)
                self.assertEqual(pokemon.load_settings(), settings)
                self.assertEqual(pokemon.sp.load_selected_generations(), [1, 3])

    def test_generation_settings_mouse_save_and_cancel(self):
        for save in (True, False):
            with self.subTest(save=save), tempfile.TemporaryDirectory() as directory:
                settings = {"style": "夜空", "order": "正序", "generations": [1, 2, 3, 4]}
                discovered = {1, 152, 252, 387}
                path = os.path.join(directory, "settings.json")
                draw_settings = pokemon.draw_settings_page
                draw_generations = pokemon.draw_generations_page
                frames = {"settings": 0, "generations": 0}

                def settings_and_click(*args, **kwargs):
                    rects = draw_settings(*args, **kwargs)
                    name = "ROW_2" if frames["settings"] == 0 else ("ROW_5" if save else "ROW_4")
                    frames["settings"] += 1
                    self.post_click(rects, name)
                    return rects

                def generations_and_click(*args, **kwargs):
                    rects = draw_generations(*args, **kwargs)
                    names = ("GEN_2", "GEN_3", "GEN_DONE")
                    if frames["generations"] < len(names):
                        self.post_click(rects, names[frames["generations"]])
                        frames["generations"] += 1
                    return rects

                pygame.event.clear()
                pygame.time.set_timer(pygame.QUIT, 2000, loops=1)
                try:
                    with patch.object(pokemon, "SETTINGS_FILE", path), \
                            patch.object(pokemon.sp, "gpio", None), \
                            patch.object(pokemon, "draw_settings_page", side_effect=settings_and_click), \
                            patch.object(pokemon, "draw_generations_page", side_effect=generations_and_click):
                        result = pokemon.settings_loop(settings, discovered)
                        self.assertEqual(result["generations"], [1, 4] if save else [1, 2, 3, 4])
                        if save:
                            self.assertEqual(pokemon.load_settings()["generations"], [1, 4])
                        else:
                            self.assertFalse(os.path.exists(path))
                finally:
                    pygame.time.set_timer(pygame.QUIT, 0)
                self.assertEqual(settings["generations"], [1, 2, 3, 4])
                self.assertEqual(discovered, {1, 152, 252, 387})

    def test_generations_support_keyboard_and_empty_selection(self):
        keys = (pygame.K_3, pygame.K_2, pygame.K_3, pygame.K_2, pygame.K_3,
                pygame.K_2, pygame.K_3, pygame.K_2, pygame.K_3)
        draw_generations = pokemon.draw_generations_page
        frame = 0

        def draw_and_press(*args, **kwargs):
            nonlocal frame
            rects = draw_generations(*args, **kwargs)
            if frame < len(keys):
                pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=keys[frame]))
                if keys[frame] == pygame.K_3:
                    pygame.event.post(pygame.event.Event(pygame.KEYUP, key=keys[frame]))
                frame += 1
            return rects

        pygame.time.set_timer(pygame.QUIT, 2000, loops=1)
        try:
            with patch.object(pokemon.sp, "gpio", None), \
                    patch.object(pokemon, "draw_generations_page", side_effect=draw_and_press):
                self.assertEqual(pokemon.generations_loop("夜空", [1, 2, 3, 4]), [])
        finally:
            pygame.time.set_timer(pygame.QUIT, 0)

    def test_generations_support_gpio_actions(self):
        actions = iter([["K3"], [], ["K2"], ["K2"], ["K2"], ["K2"], ["K3"], []])
        gpio = SimpleNamespace(LOW=0, level=1)
        gpio.input = lambda pin: gpio.level

        def poll():
            result = next(actions)
            gpio.level = 0 if "K3" in result else 1
            return result

        with patch.object(pokemon.sp, "gpio", gpio), \
                patch.object(pokemon.sp, "poll_buttons", side_effect=poll), \
                patch.object(spi_lcd, "pump", return_value=True):
            self.assertEqual(pokemon.generations_loop("夜空", [1, 4]), [4])

    def test_settings_generations_can_be_saved_with_gpio_actions(self):
        actions = iter([["K2"], ["K2"], ["K3"], [], ["K3"], [],
                        ["K2"], ["K2"], ["K2"], ["K2"], ["K3"], [],
                        ["K2"], ["K2"], ["K2"], ["K3"], []])
        gpio = SimpleNamespace(LOW=0, level=1)
        gpio.input = lambda pin: gpio.level

        def poll():
            result = next(actions)
            gpio.level = 0 if "K3" in result else 1
            return result

        settings = {"style": "夜空", "order": "正序", "generations": [1, 2, 3, 4]}
        with patch.object(pokemon.sp, "gpio", gpio), \
                patch.object(pokemon.sp, "poll_buttons", side_effect=poll), \
                patch.object(pokemon.sp, "wait_release"), \
                patch.object(spi_lcd, "pump", return_value=True), \
                patch.object(pokemon, "save_settings") as save:
            result = pokemon.settings_loop(settings, {1, 152})
        self.assertEqual(result["generations"], [2, 3, 4])
        self.assertEqual(settings["generations"], [1, 2, 3, 4])
        save.assert_called_once_with(result)

    def test_gpio_k3_hold_does_not_repeat_confirm(self):
        now = [0.0]
        gpio = SimpleNamespace(LOW=0, level=0)
        gpio.input = lambda pin: gpio.level
        hold = spi_lcd.SimulatedHold("K3", "BACK", 0.8, clock=lambda: now[0])
        actions = []
        with patch.object(pokemon.sp, "gpio", gpio), \
                patch.object(pokemon.sp, "poll_buttons", side_effect=[["K3"], ["K3"], []]), \
                patch.object(spi_lcd, "pump", return_value=True):
            pokemon.pump(actions.append, hold=hold)
            now[0] = 1.0
            pokemon.pump(actions.append, hold=hold)
            gpio.level = 1
            pokemon.pump(actions.append, hold=hold)
        self.assertEqual(actions, ["BACK"])

    def test_settings_k3_hold_cancels_without_resetting_discoveries(self):
        now = [0.0]
        hold = spi_lcd.SimulatedHold("K3", "BACK", 0.8, clock=lambda: now[0])
        settings = {"style": "夜空", "order": "正序", "generations": [1, 4]}
        discovered = {1, 152, 252, 387}
        draw_settings = pokemon.draw_settings_page
        frame = 0

        def draw_and_hold(*args, **kwargs):
            nonlocal frame
            rects = draw_settings(*args, **kwargs)
            now[0] = (0.0, 0.1, 0.2, 0.3, 1.2)[min(frame, 4)]
            if frame < 3:
                pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_2))
            elif frame == 3:
                self.post_click(pokemon._hint_button_rects, "K3", release=False)
            frame += 1
            return rects

        with patch.object(pokemon.sp, "gpio", None), \
                patch.object(spi_lcd, "SimulatedHold", return_value=hold), \
                patch.object(pokemon, "draw_settings_page", side_effect=draw_and_hold), \
                patch.object(pokemon, "save_discovered") as save_discovered, \
                patch.object(pokemon, "save_settings") as save_settings:
            result = pokemon.settings_loop(settings, discovered)
        self.assertIs(result, settings)
        self.assertEqual(discovered, {1, 152, 252, 387})
        save_discovered.assert_not_called()
        save_settings.assert_not_called()

    def test_generation_k3_hold_discards_child_changes(self):
        now = [0.0]
        settings_hold = spi_lcd.SimulatedHold("K3", "BACK", 0.8, clock=lambda: now[0])
        generation_hold = spi_lcd.SimulatedHold("K3", "BACK", 0.8, clock=lambda: now[0])
        settings = {"style": "夜空", "order": "正序", "generations": [1, 2, 4]}
        draw_settings = pokemon.draw_settings_page
        draw_generations = pokemon.draw_generations_page
        frames = {"settings": 0, "generations": 0}

        def settings_and_click(*args, **kwargs):
            rects = draw_settings(*args, **kwargs)
            self.post_click(rects, "ROW_2" if frames["settings"] == 0 else "ROW_5")
            frames["settings"] += 1
            return rects

        def generations_and_hold(*args, **kwargs):
            rects = draw_generations(*args, **kwargs)
            frame = frames["generations"]
            now[0] = (0.0, 0.1, 1.0)[min(frame, 2)]
            if frame == 0:
                self.post_click(rects, "GEN_2")
            elif frame == 1:
                self.post_click(pokemon._hint_button_rects, "K3", release=False)
            frames["generations"] += 1
            return rects

        with patch.object(pokemon.sp, "gpio", None), \
                patch.object(spi_lcd, "SimulatedHold", side_effect=[settings_hold, generation_hold]), \
                patch.object(pokemon, "draw_settings_page", side_effect=settings_and_click), \
                patch.object(pokemon, "draw_generations_page", side_effect=generations_and_hold), \
                patch.object(pokemon, "save_settings") as save:
            result = pokemon.settings_loop(settings, {1, 152})
        self.assertEqual(result["generations"], [1, 2, 4])
        save.assert_called_once_with(result)

    def test_discovery_reset_still_requires_two_confirmations(self):
        draw_settings = pokemon.draw_settings_page
        frames = 0
        discovered = {1, 152, 252, 387}

        def draw_and_click(*args, **kwargs):
            nonlocal frames
            rects = draw_settings(*args, **kwargs)
            names = ("ROW_3", "ROW_3", "ROW_5")
            if frames < len(names):
                self.post_click(rects, names[frames])
                frames += 1
            return rects

        pygame.time.set_timer(pygame.QUIT, 2000, loops=1)
        try:
            with patch.object(pokemon.sp, "gpio", None), \
                    patch.object(pokemon, "draw_settings_page", side_effect=draw_and_click), \
                    patch.object(pokemon, "save_discovered") as save_discovered, \
                    patch.object(pokemon, "save_settings") as save_settings:
                result = pokemon.settings_loop({"style": "夜空", "order": "正序", "generations": [1, 4]}, discovered)
        finally:
            pygame.time.set_timer(pygame.QUIT, 0)
        self.assertEqual(discovered, set())
        self.assertEqual(result["generations"], [1, 4])
        save_discovered.assert_called_once_with(set())
        save_settings.assert_called_once_with(result)

    def test_generation_settings_fit_portrait_and_landscape(self):
        for width, height in ((240, 320), (320, 240)):
            with self.subTest(width=width, height=height), \
                    patch.multiple(pokemon, screen=pygame.Surface((width, height)),
                                   FB_WIDTH=width, FB_HEIGHT=height, PORTRAIT=height > width), \
                    patch.object(spi_lcd, "FB_WIDTH", width), \
                    patch.object(spi_lcd, "FB_HEIGHT", height):
                choices = pokemon.draw_generations_page("夜空", 0, {1, 4}, 0)
                self.assertEqual(len(choices), 5)
                title_top = 32 if height > width else 20
                self.assertLessEqual(title_top + 32 + pokemon.sp.font_tiny.get_height(), choices[0][1].top)
                for _, rect in choices:
                    self.assertGreaterEqual(rect.left, 0)
                    self.assertLessEqual(rect.right, width)
                    self.assertLessEqual(rect.bottom, height - 18)
                self.assertLessEqual(choices[3][1].bottom, choices[4][1].top)
                settings = pokemon.draw_settings_page("夜空", 2, "正序", 0,
                                                      generations=[1, 2, 3, 4])
                self.assertEqual(len(settings), 6)
                self.assertLessEqual(settings[3][1].bottom, settings[4][1].top)
                self.assertLessEqual(settings[5][1].bottom, height - 18)

    def test_empty_selection_shows_message_in_main(self):
        draw_menu = pokemon.draw_menu
        draw_message = pokemon.draw_message
        frames = 0
        messages = []

        def draw_and_click(settings, selected, counts, now):
            nonlocal frames
            draw_menu(settings, selected, counts, now)
            frames += 1
            if frames == 1:
                self.post_click(pokemon._hint_button_rects, "K3")
            else:
                pygame.event.post(pygame.event.Event(pygame.QUIT))

        def draw_and_dismiss(style, text, now):
            messages.append(text)
            draw_message(style, text, now)
            self.post_click(pokemon._hint_button_rects, "K3")

        pygame.time.set_timer(pygame.QUIT, 2000, loops=1)
        try:
            with patch.object(pokemon, "draw_menu", side_effect=draw_and_click), \
                    patch.object(pokemon, "load_settings", return_value={"style": "夜空", "order": "正序", "generations": []}), \
                    patch.object(pokemon, "load_discovered", return_value={1}), \
                    patch.object(pokemon, "save_discovered"), \
                    patch.object(pokemon, "draw_message", side_effect=draw_and_dismiss), \
                    patch.object(pokemon.sp, "gpio", None), \
                    patch.object(pygame, "quit"):
                pokemon.main()
        finally:
            pygame.time.set_timer(pygame.QUIT, 0)
        self.assertEqual(len(messages), 1)
        self.assertIn("没有选择宝可梦世代", messages[0])

    def test_standalone_browser_uses_saved_generations(self):
        browser = pokemon.sp
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "settings.json")
            with patch.object(browser, "SETTINGS_FILE", path), \
                    patch.object(browser, "gpio", None), \
                    patch.object(browser, "browse") as browse, \
                    patch.object(pygame, "quit"):
                for generations in ([2, 4], []):
                    with self.subTest(generations=generations):
                        with open(path, "w", encoding="utf-8") as settings_file:
                            json.dump({"generations": generations}, settings_file)
                        browse.reset_mock()
                        with self.assertRaises(SystemExit):
                            browser.main()
                        if generations:
                            monsters = browse.call_args.args[0]
                            self.assertEqual((len(monsters), monsters[0]["id"], monsters[-1]["id"]),
                                             (207, 152, 493))
                        else:
                            browse.assert_not_called()


if __name__ == "__main__":
    unittest.main()