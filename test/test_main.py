import os
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

import main


class GameCatalogTests(unittest.TestCase):
    def test_only_implemented_games_are_listed(self):
        self.assertEqual(len(main.GAMES), 8)
        self.assertEqual(len({game.name for game in main.GAMES}), len(main.GAMES))
        for game in main.GAMES:
            with self.subTest(game=game.name):
                self.assertTrue(os.path.isfile(os.path.join(ROOT_DIR, game.path)))
                self.assertGreater(os.path.getsize(os.path.join(ROOT_DIR, game.path)), 0)
                self.assertTrue(game.icon)

    def test_launch_preserves_display_mode_and_orientation(self):
        for simulate, portrait in ((True, True), (True, False), (False, True), (False, False)):
            with self.subTest(simulate=simulate, portrait=portrait), \
                    patch.object(main.subprocess, "run") as run:
                run.return_value.returncode = 0
                self.assertEqual(main.launch_game(main.GAMES[0], simulate, portrait), 0)
                command = run.call_args.args[0]
                self.assertEqual(command[:2], [sys.executable, os.path.join(ROOT_DIR, main.GAMES[0].path)])
                self.assertEqual(command[2:], ["--sim" if simulate else "--spi",
                                               "--portrait" if portrait else "--landscape"])
                self.assertEqual(run.call_args.kwargs["cwd"], ROOT_DIR)
                environment = run.call_args.kwargs["env"]
                self.assertEqual(environment["POKEMON_SIMULATE"], "1" if simulate else "0")
                self.assertEqual(environment["POKEMON_PORTRAIT"], "1" if portrait else "0")


class LauncherInterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.font.init()

    def test_selection_and_power_confirmation(self):
        state = main.LauncherState()
        state.handle_action("K1")
        self.assertEqual(state.selected, len(main.GAMES) - 1)
        state.handle_action("K2")
        self.assertEqual(state.selected, 0)
        self.assertEqual(state.handle_action("K3"), "LAUNCH")
        state.handle_action("POWER")
        self.assertTrue(state.confirming_power)
        self.assertEqual(state.power_selected, 0)
        self.assertIsNone(state.handle_action("K3"))
        self.assertFalse(state.confirming_power)
        state.handle_action("POWER")
        state.handle_action("K2")
        self.assertEqual(state.handle_action("K3"), "SHUTDOWN")

    def test_all_games_and_dialog_fit_both_screen_orientations(self):
        for size in ((240, 320), (320, 240)):
            with self.subTest(size=size), patch.object(main.spi_lcd, "_pygame", pygame):
                display = main.LauncherDisplay(pygame.Surface(size))
                state = main.LauncherState()
                display.draw(state)
                self.assertEqual(len(display.game_rects), len(main.GAMES))
                for index, (game, rect) in enumerate(zip(main.GAMES, display.game_rects)):
                    self.assertGreaterEqual(rect.left, 0)
                    self.assertLessEqual(rect.right, size[0])
                    self.assertLessEqual(rect.bottom, display.footer_top)
                    self.assertTrue(any(font.size(game.name)[0] <= rect.width - 42
                                        and font.get_height() + display.small_font.get_height() <= rect.height - 4
                                        for font in display.name_fonts))
                    for other in display.game_rects[index + 1:]:
                        self.assertFalse(rect.colliderect(other))
                state.handle_action("POWER")
                display.draw(state)
                self.assertLessEqual(display.dialog.bottom, display.footer_top)
                self.assertFalse(display.power_buttons[0].colliderect(display.power_buttons[1]))
                self.assertTrue(all(display.dialog.contains(rect) for rect in display.power_buttons))

    def test_logo_shows_a_narrow_open_box_with_sparks(self):
        screen = pygame.Surface((240, 320))
        with patch.object(main.spi_lcd, "_pygame", pygame):
            display = main.LauncherDisplay(screen)
        display.draw_logo(30, 30, 100)
        self.assertEqual(screen.get_at((53, 104))[:3], (0, 0, 0))
        self.assertEqual(screen.get_at((107, 104))[:3], (0, 0, 0))
        self.assertEqual(screen.get_at((70, 79))[:3], (31, 74, 68))
        self.assertEqual(screen.get_at((65, 103))[:3], (226, 105, 88))
        self.assertEqual(screen.get_at((95, 103))[:3], (49, 151, 139))
        self.assertEqual(screen.get_at((80, 39))[:3], (255, 206, 93))
        self.assertEqual(screen.get_at((61, 48))[:3], main.CORAL)
        self.assertEqual(screen.get_at((99, 51))[:3], main.TEAL)

    def test_keyboard_and_simulated_mouse_target_the_visible_controls(self):
        with patch.object(main.spi_lcd, "_pygame", pygame):
            display = main.LauncherDisplay(pygame.Surface((240, 320)))
        state = main.LauncherState()
        for key, action in ((pygame.K_1, "K1"), (pygame.K_2, "K2"), (pygame.K_3, "K3"),
                            (pygame.K_UP, "K1"), (pygame.K_DOWN, "K2"), (pygame.K_RETURN, "K3")):
            event = pygame.event.Event(pygame.KEYDOWN, key=key)
            self.assertEqual(main.event_action(event, display, state), action)
        event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(0, 0))
        with patch.object(main.spi_lcd, "mouse_position", return_value=display.game_rects[3].center):
            self.assertEqual(main.event_action(event, display, state), "GAME_3")
        with patch.object(main.spi_lcd, "mouse_position", return_value=display.game_rects[6].center):
            self.assertEqual(main.event_action(event, display, state), "GAME_6")
        with patch.object(main.spi_lcd, "mouse_position", return_value=display.game_rects[7].center):
            self.assertEqual(main.event_action(event, display, state), "GAME_7")
        with patch.object(main.spi_lcd, "mouse_position", return_value=display.buttons[2].center):
            self.assertEqual(main.event_action(event, display, state), "K3")
        state.handle_action("POWER")
        with patch.object(main.spi_lcd, "mouse_position", return_value=display.power_buttons[0].center):
            self.assertEqual(main.event_action(event, display, state), "POWER_CANCEL")
        with patch.object(main.spi_lcd, "mouse_position", return_value=display.power_buttons[1].center):
            self.assertEqual(main.event_action(event, display, state), "POWER_CONFIRM")
        with patch.object(main.spi_lcd, "mouse_position", return_value=display.game_rects[0].center):
            self.assertIsNone(main.event_action(event, display, state))

    def test_first_start_statement_fits_and_only_confirms_intentionally(self):
        for size in ((240, 320), (320, 240)):
            with self.subTest(size=size), patch.object(main.spi_lcd, "_pygame", pygame):
                display = main.LauncherDisplay(pygame.Surface(size))
                state = main.LauncherState(show_declaration=True)
                with patch.object(display, "centered", wraps=display.centered) as centered:
                    display.draw(state)
                labels = [call.args[0] for call in centered.call_args_list]
                for text in ("使用声明", "文武天尊", "七七四十九天", "九九八十一万亿", "Token",
                             "文怡然", "文焕然", "欧泽轩", "欧阳沐希", "否则将大祸临头", "切记切记"):
                    self.assertTrue(any(text in label for label in labels), text)
                text_bounds = []
                for call in centered.call_args_list:
                    text, font, _, center = call.args
                    bounds = pygame.Rect((0, 0), font.size(text))
                    bounds.center = center
                    self.assertTrue(display.screen.get_rect().contains(bounds), text)
                    if text not in ("确认", "知道了"):
                        self.assertLessEqual(bounds.bottom, display.declaration_button.top)
                        text_bounds.append(bounds)
                for index, bounds in enumerate(text_bounds):
                    self.assertFalse(any(bounds.colliderect(other) for other in text_bounds[index + 1:]))
                self.assertLessEqual(display.declaration_button.bottom, display.footer_top)
                event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(0, 0))
                with patch.object(main.spi_lcd, "mouse_position", return_value=display.declaration_button.center):
                    self.assertEqual(main.event_action(event, display, state), "K3")
                with patch.object(main.spi_lcd, "mouse_position", return_value=display.game_rects[0].center):
                    self.assertIsNone(main.event_action(event, display, state))
                with patch.object(main.spi_lcd, "mouse_position", return_value=display.buttons[0].center):
                    self.assertIsNone(main.event_action(event, display, state))
                with patch.object(main.spi_lcd, "mouse_position", return_value=display.buttons[2].center):
                    self.assertEqual(main.event_action(event, display, state), "K3")


class ShutdownTests(unittest.TestCase):
    def setUp(self):
        self.screen = pygame.Surface((240, 320))
        self.screen.fill((255, 255, 255))

    def test_simulator_never_requests_system_shutdown(self):
        with patch.object(main.spi_lcd, "present") as present, \
                patch.object(main.subprocess, "run") as run:
            self.assertEqual(main.request_shutdown(self.screen, True), (False, "模拟模式不会关机"))
        present.assert_not_called()
        run.assert_not_called()
        self.assertEqual(self.screen.get_at((0, 0))[:3], (255, 255, 255))

    def test_hardware_blacks_screen_before_shutdown(self):
        steps = []

        def present(*, poll_events):
            self.assertFalse(poll_events)
            self.assertEqual(self.screen.get_at((0, 0))[:3], (0, 0, 0))
            self.assertEqual(self.screen.get_at((239, 319))[:3], (0, 0, 0))
            steps.append("black")
            return True

        def run(command, **kwargs):
            steps.append("shutdown")
            self.assertEqual(command[-3:], ["shutdown", "-h", "now"])
            self.assertFalse(kwargs["check"])
            return unittest.mock.Mock(returncode=0)

        with patch.object(main.spi_lcd, "present", side_effect=present), \
                patch.object(main.subprocess, "run", side_effect=run):
            self.assertEqual(main.request_shutdown(self.screen, False), (True, ""))
        self.assertEqual(steps, ["black", "shutdown"])

    def test_shutdown_flushes_black_pixels_to_framebuffer(self):
        pygame.display.init()
        pygame.display.set_mode((1, 1))
        self.addCleanup(pygame.display.quit)
        with tempfile.TemporaryDirectory() as directory:
            framebuffer = os.path.join(directory, "framebuffer")

            def run(command, **kwargs):
                with open(framebuffer, "rb") as output:
                    pixels = output.read()
                self.assertEqual(len(pixels), 240 * 320 * 2)
                self.assertEqual(set(pixels), {0})
                return Mock(returncode=0)

            with patch.multiple(main.spi_lcd, _pygame=pygame, _screen=self.screen, _simulate=False,
                                FB_DEV=framebuffer, FB_WIDTH=240, FB_HEIGHT=320), \
                    patch.object(main.subprocess, "run", side_effect=run):
                self.assertEqual(main.request_shutdown(self.screen, False), (True, ""))

    def test_failed_black_screen_never_requests_shutdown(self):
        with patch.object(main.spi_lcd, "present", side_effect=OSError("framebuffer unavailable")), \
                patch.object(main.subprocess, "run") as run, patch("builtins.print"):
            self.assertEqual(main.request_shutdown(self.screen, False), (False, "关机失败"))
        run.assert_not_called()

    def test_failed_shutdown_reports_error(self):
        with patch.object(main.spi_lcd, "present", return_value=True), \
                patch.object(main.subprocess, "run", return_value=unittest.mock.Mock(returncode=1, stderr="denied")), \
                patch("builtins.print"):
            self.assertEqual(main.request_shutdown(self.screen, False), (False, "关机失败"))


class LauncherAppTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        marker = os.path.join(self.directory.name, "declaration-accepted")
        with open(marker, "w", encoding="utf-8") as output:
            output.write("accepted\n")
        marker_patch = patch.object(main, "DECLARATION_FILE", marker)
        marker_patch.start()
        self.addCleanup(marker_patch.stop)

    def test_first_start_requires_acknowledgement_and_remembers_it(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = os.path.join(directory, "data", "declaration-accepted")
            app = main.LauncherApp(declaration_path=marker)
            self.assertTrue(app.state.show_declaration)
            app.screen = pygame.Surface((240, 320))
            app.display = Mock()
            app.clock = Mock()
            actions = [["GAME_3", "K1", "POWER"], ["K3", "GAME_5"], ["EXIT"]]
            with patch.object(app, "poll_actions", side_effect=actions), \
                    patch.object(main.spi_lcd, "present", return_value=True), \
                    patch.object(app, "play") as play:
                app.run()
            play.assert_not_called()
            self.assertEqual(app.state.selected, 0)
            self.assertFalse(app.state.confirming_power)
            self.assertFalse(app.state.show_declaration)
            self.assertTrue(os.path.isfile(marker))
            restarted = main.LauncherApp(declaration_path=marker)
            self.assertFalse(restarted.state.show_declaration)
            self.assertEqual(restarted.state.handle_action("K3"), "LAUNCH")

    def test_unconfirmed_or_unsaved_statement_reappears_on_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = os.path.join(directory, "data", "declaration-accepted")
            app = main.LauncherApp(declaration_path=marker)
            app.display = Mock()
            app.clock = Mock()
            with patch.object(app, "poll_actions", return_value=["EXIT"]), \
                    patch.object(main.spi_lcd, "present", return_value=True):
                app.run()
            self.assertFalse(os.path.exists(marker))
            self.assertTrue(main.LauncherApp(declaration_path=marker).state.show_declaration)
            with patch("builtins.open", side_effect=PermissionError("read-only")), patch("builtins.print"):
                app.accept_declaration()
            self.assertFalse(app.state.show_declaration)
            self.assertIn("保存失败", app.state.notice)
            self.assertTrue(main.LauncherApp(declaration_path=marker).state.show_declaration)

    def test_concurrent_confirmation_does_not_overwrite_existing_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = os.path.join(directory, "declaration-accepted")
            app = main.LauncherApp(declaration_path=marker)
            with open(marker, "w", encoding="utf-8") as output:
                output.write("existing record")
            app.accept_declaration()
            with open(marker, encoding="utf-8") as source:
                self.assertEqual(source.read(), "existing record")
            self.assertFalse(app.state.show_declaration)
            self.assertEqual(app.state.notice, "")

    def test_simulator_first_start_draws_statement_before_the_menu(self):
        frames = []
        original_draw = main.LauncherDisplay.draw

        def draw(display, state):
            frames.append(state.show_declaration)
            original_draw(display, state)

        def init_display():
            pygame.init()
            pygame.display.set_mode((1, 1))
            return pygame.Surface((240, 320))

        events = iter(([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_3),
                        pygame.event.Event(pygame.KEYUP, key=pygame.K_3)],
                       [pygame.event.Event(pygame.QUIT)]))
        with tempfile.TemporaryDirectory() as directory:
            marker = os.path.join(directory, "declaration-accepted")
            with patch.object(main, "DECLARATION_FILE", marker), \
                    patch.object(main.sys, "argv", ["main.py", "--portrait"]), \
                    patch.object(main.spi_lcd, "init", side_effect=init_display), \
                    patch.object(main.spi_lcd, "is_simulate", return_value=True), \
                    patch.object(main.spi_lcd, "_pygame", pygame), \
                    patch.object(main.spi_lcd, "present", return_value=True), \
                    patch.object(main.LauncherDisplay, "draw", draw), \
                    patch.object(pygame.event, "get", side_effect=lambda: next(events)), \
                    patch.object(pygame.time, "Clock"), patch("builtins.print"):
                main.main()
            self.assertEqual(frames, [True, False])
            self.assertTrue(os.path.isfile(marker))

    def test_gpio_first_start_confirms_statement_on_k3_release(self):
        now = [0.0]
        levels = {pin: 1 for pin in main.BUTTON_PINS.values()}
        gpio = SimpleNamespace(BCM=1, IN=2, PUD_UP=3, LOW=0, input=levels.__getitem__,
                               setmode=Mock(), setup=Mock(), cleanup=Mock())
        real_buttons = main.GPIOButtons
        original_draw = main.LauncherDisplay.draw
        frames = []

        def draw(display, state):
            original_draw(display, state)
            frames.append(state.show_declaration)
            now[0] += 0.05
            if len(frames) == 1:
                levels[main.BUTTON_PINS["K3"]] = 0
            elif len(frames) == 4:
                levels[main.BUTTON_PINS["K3"]] = 1
            self.assertLess(len(frames), 20)

        def init_display():
            pygame.init()
            return pygame.Surface((240, 320))

        with tempfile.TemporaryDirectory() as directory:
            marker = os.path.join(directory, "declaration-accepted")
            importer = SimpleNamespace(import_module=Mock(return_value=gpio))
            with patch.object(main, "DECLARATION_FILE", marker), \
                    patch.object(main.sys, "argv", ["main.py", "--spi", "--portrait"]), \
                    patch.dict(os.environ, {"POKEMON_PORTRAIT": "1"}), \
                    patch.object(main.spi_lcd, "init", side_effect=init_display), \
                    patch.object(main.spi_lcd, "is_simulate", return_value=False), \
                    patch.object(main.spi_lcd, "_pygame", pygame), \
                    patch.object(main.spi_lcd, "present", side_effect=lambda **kwargs: frames[-1]), \
                    patch.object(main, "importlib", importer), \
                    patch.object(main, "GPIOButtons", side_effect=lambda device: real_buttons(device, clock=lambda: now[0])), \
                    patch.object(main.LauncherDisplay, "draw", draw), \
                    patch.object(pygame.time, "Clock"), patch("builtins.print"):
                main.main()
            self.assertTrue(frames[0])
            self.assertFalse(frames[-1])
            self.assertTrue(os.path.isfile(marker))
        gpio.cleanup.assert_called_once_with(list(main.BUTTON_PINS.values()))

    def test_game_handoff_reopens_launcher_and_preserves_selection(self):
        app = main.LauncherApp()
        app.state.selected = 3
        app.simulate = True
        app.display = SimpleNamespace(portrait=True)
        steps = []
        with patch.object(app, "close", side_effect=lambda: steps.append("close")), \
                patch.object(app, "open", side_effect=lambda after_game: steps.append(("open", after_game))), \
                patch.object(main, "launch_game", side_effect=lambda *args: steps.append(args) or 0):
            app.play()
        self.assertEqual(steps, ["close", (main.GAMES[3], True, True), ("open", True)])
        self.assertEqual(app.state.selected, 3)
        self.assertEqual(app.state.notice, "")

    def test_game_launch_failure_still_reopens_launcher(self):
        app = main.LauncherApp()
        app.simulate = True
        app.display = SimpleNamespace(portrait=False)
        with patch.object(app, "close"), patch.object(app, "open") as open_display, \
                patch.object(main, "launch_game", side_effect=OSError("failed")), patch("builtins.print"):
            app.play()
        open_display.assert_called_once_with(after_game=True)
        self.assertEqual(app.state.notice, "游戏启动失败")

    def test_hardware_releases_and_reinitializes_gpio_around_game(self):
        levels = {pin: 1 for pin in main.BUTTON_PINS.values()}
        gpio = SimpleNamespace(BCM=1, IN=2, PUD_UP=3, LOW=0, input=levels.__getitem__,
                               setmode=Mock(), setup=Mock(), cleanup=Mock())
        app = main.LauncherApp()

        def init_display():
            pygame.init()
            return pygame.Surface((240, 320))

        def launch(game, simulate, portrait):
            self.assertFalse(simulate)
            self.assertTrue(portrait)
            self.assertIsNone(app.buttons)
            self.assertEqual(gpio.cleanup.call_count, 1)
            return 0

        with patch.object(main.spi_lcd, "init", side_effect=init_display), \
                patch.object(main.spi_lcd, "is_simulate", return_value=False), \
                patch.object(main.spi_lcd, "_pygame", pygame), \
                patch.object(main, "importlib") as importlib_mock, \
                patch.object(main, "launch_game", side_effect=launch):
            importlib_mock.import_module.return_value = gpio
            try:
                app.open()
                app.play()
                self.assertEqual(gpio.setup.call_count, 6)
                self.assertTrue(app.release_gate)
            finally:
                app.close()
        self.assertEqual(gpio.cleanup.call_count, 2)

    def test_release_after_game_does_not_confirm_or_open_shutdown(self):
        now = [0.0]
        levels = {pin: 1 for pin in main.BUTTON_PINS.values()}
        gpio = SimpleNamespace(BCM=1, IN=2, PUD_UP=3, LOW=0, input=levels.__getitem__,
                               setmode=Mock(), setup=Mock(), cleanup=Mock())
        app = main.LauncherApp()
        app.buttons = main.GPIOButtons(gpio, clock=lambda: now[0])
        app.release_gate = True
        levels[24] = 0
        self.assertEqual(app.poll_actions(), [])
        now[0] = 0.05
        self.assertEqual(app.poll_actions(), [])
        now[0] = 1.1
        self.assertEqual(app.poll_actions(), [])
        levels[24] = 1
        now[0] = 1.2
        self.assertEqual(app.poll_actions(), [])
        now[0] = 1.25
        self.assertEqual(app.poll_actions(), [])
        self.assertFalse(app.release_gate)
        levels[24] = 0
        now[0] = 1.3
        app.poll_actions()
        now[0] = 1.35
        app.poll_actions()
        levels[24] = 1
        now[0] = 1.4
        app.poll_actions()
        now[0] = 1.45
        self.assertEqual(app.poll_actions(), ["K3"])

    def test_run_requires_explicit_shutdown_confirmation(self):
        app = main.LauncherApp()
        app.screen = pygame.Surface((240, 320))
        app.display = Mock()
        app.clock = Mock()
        actions = [["POWER"], ["K3"], ["POWER"], ["K2"], ["K3"]]
        with patch.object(app, "poll_actions", side_effect=actions), \
                patch.object(main.spi_lcd, "present", return_value=True), \
                patch.object(main, "request_shutdown", return_value=(True, "")) as shutdown:
            app.run()
        shutdown.assert_called_once_with(app.screen, True)
        self.assertFalse(app.running)

    def test_simulated_shutdown_returns_to_menu_with_notice(self):
        app = main.LauncherApp()
        app.screen = pygame.Surface((240, 320))
        app.display = Mock()
        app.clock = Mock()
        actions = [["POWER"], ["K2"], ["K3"], ["EXIT"]]
        with patch.object(app, "poll_actions", side_effect=actions), \
                patch.object(main.spi_lcd, "present", return_value=True), \
                patch.object(main.subprocess, "run") as run:
            app.run()
        run.assert_not_called()
        self.assertFalse(app.state.confirming_power)
        self.assertEqual(app.state.notice, "模拟模式不会关机")

    def test_failed_hardware_shutdown_returns_to_menu(self):
        app = main.LauncherApp()
        app.screen = pygame.Surface((240, 320))
        app.display = Mock()
        app.clock = Mock()
        app.simulate = False
        actions = [["POWER"], ["K2"], ["K3"], ["EXIT"]]
        with patch.object(app, "poll_actions", side_effect=actions), \
                patch.object(main.spi_lcd, "present", return_value=True), \
                patch.object(main, "request_shutdown", return_value=(False, "关机失败")):
            app.run()
        self.assertFalse(app.state.confirming_power)
        self.assertEqual(app.state.notice, "关机失败")

    def test_hardware_gpio_confirmation_flushes_black_then_shuts_down(self):
        now = [0.0]
        levels = {pin: 1 for pin in main.BUTTON_PINS.values()}
        gpio = SimpleNamespace(BCM=1, IN=2, PUD_UP=3, LOW=0, input=levels.__getitem__,
                               setmode=Mock(), setup=Mock(), cleanup=Mock())
        real_buttons = main.GPIOButtons
        original_draw = main.LauncherDisplay.draw
        progress = {"stage": 0, "frames": 0, "wait": 0}

        def draw(display, state):
            original_draw(display, state)
            now[0] += 0.05
            progress["frames"] += 1
            stage = progress["stage"]
            if stage == 0:
                levels[24] = 0
                progress["stage"] = 1
            elif stage == 1 and state.confirming_power:
                self.assertEqual(state.power_selected, 0)
                levels[24] = 1
                progress["stage"] = 2
            elif stage == 2:
                progress["wait"] += 1
                if progress["wait"] == 4:
                    levels[23] = 0
                    progress["stage"] = 3
            elif stage == 3 and state.power_selected == 1:
                levels[23] = 1
                progress["stage"] = 4
                progress["wait"] = 0
            elif stage == 4:
                progress["wait"] += 1
                if progress["wait"] == 4:
                    levels[24] = 0
                    progress["stage"] = 5
                    progress["wait"] = 0
            elif stage == 5:
                progress["wait"] += 1
                if progress["wait"] == 4:
                    levels[24] = 1
                    progress["stage"] = 6
            self.assertLess(progress["frames"], 100)

        with tempfile.TemporaryDirectory() as directory:
            framebuffer = os.path.join(directory, "framebuffer")
            with open(framebuffer, "wb") as output:
                output.write(b"initial")

            def shutdown(command, **kwargs):
                self.assertEqual(progress["stage"], 6)
                with open(framebuffer, "rb") as source:
                    pixels = source.read()
                self.assertEqual(len(pixels), 240 * 320 * 2)
                self.assertEqual(set(pixels), {0})
                return Mock(returncode=0)

            with patch.dict(os.environ, {"POKEMON_SIMULATE": "0", "SDL_AUDIODRIVER": "dummy"}), \
                    patch.object(main.sys, "argv", ["main.py", "--spi"]), \
                    patch.multiple(main.spi_lcd, FB_DEV=framebuffer, _simulate=None,
                                   _screen=None, _window=None, _pygame=None), \
                    patch.object(main.spi_lcd, "_fb_size", return_value=(240, 320)), \
                    patch.object(main, "importlib") as importlib_mock, \
                    patch.object(main, "GPIOButtons", side_effect=lambda device: real_buttons(device, clock=lambda: now[0])), \
                    patch.object(main.LauncherDisplay, "draw", draw), \
                    patch.object(main.subprocess, "run", side_effect=shutdown) as run, \
                    patch.object(pygame.time, "Clock"), patch("builtins.print"):
                importlib_mock.import_module.return_value = gpio
                main.main()
        run.assert_called_once()
        gpio.cleanup.assert_called_once_with(list(main.BUTTON_PINS.values()))


if __name__ == "__main__":
    unittest.main()