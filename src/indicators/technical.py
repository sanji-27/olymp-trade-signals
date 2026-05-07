"""
Pure-function indicator calculations. No state.
Input: pd.DataFrame with columns [open, high, low, close, volume].
Output: IndicatorSnapshot with computed values.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import pandas_ta as ta


@dataclass
class IndicatorSnapshot:
    asset: str
    timeframe: int
    timestamp: pd.Timestamp
    close: float

    ema: dict[int, float] = field(default_factory=dict)
    ema_alignment: str = "neutral"
    adx: float = float("nan")
    trend_strength: str = "weak"

    rsi: float = float("nan")
    rsi_state: str = "neutral"
    macd: float = float("nan")
    macd_signal: float = float("nan")
    macd_hist: float = float("nan")
    macd_cross: str = "none"
    stoch_k: float = float("nan")
    stoch_d: float = float("nan")
    stoch_state: str = "neutral"

    atr: float = float("nan")
    bb_upper: float = float("nan")
    bb_middle: float = float("nan")
    bb_lower: float = float("nan")
    bb_width: float = float("nan")
    bb_position: float = float("nan")

    raw: dict = field(default_factory=dict, repr=False)


def compute_indicators(
    df: pd.DataFrame,
    asset: str,
    timeframe: int,
    cfg,
) -> IndicatorSnapshot | None:
    min_bars = max(cfg.ema_periods + [cfg.bb_period, cfg.macd_slow, cfg.adx_period * 2])
    if len(df) < min_bars + 5:
        return None

    snap = IndicatorSnapshot(
        asset=asset,
        timeframe=timeframe,
        timestamp=df["timestamp"].iloc[-1],
        close=float(df["close"].iloc[-1]),
    )

    close = df["close"]
    high  = df["high"]
    low   = df["low"]

    # EMAs
    for period in cfg.ema_periods:
        series = ta.ema(close, length=period)
        snap.ema[period] = float(series.iloc[-1]) if series is not None else float("nan")

    if all(not np.isnan(snap.ema[p]) for p in cfg.ema_periods):
        sorted_periods = sorted(cfg.ema_periods)
        bullish = all(
            snap.ema[sorted_periods[i]] > snap.ema[sorted_periods[i+1]]
            for i in range(len(sorted_periods)-1)
        )
        bearish = all(
            snap.ema[sorted_periods[i]] < snap.ema[sorted_periods[i+1]]
            for i in range(len(sorted_periods)-1)
        )
        snap.ema_alignment = "bull" if bullish else "bear" if bearish else "neutral"

    # ADX
    adx_df = ta.adx(high, low, close, length=cfg.adx_period)
    if adx_df is not None and not adx_df.empty:
        col = f"ADX_{cfg.adx_period}"
        if col in adx_df:
            snap.adx = float(adx_df[col].iloc[-1])
            if snap.adx >= 40:
                snap.trend_strength = "strong"
            elif snap.adx >= cfg.adx_trending_threshold:
                snap.trend_strength = "moderate"
            else:
                snap.trend_strength = "weak"

    # RSI
    rsi_series = ta.rsi(close, length=cfg.rsi_period)
    if rsi_series is not None:
        snap.rsi = float(rsi_series.iloc[-1])
        if snap.rsi <= cfg.rsi_oversold:
            snap.rsi_state = "oversold"
        elif snap.rsi >= cfg.rsi_overbought:
            snap.rsi_state = "overbought"
        else:
            snap.rsi_state = "neutral"

    # MACD
    macd_df = ta.macd(close, fast=cfg.macd_fast, slow=cfg.macd_slow, signal=cfg.macd_signal)
    if macd_df is not None and not macd_df.empty:
        m_col = f"MACD_{cfg.macd_fast}_{cfg.macd_slow}_{cfg.macd_signal}"
        s_col = f"MACDs_{cfg.macd_fast}_{cfg.macd_slow}_{cfg.macd_signal}"
        h_col = f"MACDh_{cfg.macd_fast}_{cfg.macd_slow}_{cfg.macd_signal}"
        if all(c in macd_df for c in (m_col, s_col, h_col)):
            snap.macd = float(macd_df[m_col].iloc[-1])
            snap.macd_signal = float(macd_df[s_col].iloc[-1])
            snap.macd_hist = float(macd_df[h_col].iloc[-1])
            if len(macd_df) >= 2:
                prev_m = macd_df[m_col].iloc[-2]
                prev_s = macd_df[s_col].iloc[-2]
                if prev_m <= prev_s and snap.macd > snap.macd_signal:
                    snap.macd_cross = "bull_cross"
                elif prev_m >= prev_s and snap.macd < snap.macd_signal:
                    snap.macd_cross = "bear_cross"

    # Stochastic
    stoch_df = ta.stoch(high, low, close, k=cfg.stoch_k, d=cfg.stoch_d, smooth_k=cfg.stoch_smooth)
    if stoch_df is not None and not stoch_df.empty:
        k_col = f"STOCHk_{cfg.stoch_k}_{cfg.stoch_d}_{cfg.stoch_smooth}"
        d_col = f"STOCHd_{cfg.stoch_k}_{cfg.stoch_d}_{cfg.stoch_smooth}"
        if k_col in stoch_df:
            snap.stoch_k = float(stoch_df[k_col].iloc[-1])
            snap.stoch_d = float(stoch_df[d_col].iloc[-1])
            if snap.stoch_k <= 20:
                snap.stoch_state = "oversold"
            elif snap.stoch_k >= 80:
                snap.stoch_state = "overbought"

    # ATR
    atr_series = ta.atr(high, low, close, length=cfg.atr_period)
    if atr_series is not None:
        snap.atr = float(atr_series.iloc[-1])

    # Bollinger Bands
    bb_df = ta.bbands(close, length=cfg.bb_period, std=cfg.bb_std)
    if bb_df is not None and not bb_df.empty:
        u_col = f"BBU_{cfg.bb_period}_{cfg.bb_std}"
        m_col = f"BBM_{cfg.bb_period}_{cfg.bb_std}"
        l_col = f"BBL_{cfg.bb_period}_{cfg.bb_std}"
        if all(c in bb_df for c in (u_col, m_col, l_col)):
            snap.bb_upper  = float(bb_df[u_col].iloc[-1])
            snap.bb_middle = float(bb_df[m_col].iloc[-1])
            snap.bb_lower  = float(bb_df[l_col].iloc[-1])
            if snap.bb_middle:
                snap.bb_width = (snap.bb_upper - snap.bb_lower) / snap.bb_middle
            band_range = snap.bb_upper - snap.bb_lower
            if band_range > 0:
                snap.bb_position = (snap.close - snap.bb_lower) / band_range

    return snap


def directional_bias(snap: IndicatorSnapshot) -> tuple[str, float]:
    if snap is None:
        return "NEUTRAL", 0.0

    score = 0.0
    weight = 0.0

    if snap.ema_alignment == "bull":
        score += 1.0; weight += 1.0
    elif snap.ema_alignment == "bear":
        score -= 1.0; weight += 1.0

    if snap.macd_cross == "bull_cross":
        score += 0.8; weight += 0.8
    elif snap.macd_cross == "bear_cross":
        score -= 0.8; weight += 0.8
    elif not np.isnan(snap.macd_hist):
        if snap.macd_hist > 0: score += 0.3; weight += 0.3
        else: score -= 0.3; weight += 0.3

    if snap.rsi_state == "oversold":
        score += 0.5; weight += 0.5
    elif snap.rsi_state == "overbought":
        score -= 0.5; weight += 0.5

    if snap.stoch_state == "oversold":
        score += 0.4; weight += 0.4
    elif snap.stoch_state == "overbought":
        score -= 0.4; weight += 0.4

    if not np.isnan(snap.bb_position):
        if snap.bb_position < 0.1: score += 0.3; weight += 0.3
        elif snap.bb_position > 0.9: score -= 0.3; weight += 0.3

    if weight == 0:
        return "NEUTRAL", 0.0

    normalized = score / weight
    if normalized > 0.25:
        return "CALL", min(1.0, abs(normalized))
    if normalized < -0.25:
        return "PUT", min(1.0, abs(normalized))
    return "NEUTRAL", abs(normalized)
