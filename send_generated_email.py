# 用于手动发送已生成在《已生成的邮件》目录中的 HTML 邮件副本。
# 可以通过命令行参数指定要发送的文件名，或使用 --list 参数列出可发送的邮件列表。
# 还支持 --dry-run 参数仅生成预览而不实际发送邮件。

import argparse
import logging
import os

from dotenv import load_dotenv

from email_sender import GENERATED_EMAIL_DIR, LOG_FILE_PATH, send_generated_email

load_dotenv(override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)


def list_generated_emails():
    """列出“已生成的邮件”目录中的 HTML 邮件副本。"""
    if not os.path.exists(GENERATED_EMAIL_DIR):
        logging.info(f"目录不存在: {GENERATED_EMAIL_DIR}")
        return

    files = [
        name
        for name in os.listdir(GENERATED_EMAIL_DIR)
        if name.lower().endswith(".html")
    ]
    if not files:
        logging.info(f"目录中暂无 HTML 邮件: {GENERATED_EMAIL_DIR}")
        return

    logging.info(f"已生成的邮件目录: {GENERATED_EMAIL_DIR}")
    for name in sorted(files, reverse=True):
        logging.info(name)


def parse_args():
    parser = argparse.ArgumentParser(description="手动发送“已生成的邮件”目录中的 HTML 邮件")
    parser.add_argument("filename", nargs="?", help="要发送的 HTML 文件名，可不带 .html 后缀")
    parser.add_argument("--list", action="store_true", help="列出可发送的已生成邮件")
    parser.add_argument("--dry-run", "--dry", action="store_true", help="只生成预览，不发送邮件")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.list:
        list_generated_emails()
        return

    if not args.filename:
        raise SystemExit("请提供要发送的文件名，或使用 --list 查看可发送的邮件。")

    send_generated_email(args.filename, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
