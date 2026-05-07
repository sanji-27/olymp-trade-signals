"""Entry point. Wires everything and handles graceful shutdown."""
from __future__ import annotations

import argparse
import asyncio
import signal

from loguru import logger

from config.settings import settings
from src.analytics.weekly_report import WeeklyReporter
from src.database.db_manager import DBManager
from src.notifier.telegram_bot import TelegramNotifier
from src.orchestrator.signal_engine import SignalEngine
from src.utils.logger import setup_logging


async def main(dry_run: bool = False):
    setup_logging(settings.logging.level, settings.logging.rotation_mb,
                  settings.logging.retention_days)
    for w in settings.validate_runtime():
        logger.warning(w)

    db = DBManager(settings.database.path)
    await db.connect()

    notifier = TelegramNotifier(settings, db)
    if not dry_run:
        await notifier.start()

    engine = SignalEngine(settings, db, notifier)
    notifier.attach_engine(engine)

    reporter = WeeklyReporter(settings, db, notifier)
    await reporter.start()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    engine_task = asyncio.create_task(engine.start())
    if dry_run:
        logger.warning("DRY RUN -- no Telegram messages will be sent")

    await stop_event.wait()
    logger.info("shutting down...")
    await engine.stop()
    await reporter.stop()
    await notifier.stop()
    await db.close()
    engine_task.cancel()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
