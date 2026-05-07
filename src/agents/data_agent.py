"""Data sanity checks. Vetoes hard if data is unusable."""
from __future__ import annotations

import time

import numpy as np

from src.agents.base_agent import AgentReport, BaseAgent, MarketContext

MAX_CANDLE_AGE_MULTIPLIER = 3


class DataAgent(BaseAgent):
    name = "data"

    async def _evaluate(self, ctx: MarketContext) -> AgentReport:
        reasons: list[str] = []

        primary = ctx.candles.get(ctx.primary_tf)
        if primary is None or len(primary) < self.settings.signals.warmup_bars:
            return AgentReport(
                agent=self.name, veto=True,
                reasons=[f"warming up ({len(primary) if primary is not None else 0} bars)"],
            )

        last_ts = primary["timestamp"].iloc[-1].timestamp()
        age_seconds = time.time() - last_ts
        max_age = ctx.primary_tf * 60 * MAX_CANDLE_AGE_MULTIPLIER
        if age_seconds > max_age:
            return AgentReport(
                agent=self.name, veto=True,
                reasons=[f"stale data: last candle {int(age_seconds)}s old"],
            )

        recent_close = primary["close"].tail(20)
        if recent_close.isna().any():
            return AgentReport(
                agent=self.name, veto=True,
                reasons=["NaN values in recent closes"],
            )

        if recent_close.std() == 0 or np.isnan(recent_close.std()):
            return AgentReport(
                agent=self.name, veto=True,
                reasons=["zero variance in price feed"],
            )

        for tf in self.settings.timeframes.context_tfs:
            df = ctx.candles.get(tf)
            if df is None or len(df) < 30:
                reasons.append(f"context TF {tf}m has only {0 if df is None else len(df)} bars")

        return AgentReport(
            agent=self.name,
            direction="NEUTRAL",
            confidence=1.0,
            reasons=reasons or ["data healthy"],
            metadata={
                "primary_bars": len(primary),
                "last_candle_age_s": age_seconds,
            },
        )
