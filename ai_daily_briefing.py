# 功能：AI 与半导体周报的主入口脚本，串联“生成邮件正文/标题”和“发送邮件”两个模块。
# 输入：命令行参数 --dry-run/--dry、.env 中的 OpenRouter 与 SMTP 配置、各新闻源在线内容。
# 输出：正式模式下发送周报邮件和运行日志邮件；dry-run 模式下生成 HTML 预览和本地邮件副本。
import os
import sys
import time
import logging

from dotenv import load_dotenv

from email_content_generator import generate_weekly_email
from email_sender import send_email, send_log_email

load_dotenv(override=True)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE_PATH = os.path.join(CURRENT_DIR, "ai_weekly_briefing.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)


def main(dry_run: bool = False):
    logging.info("================= [自动化任务启动] =================")
    if dry_run:
        logging.info("*** 当前为 DRY RUN 模式，不会发送邮件 ***")
    start_time = time.time()

    try:
        weekly_email = generate_weekly_email()
        if weekly_email is None:
            return

        email_title, email_content, news_date = weekly_email

        # 发送邮件（dry_run 模式下仅保存 HTML 文件）
        send_email(email_title, email_content, news_date, dry_run=dry_run)

    except Exception as e:
        logging.error(f"主程序异常: {e}", exc_info=True)

    elapsed = time.time() - start_time
    logging.info(f"================= [任务结束 | 耗时: {elapsed:.2f}秒] =================\n")
    if not dry_run:
        send_log_email()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv or "--dry" in sys.argv
    main(dry_run=dry_run)