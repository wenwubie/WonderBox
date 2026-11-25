import time


BUTTON_PINS = {"K1": 5, "K2": 23, "K3": 24}
DEBOUNCE_SECONDS = 0.035
QUIT_HOLD_SECONDS = 1.0
REPLAY_ACTION = "REPLAY"
REPLAY_HOLD_SECONDS = 0.7  # 长按 K2 重播语音的秒数


class HoldGesture:
    def __init__(self, short_action, long_action, seconds, clock=time.monotonic):
        self.short_action = short_action
        self.long_action = long_action
        self.seconds = seconds
        self.clock = clock
        self.source = None
        self.started = 0.0
        self.long_sent = False

    def press(self, source, now=None):
        if self.source is None:
            self.source = source
            self.started = self.clock() if now is None else now
            self.long_sent = False

    def release(self, source, now=None):
        if self.source != source:
            return None
        action = self.poll(now)
        if action is None and not self.long_sent:
            action = self.short_action
        self.cancel()
        return action

    def cancel(self):
        self.source = None

    def poll(self, now=None):
        if self.source is None or self.long_sent:
            return None
        if (self.clock() if now is None else now) - self.started >= self.seconds:
            self.long_sent = True
            return self.long_action
        return None


class SimulatedHold(HoldGesture):
    def __init__(self, short_action, long_action, seconds, clock=time.monotonic,
                 k2_long_action=None, k2_hold_seconds=REPLAY_HOLD_SECONDS):
        super().__init__(short_action, long_action, seconds, clock)
        self.blocked_sources = set()
        # 可选的第二路长按：K2 长按重播语音；短按 K2 语义保持不变。
        self.k2 = (HoldGesture("K2", k2_long_action, k2_hold_seconds, clock)
                   if k2_long_action else None)

    def block_held(self, pygame, keys):
        pygame.event.pump()
        pressed = pygame.key.get_pressed()
        self.blocked_sources.update(("key", key) for key in keys if pressed[key])
        if pygame.mouse.get_pressed()[0]:
            self.blocked_sources.add(("mouse", 1))

    def handle_event(self, pygame, event, action):
        if event.type == pygame.WINDOWFOCUSLOST:
            self.cancel()
            self.blocked_sources.clear()
            return None
        if event.type in (pygame.KEYDOWN, pygame.KEYUP):
            source = ("key", event.key)
            down = event.type == pygame.KEYDOWN
        elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP) and event.button == 1:
            source = ("mouse", event.button)
            down = event.type == pygame.MOUSEBUTTONDOWN
        else:
            return action
        if source in self.blocked_sources:
            if not down:
                self.blocked_sources.remove(source)
            return None
        if not down:
            # K2 的短按要等松开才发，避免长按重播时误触发 K2 原有功能
            if self.k2 is not None and self.k2.source == source:
                return self.k2.release(source)
            return self.release(source)
        if self.k2 is not None and action == "K2":
            if not getattr(event, "repeat", False):
                self.k2.press(source)
            return None
        if action == self.short_action:
            if not getattr(event, "repeat", False):
                self.press(source)
            return None
        return action

    def poll(self, now=None):
        action = super().poll(now)
        if action:
            return action
        if self.k2 is not None:
            return self.k2.poll(now)
        return None


class GPIOButtons:
    def __init__(self, gpio, clock=time.monotonic, *, hold_seconds=QUIT_HOLD_SECONDS,
                 long_action="QUIT", debounce_seconds=DEBOUNCE_SECONDS,
                 k2_long_action=None, k2_hold_seconds=REPLAY_HOLD_SECONDS):
        self.gpio = gpio
        self.clock = clock
        self.debounce_seconds = debounce_seconds
        self.hold = HoldGesture("K3", long_action, hold_seconds, clock)
        # K2 长按重播：提供 long_action 后，K2 短按改为松开时发出，避免误触
        self.k2_hold = (HoldGesture("K2", k2_long_action, k2_hold_seconds, clock)
                        if k2_long_action else None)
        try:
            gpio.setmode(gpio.BCM)
            for pin in BUTTON_PINS.values():
                gpio.setup(pin, gpio.IN, pull_up_down=gpio.PUD_UP)
        except Exception:
            gpio.cleanup()
            raise
        self.states = {name: {"raw": False, "down": False, "changed": clock()}
                       for name in BUTTON_PINS}

    def is_released(self, name):
        state = self.states[name]
        return (not state["raw"] and not state["down"]
                and self.gpio.input(BUTTON_PINS[name]) != self.gpio.LOW)

    def poll(self):
        now = self.clock()
        actions = []
        for name, pin in BUTTON_PINS.items():
            state = self.states[name]
            pressed = self.gpio.input(pin) == self.gpio.LOW
            if pressed != state["raw"]:
                state["raw"] = pressed
                state["changed"] = now
            if pressed != state["down"] and now - state["changed"] >= self.debounce_seconds:
                state["down"] = pressed
                if name == "K2" and self.k2_hold is not None:
                    if pressed:
                        self.k2_hold.press(name, state["changed"])
                    else:
                        action = self.k2_hold.release(name, state["changed"])
                        if action:
                            actions.append(action)
                elif pressed and name != "K3":
                    actions.append(name)
                elif name == "K3":
                    if pressed:
                        self.hold.press(name, state["changed"])
                    else:
                        action = self.hold.release(name, state["changed"])
                        if action:
                            actions.append(action)
            if pressed and state["down"]:
                if name == "K3":
                    action = self.hold.poll(now)
                    if action:
                        actions.append(action)
                elif name == "K2" and self.k2_hold is not None:
                    action = self.k2_hold.poll(now)
                    if action:
                        actions.append(action)
        return actions

    def cleanup(self):
        self.gpio.cleanup(list(BUTTON_PINS.values()))