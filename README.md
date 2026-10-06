# 阅读教练 Agent（Reading Coach Agent）

面向中文 CS / AI 学习者的**目标语料驱动**阅读教练：你给它一组真正要读的英文材料，它根据你已经认识的词，标出缺口、排出阅读顺序，阅读时只给刚好够用、**有词典依据**的提示，读完再检测并写回记忆。

旧版 macOS Tk 桌面应用已归档在 [`v0-tk`](https://github.com/NafYoung/english-reading-assistant/releases/tag/v0-tk)。那个版本默认模型 `deepseek-chat` 已于 2026-07-24 下线，若要运行请把 `config.json` 里的 `model` 改成 `deepseek-flash`。

## 本地安装（macOS / Linux）

需要 Python 3.12+。推荐用 [uv](https://docs.astral.sh/uv/)：

```bash
# 安装 uv（若尚未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

git clone https://github.com/NafYoung/english-reading-assistant.git
cd english-reading-assistant
uv sync
```

第一次使用构建本地词典（下载 ECDICT 压缩包约 207MB，精简后约 36MB / 21 万条，只需一次）：

```bash
uv run era setup-dict
uv run era serve
```

浏览器打开 http://127.0.0.1:8000 。应用只监听本机。

没有 DeepSeek Key 时应用也能启动，设置页会清楚提示。想先看界面、不花 API 费用：

```bash
uv run era serve --mock
```

## 五分钟上手

1. **设置**：把 DeepSeek API Key 粘贴到 `/setup`（欧路 Key、墨墨 Token 可选）。点「保存设置」，再点「测试连接」。成功后可在「调用日志」看到一条 `ping` 记录。
2. **分级测试**：打开「分级测试」，按是否认识作答（含伪词）。约 5 分钟，得到词汇量估计。
3. **导入已知词（可选）**：上传一个每行一个词的 TXT，或填写欧路 / 墨墨凭证。欧路生词本会标成 `learning`（查过 = 曾经不认识）。
4. **导入语料**：新建语料，粘贴一个 URL、上传 PDF 或 Markdown。看导入报告里的词次、乱码块过滤、OOV。
5. **阅读**：打开文档。默认只给预测生词加波浪线（L1）。点词只从 ECDICT / 已审核术语里选义项；没有合适义项会明确说「词典中没有符合本句的义项」，并进入术语审核队列。同一句要先看「结构」（L2）才能打开「中文」（L3）。
6. **读后**：结束阅读 → 确认没点过的预测生词 → 3 道理解题 + 语境填空。结果写进词状态和复习卡片。

数据在 `./data/`（已 gitignore）。密钥只存在本机 `config.json` 或环境变量 `DEEPSEEK_API_KEY`，**不要提交**。

## 开发

```bash
uv sync --extra dev
uv run pytest -q
uv run ruff check src tests
```

## 许可证

MIT。词典数据来自 [ECDICT](https://github.com/skywind3000/ECDICT)（MIT）。PDF 解析使用 pdfminer.six（MIT），不使用 AGPL 的 PyMuPDF。
