"""通用音效助手：播放按键音/欢迎语/功能提示音，复用全局 pygame mixer。

设计：
  * 公共音效（按键音/正确/错误）放 common/media，只存一份；每个功能自己的
    欢迎语/朗读/转盘音放各自 media 目录，互不混放。SFX 可同时读多个目录。
  * 复用 common.audio 已打开的 mixer，不自己开音频设备（避免 ALSA busy / 爆音）。
  * 要出声的程序必须在 spi_lcd.init() 之前调用 audio.prepare()；本模块在
    spi_lcd.init() 之后再创建（此时 mixer 已按正确驱动打开）。
  * 设备不可用或音效缺失时静默降级，不影响游戏逻辑。

用法：
    from common import audio as audio_output, sfx
    audio_output.prepare()                 # main() 开头，早于 spi_lcd.init()
    screen = spi_lcd.init()
    sound = sfx.SFX(sfx.game_media(__file__))   # 公共目录 + 本功能目录
    sound.welcome()
    for action in actions:
        if sfx.is_press(action):
            sound.button()
    sound.play("correct")
    sound.close()                           # 退出前（不 quit mixer）
"""
from __future__ import annotations

import os
import time

from common import audio as audio_output
from common import sound_settings

COMMON_MEDIA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "common", "media")

# 视为“按下”的动作（用于触发按键音）；长按/退出类不触发
_PRESS_ACTIONS = {"K1", "K2", "K3", "K1_DOWN", "K1_UP", "K3_DOWN", "K3_CANCEL"}
_PRESS_PREFIXES = ("SELECT_", "MODE_", "GAME_", "CHOOSE_", "SETUP_", "DEATH_", "POWER_CONFIRM")


def is_press(action):
    """判断一个 action 是否是短按按键（用于播放按键音）。"""
    if not action or not isinstance(action, str):
        return False
    if action in _PRESS_ACTIONS:
        return True
    return any(action.startswith(prefix) for prefix in _PRESS_PREFIXES)


def game_media(game_file):
    """返回 [公共音效目录, 该游戏目录下的 media]，供 SFX 构造。"""
    directory = os.path.dirname(os.path.abspath(game_file))
    return [COMMON_MEDIA, os.path.join(directory, "media")]


class SFX:
    """音效播放器，可按名字从多个目录查找（先加的目录优先）。

    dirs        : 一个或多个媒体目录（公共目录在前，功能目录在后）。
    fade_in_ms  : 淡入毫秒；按键音要即时响应，默认 0。
    button_gap  : 按键音最短间隔（秒），防长按连发时重复播放。
    """

    def __init__(self, dirs, fade_in_ms=0, button_gap=0.06):
        if isinstance(dirs, str):
            dirs = [dirs]
        self.dirs = list(dirs)
        self.fade_in_ms = max(0, int(fade_in_ms))
        self.button_gap = max(0.0, float(button_gap))
        self.sounds = {}
        self.enabled = False
        self.button_enabled = True
        self.voice_enabled = sound_settings.voice_enabled()  # 语音提示总开关
        self._last_button = 0.0
        self._loop_channel = None  # 转盘等循环音的独立声道
        if audio_output.is_no_audio():
            return
        if not audio_output.init_mixer():
            return
        for directory in self.dirs:
            for name in audio_output.discover_sounds(directory):
                if name not in self.sounds:
                    sound = self._load(directory, name)
                    if sound is not None:
                        # 欢迎语属语音通道，其余（按键/转盘/宠物等）属音效通道
                        sound_settings.apply(sound, "voice" if name == "welcome" else "sfx")
                        self.sounds[name] = sound
        self.enabled = bool(self.sounds)

    def _load(self, directory, name):
        for extension in audio_output.SOUND_EXTENSIONS:
            path = os.path.join(directory, name + extension)
            if os.path.exists(path):
                try:
                    import pygame
                    return pygame.mixer.Sound(path)
                except Exception:
                    return None
        return None

    def has(self, name):
        return name in self.sounds

    def play(self, name, loops=0):
        """播放指定音效（名字=文件名去掉扩展名）。不存在则静默忽略。"""
        if not self.enabled:
            return
        sound = self.sounds.get(name)
        if sound is None:
            return
        try:
            sound.play(loops=loops, fadein=self.fade_in_ms)
        except TypeError:
            try:
                sound.play(loops=loops)
            except Exception:
                pass
        except Exception:
            pass

    def button(self):
        """按键按下音（带节流）；游戏自带音效时可置 button_enabled=False 关掉。"""
        if not self.button_enabled or not self.enabled:
            return
        now = time.monotonic()
        if now - self._last_button < self.button_gap:
            return
        self._last_button = now
        self.play("button")

    def welcome(self):
        """进入功能时的语音欢迎提示；语音提示关闭时不播放。"""
        if self.voice_enabled:
            self.play("welcome")

    def loop_start(self, name):
        """循环播放某音效（转盘转动等），用独立声道，可 loop_stop 停止。"""
        if not self.enabled:
            return
        sound = self.sounds.get(name)
        if sound is None:
            return
        try:
            import pygame
            self.loop_stop()
            channel = pygame.mixer.find_channel()
            if channel is None:
                channel = pygame.mixer.Channel(0)
            channel.play(sound, loops=-1)
            self._loop_channel = channel
        except Exception:
            pass

    def loop_stop(self):
        """停止循环音（转盘停下时）。"""
        if self._loop_channel is not None:
            try:
                self._loop_channel.stop()
            except Exception:
                pass
            self._loop_channel = None

    def stop(self):
        self.loop_stop()
        for sound in self.sounds.values():
            try:
                sound.stop()
            except Exception:
                pass

    def close(self):
        # 只停音源，不 quit mixer——设备关闭交给各游戏 main() 的 pygame.quit()
        self.stop()
