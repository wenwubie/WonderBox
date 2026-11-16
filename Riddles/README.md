# 脑筋急转弯

进入后显示主菜单，K1/K2 选择“全部题目”“未答过”“已答过”或“重置进度”，K3 确认。重置需要再次按 K3 确认，按 K1 或 K2 可以取消；重置会清空已答和已看记录，但不会删除题库。

答题时 K1 回看上一题，K2 切换下一题，K3 显示答案；长按 K3 或题组结束后按 K3 返回菜单。菜单中长按 K3 退出。模拟窗口支持鼠标点击和数字键 1/2/3，并支持长按 K3 对应按钮；Backspace 或右上角按钮返回菜单，Esc 退出。

```bash
python Riddles/Riddles.py
```

本机模拟默认竖屏，可加 `--landscape` 预览横屏；树莓派使用屏幕的实际方向。真机需要按项目现有方式配置 `/dev/fb1` 和 GPIO 18、23、24，并安装 Pygame、RPi.GPIO 和中文字体（例如 `fonts-wqy-microhei`）。

按 K3 显示过答案的题归入“已答过”，只看题而没有显示答案的题仍属于“未答过”。题目随机排列，“全部题目”优先显示本轮未看过的题；回看和选择“已答过”可以主动重温。旧版只有已看记录，升级时会把它们视为已答过，以保留原有进度。

记录保存在 Windows 的 `%LOCALAPPDATA%/WonderBox/riddles_history.json` 或 Linux 的 `${XDG_STATE_HOME:-~/.local/state}/WonderBox/riddles_history.json`。无法写入时，答题进度仅在本次运行中保留；重置保存失败时不会清空已有记录。

题库是本地 JSON，无需联网；来源和许可见 [SOURCES.md](SOURCES.md)。