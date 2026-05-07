"""Weekly summary scheduler."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta

from loguru import logger


class WeeklyReporter:
    def __init__(self, settings, db, notifier):
        self.settings = settings
        self.db = db
        self.notifier = notifier
        self._task: asyncio.Task | None = None

    async def start(self):
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        if self._task:
            self._task.cancel()

    async def _loop(self):
        while True:
            try:
                await asyncio.sleep(self._seconds_until_next_run())
                await self._send_report()
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.exception(f"weekly report failed: {e}")
                await asyncio.sleep(3600)

    def _seconds_until_next_run(self) -> float:
        now = datetime.now(timezone.utc)
        days = ["Monday", "Tuesday", "Wednesday", "Thursday",
                "Friday", "Saturday", "Sunday"]
        target_dow = days.index(self.settings.telegram.weekly_report_day)
        target_hour = self.settings.telegram.weekly_report_hour_utc
        delta_days = (target_dow - now.weekday()) % 7
        target = now.replace(hour=target_hour, minute=0, second=0, microsecond=0) \
                 + timedelta(days=delta_days)
        if target <= now:
            target += timedelta(days=7)
        return (target - now).total_seconds()

    async def _send_report(self):
        weekly = await self.db.get_weekly_stats()
        per_asset = await self.db.get_per_asset_stats(days=7)
        lines = [
            "*Weekly Performance*",
            f"Total: {weekly['count']} | Wins: {weekly['wins']} | Losses: {weekly['losses']}",
            f"Win rate: {weekly['win_rate']:.1f}% | Expectancy: {weekly['expectancy']:+.2f}%",
            "",
            "*Top assets:*",
        ]
        for r in per_asset[:8]:
            lines.append(
                f"`{r['asset']:<10}` {r['tf']:>2}m  {r['wins']}/{r['count']}  "
                f"({r['win_rate']:.0f}%)  {r['pnl']:+.2f}%"
            )
        await self.notifier.send_text("\n".join(lines))
