"""通用音效输出层：按运行环境自动选择驱动，游戏只管调用 play/start_music。

设计参照 common/spi_lcd.py：

  SIMULATE_AUDIO = None  : 自动。跟随显示环境（有 /dev/fb1 为真机，否则模拟）
  SIMULATE_AUDIO = True  : 强制模拟，用 Windows / PC 系统默认声卡发声
  SIMULATE_AUDIO = False : 强制真机，用树莓派 ALSA（I2S 声卡）

模拟环境下会主动移除 SDL_AUDIODRIVER=dummy，让 pygame 走系统声卡真正发声；
真机环境固定 SDL_AUDIODRIVER=alsa + 48kHz，匹配 googlevoicehat / MAX98357。
音频设备不可用或初始化失败时整体静默降级，游戏逻辑不受影响。

如需强制静音，设环境变量 POKEMON_NO_AUDIO=1（模拟时默认会发声，
即使环境里有测试遗留的 SDL_AUDIODRIVER=dummy 也会被清掉）。
"""
from __future__ import annotations

import os

# =============================================================================
# 音频目标开关（改这一处即可全项目生效）
#   None  : 自动，跟随 spi_lcd 的模拟/真机判断
#   True  : 强制系统声卡（PC 模拟）
#   False : 强制 ALSA（树莓派真机）
# =============================================================================
SIMULATE_AUDIO = None

# 是否有程序声明需要声音。spi_lcd.init() 据此决定是否跳过 SDL_AUDIODRIVER=dummy。
# 要在 pygame.init()（即 spi_lcd.init()）之前调用 prepare() 才生效。
_ACTIVATED = False

# 淡入毫秒数：消除音效/背景乐起播瞬间的 click 声；0 表示关闭
FADE_IN_MS = 220
MUSIC_FADE_IN_MS = 600

# 支持的文件格式，按优先级排列
SOUND_EXTENSIONS = (".ogg", ".m4a", ".wav", ".mp3")


def _env_flag(name):
    value = os.environ.get(name)
    return value is not None and value.strip().lower() not in ("0", "false", "no", "off", "")


def is_no_audio() -> bool:
    """显式静音开关：POKEMON_NO_AUDIO=1。

    注意：模拟环境里测试脚本常用的 SDL_AUDIODRIVER=dummy 不算静音信号，
    因为 prepare() 会清掉它强制用系统声卡（用户要求模拟时也能发声）。
    """
    return _env_flag("POKEMON_NO_AUDIO")


def want_simulate() -> bool:
    if SIMULATE_AUDIO is not None:
        return bool(SIMULATE_AUDIO)
    from common import spi_lcd
    return spi_lcd.is_simulate()


def is_simulate() -> bool:
    return want_simulate()


def prepare() -> None:
    """声明本程序需要声音，并按环境设置 SDL 音频驱动。

    必须在 pygame.init()（即 spi_lcd.init()）之前调用：
    - 让 spi_lcd 跳过 dummy 音频驱动；
    - 真机固定 ALSA，模拟清掉 dummy 走系统声卡。
    这样 audio 设备在 pygame.init() 阶段只打开一次，避免反复开关的爆音。
    """
    global _ACTIVATED
    if is_no_audio():
        # 显式静音：不声明，让 spi_lcd 继续用 dummy，彻底不碰音频硬件
        return
    _ACTIVATED = True
    if want_simulate():
        os.environ.pop("SDL_AUDIODRIVER", None)
    else:
        os.environ["SDL_AUDIODRIVER"] = "alsa"


def is_activated() -> bool:
    """spi_lcd.init() 用来判断是否跳过 dummy 音频驱动。"""
    return _ACTIVATED


def init_mixer(frequency=None):
    """确认 pygame.mixer 处于可用状态，返回是否成功。

    关键：若 mixer 已初始化则直接复用，绝不 quit 再 init——每次
    mixer 开关都会让功放产生开关机爆音。prepare() 已在 pygame.init()
    阶段设定好驱动，这里通常不需要再动设备。
    """
    import pygame
    prepare()
    try:
        if pygame.mixer.get_init():
            return True
        if frequency is None:
            frequency = 44100 if want_simulate() else 48000
        pygame.mixer.init(frequency=frequency, size=-16, channels=2)
        return bool(pygame.mixer.get_init())
    except Exception:
        return False


def discover_sounds(media_dir, music=None):
    """扫描目录下的音频文件，返回去掉扩展名的名字列表（按名字排序）。"""
    try:
        entries = os.listdir(media_dir)
    except OSError:
        return []
    names = set()
    for entry in entries:
        stem, extension = os.path.splitext(entry)
        if extension.lower() in SOUND_EXTENSIONS:
            if music and stem == music:
                continue
            names.add(stem)
    return sorted(names)


class GameAudio:
    """通用音效播放器。

    media_dir : 音频文件目录；sounds 为 None 时自动扫描该目录全部音频。
    music     : 循环背景乐文件名（不含扩展名），可选。
    frequency : 强制采样率；None 时按环境取 44100（模拟）/ 48000（真机）。
    """

    def __init__(self, media_dir, sounds=None, music=None, frequency=None,
                 fade_in_ms=FADE_IN_MS, music_fade_in_ms=MUSIC_FADE_IN_MS):
        self.media_dir = media_dir
        self.music_name = music
        self.sounds = {}
        self.music = None
        self.enabled = False
        self.backend = "silent"
        self.fade_in_ms = max(0, int(fade_in_ms))
        self.music_fade_in_ms = max(0, int(music_fade_in_ms))
        if is_no_audio():
            return
        if sounds is None:
            sounds = discover_sounds(media_dir, music)
        if not init_mixer(frequency):
            return
        self.sounds = {name: sound for name in sounds
                       if (sound := self._load(name)) is not None}
        if music:
            self.music = self._load(music)
        self.enabled = bool(self.sounds or self.music)
        self.backend = "system" if is_simulate() else "alsa"

    def _path(self, name):
        for extension in SOUND_EXTENSIONS:
            path = os.path.join(self.media_dir, name + extension)
            if os.path.exists(path):
                return path
        return None

    def _load(self, name):
        path = self._path(name)
        if path is None:
            return None
        try:
            import pygame
            return pygame.mixer.Sound(path)
        except Exception:
            return None

    def play(self, name, loops=0):
        if not self.enabled:
            return
        sound = self.sounds.get(name)
        if sound is not None:
            try:
                sound.play(loops=loops, fadein=self.fade_in_ms)
            except TypeError:
                # 极老的 pygame 版本不支持 fadein，退回无淡入
                try:
                    sound.play(loops=loops)
                except Exception:
                    pass
            except Exception:
                pass

    def start_music(self):
        if not self.enabled or self.music is None:
            return
        try:
            self.music.play(loops=-1, fadein=self.music_fade_in_ms)
        except TypeError:
            try:
                self.music.play(loops=-1)
            except Exception:
                pass
        except Exception:
            pass

    def stop_music(self):
        for sound in list(self.sounds.values()) + ([self.music] if self.music else []):
            try:
                sound.stop()
            except Exception:
                pass

    def close(self):
        # 先把每个音源音量归零，再整体淡出后停止，最后才让调用方 pygame.quit()
        # 关闭 ALSA 设备。功放在设备关闭瞬间对直流突变很敏感，静音到位能明显减小
        # 退出时的"啪"声；这一步必须在 pygame.quit() 之前调用才有效。
        if not self.enabled:
            return
        try:
            import time
            import pygame
            for source in list(self.sounds.values()) + ([self.music] if self.music else []):
                try:
                    source.set_volume(0.0)
                except Exception:
                    pass
            pygame.mixer.fadeout(FADE_IN_MS)
            time.sleep(FADE_IN_MS / 1000.0 + 0.02)
        except Exception:
            pass
        self.stop_music()
