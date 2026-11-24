"""兼容入口：脑筋急转弯朗读音频现由 tools/generate_assets.py 统一生成。

旧版本脚本只生成脑筋急转弯的朗读 ogg；现已扩展为全项目音频生成工具，
并按功能分目录存放（含欢迎语、对/错提示、转盘音、诗词、宝可梦名字）。

请用：
    python tools/generate_assets.py                    # 生成全部（已存在跳过）
    python tools/generate_assets.py --only riddles     # 只生成脑筋急转弯朗读
    python tools/generate_assets.py --list             # 查看清单

旧参数 --force/--limit 仅为兼容保留：新工具按文件是否存在自动增量，
无需 --force 也不会重复生成已存在的文件。
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    print("提示：generate_tts.py 已并入 generate_assets.py，转交新工具执行…")
    from tools import generate_assets
    return generate_assets.main()


if __name__ == "__main__":
    sys.exit(main())
