"""Classifies regime: trending / ranging / volatile."""
from __future__ import annotations

import numpy as np

from src.agents.base_agent import AgentReport, BaseAgent, MarketContext
from src.indicators.technical import compute_indicators


class RegimeAgent(BaseAgent):
    name = "regime"

    async def _evaluate(self, ctx: MarketContext) -> AgentReport:
        cfg = self.settings.indicators
        rcfg = self.settings.regime

        df = ctx.candles[ctx.primary_tf]
        snap = compute_indicators(df, ctx.asset, ctx.primary_tf, cfg)
        if snap is None:
            return AgentReport(agent=self.name, reasons=["indicators unavailable"])

        regime = "ranging"
        regime_reasons = []

        if not np.isnan(snap.adx) and snap.adx >= rcfg.trending_adx_min:
            regime = "trending"
            regime_reasons.append(f"ADX {snap.adx:.1f} >= {rcfg.trending_adx_min}")
        elif not np.isnan(snap.bb_width) and snap.bb_width <= rcfg.ranging_bb_width_max:
            regime = "ranging"
            regime_reasons.append(f"BB width {snap.bb_width:.4f} <= {rcfg.ranging_bb_width_max}")

        atr_recent = df["high"].sub(df["low"]).tail(20).mean()
        is_volatile = (
            not np.isnan(snap.atr)
            and atr_recent > 0
            and snap.atr > atr_recent * rcfg.volatile_atr_multiplier
        )
        if is_volatile:
            regime = "volatile"
            regime_reasons.append(f"ATR spike: {snap.atr:.5f} vs avg {atr_recent:.5f}")

        if regime == "trending":
            confidence = 0.85
            reasons = [f"trending regime -- favorable for momentum"] + regime_reasons
        elif regime == "ranging":
            confidence = 0.55
            reasons = [f"ranging regime -- favors mean-reversion only"] + regime_reasons
        elif regime == "volatile":
            confidence = 0.20
            reasons = [f"volatile regime -- high noise, low edge"] + regime_reasons
        else:
            confidence = 0.40
            reasons = [f"regime: {regime}"] + regime_reasons

        return AgentReport(
            agent=self.name,
            direction="NEUTRAL",
            confidence=confidence,
            reasons=reasons,
            metadata={
                "regime": regime,
                "adx": snap.adx,
                "bb_width": snap.bb_width,
                "atr": snap.atr,
            },
        )
