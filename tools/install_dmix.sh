#!/usr/bin/env bash
# 在树莓派上安装“plug + dmix”全局音频配置（WonderBox 用）
# 用法：cd ~/WonderBox && bash tools/install_dmix.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/asound.conf.dmix"
DEST="/etc/asound.conf"

if [ ! -f "$SRC" ]; then
    echo "找不到配置文件: $SRC" >&2
    exit 1
fi

# 先备份旧配置，方便回滚
if [ -f "$DEST" ]; then
    BACKUP="$DEST.bak.$(date +%Y%m%d%H%M%S)"
    sudo cp "$DEST" "$BACKUP"
    echo "已备份旧配置: $BACKUP"
fi

sudo cp "$SRC" "$DEST"
echo "已安装: $DEST"

# 校验声卡 id 是否一致（配置里默认 sndrpigooglevoi）
CARD="$(aplay -L 2>/dev/null | grep -m1 -o 'CARD=[^,]*' | cut -d= -f2 || true)"
if [ -n "$CARD" ] && ! grep -q "$CARD" "$DEST"; then
    echo "警告: 当前声卡 id 为 [$CARD]，配置里没有它；请编辑 $DEST 里的 sndrpigooglevoi。" >&2
fi

echo "--- aplay -L（应能看到 default / dmixer）---"
aplay -L 2>/dev/null | head -20
echo "--- 安装完成，重启 WonderBox 生效 ---"
