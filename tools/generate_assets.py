"""一键生成全项目所需的本地音频素材（在开发机跑一次，产物随项目拷到 Pi）。

所有音效/语音都按功能分目录存放，互不混放：
  common/media/                       按键音、正确/错误提示音（各游戏共用，只存一份）
  <功能>/media/welcome.ogg            进入该功能时的语音欢迎
  <功能>/media/tts/*.ogg              该功能专属朗读（题目/答案/选项/结果/名字，hash 命名）
  <功能>/media/<name>.ogg             该功能专属音效（宠物动作、转盘等）

语音用 edge-tts 的微软神经网络音色（默认 zh-CN-XiaoyiNeural 晓伊·萌版），
自然度远高于 Piper，联网合成后压成 ogg 随项目走；运行时零联网、零合成。
可用环境变量覆盖：
  WONDERBOX_VOICE           音色名（默认 zh-CN-XiaoyiNeural）
  WONDERBOX_VOICE_RATE      语速（默认 +8%）
  WONDERBOX_VOICE_PITCH     音高（默认 +30Hz，越高越萌）
按键音/提示音/转盘音/宠物动作音用程序合成（正弦/噪声包络），不依赖素材。

用法（开发机，需 edge-tts + ffmpeg，联网）：
    python tools/generate_assets.py                 # 生成全部，已存在自动跳过
    python tools/generate_assets.py --only welcome  # 只生成欢迎语
    python tools/generate_assets.py --force         # 强制重生成（换音色后用）
    python tools/generate_assets.py --list          # 列出将生成的清单

运行时（Pi）零依赖：只读取这些 ogg 播放。
"""
from __future__ import annotations

import argparse
import ast
import asyncio
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

# 三个转盘游戏各自的转盘音（风格/音高/节奏都不同，听起来明显不一样）
#   tick  骰子对决：清脆高频滴答，双音交替
#   wood  幸运转盘：中频木质哒哒，带泛音
#   magic 星愿占卜屋：低频神秘旋转，音阶缓升带气声
WHEEL_TONES = {
    DUEL_DIR: dict(style="tick", freq=880, ticks=24, gap=0.055, seed=11),
    WHEEL_DIR: dict(style="wood", freq=520, ticks=20, gap=0.075, seed=23),
    MAGIC_DIR: dict(style="magic", freq=330, ticks=30, gap=0.060, seed=37),
}
# 占卜屋改为「每过一格响一次」: 单次短音会随星轮减速自然变慢。
MAGIC_WHEEL_TICK = dict(style="magic", freq=330, ticks=1, gap=0.060, seed=37)

# 宠物动作音效（8 种动作各有独特声音）
PET_ACTIONS = {
    "feed": [(300, 0.07, 0.42, "tone"), (0, 0.03, 0, "silence"),
             (420, 0.07, 0.42, "tone")],
    "play": [(523, 0.10, 0.40, "tone"), (659, 0.10, 0.40, "tone"),
             (784, 0.18, 0.44, "tone")],
    "wash": [(210, 0.06, 0.30, "noise"), (0, 0.03, 0, "silence"),
             (180, 0.08, 0.26, "noise"), (0, 0.03, 0, "silence"),
             (240, 0.05, 0.28, "noise")],
    "sleep": [(440, 0.20, 0.30, "tone"), (330, 0.24, 0.28, "tone"),
              (262, 0.34, 0.26, "tone")],
    "pat": [(600, 0.09, 0.30, "tone"), (0, 0.04, 0, "silence"),
            (800, 0.09, 0.28, "tone")],
    "medicine": [(880, 0.08, 0.34, "tone"), (990, 0.14, 0.30, "tone")],
    "explore": [(392, 0.08, 0.34, "tone"), (523, 0.08, 0.34, "tone"),
                (659, 0.08, 0.34, "tone"), (784, 0.16, 0.38, "tone")],
    "skill": [(523, 0.07, 0.34, "tone"), (659, 0.07, 0.34, "tone"),
              (784, 0.07, 0.34, "tone"), (1046, 0.20, 0.40, "tone")],
}

# 诗词儿童模式朗读前缀（与 poetry.py 保持一致）
SPEAK_QUESTION_PREFIX = "请听题。"
SPEAK_ANSWER_PREFIX = "答案是。"
SPEAK_OPTION_PREFIX = ("选项一，", "选项二，", "选项三，")

# —— 音色（晓伊·萌版）——
VOICE_NAME = os.environ.get("WONDERBOX_VOICE", "zh-CN-XiaoyiNeural")
VOICE_RATE = os.environ.get("WONDERBOX_VOICE_RATE", "+8%")
VOICE_PITCH = os.environ.get("WONDERBOX_VOICE_PITCH", "+30Hz")


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


def synth_wheel(path, style, freq, ticks, gap, seed):
    """三种转盘音风格，音高/音色/节奏都不同，避免听起来一样。"""
    rng = random.Random(seed)
    segments = []
    if style == "tick":
        # 骰子对决：高频清脆滴答，双音交替
        for index in range(ticks):
            f = freq if index % 2 == 0 else freq * 0.75
            segments.append((f, gap * 0.18, 0.42, "tone"))
            segments.append((0, gap * 0.82, 0, "silence"))
    elif style == "wood":
        # 幸运转盘：中频木质哒哒，带二次谐波
        for _ in range(ticks):
            f = freq * rng.uniform(0.96, 1.04)
            segments.append((f, gap * 0.22, 0.34, "tone"))
            segments.append((f * 2.02, gap * 0.10, 0.12, "tone"))
            segments.append((0, gap * 0.68, 0, "silence"))
    else:  # magic
        # 占卜屋：低频神秘旋转，音阶缓升带气声
        scale = (1.0, 1.122, 1.26, 1.335, 1.5)
        for index in range(ticks):
            f = freq * scale[index % len(scale)]
            segments.append((f, gap * 0.42, 0.30, "tone"))
            segments.append((f * 0.5, gap * 0.42, 0.16, "tone"))
            segments.append((f, gap * 0.16, 0.10, "noise"))
    _write_tone_wav(path, segments)


def synth_pet(path, name):
    _write_tone_wav(path, PET_ACTIONS[name])


# ----------------------------------------------------------------------------
# 语音合成（edge-tts 神经音色） -> wav -> ogg
# ----------------------------------------------------------------------------
async def _edge_save(text, mp3_path):
    import edge_tts
    communicate = edge_tts.Communicate(text, VOICE_NAME, rate=VOICE_RATE, pitch=VOICE_PITCH)
    await communicate.save(mp3_path)


async def voice_to_wav(text, wav_path, mp3_path, retries=3, timeout=45):
    """edge-tts 合成 mp3（网络抖动/卡死自动重试），再转 22050 单声道 wav。

    edge-tts 底层 websocket 偶尔会挂起且不报错，必须用 wait_for 超时兜底，
    否则 gather 会一直等这个连接，整批生成卡死。
    """
    last_error = None
    for attempt in range(retries):
        try:
            await asyncio.wait_for(_edge_save(text, mp3_path), timeout=timeout)
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error",
                 "-y", "-i", mp3_path, "-ac", "1", "-ar", "22050", wav_path],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            return
        except Exception as error:  # noqa: BLE001 - 网络错误类型多，统一重试
            last_error = error
            try:
                os.remove(mp3_path)
            except OSError:
                pass
            await asyncio.sleep(0.5 * (attempt + 1))
    raise RuntimeError("语音合成失败 %r: %s" % (text[:20], last_error))


def wav_to_ogg(wav_path, ogg_path):
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", wav_path,
         "-c:a", "libvorbis", "-q:a", "4", ogg_path],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


# ----------------------------------------------------------------------------
# 从游戏源码提取结果文本（纯字面量，ast 安全读取）
# ----------------------------------------------------------------------------
def source_literal(path, variable):
    try:
        with open(path, encoding="utf-8") as source:
            tree = ast.parse(source.read())
    except (OSError, SyntaxError):
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == variable:
                    try:
                        return ast.literal_eval(node.value)
                    except (ValueError, TypeError):
                        return None
    return None


def wheel_task_texts():
    """幸运转盘所有可能结果文本。GAMES 每项为 (类别, 颜色, 任务列表)。"""
    games = source_literal(os.path.join(WHEEL_DIR, "lucky_wheel.py"), "GAMES") or []
    texts = []
    for entry in games:
        if isinstance(entry, (tuple, list)) and len(entry) >= 3 and isinstance(entry[2], (tuple, list)):
            texts.extend(str(task).strip() for task in entry[2] if str(task).strip())
    return list(dict.fromkeys(texts))


def duel_task_texts():
    """骰子对决挑战转盘所有可能结果文本。CHALLENGES 结构同 GAMES。"""
    challenges = source_literal(os.path.join(DUEL_DIR, "quick_duel.py"), "CHALLENGES") or []
    texts = []
    for entry in challenges:
        if isinstance(entry, (tuple, list)) and len(entry) >= 3 and isinstance(entry[2], (tuple, list)):
            texts.extend(str(task).strip() for task in entry[2] if str(task).strip())
    return list(dict.fromkeys(texts))


def poetry_option_values():
    """儿童诗词题库里所有可能作为选项的文本值。"""
    path = os.path.join(POETRY_DIR, "data", "children_poetry.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as source:
        works = json_load(source)
    values = set()
    for work in works:
        for field in ("following", "author", "title"):
            value = str(work.get(field, "")).strip()
            if value:
                values.add(value)
    return sorted(values)


def json_load(source):
    import json
    return json.load(source)


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

    # 三个转盘音，各放各的功能目录，风格/参数不同
    for directory, params in WHEEL_TONES.items():
        add("sfx", os.path.join(directory, "media", "wheel.ogg"), "wheel", params)
    # 占卜屋的逐格滴答声（跟随星轮实际转速，而不是固定速率循环）
    add("sfx", os.path.join(MAGIC_DIR, "media", "wheel_tick.ogg"), "wheel", MAGIC_WHEEL_TICK)

    # 宠物动作音效（各放宠物乐园自己的目录）
    for name in PET_ACTIONS:
        add("petact", os.path.join(PET_DIR, "media", "act_%s.ogg" % name), "petact", name)

    # 各功能欢迎语（放各自 media 目录）
    for directory, text in WELCOME.items():
        add("welcome", os.path.join(directory, "media", "welcome.ogg"), "voice", text)

    # 脑筋急转弯：题目/答案（已有 1000 段，这里只补缺）
    riddles_path = os.path.join(RIDDLES_DIR, "riddles.json")
    if os.path.exists(riddles_path):
        with open(riddles_path, encoding="utf-8") as source:
            bank = json_load(source)
        for entry in bank:
            question, answer = entry.get("q"), entry.get("a")
            if isinstance(question, str) and isinstance(answer, str):
                add("riddles", tts.pregen_path(SPEAK_QUESTION_PREFIX + question.strip(),
                                               os.path.join(RIDDLES_DIR, "media", "tts")),
                    "voice", SPEAK_QUESTION_PREFIX + question.strip())
                add("riddles", tts.pregen_path(SPEAK_ANSWER_PREFIX + answer.strip(),
                                               os.path.join(RIDDLES_DIR, "media", "tts")),
                    "voice", SPEAK_ANSWER_PREFIX + answer.strip())

    # 诗词儿童模式：题目 + 选项 + 答案（只预生成儿童 77 首，其它模式不朗读）
    children_path = os.path.join(POETRY_DIR, "data", "children_poetry.json")
    poetry_tts = os.path.join(POETRY_DIR, "media", "tts")
    if os.path.exists(children_path):
        with open(children_path, encoding="utf-8") as source:
            works = json_load(source)
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
        # 选项文本：每个可能值 × 三个位置（位置决定"选项一/二/三"）
        for value in poetry_option_values():
            for prefix in SPEAK_OPTION_PREFIX:
                otext = prefix + value
                add("poetry", tts.pregen_path(otext, poetry_tts), "voice", otext)

    # 宝可梦名字（493 只）
    pokedex = os.path.join(POKEMON_DIR, "pokedex_data", "pokemon_platinum.json")
    if os.path.exists(pokedex):
        with open(pokedex, encoding="utf-8") as source:
            bank = json_load(source)
        mon_tts = os.path.join(POKEMON_DIR, "media", "tts")
        for entry in bank:
            name = str(entry.get("name_zh", "")).strip()
            if name:
                add("pokemon", tts.pregen_path(name, mon_tts), "voice", name)

    # 幸运转盘 / 骰子对决：转完后的结果文本（各放各的 tts 目录）
    wheel_tts = os.path.join(WHEEL_DIR, "media", "tts")
    for text in wheel_task_texts():
        add("wheel", tts.pregen_path(text, wheel_tts), "voice", text)
    duel_tts = os.path.join(DUEL_DIR, "media", "tts")
    for text in duel_task_texts():
        add("duel", tts.pregen_path(text, duel_tts), "voice", text)

    return tasks


def main():
    parser = argparse.ArgumentParser(description="生成全项目本地音频素材")
    parser.add_argument("--force", action="store_true", help="强制重生成已存在文件")
    parser.add_argument("--only", default="", help="只生成某组：sfx/petact/welcome/riddles/poetry/pokemon/wheel/duel")
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
    print("音色: %s rate=%s pitch=%s" % (VOICE_NAME, VOICE_RATE, VOICE_PITCH), flush=True)
    print("待生成 %d / 共 %d 项" % (len(pending), len(tasks)), flush=True)
    if not pending:
        return 0

    # 音效（button/correct/wrong/wheel/petact）无需联网，先同步生成
    local_tasks = [(g, o, k, p) for g, o, k, p in pending if k != "voice"]
    voice_tasks = [(g, o, k, p) for g, o, k, p in pending if k == "voice"]
    with tempfile.TemporaryDirectory(prefix="wonderbox_assets_") as tmp:
        wav_path = os.path.join(tmp, "seg.wav")
        for index, (group, out, kind, payload) in enumerate(local_tasks, 1):
            os.makedirs(os.path.dirname(out), exist_ok=True)
            if kind == "button":
                synth_button(wav_path)
            elif kind == "correct":
                synth_correct(wav_path)
            elif kind == "wrong":
                synth_wrong(wav_path)
            elif kind == "wheel":
                synth_wheel(wav_path, payload["style"], payload["freq"],
                            payload["ticks"], payload["gap"], payload["seed"])
            elif kind == "petact":
                synth_pet(wav_path, payload)
            wav_to_ogg(wav_path, out)
        if local_tasks:
            print("音效完成 %d 项" % len(local_tasks), flush=True)

        # 语音并发合成：每任务独立临时文件，并发度受信号量控制
        # 并发过高会触发 edge-tts 服务端限流/连接挂起，用 3 较稳
        semaphore = asyncio.Semaphore(3)
        done = {"count": 0, "failed": 0}

        async def one(index, out, text):
            my_wav = os.path.join(tmp, "v_%d.wav" % index)
            my_mp3 = os.path.join(tmp, "v_%d.mp3" % index)
            async with semaphore:
                try:
                    await voice_to_wav(text, my_wav, my_mp3)
                    wav_to_ogg(my_wav, out)
                except Exception as error:  # noqa: BLE001
                    done["failed"] += 1
                    print("生成失败 %r: %s" % (text[:20], error), flush=True)
            done["count"] += 1
            if done["count"] % 100 == 0 or done["count"] == len(voice_tasks):
                print("语音进度 %d/%d (失败 %d)" %
                      (done["count"], len(voice_tasks), done["failed"]), flush=True)

        async def run_all():
            await asyncio.gather(*[
                one(index, out, payload)
                for index, (group, out, kind, payload) in enumerate(voice_tasks, 1)
            ])

        if voice_tasks:
            asyncio.run(run_all())
    print("完成。所有音频已按功能分目录存放。失败 %d 项。" % done["failed"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
