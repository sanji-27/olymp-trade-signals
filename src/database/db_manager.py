"""Async SQLite wrapper. One connection, serialized writes."""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

import aiosqlite
from loguru import logger

from src.agents.oracle_agent import FinalSignal


class DBManager:
    def __init__(self, db_path: str):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db: aiosqlite.Connection | None = None

    async def connect(self):
        self.db = await aiosqlite.connect(self.path)
        schema = (Path(__file__).parent / "schema.sql").read_text()
        await self.db.executescript(schema)
        await self.db.commit()
        logger.success(f"db ready: {self.path}")

    async def close(self):
        if self.db:
            await self.db.close()

    async def save_signal(self, sig: FinalSignal, reports: dict) -> int:
        safe_reports = {k: {kk: vv for kk, vv in r.__dict__.items()
                            if kk != "metadata"} for k, r in reports.items()}
        cursor = await self.db.execute(
            "INSERT INTO signals (created_at, asset, direction, expiry_minutes, "
            "confidence_pct, position_usd, reasons_json, reports_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.now(timezone.utc).isoformat(),
                sig.asset, sig.direction, sig.expiry_minutes,
                sig.confidence_pct, sig.position_size_usd,
                json.dumps(sig.reasons),
                json.dumps(safe_reports, default=str),
            ),
        )
        await self.db.commit()
        return cursor.lastrowid

    async def record_outcome(self, sig_id: int, won: bool, pnl_pct: float):
        await self.db.execute(
            "UPDATE signals SET outcome=?, pnl_pct=?, closed_at=? WHERE id=?",
            ("WIN" if won else "LOSS", pnl_pct,
             datetime.now(timezone.utc).isoformat(), sig_id),
        )
        await self.db.commit()

    async def get_daily_stats(self, day: date) -> dict:
        start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc).isoformat()
        end   = (datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
                 + timedelta(days=1)).isoformat()
        async with self.db.execute(
            "SELECT COUNT(*), COALESCE(SUM(pnl_pct),0), "
            "SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) "
            "FROM signals WHERE created_at >= ? AND created_at < ?",
            (start, end),
        ) as cur:
            row = await cur.fetchone()

        async with self.db.execute(
            "SELECT outcome FROM signals WHERE created_at >= ? AND created_at < ? "
            "AND outcome IS NOT NULL ORDER BY id DESC", (start, end),
        ) as cur:
            rows = await cur.fetchall()
        streak = 0
        for (o,) in rows:
            if o == "LOSS": streak += 1
            else: break

        return {
            "signals_count": row[0] or 0,
            "daily_pnl_pct": row[1] or 0.0,
            "consecutive_losses": streak,
        }

    async def get_weekly_stats(self) -> dict:
        since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        async with self.db.execute(
            "SELECT COUNT(*), "
            "SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END), "
            "COALESCE(AVG(pnl_pct),0) "
            "FROM signals WHERE created_at >= ? AND outcome IS NOT NULL",
            (since,),
        ) as cur:
            row = await cur.fetchone()
        count, wins, losses, expectancy = row[0] or 0, row[1] or 0, row[2] or 0, row[3] or 0
        win_rate = (wins / count * 100) if count else 0
        return {"count": count, "wins": wins, "losses": losses,
                "win_rate": win_rate, "expectancy": expectancy}

    async def get_per_asset_stats(self, days: int = 7) -> list[dict]:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        async with self.db.execute(
            "SELECT asset, expiry_minutes, COUNT(*), "
            "SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END), "
            "COALESCE(SUM(pnl_pct),0) "
            "FROM signals WHERE created_at >= ? AND outcome IS NOT NULL "
            "GROUP BY asset, expiry_minutes ORDER BY COUNT(*) DESC",
            (since,),
        ) as cur:
            rows = await cur.fetchall()
        return [
            {"asset": r[0], "tf": r[1], "count": r[2], "wins": r[3],
             "win_rate": (r[3]/r[2]*100) if r[2] else 0, "pnl": r[4]}
            for r in rows
        ]
