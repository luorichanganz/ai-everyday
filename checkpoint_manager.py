# 功能：管理 AI 周报生成流程的本地 checkpoint，用于中断后恢复进度。
# 输入：步骤名称和步骤产物数据。
# 输出：`.checkpoints/ai_weekly_briefing.json` checkpoint 文件；也可清理所有 checkpoint。

import json
import logging
import os
import shutil
from datetime import datetime, timedelta


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
CHECKPOINT_DIR = os.path.join(CURRENT_DIR, ".checkpoints")
CHECKPOINT_FILE = os.path.join(CHECKPOINT_DIR, "ai_weekly_briefing.json")
DEFAULT_CHECKPOINT_TTL_HOURS = 12


def _parse_checkpoint_time(value: str | None) -> datetime | None:
    """解析 checkpoint 中保存的 ISO 时间。"""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _checkpoint_updated_at(checkpoint: dict) -> datetime | None:
    """读取整个 checkpoint 的最后更新时间，兼容旧结构中的步骤完成时间。"""
    updated_at = _parse_checkpoint_time(checkpoint.get("updated_at"))
    if updated_at is not None:
        return updated_at

    step_times = []
    for step in checkpoint.get("steps", {}).values():
        if isinstance(step, dict):
            completed_at = _parse_checkpoint_time(step.get("completed_at"))
            if completed_at is not None:
                step_times.append(completed_at)
    return max(step_times) if step_times else None


def is_checkpoint_expired(checkpoint: dict, ttl_hours: int = DEFAULT_CHECKPOINT_TTL_HOURS) -> bool:
    """判断 checkpoint 是否超过有效期；ttl_hours <= 0 时禁用过期判断。"""
    if ttl_hours <= 0:
        return False
    if not checkpoint.get("steps"):
        return False

    updated_at = _checkpoint_updated_at(checkpoint)
    if updated_at is None:
        return True

    now = datetime.now(updated_at.tzinfo) if updated_at.tzinfo else datetime.now()
    return now - updated_at > timedelta(hours=ttl_hours)


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
        if is_checkpoint_expired(checkpoint):
            updated_at = _checkpoint_updated_at(checkpoint)
            logging.info(
                f"checkpoint 已超过 {DEFAULT_CHECKPOINT_TTL_HOURS} 小时有效期，"
                f"将重新开始；最后更新时间: {updated_at}"
            )
            clear_checkpoints()
            return {"steps": {}}
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
