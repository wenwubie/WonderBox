"""一键生成全项目所需的本地音频素材（在开发机跑一次，产物随项目拷到 Pi）。

所有音效/语音都按功能分目录存放，互不混放：
  common/media/                       按键音、正确/错误提示音（各游戏共用，只存一份）
  <功能>/media/welcome.ogg            进入该功能时的语音欢迎
  <功能>/media/tts/*.ogg              该功能专属朗读（题目/答案/名字等，hash 命名）

语音用 Piper 神经语音合成（zh_CN-huayan-medium），ffmpeg 压 ogg；
按键音/提示音/转盘音用程序合成（正弦+噪声包络），不依赖素材。

用法（开发机，需 piper-tts + onnxruntime + ffmpeg）：
    python tools/generate_assets.py                 # 生成全部，已存在自动跳过
    python tools/generate_assets.py --only welcome  # 只生成欢迎语
    python tools/generate_assets.py --force         # 强制重生成
    python tools/generate_assets.py --list          # 列出将生成的清单

运行时（Pi）零依赖：只读取这些 ogg 播放。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import struct
import subprocess
import sys
import tempfile
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from common import tts  # noqa: E402

# —— 功能目录 ——
COMMON_MEDIA = os.path.join(ROOT, "common", "media")
RIDDLES_DIR = os.path.join(ROOT, "Riddles")
POETRY_DIR = os.path.join(ROOT, "Poetry Quest")
POKEMON_DIR = os.path.join(ROOT, "Pokemon")
BRAIN_DIR = os.path.join(ROOT, "Brain Challenge")
DUEL_DIR = os.path.join(ROOT, "Quick Duel")
WHEEL_DIR = os.path.join(ROOT, "Lucky Wheel")
MAGIC_DIR = os.path.join(ROOT, "Magic")
PET_DIR = os.path.join(ROOT, "Virtual Pet")
WOLF_DIR = os.path.join(ROOT, "Werewolf")
MONKEY_DIR = os.path.join(ROOT, "Mini Games", "Sticky Monkey")

# 每个功能：进入时的欢迎语
WELCOME = {
    RIDDLES_DIR: "欢迎进入脑筋急转弯",
    POETRY_DIR: "欢迎进入诗词大赛",
    POKEMON_DIR: "欢迎进入宝可梦图鉴",
    BRAIN_DIR: "欢迎进入头脑挑战",
    DUEL_DIR: "欢迎进入骰子对决",
    WHEEL_DIR: "欢迎进入幸运转盘",
    MAGIC_DIR: "欢迎进入星愿占卜屋",
    PET_DIR: "欢迎进入宠物乐园",
    WOLF_DIR: "欢迎进入狼人杀",
    MONKEY_DIR: "欢迎进入粘猴",
}

# 三个转盘游戏各自的转盘音种子（不同时长/音高/节奏，保证听起来不同）
WHEEL_TONES = {
    DUEL_DIR: dict(freq=420, ticks=26, gap=0.055, seed=11),
    WHEEL_DIR: dict(freq=540, ticks=20, gap=0.070, seed=23),
    MAGIC_DIR: dict(freq=330, ticks=34, gap=0.045, seed=37),
}

# 诗词儿童模式朗读前缀（与 poetry.py 保持一致）
SPEAK_QUESTION_PREFIX = "请听题。"
SPEAK_ANSWER_PREFIX = "答案是。"


# ----------------------------------------------------------------------------
# 合成音效（正弦 + 包络 / 噪声），写 wav
# ----------------------------------------------------------------------------
def _write_tone_wav(path, segments, rate=22050):
    """segments: [(freq, seconds, volume, kind), ...] kind: 'tone'/'noise'/'silence'."""
    frames = bytearray()
    rng = random.Random(7)
    for freq, seconds, volume, kind in segments:
        count = int(rate * seconds)
        for i in range(count):
            t = i / rate
            if kind == "silence" or volume <= 0:
                value = 0.0
            elif kind == "noise":
                value = rng.uniform(-1, 1) * volume
            else:
                value = math.sin(2 * math.pi * freq * t) * volume
            # 短音的起止做渐变，减少爆音
            edge = min(1.0, i / max(1, int(rate * 0.006)), (count - i) / max(1, int(rate * 0.02)))
            value *= max(0.0, edge)
            frames += struct.pack("<h", int(max(-1, min(1, value)) * 32767))
    with wave.open(path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(bytes(frames))


def synth_button(path):
    _write_tone_wav(path, [(880, 0.045, 0.5, "tone"), (1320, 0.035, 0.3, "tone")])


def synth_correct(path):
    _write_tone_wav(path, [(523, 0.12, 0.45, "tone"), (659, 0.12, 0.45, "tone"),
                           (784, 0.22, 0.5, "tone")])


def synth_wrong(path):
    _write_tone_wav(path, [(330, 0.16, 0.45, "tone"), (220, 0.30, 0.45, "tone")])


def synth_wheel(path, freq, ticks, gap, seed):
    rng = random.Random(seed)
    segments = []
    for _ in range(ticks):
        f = freq * rng.uniform(0.9, 1.1)
        segments.append((f, gap * 0.25, 0.35, "noise"))
        segments.append((0, gap * 0.75, 0, "silence"))
    _write_tone_wav(path, segments)


# ----------------------------------------------------------------------------
# Piper 语音合成 -> ogg
# ----------------------------------------------------------------------------
class Voice:
    def __init__(self):
        self.engine = None
        self.model = None
        self.config = None

    def load(self):
        from piper import PiperVoice
        model, config = tts.find_model()
        if not model:
            raise RuntimeError("未找到 Piper 模型（common/models 或 ~/piper）")
        self.engine = PiperVoice.load(model, config_path=config)
        self.model, self.config = model, config
        print("模型:", model)

    def to_wav(self, text, wav_path):
        import wave
        with wave.open(wav_path, "wb") as wav_file:
            try:
                from piper.config import SynthesisConfig
                self.engine.synthesize_wav(
                    text, wav_file,
                    syn_config=SynthesisConfig(length_scale=tts.DEFAULT_LENGTH_SCALE))
            except (ImportError, TypeError):
                self.engine.synthesize_wav(text, wav_file)


def wav_to_ogg(wav_path, ogg_path):
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", wav_path,
         "-c:a", "libvorbis", "-q:a", "4", ogg_path],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


# ----------------------------------------------------------------------------
# 任务清单
# ----------------------------------------------------------------------------
def collect_tasks():
    """返回 [(group, out_path, kind, payload), ...]。"""
    tasks = []

    def add(group, out, kind, payload):
        tasks.append((group, out, kind, payload))

    # 公共音效（共用一份，放 common/media）
    add("sfx", os.path.join(COMMON_MEDIA, "button.ogg"), "button", None)
    add("sfx", os.path.join(COMMON_MEDIA, "correct.ogg"), "correct", None)
    add("sfx", os.path.join(COMMON_MEDIA, "wrong.ogg"), "wrong", None)

    # 三个转盘音，各放各的功能目录，参数不同
    for directory, params in WHEEL_TONES.items():
        add("sfx", os.path.join(directory, "media", "wheel.ogg"), "wheel", params)

    # 各功能欢迎语（放各自 media 目录）
    for directory, text in WELCOME.items():
        add("welcome", os.path.join(directory, "media", "welcome.ogg"), "voice", text)

    # 脑筋急转弯：题目/答案（已有 1000 段，这里只补缺）
    riddles_path = os.path.join(RIDDLES_DIR, "riddles.json")
    if os.path.exists(riddles_path):
        with open(riddles_path, encoding="utf-8") as source:
            bank = json.load(source)
        for entry in bank:
            question, answer = entry.get("q"), entry.get("a")
            if isinstance(question, str) and isinstance(answer, str):
                add("riddles", tts.pregen_path("请听题。" + question.strip(),
                                               os.path.join(RIDDLES_DIR, "media", "tts")),
                    "voice", "请听题。" + question.strip())
                add("riddles", tts.pregen_path("答案是。" + answer.strip(),
                                               os.path.join(RIDDLES_DIR, "media", "tts")),
                    "voice", "答案是。" + answer.strip())

    # 诗词儿童模式：题目 + 答案（只预生成儿童 77 首，其它模式不朗读）
    children_path = os.path.join(POETRY_DIR, "data", "children_poetry.json")
    if os.path.exists(children_path):
        with open(children_path, encoding="utf-8") as source:
            works = json.load(source)
        poetry_tts = os.path.join(POETRY_DIR, "media", "tts")
        for work in works:
            stem = work.get("stem", "")
            variants = {kind: {"续句": "following", "作者": "author", "作品": "title"}[kind]
                        for kind in ("续句", "作者", "作品")}
            for kind, field in variants.items():
                if kind == "续句":
                    prompt = "“%s”的下一句是？" % stem
                elif kind == "作者":
                    prompt = "“%s”是谁写的？" % stem
                else:
                    suffix = "词" if work.get("genre", "").endswith("词") else "诗"
                    prompt = "“%s”的词牌是？" % stem if suffix == "词" else "“%s”出自哪首诗？" % stem
                qtext = SPEAK_QUESTION_PREFIX + prompt
                add("poetry", tts.pregen_path(qtext, poetry_tts), "voice", qtext)
            for field in ("following", "author", "title"):
                atext = SPEAK_ANSWER_PREFIX + str(work.get(field, "")).strip()
                if atext.strip():
                    add("poetry", tts.pregen_path(atext, poetry_tts), "voice", atext)

    # 宝可梦名字（493 只）
    pokedex = os.path.join(POKEMON_DIR, "pokedex_data", "pokemon_platinum.json")
    if os.path.exists(pokedex):
        with open(pokedex, encoding="utf-8") as source:
            bank = json.load(source)
        mon_tts = os.path.join(POKEMON_DIR, "media", "tts")
        for entry in bank:
            name = str(entry.get("name_zh", "")).strip()
            if name:
                add("pokemon", tts.pregen_path(name, mon_tts), "voice", name)

    return tasks


def main():
    parser = argparse.ArgumentParser(description="生成全项目本地音频素材")
    parser.add_argument("--force", action="store_true", help="强制重生成已存在文件")
    parser.add_argument("--only", default="", help="只生成某组：sfx/welcome/riddles/poetry/pokemon")
    parser.add_argument("--list", action="store_true", help="只列出任务清单")
    args = parser.parse_args()

    tasks = collect_tasks()
    if args.only:
        tasks = [task for task in tasks if task[0] == args.only]
    if args.list:
        groups = {}
        for group, _, _, _ in tasks:
            groups[group] = groups.get(group, 0) + 1
        print("任务清单:", groups)
        print("合计:", len(tasks))
        return 0

    pending = [(g, out, k, p) for g, out, k, p in tasks
               if args.force or not os.path.exists(out) or os.path.getsize(out) < 44]
    print("待生成 %d / 共 %d 项" % (len(pending), len(tasks)), flush=True)
    if not pending:
        return 0

    voice = None
    with tempfile.TemporaryDirectory(prefix="wonderbox_assets_") as tmp:
        wav_path = os.path.join(tmp, "seg.wav")
        for index, (group, out, kind, payload) in enumerate(pending, 1):
            os.makedirs(os.path.dirname(out), exist_ok=True)
            if kind == "button":
                synth_button(wav_path)
            elif kind == "correct":
                synth_correct(wav_path)
            elif kind == "wrong":
                synth_wrong(wav_path)
            elif kind == "wheel":
                synth_wheel(wav_path, payload["freq"], payload["ticks"],
                            payload["gap"], payload["seed"])
            else:
                if voice is None:
                    voice = Voice()
                    voice.load()
                voice.to_wav(payload, wav_path)
            wav_to_ogg(wav_path, out)
            if index % 25 == 0 or index == len(pending):
                print("进度 %d/%d (%s)" % (index, len(pending), group), flush=True)
    print("完成。所有音频已按功能分目录存放。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
