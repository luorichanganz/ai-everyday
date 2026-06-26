# AI 与半导体周报（AI Weekly Briefing）

自动收集多个 RSS、API 和 Web 新闻源的最近 7 天更新，通过 LLM 总结生成每周 AI 与半导体领域简报邮件，并通过 QQ SMTP 自动发送。

## 当前结构

项目现在拆成三个主要 Python 模块：

```text
ai-everyday/
├── ai_daily_briefing.py        # 主入口：从 0 到发送邮件，只运行这个脚本
├── email_content_generator.py  # 生成邮件正文和主题：抓取新闻、筛选去重、调用 LLM
├── email_sender.py             # 发送邮件：Markdown 转 HTML、套模板、SMTP 发送
├── send_generated_email.py     # 手动发送“已生成的邮件”中的 HTML 邮件副本
├── email_template.html         # HTML 邮件模板，可自行修改样式
├── 已生成的邮件/               # 每次生成的 HTML 邮件副本
├── .env                        # 环境变量配置，不入库
├── .gitignore
└── README.md
```

日常使用只需要运行 `ai_daily_briefing.py`。另外两个脚本会在主脚本运行时被自动导入调用，不需要单独执行。

## 功能

- 多源新闻采集（RSS + API + Web 抓取）
- 最近 7 天内容筛选
- AI 智能体架构、半导体晶圆制造等方向关键词过滤
- LLM 生成周报正文和邮件主题
- 根据原始新闻材料为正文条目自动追加信源链接
- Markdown 正文转 HTML
- 自动识别正文中的 H2 标题，并套用 `email_template.html` 中的正文标题样式
- 每次生成邮件都会在 `已生成的邮件/` 中保存一份 HTML 副本
- 支持按文件名手动发送已生成的邮件，收件人仍使用 `.env` 中的 `RECEIVER_EMAILS`
- 支持 dry-run 预览，不发送真实邮件
- 支持 QQ SMTP 自动发送邮件和运行日志邮件

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
| Juya AI Daily RSS | RSS | AI 日报，按日期聚合 |
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

安装依赖：

```bash
pip install requests python-dotenv
```

## 配置

在项目根目录创建 `.env` 文件：

```env
# 发件邮箱（QQ 邮箱）
SENDER_EMAIL=your-sender@qq.com

# QQ 邮箱 SMTP 授权码
SENDER_PASSWORD=your-auth-code

# 接收简报的邮箱，多个邮箱用逗号分隔
RECEIVER_EMAILS=user1@example.com,user2@example.com

# 接收运行日志的邮箱
LOG_RECEIVER_EMAIL=your-log@qq.com

# OpenRouter API Key
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxx
```

## 使用

发送真实邮件：

```bash
python ai_daily_briefing.py
```

只生成 HTML 预览，不发送邮件：

```bash
python ai_daily_briefing.py --dry-run
```

dry-run 会在项目根目录生成：

```text
email_preview.html
```

每次生成邮件还会在 `已生成的邮件/` 中保留一份 HTML 副本，文件名格式为：

```text
邮件主题__YYYY-MM-DD_HH-MM-SS.html
```

手动发送某一封已生成邮件：

```bash
python send_generated_email.py "邮件主题__YYYY-MM-DD_HH-MM-SS.html"
```

查看可发送的已生成邮件：

```bash
python send_generated_email.py --list
```

只预览手动发送的归档邮件，不真实发送：

```bash
python send_generated_email.py "邮件主题__YYYY-MM-DD_HH-MM-SS.html" --dry-run
```

建议配合 cron、Windows 任务计划程序或 GitHub Actions 每周执行一次。

## 运行流程

`ai_daily_briefing.py` 是唯一入口，内部流程如下：

1. 调用 `email_content_generator.generate_weekly_email()`
2. 抓取 Juya RSS、AI HOT API、多源半导体新闻
3. 筛选最近 7 天且符合关键词方向的内容
4. 调用 OpenRouter LLM 生成邮件正文
5. 按新闻材料为正文条目追加来源链接
6. 再调用 LLM 生成邮件主题
7. 调用 `email_sender.send_email()`
8. 将正文 Markdown 转成 HTML
9. 将正文 H2 标题替换为编号标题模板样式
10. 套用 `email_template.html`
11. 将 HTML 邮件副本保存到 `已生成的邮件/`
12. dry-run 保存预览，正式运行则发送邮件

## HTML 邮件模板

邮件外壳、开头问候、页脚说明、颜色、间距和正文标题模板都放在：

```text
email_template.html
```

模板中保留两个占位符：

- `{{formatted_date}}`：发送日期
- `{{content_html}}`：AI 生成正文转换后的 HTML 内容

正文内容中的 H2 标题，例如：

```markdown
## AI 智能体架构
```

会在 `email_sender.py` 中自动转换为带编号的标题模板样式，例如 `01 AI 智能体架构`。H3 标题和正文段落保持普通正文样式。

## 技术栈

- **LLM**: OpenRouter API，默认模型 `deepseek/deepseek-v4-pro`
- **邮件**: QQ SMTP SSL
- **HTTP 请求**: `requests`，用于 RSS、API 和 Web 新闻源抓取
- **RSS 解析**: `xml.etree.ElementTree`
- **HTML 清洗**: 正则表达式 + `html.unescape`
- **配置加载**: `python-dotenv`

## License

MIT
