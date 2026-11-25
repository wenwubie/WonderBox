# -*- coding: utf-8 -*-
"""语音诊断：定位"按键音正常但没有语音"的原因。

在 Pi 项目根目录运行：
    python tools/diagnose_voice.py

会依次检查：设置开关 -> mixer -> 预生成文件 -> 加载 ogg -> 播放，
每步打印结果，最后给出最可能的结论。不修改任何文件、不发声以外无副作用。
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from common import audio as audio_output
from common import sound_settings
from common import tts

print("=" * 60)
print("[1] 设置")
print("    settings:", sound_settings.settings())
print("    POKEMON_NO_AUDIO:", os.environ.get("POKEMON_NO_AUDIO"))

print("=" * 60)
print("[2] 音频环境")
print("    SDL_AUDIODRIVER:", os.environ.get("SDL_AUDIODRIVER"))
print("    SDL_AUDIODEV:", os.environ.get("SDL_AUDIODEV"))
audio_output.prepare()
print("    prepare 后 SDL_AUDIODEV:", os.environ.get("SDL_AUDIODEV"))
print("    init_mixer():", audio_output.init_mixer())

import pygame
print("    pygame:", pygame.version.ver)
print("    mixer.get_init():", pygame.mixer.get_init())

pregen = os.path.join(ROOT, "Pokemon", "media", "tts")
print("=" * 60)
print("[3] Speaker")
speaker = tts.Speaker(pregen_dir=pregen)
st = speaker.status()
for key, value in st.items():
    print("    %-16s %s" % (key, value))

# 找一个实际存在的宝可梦名字做测试（常见名优先，再扫数据文件）
print("=" * 60)
print("[4] 选一个测试名字")
name = None
for candidate in ("皮卡丘", "妙蛙种子", "小火龙", "杰尼龟", "梦幻"):
    if speaker.has(candidate):
        name = candidate
        break
if name is None:
    data_file = os.path.join(ROOT, "Pokemon", "pokedex_data", "pokemon_platinum.json")
    try:
        import json
        with open(data_file, encoding="utf-8") as source:
            data = json.load(source)
        if isinstance(data, dict):
            data = data.get("pokemon") or data.get("list") or list(data.values())
        for item in data[:1000]:
            if isinstance(item, dict) and item.get("name_zh"):
                candidate = str(item["name_zh"]).strip()
                if speaker.has(candidate):
                    name = candidate
                    break
    except Exception as error:
        print("    读数据失败:", error)
print("    选中:", name)
if name:
    path = tts.pregen_path(name, pregen)
    print("    音频文件:", os.path.basename(path), "存在:", os.path.exists(path),
          "大小:", os.path.getsize(path) if os.path.exists(path) else 0)

    print("=" * 60)
    print("[5] 直接加载 + 播放（不走 Speaker 线程）")
    try:
        sound = pygame.mixer.Sound(path)
        sound_settings.apply(sound, "voice")
        print("    Sound 加载成功, 时长:", round(sound.get_length(), 2), "秒")
        print("    音量:", sound.get_volume())
        channel = sound.play()
        print("    play() 返回 channel:", channel)
        if channel is not None:
            print("    播放中 get_busy():", channel.get_busy())
            time.sleep(0.5)
            print("    0.5s 后 get_busy():", channel.get_busy())
    except Exception as error:
        print("    直接播放异常:", type(error).__name__, error)

    print("=" * 60)
    print("[6] 走 Speaker.speak() 播放")
    before = speaker.play_count
    print("    speak() 返回:", speaker.speak(name))
    time.sleep(1.5)
    print("    play_count %d -> %d" % (before, speaker.play_count))
    st2 = speaker.status()
    for key in ("load_error", "miss_count", "play_count"):
        print("    %-16s %s" % (key, st2.get(key)))

print("=" * 60)
print("诊断结束。请把以上全部输出贴回。")
