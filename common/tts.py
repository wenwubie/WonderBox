"""本地语音播放层：只播放预生成 ogg，零合成、零延迟（接口 speak/stop/close 不变）。

设计要点（针对 32 位 Pi Zero 2 W 算力弱，Piper 实时合成一句要几秒）：
  * 全部语音在开发机用 tools/generate_assets.py 预生成为 ogg，随项目拷到 Pi。
  * 运行时 Speaker 只按文本 hash 查对应功能的 media/tts 目录，命中即播；
    不联网、不起 piper、不合成，按键零延迟。
  * 每个功能有自己的 media/tts 子目录，互不混放；Speaker 的 pregen_dir 参数指定。
  * 文本->文件名用 audio_key()（sha1 前 20 位），生成脚本与运行时同源。

接口：
  Speaker(pregen_dir=..., ...).speak(text)  异步播放，新朗读打断旧的
  .stop() / .close() / .status() / .warmup()（空操作，兼容历史调用）

环境变量：
  POKEMON_NO_AUDIO=1           静音
  WONDERBOX_TTS_MEDIA          覆盖默认预生成目录（一般不需要，直接传 pregen_dir）
"""
from __future__ import annotations

import glob
import hashlib
import os
import threading
import time

from common import sound_settings

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_MODULE_DIR)

# 默认目录：脑筋急转弯历史路径（新功能请显式传自己的 pregen_dir）
DEFAULT_PREGEN_DIR = os.path.join(_ROOT_DIR, "Riddles", "media", "tts")
PREGEN_DIR = os.environ.get("WONDERBOX_TTS_MEDIA", DEFAULT_PREGEN_DIR)
PREGEN_EXT = ".ogg"


def _env_flag(name):
    value = os.environ.get(name)
    return value is not None and value.strip().lower() not in ("0", "false", "no", "off", "")


def is_muted() -> bool:
    return _env_flag("POKEMON_NO_AUDIO")


def audio_key(text):
    """文本 -> 音频文件名（不含扩展名）。生成脚本与运行时共用，保证一致。"""
    return hashlib.sha1(str(text).strip().encode("utf-8")).hexdigest()[:20]


def pregen_path(text, directory=None):
    return os.path.join(directory or PREGEN_DIR, audio_key(text) + PREGEN_EXT)


def pregen_ready(directory=None) -> bool:
    directory = directory or PREGEN_DIR
    try:
        return any(name.lower().endswith(PREGEN_EXT) for name in os.listdir(directory))
    except OSError:
        return False


def find_model():
    """兼容旧工具：返回 (模型路径, 配置路径或None)；运行层已不再需要模型。"""
    candidates = []
    override = os.environ.get("WONDERBOX_TTS_MODEL")
    if override:
        candidates.append(override)
    candidates.append(os.path.join(_MODULE_DIR, "models", "zh_CN-huayan-medium.onnx"))
    home = os.path.expanduser("~")
    for pattern in (os.path.join(home, "piper", "*.onnx"),
                    os.path.join(home, "piper", "models", "*.onnx"),
                    os.path.join(home, "piper", "zh_CN", "*.onnx")):
        candidates.extend(sorted(glob.glob(pattern)))
    for model in candidates:
        if model and os.path.exists(model) and os.path.getsize(model) > 1024:
            config = os.environ.get("WONDERBOX_TTS_MODEL_CONFIG") or (model + ".json")
            if not os.path.exists(config):
                config = None
            return model, config
    return None, None


# 旧工具兼容符号
DEFAULT_MODEL = os.path.join(_MODULE_DIR, "models", "zh_CN-huayan-medium.onnx")
DEFAULT_LENGTH_SCALE = 1.05


class Speaker:
    """本地语音播放器。speak() 异步返回，新朗读打断旧的。

    pregen_dir : 该功能预生成 ogg 的目录（默认 Riddles/media/tts）。
    enabled    : 目录里存在 ogg 且未静音时为 True。
    """

    def __init__(self, pregen_dir=None, _mixer_check=None):
        self.pregen_dir = pregen_dir or PREGEN_DIR
        self._mixer_check = _mixer_check
        self.voice_enabled = sound_settings.voice_enabled()  # 语音提示总开关
        self.enabled = pregen_ready(self.pregen_dir) and not is_muted() and self.voice_enabled
        self._generation = 0
        self._lock = threading.Lock()
        self._threads = set()
        self._sound = None
        self._cache = {}
        self.play_count = 0
        self.miss_count = 0
        self._load_error = None

    @property
    def available(self):
        return self.enabled

    def status(self):
        return {
            "enabled": self.enabled,
            "voice_enabled": self.voice_enabled,
            "pregen_dir": self.pregen_dir,
            "pregen_ready": pregen_ready(self.pregen_dir),
            "muted": is_muted(),
            "play_count": self.play_count,
            "miss_count": self.miss_count,
            "load_error": self._load_error,
        }

    def warmup(self):
        """本地音频无需预热，保留空接口兼容历史调用。"""
        return

    def prefetch(self, texts):
        """本地音频命中即播，无需预取，保留空接口兼容历史调用。"""
        return 0

    def warm_library(self, texts):
        """本地音频无需预热，保留空接口兼容历史调用。"""
        return 0

    def has(self, text):
        path = pregen_path(text, self.pregen_dir)
        return os.path.exists(path) and os.path.getsize(path) > 44

    def speak(self, text):
        """异步播放文本对应的预生成音频；未命中则忽略并返回 False。"""
        if not self.enabled or not text:
            return False
        text = str(text).strip()
        if not text:
            return False
        path = self._resolve(text)
        if path is None:
            return False
        with self._lock:
            self._generation += 1
            generation = self._generation
            sound = self._sound
            self._sound = None
        if sound is not None:
            try:
                sound.stop()
            except Exception:
                pass
        thread = threading.Thread(target=self._run, args=(path, generation), daemon=True)
        with self._lock:
            self._threads.add(thread)
        thread.start()
        return True

    def speak_sequence(self, texts):
        """串行朗读多条文本（如题目 + 三个选项），一条播完再播下一条。

        整串共用一个 generation：新的 speak/speak_sequence/stop 会打断整串，
        但串内各条不会互相打断。任一文本未命中预生成音频则整串放弃（避免
        读到一半断掉），返回 False。
        """
        if not self.enabled or not texts:
            return False
        if isinstance(texts, str):
            texts = [texts]
        cleaned = [str(item).strip() for item in texts if item and str(item).strip()]
        if not cleaned:
            return False
        paths = []
        for text in cleaned:
            path = self._resolve(text)
            if path is None:
                return False
            paths.append(path)
        with self._lock:
            self._generation += 1
            generation = self._generation
            previous = self._sound
            self._sound = None
        if previous is not None:
            try:
                previous.stop()
            except Exception:
                pass
        thread = threading.Thread(target=self._run_sequence, args=(paths, generation), daemon=True)
        with self._lock:
            self._threads.add(thread)
        thread.start()
        return True

    def _run_sequence(self, paths, generation):
        try:
            if self._mixer_check is not None:
                mixer_ok = self._mixer_check()
            else:
                from common import audio as audio_output
                mixer_ok = audio_output.init_mixer()
            if not mixer_ok:
                self._load_error = "mixer 未就绪"
                return
            import pygame
            for path in paths:
                with self._lock:
                    if generation != self._generation:
                        return
                try:
                    sound = pygame.mixer.Sound(path)
                except Exception as error:
                    self._load_error = "加载音频失败: %s" % error
                    return
                sound_settings.apply(sound, "voice")
                with self._lock:
                    if generation != self._generation:
                        return
                    self._sound = sound
                    self.play_count += 1
                try:
                    channel = sound.play()
                except Exception as error:
                    self._load_error = "播放失败: %s" % error
                    return
                # 等本条播完再播下一条；期间若被新朗读打断则立即停止
                while getattr(channel, "get_busy", lambda: False)():
                    with self._lock:
                        if generation != self._generation:
                            try:
                                sound.stop()
                            except Exception:
                                pass
                            return
                    time.sleep(0.03)
        finally:
            with self._lock:
                self._threads.discard(threading.current_thread())

    def _resolve(self, text):
        with self._lock:
            cached = self._cache.get(text)
        if cached and os.path.exists(cached):
            return cached
        path = pregen_path(text, self.pregen_dir)
        if os.path.exists(path) and os.path.getsize(path) > 44:
            with self._lock:
                self._cache[text] = path
            return path
        with self._lock:
            self.miss_count += 1
            self._load_error = "缺少预生成音频: %s" % text
        return None

    def _run(self, path, generation):
        try:
            if self._mixer_check is not None:
                mixer_ok = self._mixer_check()
            else:
                from common import audio as audio_output
                mixer_ok = audio_output.init_mixer()
            if not mixer_ok:
                self._load_error = "mixer 未就绪"
                return
            import pygame
            try:
                sound = pygame.mixer.Sound(path)
            except Exception as error:
                self._load_error = "加载音频失败: %s" % error
                return
            sound_settings.apply(sound, "voice")
            with self._lock:
                if generation != self._generation:
                    return
                self._sound = sound
                self.play_count += 1
            try:
                sound.play()
            except Exception as error:
                self._load_error = "播放失败: %s" % error
        finally:
            with self._lock:
                self._threads.discard(threading.current_thread())

    def stop(self):
        with self._lock:
            self._generation += 1
            sound = self._sound
            self._sound = None
        if sound is not None:
            try:
                sound.stop()
            except Exception:
                pass

    def close(self):
        self.stop()
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            with self._lock:
                if not self._threads:
                    break
            time.sleep(0.02)
        with self._lock:
            self._cache.clear()
