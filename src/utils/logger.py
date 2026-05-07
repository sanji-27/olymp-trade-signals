"""Centralized loguru config. Import setup_logging() once at startup."""
from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def setup_logging(level: str = "INFO", rotation_mb: int = 50, retention_days: int = 30) -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        colorize=True,
    )
    logs_dir = PROJECT_ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)
    logger.add(
        logs_dir / "bot.log",
        level=level,
        rotation=f"{rotation_mb} MB",
        retention=f"{retention_days} days",
        compression="gz",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        enqueue=True,
    )
    logger.info(f"logging initialized (level={level})")
