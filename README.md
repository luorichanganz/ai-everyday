# AI 与半导体周报（AI Weekly Briefing）

自动收集多个 RSS、API 和 Web 新闻源的最近 7 天更新，通过 LLM 总结生成每周 AI 与半导体领域简报邮件，并通过 QQ SMTP 自动发送。

## 项目结构

```
ai-everyday/
├── ai_weekly_briefing.py        # 主入口：从 0 到发送邮件，只运行这个脚本
├── email_content_generator.py  # 生成邮件正文和主题：抓取新闻、筛选去重、调用 LLM
├── email_sender.py             # 发送邮件：Markdown 转 HTML、套用模板、SMTP 发送
├── send_generated_email.py     # 手动发送"已生成的邮件"中的 HTML 邮件副本
├── checkpoint_manager.py       # 管理生成流程的阶段 checkpoint，用于中断后恢复进度
├── email_template.html         # HTML 邮件模板，可自行修改样式
├── 已生成的邮件/               # 每次生成的 HTML 邮件副本
├── .github/workflows/          # GitHub Actions 自动运行配置
├── .env                        # 环境变量配置，不入库
├── .gitignore
├── requirements.txt
└── README.md
```

日常使用只需要运行 `ai_weekly_briefing.py`，其余模块会被自动导入调用。

## 功能

- 多源新闻采集（RSS + API + Web 抓取），覆盖 9 个新闻源
- 最近 7 天内容筛选，关键词智能过滤
- **断点续传**：生成流程分多个阶段，每阶段完成后保存 checkpoint，中断后可从上次断点恢复，避免重复调用 LLM
- LLM 生成周报正文和邮件主题
- 根据原始新闻材料为正文条目自动追加信源链接
- Markdown 正文转 HTML，自动识别 H2 标题并套用模板样式
- 每次生成后保存 HTML 副本到 `已生成的邮件/`
- 支持 `--dry-run` 模式，仅生成预览不发送邮件
- 支持手动发送已生成的邮件（`send_generated_email.py`）
- QQ SMTP 自动发送邮件及运行日志邮件

## 断点续传（Checkpoint）

生成流程被拆分为 4 个阶段，每阶段完成后自动保存到 `.checkpoints/ai_weekly_briefing.json`：

> 阶段 1 → 阶段 2 → 阶段 3 → 阶段 4（生成完毕，清除 checkpoint）

如果中途失败（如网络波动、LLM 超时），重新运行脚本会自动从已完成的最后一步继续，已完成的 LLM 调用无需重跑。Checkpoint 默认 12 小时过期。

## 关注方向

邮件输出主要覆盖两个主题：

| 邮件主题 | 覆盖方向 |
| --- | --- |
| **AI 智能体架构** | Agent 架构设计、提示词工程、Context Engineering、MCP 协议、RAG、多智能体协作等 |
| **半导体晶圆制造** | Foundry 代工动态、AI for 智能制造、AI for EDA/IC 设计、AI for Science、先进制程与封装 |

内容偏向 **Foundry 代工与晶圆制造** 视角。

## 新闻源

| 源 | 类型 | 说明 |
| --- | --- | --- |
| Juya AI Daily RSS | RSS | AI 日报，按日聚合 |
| AI HOT 每日精选 | API | AI 行业动态；先取最近 7 期日报索引，再逐日获取日报详情 |
| Semiconductor Engineering | RSS | 半导体专题 |
| Semiconductor Digest | RSS | 半导体专题 |
| SemiWiki | RSS | 半导体专题 |
| GlobalFoundries | RSS | 半导体专题 |
| Synopsys News | Web | 半导体与 EDA 相关新闻 |
| Cadence Press | RSS | 半导体与 EDA 相关新闻 |
| DIGITIMES | Web | 半导体产业新闻 |

## 环境要求

- Python 3.10+
- OpenRouter API Key
- QQ 邮箱 SMTP 授权码
- GitHub Actions（可选，用于自动化运行）

安装依赖：

```bash
pip install requests python-dotenv
```

## 配置（.env）

在项目根目录创建 `.env` 文件：

```env
# === 邮箱配置（QQ SMTP） ===
SENDER_EMAIL=your-sender@qq.com
SENDER_PASSWORD=your-auth-code
RECEIVER_EMAILS=user1@example.com,user2@example.com
LOG_RECEIVER_EMAIL=your-log@qq.com

# === LLM 配置 ===
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxx

# 可选：自定义 LLM 供应商与模型（不设置则使用默认值）
LLM_API_URL=https://openrouter.ai/api/v1/chat/completions
LLM_MODEL=deepseek/deepseek-v4-pro
```

OpenRouter API Key 在 [openrouter.ai/keys](https://openrouter.ai/keys) 获取。QQ 授权码在 QQ 邮箱设置 → 账户 → POP3/IMAP/SMTP 服务中生成。`LLM_API_URL` 和 `LLM_MODEL` 可选，用于切换到其他 LLM 供应商（任何兼容 OpenAI 接口的 API 均可）。

## 使用

**发送真实邮件：**

```bash
python ai_weekly_briefing.py
```

**只生成 HTML 预览，不发送邮件：**

```bash
python ai_weekly_briefing.py --dry-run
```

dry-run 会在项目根目录生成 `email_preview.html`。

每次生成还会在 `已生成的邮件/` 中保留一份 HTML 副本，文件名的格式为 `邮件主题__YYYY-MM-DD_HH-MM-SS.html`。

**手动发送某一封已生成邮件：**

```bash
python send_generated_email.py "邮件主题__YYYY-MM-DD_HH-MM-SS.html"
```

**列出可手动发送的已生成邮件：**

```bash
python send_generated_email.py --list
```

**预览而不发送：**

```bash
python send_generated_email.py "文件名.html" --dry-run
```

建议配合 cron、Windows 任务计划程序或 GitHub Actions 每周执行一次。

## GitHub Actions 自动化

项目包含 [`.github/workflows/weekly-briefing.yml`](.github/workflows/weekly-briefing.yml)，配置如下：

- **定时触发**：每周二 16:20（北京时间）
- **手动触发**：支持 `workflow_dispatch`，可指定是否真实发送
- **断点续传**：支持从上一次失败的 workflow run 恢复 checkpoint 和已生成的邮件
- **Artifact 保存**：每次运行自动上传生成的邮件（`ai-weekly-email`）和日志/checkpoint（`ai-weekly-checkpoint`），保留 14 天
- **预生成邮件发送**：如果上次 dry-run 已经生成了邮件，本次可直接发送，无需重复跑 LLM

需要在 GitHub 仓库设置以下 Secrets：

- `SENDER_EMAIL`
- `SENDER_PASSWORD`
- `RECEIVER_EMAILS`
- `LOG_RECEIVER_EMAIL`
- `OPENROUTER_API_KEY`

可选 Variables：

- `LLM_API_URL`
- `LLM_MODEL`

## 运行流程

`ai_weekly_briefing.py` 是唯一入口，内部流程如下：

1. 调用 `generate_weekly_email()`
2. 抓取 JUYA RSS、AI HOT API（近 7 期日报）、多源半导体新闻
3. 筛选最近 7 天且符合关键词方向的内容
4. 调用 LLM 生成邮件正文（**有 checkpoint**）
5. 按新闻材料为正文条目追加来源链接（**有 checkpoint**）
6. 调用 LLM 生成邮件主题（**有 checkpoint**）
7. 调用 `send_email()`
8. 将正文 Markdown 转换成 HTML
9. 将正文 H2 标题替换为编号标题模板样式
10. 套用 `email_template.html`
11. 将 HTML 邮件副本保存到 `已生成的邮件/`
12. dry-run 保存预览（`email_preview.html`），正常运行时发送邮件
13. 发送成功后清除 checkpoint

## HTML 邮件模板

邮件外壳、开头问候、页脚说明、配色、间距和正文标题模板都放在 [`email_template.html`](email_template.html) 中。

模板中保留两个占位符：
- `{{formatted_date}}`：发送日期
- `{{content_html}}`：AI 生成正文转换后的 HTML 内容

正文内容中的 H2 标题，例如：

```markdown
## AI 智能体架构
```

会在 `email_sender.py` 中自动转换为带编号的标题模板样式，例如 `01 AI 智能体架构`。H3 标题和正文段落保持普通正文样式。

## 技术栈

- **LLM**：OpenRouter API，默认模型 `deepseek/deepseek-v4-pro`，支持通过 `LLM_API_URL` / `LLM_MODEL` 切换到任意兼容 OpenAI 接口的供应商
- **邮件**：QQ SMTP SSL
- **HTTP 请求**：`requests`，用于 RSS、API 和 Web 新闻源抓取
- **RSS 解析**：`xml.etree.ElementTree`
- **HTML 清洗**：正则表达式 + `html.unescape`
- **配置加载**：`python-dotenv`

## License

MIT
