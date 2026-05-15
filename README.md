# English Reading Assistant

这是一个使用 Python 3.12 和 Tkinter 的 macOS 桌面应用。项目入口统一为 `main.py`，推荐在 conda 环境中运行。

## 1. 创建环境

```bash
conda env create -f environment.yml
```

如果环境已经存在，更新时使用：

```bash
conda env update -f environment.yml --prune
```

## 2. 激活环境

```bash
conda activate english-reading-assistant
```

## 3. 启动项目

首次使用先准备本地配置：

```bash
cp config.json.example config.json
```

然后把 `config.json` 里的 `api_key` 改成你自己的 DeepSeek Key，再启动：

```bash
python main.py
```

如果解析较长文章时偶尔超时，可以把 `config.json` 里的 `timeout_seconds` 调大到 `60` 或 `90`。

现在程序遇到较长文章时，也会自动按段落分成多次请求再合并结果，避免整篇一次请求导致超时。
对于被拆成多段的长文章，程序还会在分段解析后自动生成一版“整篇总览”，方便先看全文重点，再看各部分细节。
桌面界面已经优化为双栏卡片布局，增加了输入统计、进度状态、复制结果和清空原文按钮。
结果区现在会按“整篇总览 / 分段标题 / 编号小节 / 成功或失败提示”做富文本高亮；桌面 `.app` 也会自动使用项目内的自定义图标。
输入区现在支持导入 UTF-8 编码的 `txt/md/markdown` 文件，结果区支持一键导出 Markdown。

如果你不想每次打开终端，也可以在 macOS 里直接双击项目根目录的 `run.command`。

如果你想要一个更像“桌面按钮”的入口，而且不想依赖 Terminal，可以在项目目录运行：

```bash
python install_desktop_launcher.py
```

执行后会在桌面生成或更新 `英语阅读助手.app`。以后双击它即可在后台启动项目，不会再弹出 Terminal，也不会因为关闭 Terminal 而把程序一起关掉。

如果桌面按钮点击后没有正常打开，可以查看日志：

```bash
tail -n 50 ~/Library/Logs/English\ Reading\ Assistant/app.log
```

如果你要连接 Obsidian，请在 `config.json` 里补上：

```json
"obsidian": {
  "vault_path": "/你的/Obsidian/Vault/绝对路径",
  "note_path": "Inbox/English Reading.md"
}
```

解析成功后，界面会启用“保存到 Obsidian”按钮，并把当前原文和解析结果追加到该笔记。

## 4. 运行测试

```bash
python -m unittest discover -s tests
```
