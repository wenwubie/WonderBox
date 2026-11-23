"""320x240 SPI LCD 显示层：本机窗口模拟，或写入树莓派 /dev/fb1。"""
from __future__ import annotations

import array
import os
import sys
import time

from common.button_input import SimulatedHold as _SimulatedHold

# =============================================================================
# 显示目标开关（改这一处即可，test_show / test_tft 都会跟着变）
#
#   True  : 本机弹出 pygame 窗口，按 240x320 或 320x240 逻辑分辨率绘制
#   False : dummy 驱动 + 写入 /dev/fb1（树莓派 SPI 屏）
#   None  : 自动。存在 /dev/fb1 用真机，否则本机窗口
# =============================================================================
SIMULATE_DISPLAY = None

FB_WIDTH = 320
FB_HEIGHT = 240
FB_DEV = "/dev/fb1"
WINDOW_SCALE = 2  # 本机窗口放大倍数；初始化时按可用桌面尺寸自动下调
WINDOW_ACTUAL_SCALE = WINDOW_SCALE

# =============================================================================
# 显示校色（仅真机写 /dev/fb1 时生效，PC 模拟窗口不受影响）
#
# 针对 SPI 屏泛白/发灰/反光感：写屏前对 RGB 做伽马 + 对比度校正。
#   GAMMA    >1 压暗画面（治泛白），<1 提亮；1.0 = 关闭
#   CONTRAST >1 增强对比（黑更黑白更白），<1 降低；1.0 = 关闭
# 推荐起点：GAMMA=1.10, CONTRAST=1.25，配合 tune_display.py 实时微调。
# =============================================================================
DISPLAY_GAMMA = 1.10
DISPLAY_CONTRAST = 1.20

_lut_cache = None  # (gamma, contrast, lut) 简单缓存, 参数变化自动重建


def _get_display_lut():
    """构建 256 项颜色查找表; 参数均为 1.0 时返回 None(不校正)。"""
    global _lut_cache
    if DISPLAY_GAMMA == 1.0 and DISPLAY_CONTRAST == 1.0:
        return None
    if _lut_cache is not None:
        g, c, lut = _lut_cache
        if g == DISPLAY_GAMMA and c == DISPLAY_CONTRAST:
            return lut
    lut = []
    for i in range(256):
        v = i / 255.0
        v = v ** (1.0 / DISPLAY_GAMMA)          # 伽马
        v = (v - 0.5) * DISPLAY_CONTRAST + 0.5   # 围绕中点的对比度拉伸
        v = max(0.0, min(1.0, v))
        lut.append(int(round(v * 255)))
    _lut_cache = (DISPLAY_GAMMA, DISPLAY_CONTRAST, lut)
    return lut

_simulate: bool | None = None
_screen = None
_window = None
_pygame = None


def _want_simulate() -> bool:
    if SIMULATE_DISPLAY is not None:
        return bool(SIMULATE_DISPLAY)
    env = os.environ.get("POKEMON_SIMULATE")
    if env is not None:
        return env.strip().lower() not in ("0", "false", "no", "spi")
    if "--spi" in sys.argv:
        return False
    if "--sim" in sys.argv:
        return True
    return not os.path.exists(FB_DEV)


def is_simulate() -> bool:
    if _simulate is None:
        return _want_simulate()
    return _simulate


def load_font(size: int = 24):
    """优先用项目里的 font.ttf，本机自动回退到系统中文字体。"""
    pygame = _pygame
    if pygame is None:
        raise RuntimeError("请先调用 spi_lcd.init()")

    candidates = [
        "font.ttf",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "font.ttf"),
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simsun.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttf",
        "/usr/share/fonts/truetype/wqy-zenhei/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    ]
    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            return pygame.font.Font(path, size)
        except Exception:
            continue
    return pygame.font.Font(None, size)


def _want_portrait() -> bool:
    """模拟模式默认竖屏(240x320)，POKEMON_PORTRAIT 或参数可覆盖。"""
    env = os.environ.get("POKEMON_PORTRAIT")
    if env is not None:
        return env.strip().lower() not in ("0", "false", "no", "landscape")
    return "--landscape" not in sys.argv


def _fit_window_scale(pygame, width: int, height: int) -> int:
    """将模拟窗口限制在可用桌面内，并为窗口边框预留空间。"""
    info = pygame.display.Info()
    desktop_width, desktop_height = info.current_w, info.current_h
    if desktop_width <= 0 or desktop_height <= 0:
        return max(1, int(WINDOW_SCALE))

    if os.name == "nt":
        try:
            import ctypes

            class Rect(ctypes.Structure):
                _fields_ = [(name, ctypes.c_long) for name in ("left", "top", "right", "bottom")]

            work_area = Rect()
            if ctypes.windll.user32.SystemParametersInfoW(
                0x0030, 0, ctypes.byref(work_area), 0
            ):
                desktop_width = work_area.right - work_area.left - 32
                desktop_height = work_area.bottom - work_area.top - 48
        except (AttributeError, OSError):
            desktop_width -= 32
            desktop_height -= 96
    else:
        desktop_width -= 32
        desktop_height -= 96

    if desktop_width <= 0 or desktop_height <= 0:
        return 1
    return max(1, min(int(WINDOW_SCALE), desktop_width // width, desktop_height // height))


def _fb_size():
    """ioctl 读取 /dev/fb1 实际分辨率。
    fbtft 驱动 rotate=90/270 时为 320x240(横), rotate=0/180 时为 240x320(竖)。"""
    import fcntl
    import struct

    FBIOGET_VSCREENINFO = 0x4600
    with open(FB_DEV, "rb") as f:
        buf = bytearray(160)
        fcntl.ioctl(f.fileno(), FBIOGET_VSCREENINFO, buf)
        xres, yres = struct.unpack_from("II", buf, 0)
    return int(xres), int(yres)


def init():
    """初始化画布。必须在 import pygame 之前、或至少在 pygame.init 之前调用。

    真机: 自动读取 fb1 实际分辨率(横竖屏自适应), FB_WIDTH/FB_HEIGHT 会随之更新。
    模拟: 默认 240x320 竖屏; 设 POKEMON_PORTRAIT=0 或加 --landscape 可模拟横屏。
    """
    global _simulate, _screen, _window, _pygame, FB_WIDTH, FB_HEIGHT, WINDOW_ACTUAL_SCALE

    _simulate = _want_simulate()
    os.environ.setdefault("PYGAME_DETECT_AVX2", "1")

    # 默认让 pygame.init() 用 dummy 音频驱动：本程序大多不需要声音，
    # 用真驱动会打开 ALSA/系统声卡，MAX98357 功放在设备开关时会"啪"一声。
    # 需要发声的游戏只要在 init() 之前调用 common.audio.prepare() 声明，
    # 这里就会跳过 dummy，让 pygame.init() 一次打开真实设备。
    try:
        from common import audio as _audio
        _want_sound = _audio.is_activated()
    except Exception:
        _want_sound = False
    if not _want_sound:
        # 必须无条件覆盖，不能用 setdefault：
        # 若 shell 环境里残留了 SDL_AUDIODRIVER=alsa（例如调试粘猴音频时 export 过），
        # setdefault 会失效，导致启动器/无声游戏也打开真实音频设备。
        # 启动器每次进出游戏都会 pygame.quit()+init()，于是每次切换都开关功放、
        # 发出"啪啪"爆音。无声程序强制走 dummy，彻底不碰真实设备。
        os.environ["SDL_AUDIODRIVER"] = "dummy"
    else:
        # 声明需要声音的程序（如粘猴）：清掉可能残留的 dummy，
        # 让 audio.prepare() 设定的驱动（真机 alsa / 模拟系统声卡）生效。
        # 只清 dummy，尊重调用方显式指定的其它驱动。
        if os.environ.get("SDL_AUDIODRIVER", "").strip().lower() == "dummy":
            os.environ.pop("SDL_AUDIODRIVER", None)

    if not _simulate:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_FBDEV"] = FB_DEV
    else:
        # 本机调试绝不能走 dummy，否则没有可见窗口
        os.environ.pop("SDL_VIDEODRIVER", None)
        os.environ.pop("SDL_FBDEV", None)

    import pygame

    _pygame = pygame
    pygame.init()

    if _simulate:
        if _want_portrait():
            FB_WIDTH, FB_HEIGHT = 240, 320
        else:
            FB_WIDTH, FB_HEIGHT = 320, 240
        WINDOW_ACTUAL_SCALE = _fit_window_scale(pygame, FB_WIDTH, FB_HEIGHT)
        pygame.display.set_caption("SPI LCD 模拟  %dx%d  x%d" % (FB_WIDTH, FB_HEIGHT, WINDOW_ACTUAL_SCALE))
        _window = pygame.display.set_mode((FB_WIDTH * WINDOW_ACTUAL_SCALE, FB_HEIGHT * WINDOW_ACTUAL_SCALE))
        _screen = pygame.Surface((FB_WIDTH, FB_HEIGHT))
        print("显示模式: 本机窗口模拟（%dx%d，窗口放大 %d 倍）" % (FB_WIDTH, FB_HEIGHT, WINDOW_ACTUAL_SCALE))
        print("关闭窗口或按 Esc 退出。树莓派真机请把 spi_lcd.SIMULATE_DISPLAY 改为 False。")
    else:
        if not os.path.exists(FB_DEV):
            raise FileNotFoundError(
                "未找到 %s。本机调试请设 SIMULATE_DISPLAY = True，"
                "或去掉强制 SPI；真机请确认 fbtft / LCD-show 已加载。" % FB_DEV
            )
        FB_WIDTH, FB_HEIGHT = _fb_size()
        _window = None
        _screen = pygame.display.set_mode((FB_WIDTH, FB_HEIGHT))
        print("显示模式: 树莓派 SPI  %s  (%dx%d%s)" % (
            FB_DEV, FB_WIDTH, FB_HEIGHT,
            " 竖屏" if FB_HEIGHT > FB_WIDTH else " 横屏"))

    return _screen


def screen():
    if _screen is None:
        raise RuntimeError("请先调用 spi_lcd.init()")
    return _screen


def mouse_position(event):
    """将模拟窗口中的鼠标点击换算为逻辑屏幕坐标。"""
    pygame = _pygame
    if (not _simulate or pygame is None or event.type != pygame.MOUSEBUTTONDOWN
            or event.button != 1):
        return None
    window = pygame.display.get_surface()
    if window is None:
        return None
    x = event.pos[0] * FB_WIDTH / window.get_width()
    y = event.pos[1] * FB_HEIGHT / window.get_height()
    return int(x), int(y)


def text_button_rects(text, font, y: int, labels=("K1", "K2", "K3")):
    """返回可见文本标签对应的按键命中区域。"""
    pygame = _pygame
    if pygame is None:
        return []
    text_x = (FB_WIDTH - font.size(text)[0]) // 2
    rects = []
    for label in labels:
        name, visible = (label, label) if isinstance(label, str) else label
        if not visible:
            continue
        start = 0
        while True:
            index = text.find(visible, start)
            if index < 0:
                break
            x = text_x + font.size(text[:index])[0]
            width = font.size(visible)[0]
            rects.append((name, pygame.Rect(x - 2, y - 2, width + 4, font.get_height() + 4)))
            start = index + len(visible)
    return rects


def button_from_mouse(event, button_rects):
    """按文本命中区域将模拟鼠标点击映射为 K1、K2 或 K3。"""
    position = mouse_position(event)
    if position is None:
        return None
    for name, rect in button_rects:
        if rect.collidepoint(position):
            return name
    return None


class SimulatedHold(_SimulatedHold):
    def process_event(self, event, action):
        return self.handle_event(_pygame, event, action)


def present(poll_events: bool = True) -> bool:
    """刷新画布；默认处理退出事件，自行处理输入时可关闭事件读取。"""
    pygame = _pygame
    if pygame is None or _screen is None:
        raise RuntimeError("请先调用 spi_lcd.init()")

    if _simulate:
        pygame.transform.scale(_screen, _window.get_size(), _window)
        pygame.display.flip()
        return pump() if poll_events else True

    pygame.display.flip()
    _flush_fb()
    return True


def pump() -> bool:
    """处理窗口事件。模拟模式必须定期调用，否则窗口会假死。"""
    pygame = _pygame
    if pygame is None or not _simulate:
        return True
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_q):
            return False
    return True


def idle(ms: int = 100) -> bool:
    """等待一小段时间并泵事件。返回 False 表示用户要退出。"""
    if _pygame is not None:
        _pygame.time.wait(ms)
    return pump()


def _flush_fb() -> None:
    pygame = _pygame
    try:
        import numpy as np

        rgb_array = pygame.surfarray.array3d(_screen)
        lut = _get_display_lut()
        if lut is not None:
            # 显示校色: LUT 查表(numpy 高级索引, 整个数组一次完成)
            lut_arr = np.array(lut, dtype=np.uint8)
            rgb_array = lut_arr[rgb_array]
        rgb_array = np.transpose(rgb_array, (1, 0, 2))
        r = rgb_array[:, :, 0].astype(np.uint16)
        g = rgb_array[:, :, 1].astype(np.uint16)
        b = rgb_array[:, :, 2].astype(np.uint16)
        rgb565 = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
        data = rgb565.tobytes()
    except Exception:
        raw_rgb = pygame.image.tostring(_screen, "RGB")
        lut = _get_display_lut()
        if lut is not None:
            raw_rgb = bytes(bytearray(map(lut.__getitem__, raw_rgb)))
        total = FB_WIDTH * FB_HEIGHT
        buf = array.array("H", [0]) * total
        for i in range(total):
            r = raw_rgb[i * 3]
            g = raw_rgb[i * 3 + 1]
            b = raw_rgb[i * 3 + 2]
            buf[i] = ((r >> 3) & 0x1F) << 11 | ((g >> 2) & 0x3F) << 5 | ((b >> 3) & 0x1F)
        data = buf.tobytes()

    max_bytes = FB_WIDTH * FB_HEIGHT * 2
    with open(FB_DEV, "wb") as f:
        f.write(data[:max_bytes])
