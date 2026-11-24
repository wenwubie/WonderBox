# 题库来源

## 当前题库（2026-11-24 起）

`riddles.json` 的 500 道题全部提取自：

> 《激发无限潜能的500个脑筋急转弯游戏（越玩越聪明）》
> 薛莎莎 编著，清华大学出版社，2014，ISBN 978-7-302-34322-6

提取脚本：`tools/extract_epub_riddles.py`。每道题取“快来接招吧”下的题目正文（`q`）
与“答案在这里”下的答案（`a`），舍弃思维提示与插图，按 `question_key` 去重。
提取前的题库备份为 `riddles.json.bak`。

## 历史题库（已替换）

旧 `riddles.json` 包含经过筛选、改写的题目及补充题目。部分题目来自
[EpochcraftMC/AnswerTime](https://github.com/EpochcraftMC/AnswerTime)，
上游文件为 `src/main/resources/assets/answer_time/bank/riddle.json`，
版本 `2e2156d2ec05c13319edb318247fb9bc31259485`。题目已筛选、调整措辞，
并去掉选择题干扰项；补充题目并非上游原始内容。

上游项目采用 MIT License：

```text
MIT License

Copyright (c) 2026 ALingqing_

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```