# 功能：管理 AI 周报生成流程的本地 checkpoint，用于中断后恢复进度。
# 输入：步骤名称和步骤产物数据。
# 输出：`.checkpoints/ai_daily_briefing.json` checkpoint 文件；也可清理所有 checkpoint。

import json
import logging
import os
import shutil
from datetime import datetime


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
CHECKPOINT_DIR = os.path.join(CURRENT_DIR, ".checkpoints")
CHECKPOINT_FILE = os.path.join(CHECKPOINT_DIR, "ai_daily_briefing.json")


def load_checkpoint() -> dict:
    """读取当前 checkpoint；不存在或损坏时返回空结构。"""
    if not os.path.exists(CHECKPOINT_FILE):
        return {"steps": {}}

    try:
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            checkpoint = json.load(f)
        if not isinstance(checkpoint, dict):
            raise ValueError("checkpoint root is not a dict")
        checkpoint.setdefault("steps", {})
        return checkpoint
    except Exception as e:
        logging.warning(f"checkpoint 读取失败，将从头开始: {e}")
        return {"steps": {}}


def get_checkpoint_step(checkpoint: dict, step_name: str) -> dict | None:
    """读取指定步骤的数据。"""
    step = checkpoint.get("steps", {}).get(step_name)
    if not isinstance(step, dict):
        return None
    data = step.get("data")
    return data if isinstance(data, dict) else None


def save_checkpoint_step(step_name: str, data: dict):
    """保存指定步骤的 checkpoint。"""
    checkpoint = load_checkpoint()
    checkpoint.setdefault("steps", {})[step_name] = {
        "completed_at": datetime.now().isoformat(timespec="seconds"),
        "data": data,
    }
    checkpoint["updated_at"] = datetime.now().isoformat(timespec="seconds")

    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    tmp_file = f"{CHECKPOINT_FILE}.tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, ensure_ascii=False, indent=2)
    os.replace(tmp_file, CHECKPOINT_FILE)
    logging.info(f"checkpoint 已保存: {step_name}")


def clear_checkpoints():
    """清理所有 checkpoint。"""
    if os.path.exists(CHECKPOINT_DIR):
        shutil.rmtree(CHECKPOINT_DIR)
        logging.info("checkpoint 已清理")
