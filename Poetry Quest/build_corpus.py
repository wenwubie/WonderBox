"""从 chinese-poetry 生成离线诗词数据库。"""

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from urllib.parse import quote
from urllib.request import Request, urlopen
import zlib


REVISION = "b8594f81a89752241442f2ce267d6f66f96704ee"
SOURCE_URL = "https://raw.githubusercontent.com/chinese-poetry/chinese-poetry/" + REVISION + "/"
DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_DATABASE = DATA_DIR / "poetry.sqlite3"
SOURCE_FILES = (
    *(("唐诗", "全唐诗/poet.tang.%d.json" % number) for number in range(0, 58000, 1000)),
    ("唐诗", "全唐诗/唐诗补录.json"),
    *(("宋词", "宋词/ci.song.%d.json" % number) for number in range(0, 22000, 1000)),
    ("宋词", "宋词/ci.song.2019y.json"),
)
POPULAR_FILES = (("唐诗", "全唐诗/唐诗三百首.json"), ("宋词", "宋词/宋词三百首.json"))
COMMON_VARIANTS = (("唐诗", "唐诗三百首/静夜思常见版本", (
    {"author": "李白", "title": "静夜思",
     "paragraphs": ["床前明月光，疑是地上霜。", "举头望明月，低头思故乡。"]},
)),)
VERSE_SPLIT = re.compile(r"[，。！？；：、,.!?;:\n\r]+")
VERSE_PATTERN = re.compile(r"[\u3400-\u9fff]{4,10}\Z")
NAME_PATTERN = re.compile(r"[\u3400-\u9fff]{1,8}\Z")
TITLE_PATTERN = re.compile(r"[\u3400-\u9fff]{2,9}\Z")


def download_json(item):
    genre, path = item
    request = Request(SOURCE_URL + quote(path), headers={"User-Agent": "WonderBox-Poetry/1.0"})
    last_error = None
    for _ in range(3):
        try:
            with urlopen(request, timeout=45) as response:
                records = json.load(response)
            if not isinstance(records, list) or not records or not all(isinstance(record, dict) for record in records):
                raise ValueError("语料为空或格式不正确: " + path)
            return genre, path, records
        except (OSError, ValueError) as error:
            last_error = error
    raise RuntimeError("下载诗词数据失败: " + path) from last_error


def download_license():
    request = Request(SOURCE_URL + "LICENSE", headers={"User-Agent": "WonderBox-Poetry/1.0"})
    with urlopen(request, timeout=45) as response:
        text = response.read()
    if b"Permission is hereby granted" not in text:
        raise ValueError("上游许可文件格式不正确")
    return text


def normalize_record(genre, source, record, convert):
    def normalized(value):
        return convert(value).strip() if isinstance(value, str) else ""

    author = normalized(record.get("author"))
    title = normalized(record.get("title") if genre == "唐诗" else record.get("rhythmic"))
    paragraphs = [normalized(paragraph) for paragraph in record.get("paragraphs", [])
                  if isinstance(paragraph, str)]
    first = "".join(paragraphs[0].split()) if paragraphs else ""
    key = (genre, author, title, first)
    return {"genre": genre, "source": source, "author": author, "title": title,
            "paragraphs": paragraphs, "key": key, "original": record}


def split_verses(paragraphs):
    verses = []
    for paragraph in paragraphs:
        for part in VERSE_SPLIT.split(paragraph):
            text = "".join(part.split())
            if text:
                verses.append(text)
    return verses


def build_database(destination, sources, popular_sources, convert):
    popular = {}
    popular_ids = defaultdict(set)
    for genre, source, records in popular_sources:
        for record in records:
            item = normalize_record(genre, source, record, convert)
            popular[item["key"]] = item
            if record.get("id"):
                popular_ids[record["id"]].add(item["key"])

    works = []
    matched_popular = set()
    counts = defaultdict(int)
    for genre, source, records in sources:
        for record in records:
            item = normalize_record(genre, source, record, convert)
            matched = {item["key"]} & popular.keys()
            matched.update(popular_ids.get(record.get("id"), ()))
            item["classic"] = bool(matched)
            matched_popular.update(matched)
            works.append(item)
            counts[genre] += 1
    for key, item in popular.items():
        if key not in matched_popular:
            item["classic"] = True
            works.append(item)

    verse_data = defaultdict(lambda: {"authors": set(), "titles": set(), "next": set(), "unknown": False})
    with closing(sqlite3.connect(destination)) as database:
        database.executescript("""
            CREATE TABLE metadata (name TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE works (
                id INTEGER PRIMARY KEY, genre TEXT NOT NULL, author TEXT NOT NULL,
                title TEXT NOT NULL, paragraphs TEXT NOT NULL, source TEXT NOT NULL,
                original BLOB NOT NULL, classic INTEGER NOT NULL
            );
            CREATE TABLE questions (
                id INTEGER PRIMARY KEY, work_id INTEGER NOT NULL, genre TEXT NOT NULL,
                kind TEXT NOT NULL, stem TEXT NOT NULL, answer TEXT NOT NULL,
                classic INTEGER NOT NULL, FOREIGN KEY (work_id) REFERENCES works(id)
            );
            CREATE TABLE options (
                kind TEXT NOT NULL, genre TEXT NOT NULL, answer TEXT NOT NULL,
                classic INTEGER NOT NULL, PRIMARY KEY (kind, genre, answer)
            );
        """)
        for item in works:
            original = json.dumps(item["original"], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            cursor = database.execute(
                "INSERT INTO works (genre, author, title, paragraphs, source, original, classic) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (item["genre"], item["author"], item["title"],
                 json.dumps(item["paragraphs"], ensure_ascii=False, separators=(",", ":")),
                 item["source"], zlib.compress(original), int(item["classic"])))
            item["id"] = cursor.lastrowid
            item["verses"] = split_verses(item["paragraphs"])
            for index, verse in enumerate(item["verses"]):
                if not VERSE_PATTERN.fullmatch(verse):
                    continue
                info = verse_data[verse]
                info["authors"].add(item["author"])
                info["titles"].add(item["title"])
                following = item["verses"][index + 1] if index + 1 < len(item["verses"]) else ""
                if VERSE_PATTERN.fullmatch(following):
                    info["next"].add(following)
                else:
                    info["unknown"] = True

        seen = set()
        option_flags = {}
        candidates = []
        for item in sorted(works, key=lambda work: not work["classic"]):
            for kind in ("续句", "作者", "作品"):
                for index, verse in enumerate(item["verses"]):
                    if not VERSE_PATTERN.fullmatch(verse):
                        continue
                    info = verse_data[verse]
                    if kind == "续句":
                        following = item["verses"][index + 1] if index + 1 < len(item["verses"]) else ""
                        if info["unknown"] or len(info["next"]) != 1 or following not in info["next"]:
                            continue
                        answer = following
                    elif kind == "作者":
                        answer = item["author"]
                        if len(info["authors"]) != 1 or not NAME_PATTERN.fullmatch(answer) or answer in ("佚名", "无名氏"):
                            continue
                    else:
                        answer = item["title"]
                        if len(info["titles"]) != 1 or not TITLE_PATTERN.fullmatch(answer):
                            continue
                    key = (item["genre"], kind, verse, answer)
                    if key in seen:
                        continue
                    seen.add(key)
                    candidates.append((item["id"], item["genre"], kind, verse, answer, int(item["classic"])))
                    option_key = (kind, item["genre"], answer)
                    option_flags[option_key] = max(option_flags.get(option_key, 0), int(item["classic"]))
                    break
        database.executemany("INSERT INTO questions (work_id, genre, kind, stem, answer, classic) "
                             "VALUES (?, ?, ?, ?, ?, ?)", candidates)
        database.executemany("INSERT INTO options (kind, genre, answer, classic) VALUES (?, ?, ?, ?)",
                             ((*key, flag) for key, flag in option_flags.items()))
        database.executemany("INSERT INTO metadata (name, value) VALUES (?, ?)", (
            ("revision", REVISION), ("tang_records", str(counts["唐诗"])),
            ("song_records", str(counts["宋词"])), ("works", str(len(works))),
            ("classic_works", str(sum(item["classic"] for item in works))),
            ("questions", str(len(candidates))),
        ))
        database.executescript("""
            CREATE INDEX questions_kind_id ON questions(kind, id);
            CREATE INDEX questions_genre_kind_id ON questions(genre, kind, id);
            CREATE INDEX questions_classic_kind_id ON questions(classic, kind, id);
        """)
        database.commit()
    return {"tang": counts["唐诗"], "song": counts["宋词"], "works": len(works),
            "classic": sum(item["classic"] for item in works), "questions": len(candidates)}


def main():
    parser = argparse.ArgumentParser(description="生成 Wonder Box 唐诗宋词离线题库")
    parser.add_argument("--output", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--force", action="store_true", help="替换已有的生成数据库")
    args = parser.parse_args()
    if args.output.exists() and not args.force:
        parser.error("数据库已存在；如需重新生成，请使用 --force")
    try:
        from opencc import OpenCC
    except ImportError as error:
        parser.error("生成数据需要 opencc-python-reimplemented: " + str(error))
    converter = OpenCC("t2s")
    print("下载唐诗宋词原始分片...", flush=True)
    with ThreadPoolExecutor(max_workers=4) as executor:
        sources = list(executor.map(download_json, SOURCE_FILES))
        popular = list(executor.map(download_json, POPULAR_FILES))
    popular.extend(COMMON_VARIANTS)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    license_path = args.output.parent / "UPSTREAM_LICENSE.txt"
    if not license_path.exists():
        license_text = download_license()
        try:
            with license_path.open("xb") as file:
                file.write(license_text)
        except FileExistsError:
            pass
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=args.output.parent, suffix=".sqlite3", delete=False) as file:
            temporary = Path(file.name)
        print("整理原文并筛选无歧义题目...", flush=True)
        stats = build_database(temporary, sources, popular, converter.convert)
        os.replace(temporary, args.output)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print("离线题库已生成:", args.output, stats, flush=True)


if __name__ == "__main__":
    main()