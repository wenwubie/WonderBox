import time


BUTTON_PINS = {"K1": 5, "K2": 23, "K3": 24}
DEBOUNCE_SECONDS = 0.035
QUIT_HOLD_SECONDS = 1.0


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
    def __init__(self, short_action, long_action, seconds, clock=time.monotonic):
        super().__init__(short_action, long_action, seconds, clock)
        self.blocked_sources = set()

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
            return self.release(source)
        if action == self.short_action:
            if not getattr(event, "repeat", False):
                self.press(source)
            return None
        return action


class GPIOButtons:
    def __init__(self, gpio, clock=time.monotonic, *, hold_seconds=QUIT_HOLD_SECONDS,
                 long_action="QUIT", debounce_seconds=DEBOUNCE_SECONDS):
        self.gpio = gpio
        self.clock = clock
        self.debounce_seconds = debounce_seconds
        self.hold = HoldGesture("K3", long_action, hold_seconds, clock)
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
                if pressed and name != "K3":
                    actions.append(name)
                elif name == "K3":
                    if pressed:
                        self.hold.press(name, state["changed"])
                    else:
                        action = self.hold.release(name, state["changed"])
                        if action:
                            actions.append(action)
            if name == "K3" and pressed and state["down"]:
                action = self.hold.poll(now)
                if action:
                    actions.append(action)
        return actions

    def cleanup(self):
        self.gpio.cleanup(list(BUTTON_PINS.values()))