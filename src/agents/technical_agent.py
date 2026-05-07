"""
Heavy agent: indicators on every TF, multi-timeframe alignment, patterns, S/R.
"""
from __future__ import annotations

from src.agents.base_agent import AgentReport, BaseAgent, MarketContext
from src.indicators.patterns import detect_patterns
from src.indicators.support_resistance import find_levels, is_near_level
from src.indicators.technical import (
    IndicatorSnapshot,
    compute_indicators,
    directional_bias,
)


class TechnicalAgent(BaseAgent):
    name = "technical"

    async def _evaluate(self, ctx: MarketContext) -> AgentReport:
        cfg = self.settings.indicators

        snapshots: dict[int, IndicatorSnapshot] = {}
        for tf, df in ctx.candles.items():
            snap = compute_indicators(df, ctx.asset, tf, cfg)
            if snap is not None:
                snapshots[tf] = snap

        if ctx.primary_tf not in snapshots:
            return AgentReport(
                agent=self.name, veto=True,
                reasons=["could not compute primary TF indicators"],
            )

        primary_snap = snapshots[ctx.primary_tf]

        biases: dict[int, tuple[str, float]] = {}
        for tf, snap in snapshots.items():
            biases[tf] = directional_bias(snap)

        primary_dir, primary_strength = biases[ctx.primary_tf]
        if primary_dir == "NEUTRAL":
            return AgentReport(
                agent=self.name,
                direction="NEUTRAL",
                confidence=primary_strength * 0.5,
                reasons=["primary TF shows no directional bias"],
                metadata={"biases": {tf: b for tf, b in biases.items()}},
            )

        aligned = 0
        opposed = 0
        for tf, (d, _) in biases.items():
            if tf == ctx.primary_tf:
                continue
            if d == primary_dir:
                aligned += 1
            elif d != "NEUTRAL":
                opposed += 1

        total_other = max(1, aligned + opposed)
        alignment_ratio = aligned / total_other

        patterns = detect_patterns(ctx.candles[ctx.primary_tf])
        pattern_bonus = 0.0
        pattern_reasons = []
        for name, dir_ in patterns.items():
            if dir_ == "bull" and primary_dir == "CALL":
                pattern_bonus += 0.10
                pattern_reasons.append(f"pattern: {name}")
            elif dir_ == "bear" and primary_dir == "PUT":
                pattern_bonus += 0.10
                pattern_reasons.append(f"pattern: {name}")
            elif dir_ in ("bull", "bear"):
                pattern_bonus -= 0.08
                pattern_reasons.append(f"contradicting pattern: {name}")
        pattern_bonus = max(-0.15, min(0.15, pattern_bonus))

        levels = find_levels(ctx.candles[ctx.primary_tf])
        sr_bonus = 0.0
        sr_reasons = []
        near = is_near_level(levels, ctx.current_price, threshold_pct=0.10)
        if near:
            if near.kind == "support" and primary_dir == "CALL":
                sr_bonus = 0.08
                sr_reasons.append(f"price at support ({near.price:.5f}, {near.touches} touches)")
            elif near.kind == "resistance" and primary_dir == "PUT":
                sr_bonus = 0.08
                sr_reasons.append(f"price at resistance ({near.price:.5f}, {near.touches} touches)")
            elif near.kind == "resistance" and primary_dir == "CALL":
                sr_bonus = -0.10
                sr_reasons.append(f"CALL into resistance at {near.price:.5f}")
            elif near.kind == "support" and primary_dir == "PUT":
                sr_bonus = -0.10
                sr_reasons.append(f"PUT into support at {near.price:.5f}")

        confidence = (
            0.60 * primary_strength
            + 0.30 * alignment_ratio
            + pattern_bonus
            + sr_bonus
        )
        confidence = max(0.0, min(1.0, confidence))

        reasons = [
            f"{ctx.primary_tf}m bias: {primary_dir} (strength {primary_strength:.2f})",
            f"EMA alignment: {primary_snap.ema_alignment}",
            f"RSI {primary_snap.rsi:.1f} ({primary_snap.rsi_state})",
            f"MACD: {primary_snap.macd_cross or 'none'} (hist {primary_snap.macd_hist:.5f})",
            f"MTF alignment: {aligned}/{total_other} TFs agree",
        ] + pattern_reasons + sr_reasons

        return AgentReport(
            agent=self.name,
            direction=primary_dir,
            confidence=confidence,
            reasons=reasons,
            metadata={
                "primary_snapshot": primary_snap.__dict__,
                "biases": biases,
                "alignment_ratio": alignment_ratio,
                "patterns": patterns,
                "near_level": near.__dict__ if near else None,
            },
        )
