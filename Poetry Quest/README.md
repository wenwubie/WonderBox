# 诗词大赛

在 Wonder Box 总入口选择“诗词大赛”，或从项目根目录运行：

```bash
python "Poetry Quest/poetry.py"
```

有经典名篇、唐诗题库、宋词题库、混合题库和儿童诗词五种范围。每场 10 题，题型包括诗句接龙、辨认作者及辨认诗题或词牌。K1、K2、K3 分别选择三个答案；答题后按 K3 进入下一题。长按 K3 返回菜单，在菜单长按 K3 返回总入口。模拟模式也可点击菜单项和选项。

儿童诗词精选 77 首常见作品，包含《咏鹅》《静夜思》《小池》《村居》等，也收录宋诗及其他朝代的作品。每场以 6 道接句题为主，另有 2 道作者题和 2 道诗题或词牌题。精选题独立保存在 [children_poetry.json](data/children_poetry.json)，使用常见通行版本，不影响原有离线大题库。

## 题库来源

离线数据库包含 chinese-poetry 项目的全唐诗和宋词全部编号分片及补录：57,608 条唐诗、21,053 条宋词。另收录两套经典选集及《静夜思》的常见传本，共 78,674 条作品记录、647 条经典记录和 201,256 道候选题。每条原始作品及其来源都保存在数据库中；出题时会过滤不适合小屏显示或存在多个合理答案的诗句，因此并非每首作品都会生成题目。

上游语料并不能保证涵盖所有存世作品，且可能有异文、错字或归属争议。唐诗显示文字使用 OpenCC 自动转换为简体，可能存在转换误差，原始数据仍保留。经典传本参考维基文库的[《静夜思》](https://zh.wikisource.org/wiki/%E9%9D%9C%E5%A4%9C%E6%80%9D)。

儿童精选采用常见选本的诗句和题名，参考维基文库的[《咏鹅》](https://zh.wikisource.org/wiki/%E8%A9%A0%E9%B5%9D)、[《登鹳雀楼》](https://zh.wikisource.org/wiki/%E7%99%BB%E9%B8%9B%E9%9B%80%E6%A8%93_(%E7%8E%8B%E4%B9%8B%E6%B8%99))、[《小池》](https://zh.wikisource.org/wiki/%E5%B0%8F%E6%B1%A0)及[《村居》](https://zh.wikisource.org/wiki/%E6%9D%91%E5%B1%85_(%E9%AB%98%E9%BC%8E))等；不同选本可能有异文。

语料来自 [chinese-poetry](https://github.com/chinese-poetry/chinese-poetry)，固定版本 `b8594f81a89752241442f2ce267d6f66f96704ee`，许可见 [上游许可](data/UPSTREAM_LICENSE.txt)。

## 重建题库

游戏运行时不需要联网或 OpenCC。若需要重新生成数据库，先安装 `opencc-python-reimplemented==0.1.7`，然后运行：

```bash
python "Poetry Quest/build_corpus.py"
```

脚本会联网下载固定版本的公开语料和许可文件，并生成 `data/poetry.sqlite3`。已有数据库不会被覆盖；确需重建时可加 `--force`。数据库约 85 MB，重建需要额外的临时磁盘空间。