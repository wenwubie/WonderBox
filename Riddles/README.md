# 脑筋急转弯

进入后显示主菜单，K1/K2 选择“全部题目”“未答过”“已答过”或“重置进度”，K3 确认。重置需要再次按 K3 确认，按 K1 或 K2 可以取消；重置会清空已答和已看记录，但不会删除题库。

答题时 K1 回看上一题，K2 切换下一题，K3 显示答案。答题中长按 K3 返回菜单，题组结束后短按 K3 返回菜单。菜单中长按 K3 退出。模拟窗口支持鼠标点击和数字键 1/2/3，并支持长按 K3 对应按钮；Backspace 或右上角按钮返回菜单，Esc 退出。

显示题目后自动朗读题目（“请听题。…”），揭晓答案后语音提示答案内容（“答案是。…”），均为预生成的微软神经网络音色 ogg（晓伊·萌版，自然又可爱），**本地播放、零延迟、不联网**。进入功能时有语音欢迎，按键按下有按键音。

**音频文件**（都在本功能 `media/` 目录，不和其它功能混放）：
- `media/welcome.ogg`：进入时的语音欢迎。
- `media/tts/*.ogg`：500 题的题目+答案共 1000 段，按文本 hash 命名，`common/tts.py` 命中即播。题目出现顺序虽随机，但文本固定，全部预生成，所以任意题都秒播。

改题库后，在开发机重跑 `python tools/generate_assets.py --only riddles --force`（生成需联网，用 edge-tts 晓伊萌版；已存在默认跳过）。排查可跑 `python -c "from common import tts; print(tts.Speaker(pregen_dir='Riddles/media/tts').status())"` 看 `play_count` / `miss_count` / `load_error`。设 `POKEMON_NO_AUDIO=1` 静音。Pi 端无需联网/模型。

```bash
python Riddles/Riddles.py
```

本机模拟默认竖屏，可加 `--landscape` 预览横屏；树莓派使用屏幕的实际方向。真机需要按项目现有方式配置 `/dev/fb1` 和 GPIO 18、23、24，并安装 Pygame、RPi.GPIO 和中文字体（例如 `fonts-wqy-microhei`）。

按 K3 显示过答案的题归入“已答过”，只看题而没有显示答案的题仍属于“未答过”。题目随机排列，“全部题目”优先显示本轮未看过的题；回看和选择“已答过”可以主动重温。旧版只有已看记录，升级时会把它们视为已答过，以保留原有进度。

记录保存在 Windows 的 `%LOCALAPPDATA%/WonderBox/riddles_history.json` 或 Linux 的 `${XDG_STATE_HOME:-~/.local/state}/WonderBox/riddles_history.json`。无法写入时，答题进度仅在本次运行中保留；重置保存失败时不会清空已有记录。

题库是本地 JSON，无需联网；来源和许可见 [SOURCES.md](SOURCES.md)。