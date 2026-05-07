"""
Candlestick patterns. Returns dict of pattern_name -> direction ("bull"/"bear"/"neutral").
Only checks the last 1-3 bars (live signal generation, not historical scanning).
"""
from __future__ import annotations

import pandas as pd


def _body(c: pd.Series) -> float: return abs(c["close"] - c["open"])
def _range(c: pd.Series) -> float: return c["high"] - c["low"]
def _is_bull(c: pd.Series) -> bool: return c["close"] > c["open"]
def _is_bear(c: pd.Series) -> bool: return c["close"] < c["open"]


def detect_patterns(df: pd.DataFrame) -> dict[str, str]:
    out: dict[str, str] = {}
    if len(df) < 3:
        return out

    c0 = df.iloc[-1]
    c1 = df.iloc[-2]
    c2 = df.iloc[-3]

    # Engulfing
    if _is_bull(c0) and _is_bear(c1):
        if c0["close"] > c1["open"] and c0["open"] < c1["close"]:
            out["bullish_engulfing"] = "bull"
    if _is_bear(c0) and _is_bull(c1):
        if c0["close"] < c1["open"] and c0["open"] > c1["close"]:
            out["bearish_engulfing"] = "bear"

    # Pin bars
    rng = _range(c0)
    if rng > 0:
        body = _body(c0)
        upper_wick = c0["high"] - max(c0["open"], c0["close"])
        lower_wick = min(c0["open"], c0["close"]) - c0["low"]
        if body / rng < 0.35 and lower_wick > 2 * body and upper_wick < body:
            out["hammer"] = "bull"
        if body / rng < 0.35 and upper_wick > 2 * body and lower_wick < body:
            out["shooting_star"] = "bear"

    # Doji
    if rng > 0 and _body(c0) / rng < 0.1:
        out["doji"] = "neutral"

    # Inside bar
    if c0["high"] < c1["high"] and c0["low"] > c1["low"]:
        out["inside_bar"] = "neutral"

    # Three white soldiers / black crows
    if (
        _is_bull(c0) and _is_bull(c1) and _is_bull(c2)
        and c0["close"] > c1["close"] > c2["close"]
        and c0["open"] > c1["open"] > c2["open"]
    ):
        out["three_white_soldiers"] = "bull"
    if (
        _is_bear(c0) and _is_bear(c1) and _is_bear(c2)
        and c0["close"] < c1["close"] < c2["close"]
        and c0["open"] < c1["open"] < c2["open"]
    ):
        out["three_black_crows"] = "bear"

    return out
