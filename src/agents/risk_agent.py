"""
The hard-rule enforcer. Vetoes signals that violate any risk limit.
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.agents.base_agent import AgentReport, BaseAgent, MarketContext


class RiskAgent(BaseAgent):
    name = "risk"

    def __init__(self, settings, db_manager):
        super().__init__(settings)
        self.db = db_manager
        self._consecutive_losses = 0
        self._daily_pnl_pct = 0.0
        self._signals_today = 0
        self._last_signal_per_asset: dict[str, datetime] = {}
        self._stats_date: datetime | None = None

    async def refresh_daily_stats(self) -> None:
        today = datetime.now(timezone.utc).date()
        if self._stats_date == today and self._signals_today > 0:
            return
        stats = await self.db.get_daily_stats(today)
        self._stats_date = today
        self._signals_today = stats.get("signals_count", 0)
        self._daily_pnl_pct = stats.get("daily_pnl_pct", 0.0)
        self._consecutive_losses = stats.get("consecutive_losses", 0)

    async def _evaluate(self, ctx: MarketContext) -> AgentReport:
        await self.refresh_daily_stats()
        rcfg = self.settings.risk
        scfg = self.settings.signals

        now = datetime.now(timezone.utc)

        if self._signals_today >= scfg.max_signals_per_day:
            return AgentReport(
                agent=self.name, veto=True, confidence=0.0,
                reasons=[f"daily signal cap reached ({self._signals_today}/{scfg.max_signals_per_day})"],
            )

        if self._daily_pnl_pct <= -rcfg.max_daily_drawdown_pct:
            return AgentReport(
                agent=self.name, veto=True, confidence=0.0,
                reasons=[f"daily drawdown hit ({self._daily_pnl_pct:.2f}%)"],
            )

        if self._consecutive_losses >= rcfg.consecutive_loss_limit:
            return AgentReport(
                agent=self.name, veto=True, confidence=0.0,
                reasons=[f"{self._consecutive_losses} consecutive losses -- paused for the day"],
            )

        if now.hour in rcfg.blackout_hours_utc:
            return AgentReport(
                agent=self.name, veto=True, confidence=0.0,
                reasons=[f"blackout hour {now.hour:02d}:00 UTC (low liquidity)"],
            )

        last = self._last_signal_per_asset.get(ctx.asset)
        if last:
            elapsed = (now - last).total_seconds() / 60
            if elapsed < rcfg.asset_cooldown_minutes:
                return AgentReport(
                    agent=self.name, veto=True, confidence=0.0,
                    reasons=[f"{ctx.asset} cooldown -- {rcfg.asset_cooldown_minutes - elapsed:.1f} min left"],
                )

        position_size = self._position_size_usd()
        return AgentReport(
            agent=self.name,
            direction="NEUTRAL",
            confidence=1.0,
            reasons=[
                f"risk OK ({self._signals_today}/{scfg.max_signals_per_day} signals today)",
                f"day P/L: {self._daily_pnl_pct:+.2f}%",
                f"position size: ${position_size:.2f}",
            ],
            metadata={
                "position_size_usd": position_size,
                "signals_today": self._signals_today,
                "daily_pnl_pct": self._daily_pnl_pct,
                "consecutive_losses": self._consecutive_losses,
            },
        )

    def _position_size_usd(self) -> float:
        return round(
            self.settings.account.balance_usd * self.settings.risk.risk_per_trade_pct / 100,
            2,
        )

    def mark_signal_sent(self, asset: str) -> None:
        self._signals_today += 1
        self._last_signal_per_asset[asset] = datetime.now(timezone.utc)

    def update_outcome(self, won: bool, pnl_pct: float) -> None:
        self._daily_pnl_pct += pnl_pct
        self._consecutive_losses = 0 if won else self._consecutive_losses + 1
