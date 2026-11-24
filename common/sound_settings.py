"""全局声音设置：按键/音效音量、语音音量、语音提示开关。

与界面风格共用项目根目录 settings.json：
  * 主界面“设置”页修改后立即持久化；
  * 各子游戏是独立进程，启动时读取本模块并应用到音效/朗读，无需传环境变量。

settings.json 字段：
  style          界面风格（由 ui_theme 管理）
  sfx_volume     按键与游戏音效音量 0-100（默认 80）
  voice_volume   语音朗读/欢迎语音量 0-100（默认 100）
  voice_enabled  语音提示开关 bool（默认 True；关闭后不播放语音，按键音保留）

音量作用于 pygame.mixer.Sound.set_volume(0.0~1.0)。pygame 没有全局主音量，
因此每个音源在加载/播放时按用途调用 apply()，分别落在不同通道上。
"""
from __future__ import annotations

import json
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_FILE = os.path.join(ROOT_DIR, "settings.json")

DEFAULTS = {
    "sfx_volume": 80,
    "voice_volume": 100,
    "voice_enabled": True,
}
VOLUME_STEP = 10
MIN_VOLUME = 0
MAX_VOLUME = 100
VOLUME_KEYS = ("sfx_volume", "voice_volume")


def read_raw():
    """读取 settings.json 原始字典；文件缺失/损坏时返回空字典。"""
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as source:
            data = json.load(source)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def settings():
    """返回经过校验的声音设置（只包含本模块的三个键）。"""
    raw = read_raw()
    result = dict(DEFAULTS)
    for key in VOLUME_KEYS:
        value = raw.get(key)
        if (isinstance(value, int) and not isinstance(value, bool)
                and MIN_VOLUME <= value <= MAX_VOLUME):
            result[key] = value
    if isinstance(raw.get("voice_enabled"), bool):
        result["voice_enabled"] = raw["voice_enabled"]
    return result


def update(patch):
    """合并写入部分字段（保留 style 等其它键），立即持久化。"""
    data = read_raw()
    data.update(patch)
    temporary = SETTINGS_FILE + ".tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as output:
            json.dump(data, output, ensure_ascii=False, indent=1)
        os.replace(temporary, SETTINGS_FILE)
    except OSError:
        try:
            os.remove(temporary)
        except OSError:
            pass
        return False
    return True


def volume(kind):
    """返回 0.0~1.0 的音量；kind 为 "sfx" 或 "voice"。"""
    values = settings()
    key = "voice_volume" if kind == "voice" else "sfx_volume"
    return values[key] / float(MAX_VOLUME)


def voice_enabled():
    return settings()["voice_enabled"]


def apply(sound, kind):
    """按用途给单个音源设置音量；异常时静默降级。"""
    try:
        sound.set_volume(volume(kind))
    except Exception:
        pass


def step(key, direction):
    """把音量按 VOLUME_STEP 增减，返回写入后的值。"""
    if key not in VOLUME_KEYS:
        return None
    current = settings()[key]
    value = max(MIN_VOLUME, min(MAX_VOLUME,
                                current + (VOLUME_STEP if direction > 0 else -VOLUME_STEP)))
    update({key: value})
    return value


def toggle_voice():
    """切换语音提示开关，返回写入后的值。"""
    value = not settings()["voice_enabled"]
    update({"voice_enabled": value})
    return value
