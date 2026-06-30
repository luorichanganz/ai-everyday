# Entry point for the AI and semiconductor briefing job.
# Inputs: --dry-run/--dry, .env OpenRouter and SMTP config, online news sources.
# Outputs: sends briefing and log emails, or writes HTML previews in dry-run mode.
import os
import sys
import time
import logging

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        return False

from email_content_generator import generate_weekly_email
from email_sender import send_email, send_log_email
from checkpoint_manager import clear_checkpoints

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
    logging.info("================= [automation start] =================")
    if dry_run:
        logging.info("*** DRY RUN: no email will be sent ***")
    start_time = time.time()
    success = True
    briefing_sent = False
    log_email_sent = False

    try:
        weekly_email = generate_weekly_email()
        if weekly_email is None:
            success = False
            return success

        email_title, email_content, news_date = weekly_email
        send_email(email_title, email_content, news_date, dry_run=dry_run)
        briefing_sent = not dry_run

    except Exception as e:
        success = False
        logging.error(f"Main job failed: {e}", exc_info=True)
    finally:
        elapsed = time.time() - start_time
        logging.info(f"================= [automation end | elapsed: {elapsed:.2f}s] =================\n")
        if not dry_run:
            try:
                send_log_email()
                log_email_sent = True
            except Exception as e:
                success = False
                logging.error(f"Log email failed: {e}", exc_info=True)
        if briefing_sent and log_email_sent:
            clear_checkpoints()
    return success


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv or "--dry" in sys.argv
    sys.exit(0 if main(dry_run=dry_run) else 1)
