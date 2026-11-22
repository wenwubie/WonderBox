"""测试树莓派 Zero 2W 上的三个按键 K1/K2/K3。

接线（按键另一端统一接 GND，启用内部上拉，按下为低电平）：
    K1 -> GPIO5 (物理引脚 29)
    K2 -> GPIO23 (物理引脚 16)
    K3 -> GPIO24 (物理引脚 18)

按下任意按键后，SPI 屏上实时显示对应 "Kx 已按下"。

本机调试（无树莓派）时会自动进入模拟模式：按键盘 1/2/3 或点击对应按键行代替 K1/K2/K3。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import spi_lcd

# 覆盖开关（不改则沿用 common/spi_lcd.py 顶部的 SIMULATE_DISPLAY / 自动检测）
# spi_lcd.SIMULATE_DISPLAY = True   # 强制本机窗口
# spi_lcd.SIMULATE_DISPLAY = False  # 强制树莓派 /dev/fb1

BUTTONS = {  # 名称 -> BCM 编号
    "K1": 5,
    "K2": 23,
    "K3": 24,
}

BG_COLOR = (20, 40, 80)
TEXT_COLOR = (255, 255, 255)
ACTIVE_COLOR = (0, 255, 127)
GPIO_COLOR = (255, 215, 0)

# ---------------------------------------------------------------------------
# 初始化显示（必须在 import pygame 之前）
# ---------------------------------------------------------------------------
screen = spi_lcd.init()
import pygame  # noqa: E402  必须在 spi_lcd.init() 之后，环境变量才生效

FB_WIDTH, FB_HEIGHT = screen.get_size()

title_font = spi_lcd.load_font(22)
item_font = spi_lcd.load_font(28)

pressed = {name: False for name in BUTTONS}

# ---------------------------------------------------------------------------
# 尝试初始化真实 GPIO；失败则进入键盘模拟模式
# ---------------------------------------------------------------------------
gpio = None
try:
    import RPi.GPIO as GPIO  # noqa: E402

    GPIO.setmode(GPIO.BCM)
    for name, pin in BUTTONS.items():
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    gpio = GPIO
    print("GPIO 初始化完成：" + ", ".join(f"{n}=GPIO{p}" for n, p in BUTTONS.items()))
except ImportError:
    print("⚠️ 未检测到 RPi.GPIO，进入模拟模式：按 1/2/3 或点击对应按键行，Esc 退出。")
except Exception as e:
    print(f"⚠️ GPIO 初始化失败（{e}），进入模拟模式：按 1/2/3 或点击对应按键行，Esc 退出。")


def draw():
    """根据 pressed 状态刷新整屏。"""
    screen.fill(BG_COLOR)

    title = title_font.render("按键测试 K1/K2/K3", True, TEXT_COLOR)
    screen.blit(title, ((FB_WIDTH - title.get_width()) // 2, 12))

    y = 55
    for name, pin in BUTTONS.items():
        if pressed[name]:
            text = item_font.render(f"{name} 已按下!", True, ACTIVE_COLOR)
            pygame.draw.circle(screen, ACTIVE_COLOR, (45, y + 18), 8)
        else:
            text = item_font.render(f"{name} 未按下", True, (120, 140, 170))
            pygame.draw.circle(screen, (120, 140, 170), (45, y + 18), 8)
        screen.blit(text, (70, y))
        pin_text = title_font.render(f"GPIO{pin}", True, GPIO_COLOR)
        screen.blit(pin_text, (FB_WIDTH - pin_text.get_width() - 15, y + 5))
        y += 55

    return spi_lcd.present()


def read_gpio_state():
    """真机：读三个引脚电平（内部上拉，低电平 = 按下）。"""
    for name, pin in BUTTONS.items():
        pressed[name] = gpio.input(pin) == gpio.LOW


def read_keyboard_events(running):
    """模拟：键盘 1/2/3 切换对应按键状态。"""
    key_map = {pygame.K_1: "K1", pygame.K_2: "K2", pygame.K_3: "K3"}
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_q):
                return False
            if event.key in key_map:
                name = key_map[event.key]
                pressed[name] = not pressed[name]
        elif event.type == pygame.MOUSEBUTTONDOWN:
            position = spi_lcd.mouse_position(event)
            if position is not None:
                y = position[1]
                if 55 <= y < 55 + len(BUTTONS) * 55:
                    name = tuple(BUTTONS)[(y - 55) // 55]
                    pressed[name] = not pressed[name]
    return running


try:
    draw()
    running = True
    last_state = dict(pressed)

    while running:
        if gpio is not None:
            read_gpio_state()
        running = read_keyboard_events(running) if gpio is None else spi_lcd.pump()

        # 状态有变化才重绘（真机），模拟模式事件驱动也会走到这里
        if pressed != last_state:
            for name in BUTTONS:
                if pressed[name] != last_state[name]:
                    state = "已按下" if pressed[name] else "已松开"
                    print(f"{name} {state}")
            last_state = dict(pressed)
            if not draw():
                break
        elif gpio is None:
            # 模拟模式：无变化时也定期 pump 事件，窗口才能保持响应
            pygame.time.wait(16)

        if gpio is not None:
            pygame.time.wait(10)  # 轮询间隔，兼顾响应速度与 CPU 占用
except KeyboardInterrupt:
    print("\n程序已安全退出。")
finally:
    if gpio is not None:
        gpio.cleanup()
    pygame.quit()
    sys.exit()
