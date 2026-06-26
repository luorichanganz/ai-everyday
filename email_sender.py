import os
import sys
import time
import html as html_module
import logging
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from datetime import datetime

from dotenv import load_dotenv

load_dotenv(override=True)

# ================= 邮件配置 =================
SMTP_SERVER = "smtp.qq.com"
SMTP_PORT = 465
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "your-sender@qq.com")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD", "your-email-auth-code")
# 接收结果的指定邮箱，逗号分隔，通过环境变量 RECEIVER_EMAILS 配置
_RECEIVER_EMAILS_RAW = os.environ.get("RECEIVER_EMAILS", "")
RECEIVER_EMAIL = [addr.strip() for addr in _RECEIVER_EMAILS_RAW.split(",") if addr.strip()]
LOG_RECEIVER_EMAIL = os.environ.get("LOG_RECEIVER_EMAIL", "your-log@qq.com")

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE_PATH = os.path.join(CURRENT_DIR, "ai_weekly_briefing.log")
EMAIL_TEMPLATE_PATH = os.path.join(CURRENT_DIR, "email_template.html")
GENERATED_EMAIL_DIR = os.path.join(CURRENT_DIR, "已生成的邮件")

def markdown_to_html(text: str) -> str:
    """将 Markdown 格式文本转换为 HTML 片段（纯正则，无第三方依赖）"""
    lines = text.split("\n")
    html_lines: list[str] = []
    in_paragraph = False

    i = 0
    while i < len(lines):
        line = lines[i]

        # 空行 → 段落结束
        if not line.strip():
            if in_paragraph:
                html_lines.append("</p>")
                in_paragraph = False
            i += 1
            continue

        # 分隔线
        if line.strip() == "---":
            if in_paragraph:
                html_lines.append("</p>")
                in_paragraph = False
            html_lines.append("<hr>")
            i += 1
            continue

        # H2 标题
        if line.startswith("## ") and not line.startswith("### "):
            if in_paragraph:
                html_lines.append("</p>")
                in_paragraph = False
            html_lines.append(f"<h2>{_inline_markdown(line[3:].strip())}</h2>")
            i += 1
            continue

        # H3 标题
        if line.startswith("### "):
            if in_paragraph:
                html_lines.append("</p>")
                in_paragraph = False
            html_lines.append(f"<h3>{_inline_markdown(line[4:].strip())}</h3>")
            i += 1
            continue

        # 无序列表项
        if line.strip().startswith("* ") or line.strip().startswith("- "):
            if in_paragraph:
                html_lines.append("</p>")
                in_paragraph = False
            stripped = line.strip()[2:]
            html_lines.append(f"<li>{_inline_markdown(stripped)}</li>")
            i += 1
            continue

        # 普通段落
        if not in_paragraph:
            html_lines.append("<p>")
            in_paragraph = True
            html_lines.append(_inline_markdown(line))
        else:
            html_lines.append(f"<br>{_inline_markdown(line)}")
        i += 1

    if in_paragraph:
        html_lines.append("</p>")

    return "\n".join(html_lines)


def _inline_markdown(text: str) -> str:
    """转换行内 Markdown：**粗体**、*斜体*、[链接](url)"""
    import re as _re
    # 粗体 **xxx**
    text = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # 斜体 *xxx*（排除列表标记）
    text = _re.sub(r"(?<!\*)\*(?!\*)([^*]+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
    # 链接 [text](url)
    text = _re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def _wrap_section_titles(html: str) -> str:
    """将 HTML 中的 H2 章节标题替换为带编号的标题模板样式。"""
    import re as _re
    import html as _html

    pattern = _re.compile(r'<h2>(.*?)</h2>')
    
    class _Counter:
        value = 0

    def _replacer(match: _re.Match) -> str:
        _Counter.value += 1
        num = str(_Counter.value).zfill(2)
        safe_title = _html.escape(match.group(1))
        return (
            '<div style="margin:18px 0 12px 0;">'
            '<table cellpadding="0" cellspacing="0" style="width:100%;font-family:-apple-system,BlinkMacSystemFont,\'Microsoft YaHei\',\'PingFang SC\',sans-serif;">'
            '<tr>'
            f'<td style="vertical-align:middle;font-size:38px;font-weight:800;color:#3bdcee;line-height:1;padding-right:16px;letter-spacing:-2px;width:1%;white-space:nowrap;">{num}</td>'
            f'<td style="vertical-align:middle;font-size:22px;font-weight:700;color:#1a1a1a;line-height:1.2;text-align:left;">{safe_title}</td>'
            '</tr>'
            '</table>'
            '</div>'
        )

    result = pattern.sub(_replacer, html)
    return result



def render_email_template(content_html: str, formatted_date: str) -> str:
    """渲染外部 HTML 邮件模板。"""
    with open(EMAIL_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    replacements = {
        "{{formatted_date}}": html_module.escape(formatted_date),
        "{{content_html}}": content_html,
    }
    missing_placeholders = [placeholder for placeholder in replacements if placeholder not in template]
    if missing_placeholders:
        logging.warning(f"邮件 HTML 模板缺少占位符: {', '.join(missing_placeholders)}")

    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)
    return template


def _safe_filename_part(text: str, max_length: int = 140) -> str:
    """将邮件主题转换为 Windows 可用的文件名片段。"""
    translation = str.maketrans({
        "<": "＜",
        ">": "＞",
        ":": "：",
        '"': "＂",
        "/": "／",
        "\\": "＼",
        "|": "｜",
        "?": "？",
        "*": "＊",
    })
    safe_text = text.translate(translation)
    safe_text = "".join(ch for ch in safe_text if ord(ch) >= 32)
    safe_text = " ".join(safe_text.split()).strip(" .")
    return (safe_text or "未命名邮件")[:max_length].rstrip(" .")


def save_generated_email_copy(title: str, html_body: str) -> str:
    """保存一份本次生成的 HTML 邮件副本，并返回文件路径。"""
    os.makedirs(GENERATED_EMAIL_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_title = _safe_filename_part(title)
    html_file = os.path.join(GENERATED_EMAIL_DIR, f"{safe_title}__{timestamp}.html")

    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html_body)

    logging.info(f"HTML 邮件副本已保存至: {html_file}")
    return html_file


def _plain_text_from_html(html_body: str) -> str:
    """为旧邮件重发生成纯文本备选内容。"""
    import re as _re

    text = _re.sub(r"<(script|style).*?>.*?</\1>", "", html_body, flags=_re.DOTALL | _re.IGNORECASE)
    text = _re.sub(r"<br\s*/?>", "\n", text, flags=_re.IGNORECASE)
    text = _re.sub(r"</(p|div|tr|h1|h2|h3|li)>", "\n", text, flags=_re.IGNORECASE)
    text = _re.sub(r"<.*?>", "", text)
    text = html_module.unescape(text)
    text = _re.sub(r"\n\s*\n", "\n\n", text)
    return text.strip()


def _send_html_message(title: str, html_body: str, plain_body: str):
    """按当前收件人配置发送 HTML 邮件。"""
    msg = MIMEMultipart("alternative")
    sender_nickname = "每周AI简报助手"
    msg["From"] = formataddr(
        (Header(sender_nickname, "utf-8").encode(), SENDER_EMAIL)
    )
    msg["To"] = Header(", ".join(RECEIVER_EMAIL), "utf-8")
    msg["Subject"] = Header(title, "utf-8")

    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    to_addrs = RECEIVER_EMAIL if isinstance(RECEIVER_EMAIL, list) else [RECEIVER_EMAIL]

    logging.info("正在发送邮件...")
    server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
    server.login(SENDER_EMAIL, SENDER_PASSWORD)
    server.sendmail(SENDER_EMAIL, to_addrs, msg.as_string())
    server.quit()
    logging.info(f"邮件已成功发送给：{', '.join(to_addrs)}，共 {len(to_addrs)} 个收件人")


def _resolve_generated_email_path(filename: str) -> str:
    """根据文件名定位“已生成的邮件”目录中的 HTML 文件。"""
    clean_name = os.path.basename(filename.strip().strip('"').strip("'"))
    if not clean_name:
        raise ValueError("请提供要发送的邮件文件名")
    if not clean_name.lower().endswith(".html"):
        clean_name = f"{clean_name}.html"

    generated_dir = os.path.abspath(GENERATED_EMAIL_DIR)
    html_file = os.path.abspath(os.path.join(generated_dir, clean_name))
    if os.path.dirname(html_file) != generated_dir:
        raise ValueError("只能选择“已生成的邮件”目录中的文件名")
    if not os.path.exists(html_file):
        raise FileNotFoundError(f"未找到已生成邮件: {html_file}")
    return html_file


def _title_from_generated_filename(filename: str) -> str:
    """根据归档文件名生成默认邮件主题。"""
    stem = os.path.splitext(os.path.basename(filename))[0]
    marker = "__"
    if marker in stem:
        return stem.rsplit(marker, 1)[0]
    return stem


def send_generated_email(filename: str, dry_run: bool = False):
    """从“已生成的邮件”目录按文件名选择 HTML 副本并发送。"""
    html_file = _resolve_generated_email_path(filename)
    with open(html_file, "r", encoding="utf-8") as f:
        html_body = f.read()

    title = _title_from_generated_filename(html_file)

    if dry_run:
        preview_file = os.path.join(CURRENT_DIR, "email_preview.html")
        with open(preview_file, "w", encoding="utf-8") as f:
            f.write(html_body)
        logging.info(f"[DRY RUN] 已生成邮件预览已保存至: {preview_file}")
        logging.info(f"[DRY RUN] 将发送归档邮件: {html_file}")
        logging.info(f"[DRY RUN] 邮件主题: {title}")
        logging.info(f"[DRY RUN] 收件人(未发送): {', '.join(RECEIVER_EMAIL)}, 共 {len(RECEIVER_EMAIL)} 人")
        return

    plain_body = _plain_text_from_html(html_body)
    _send_html_message(title, html_body, plain_body)
    logging.info(f"已发送本地归档邮件: {html_file}")


def send_email(title: str, content: str, news_date: str, dry_run: bool = False):
    """发送 HTML 邮件（含纯文本备选）；dry_run=True 时保存到本地文件"""
    # 格式化日期
    try:
        clean_date = news_date.strip().replace("/", "-")
        date_obj = datetime.strptime(clean_date, "%Y-%m-%d")
        formatted_date = f"{date_obj.year} 年 {date_obj.month} 月 {date_obj.day} 日"
    except Exception:
        formatted_date = news_date

    # LLM 输出的 Markdown → HTML
    content_html = markdown_to_html(content)

    # 将 H2 章节标题替换为模板中的正文标题样式（带编号）
    content_html = _wrap_section_titles(content_html)

    # HTML 邮件模板（从外部文件读取，便于自行修改）
    html_body = render_email_template(content_html, formatted_date)

    # 每次生成邮件都保留一份 HTML 副本
    save_generated_email_copy(title, html_body)

    # Dry run：保存 HTML 到本地文件，不发邮件
    if dry_run:
        html_file = os.path.join(CURRENT_DIR, "email_preview.html")
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html_body)
        logging.info(f"[DRY RUN] HTML 邮件已保存至: {html_file}")
        logging.info(f"[DRY RUN] 收件人(未发送): {', '.join(RECEIVER_EMAIL)}, 共 {len(RECEIVER_EMAIL)} 人")
        return

    # 纯文本备选（兼容不支持 HTML 的邮件客户端）
    plain_body = (
        f"【简报周期：过去 7 天 | 发送日期：{formatted_date}】\n\n"
        f"亲爱的读者，\n\n"
        f"您好！\n\n"
        f"以下是过去一周 AI 智能体架构与半导体晶圆制造领域的重点动态核心摘要：\n\n"
        f"{content}"
        f"\n\n祝您工作顺利，生活愉快！\n\n"
        f"----------------------------------------\n"
        f"提示：内容由AI辅助创作，可能存在幻觉和错误。\n"
    )

    _send_html_message(title, html_body, plain_body)


def send_log_email():
    """发送运行日志邮件"""
    if not os.path.exists(LOG_FILE_PATH):
        return

    with open(LOG_FILE_PATH, "r", encoding="utf-8") as f:
        log_lines = f.readlines()

    last_log = []
    for line in reversed(log_lines):
        last_log.insert(0, line)
        if "[自动化任务启动]" in line:
            break
    log_text = "".join(last_log)

    message = MIMEText(log_text, "plain", "utf-8")
    message["From"] = SENDER_EMAIL
    message["To"] = LOG_RECEIVER_EMAIL
    message["Subject"] = Header(
        f"自动化任务运行日志 - {time.strftime('%Y-%m-%d %H:%M:%S')}", "utf-8"
    )

    server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
    server.login(SENDER_EMAIL, SENDER_PASSWORD)
    server.sendmail(SENDER_EMAIL, [LOG_RECEIVER_EMAIL], message.as_string())
    server.quit()
    logging.info(f"日志邮件已发送至 {LOG_RECEIVER_EMAIL}")
