# -*- coding: utf-8 -*-
"""SPI 屏校色工具: 实时调整 GAMMA / CONTRAST, 治理屏幕泛白发灰。

画面: 上半部灰阶条(看黑位是否发灰/白位是否刺眼)
      中部彩色条 + 实际图鉴页面预览
      底部显示当前参数

按键:
    K1 (GPIO5): 当前参数 -0.05
    K2 (GPIO23): 当前参数 +0.05
    K3 (GPIO24): 在 GAMMA / CONTRAST 之间切换

本机模拟: 键盘 1/2/3 代替按键, Esc 退出。
注意: 校色只对真机 /dev/fb1 输出生效, PC 窗口预览数值变化但不显色差。

调好后把满意的两 个数值写回 spi_lcd.py 顶部:
    DISPLAY_GAMMA = ...
    DISPLAY_CONTRAST = ...
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import spi_lcd

screen = spi_lcd.init()
import pygame  # noqa: E402

FB_WIDTH, FB_HEIGHT = screen.get_size()
PORTRAIT = FB_HEIGHT > FB_WIDTH  # 旋屏后 240x320

font = spi_lcd.load_font(16)
font_small = spi_lcd.load_font(13)

# 预览图: 取图鉴里的一张, 没有就用色块代替
PREVIEW_IMG = None
_img_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "pokedex_data", "images", "骑拉帝纳.png")
if os.path.exists(_img_path):
    PREVIEW_IMG = pygame.transform.smoothscale(
        pygame.image.load(_img_path).convert_alpha(), (100, 100))

# ---------------------------------------------------------------------------
# GPIO(与 test_button.py 相同)
# ---------------------------------------------------------------------------
BUTTONS = {"K1": 5, "K2": 23, "K3": 24}
gpio = None
try:
    import RPi.GPIO as GPIO  # noqa: E402

    GPIO.setmode(GPIO.BCM)
    for name, pin in BUTTONS.items():
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    gpio = GPIO
    print("GPIO 初始化完成: K1=GPIO5 K2=GPIO23 K3=GPIO24")
except ImportError:
    print("模拟模式: 按 1/2/3 代替 K1/K2/K3 (K1减 K2加 K3切换项), Esc 退出。")
except Exception as e:
    print("GPIO 初始化失败(%s), 模拟模式: 1/2/3 操作, Esc 退出。" % e)

adjust_key = "GAMMA"  # 当前正在调的参数
STEP = 0.05


def clamp_param(key, val):
    return max(0.5, min(2.5, round(val * 100) / 100))


def draw():
    screen.fill((0, 0, 0))

    # --- 灰阶条 (8 段, 从黑到白) ---
    bar_h = 40
    for i in range(8):
        v = int(i * 255 / 7)
        pygame.draw.rect(screen, (v, v, v), (i * FB_WIDTH // 8, 6,
                                             FB_WIDTH // 8, bar_h))

    # --- 彩色条 ---
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255),
              (255, 255, 0), (0, 255, 255), (255, 0, 255),
              (255, 128, 0), (128, 128, 128)]
    cw = FB_WIDTH // len(colors)
    for i, c in enumerate(colors):
        pygame.draw.rect(screen, c, (i * cw, 50, cw, 18))

    # --- 实际内容预览(图鉴页) ---
    pygame.draw.rect(screen, (18, 22, 30), (0, 72, FB_WIDTH, FB_HEIGHT - 92))
    if PORTRAIT:
        # 竖屏 240x320: 小图 + 短提示
        pv = pygame.transform.smoothscale(PREVIEW_IMG, (84, 84)) if PREVIEW_IMG else None
        if pv:
            screen.blit(pv, (10, 84))
        tx = 100
        screen.blit(font_small.render("#487 骑拉帝纳", True, (235, 238, 244)), (tx, 86))
        screen.blit(font_small.render("幽灵/龙", True, (150, 160, 178)), (tx, 106))
        screen.blit(font_small.render("黑位别发灰", True, (0, 255, 140)), (tx, 134))
        screen.blit(font_small.render("白位别刺眼", True, (0, 255, 140)), (tx, 152))
    else:
        if PREVIEW_IMG:
            screen.blit(PREVIEW_IMG, (10, 90))
        tx = 120
        screen.blit(font.render("#487 骑拉帝纳", True, (235, 238, 244)), (tx, 88))
        screen.blit(font_small.render("幽灵 / 龙", True, (150, 160, 178)), (tx, 112))
        screen.blit(font_small.render("黑位: 看左上角是否发灰", True, (0, 255, 140)), (tx, 140))
        screen.blit(font_small.render("白位: 看右上网点是否刺眼", True, (0, 255, 140)), (tx, 158))
        screen.blit(font_small.render("皮肤/彩色是否过饱和", True, (0, 255, 140)), (tx, 176))

    # --- 参数显示 ---
    pygame.draw.rect(screen, (40, 52, 74), (0, FB_HEIGHT - 20, FB_WIDTH, 20))
    g, c = spi_lcd.DISPLAY_GAMMA, spi_lcd.DISPLAY_CONTRAST
    g_mark = "<" if adjust_key == "GAMMA" else " "
    c_mark = "<" if adjust_key == "CONTRAST" else " "
    txt = "GAMMA%s %.2f    CONTRAST%s %.2f   (K3切换)" % (g_mark, g, c_mark, c)
    t = font_small.render(txt, True, (0, 255, 140) if True else (235, 238, 244))
    screen.blit(t, (10, FB_HEIGHT - 18))

    return spi_lcd.present()


def adjust(direction):
    """K1: -step, K2: +step, 作用于当前选中参数。"""
    global adjust_key
    if adjust_key == "GAMMA":
        spi_lcd.DISPLAY_GAMMA = clamp_param("GAMMA", spi_lcd.DISPLAY_GAMMA + direction * STEP)
    else:
        spi_lcd.DISPLAY_CONTRAST = clamp_param("CONTRAST", spi_lcd.DISPLAY_CONTRAST + direction * STEP)
    print("GAMMA=%.2f  CONTRAST=%.2f" % (spi_lcd.DISPLAY_GAMMA, spi_lcd.DISPLAY_CONTRAST))


_state = {}  # 按键状态


def _act(name):
    """按键动作分发。"""
    global adjust_key
    if name == "K3":
        adjust_key = "CONTRAST" if adjust_key == "GAMMA" else "GAMMA"
        print("正在调整:", adjust_key)
    elif name == "K1":
        adjust(-1)
    elif name == "K2":
        adjust(1)
    # 关键: 参数变化后必须重绘, 真机才会重新写 /dev/fb1 生效
    draw()


try:
    running = draw()
    import time

    while running:
        if gpio is not None:
            # 真机: 轮询按键(带长按连发)
            for name, pin in BUTTONS.items():
                pressed = gpio.input(pin) == gpio.LOW
                st = _state.setdefault(name, {"down": False, "t0": 0, "last": 0})
                if pressed and not st["down"]:
                    st["down"], st["t0"], st["last"] = True, time.time(), time.time()
                    _act(name)
                elif pressed and st["down"] and time.time() - st["t0"] > 0.4 \
                        and time.time() - st["last"] > 0.12:
                    st["last"] = time.time()
                    _act(name)
                elif not pressed:
                    st["down"] = False
            if not spi_lcd.pump():
                break
            time.sleep(0.01)
        else:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_q):
                        running = False
                    elif event.key == pygame.K_1:
                        _act("K1")
                    elif event.key == pygame.K_2:
                        _act("K2")
                    elif event.key == pygame.K_3:
                        _act("K3")
            pygame.time.wait(16)
except KeyboardInterrupt:
    pass
finally:
    print()
    print("=" * 46)
    print("最终参数(写回 spi_lcd.py 顶部):")
    print("DISPLAY_GAMMA = %.2f" % spi_lcd.DISPLAY_GAMMA)
    print("DISPLAY_CONTRAST = %.2f" % spi_lcd.DISPLAY_CONTRAST)
    print("=" * 46)
    if gpio is not None:
        gpio.cleanup()
    pygame.quit()
    sys.exit()