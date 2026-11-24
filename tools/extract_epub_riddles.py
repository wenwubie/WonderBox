"""从《激发无限潜能的500个脑筋急转弯游戏》EPUB 提取题目和答案，生成题库 JSON。

只保留“题目 + 答案”，丢弃章节说明、思维提示、插图等。
输出格式与 Riddles/riddles.json 一致（[{"q": ..., "a": ...}, ...]）。

用法：
    python tools/extract_epub_riddles.py                       # 自动找项目根目录的 .epub
    python tools/extract_epub_riddles.py <epub路径> [-o 输出路径]
"""
from __future__ import annotations

import glob
import html
import json
import os
import re
import sys
import unicodedata
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(ROOT, "Riddles", "riddles.json")

# 每道题是一个 h2（<a id="secNNN"></a> 序号．标题），正文到下一个 h2 为止。
BLOCK_RE = re.compile(
    r'<h2[^>]*class="kindle-cn-heading2"[^>]*>.*?</h2>(.*?)'
    r'(?=<h2[^>]*class="kindle-cn-heading2"|\Z)', re.S)
# 题目正文：class="font2" 的段落（“快来接招吧”下面那段）。
QUESTION_RE = re.compile(r'<p class="font2"[^>]*>(.*?)</p>', re.S)
# 答案：class="kindle-cn-hei" 的段落（“答案在这里”下面那段）。
ANSWER_RE = re.compile(r'<p class="kindle-cn-hei"[^>]*>(.*?)</p>', re.S)
HTML_FILE_RE = re.compile(r'OEBPS/text\d+\.html$')


def clean(fragment):
    """HTML 片段 -> 纯文本：去标签、解实体、归一空白。"""
    text = re.sub(r"<[^>]+>", "", fragment)
    text = html.unescape(text)
    text = text.replace("\u3000", " ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def question_key(question):
    """与 Riddles.Riddles.question_key 保持一致，用于去重。"""
    text = unicodedata.normalize("NFKC", question).casefold()
    return "".join(c for c in text
                   if not c.isspace() and not unicodedata.category(c).startswith("P"))


def extract(epub_path):
    rows = []
    with zipfile.ZipFile(epub_path) as archive:
        names = sorted(n for n in archive.namelist() if HTML_FILE_RE.match(n))
        for name in names:
            document = archive.read(name).decode("utf-8", errors="replace")
            for block in BLOCK_RE.finditer(document):
                body = block.group(1)
                questions = QUESTION_RE.findall(body)
                answers = ANSWER_RE.findall(body)
                if not questions or not answers:
                    continue
                question = clean(questions[0])
                answer = " ".join(part for part in map(clean, answers) if part)
                if question and answer:
                    rows.append({"q": question, "a": answer})
    return dedupe(rows)


def dedupe(rows):
    seen = set()
    result = []
    for row in rows:
        key = question_key(row["q"])
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def main():
    epub_path = sys.argv[1] if len(sys.argv) > 1 else None
    if epub_path is None:
        candidates = sorted(glob.glob(os.path.join(ROOT, "*.epub")))
        if not candidates:
            print("未找到 EPUB 文件", file=sys.stderr)
            return 1
        epub_path = candidates[0]
    out_path = DEFAULT_OUT
    if "-o" in sys.argv:
        out_path = sys.argv[sys.argv.index("-o") + 1]

    rows = extract(epub_path)
    if len(rows) < 100:
        print("提取到的题目过少（%d），疑似解析失败，未写入" % len(rows), file=sys.stderr)
        return 1
    with open(out_path, "w", encoding="utf-8") as source:
        json.dump(rows, source, ensure_ascii=False, indent=2)
        source.write("\n")
    print("从 %s 提取 %d 道题 -> %s" % (os.path.basename(epub_path), len(rows), out_path))
    print("示例：")
    for row in rows[:5]:
        print("  Q: %s" % row["q"])
        print("  A: %s" % row["a"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
