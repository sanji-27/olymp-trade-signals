"""
Detects swing highs/lows and clusters them into S/R zones.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema


@dataclass
class Level:
    price: float
    kind: str
    touches: int

    def distance_pct(self, current_price: float) -> float:
        return abs(self.price - current_price) / current_price * 100


def find_levels(
    df: pd.DataFrame,
    order: int = 5,
    cluster_pct: float = 0.15,
    max_levels: int = 6,
) -> list[Level]:
    if len(df) < order * 4:
        return []

    highs = df["high"].values
    lows  = df["low"].values

    high_idx = argrelextrema(highs, np.greater_equal, order=order)[0]
    low_idx  = argrelextrema(lows,  np.less_equal,    order=order)[0]

    swing_highs = highs[high_idx]
    swing_lows  = lows[low_idx]

    resistances = _cluster(swing_highs, cluster_pct, kind="resistance")
    supports    = _cluster(swing_lows,  cluster_pct, kind="support")

    all_levels = sorted(resistances + supports, key=lambda l: l.touches, reverse=True)
    return all_levels[:max_levels]


def _cluster(prices: np.ndarray, threshold_pct: float, kind: str) -> list[Level]:
    if len(prices) == 0:
        return []
    sorted_p = np.sort(prices)
    clusters: list[list[float]] = [[sorted_p[0]]]
    for p in sorted_p[1:]:
        ref = clusters[-1][0]
        if abs(p - ref) / ref * 100 <= threshold_pct:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    return [
        Level(price=float(np.mean(c)), kind=kind, touches=len(c))
        for c in clusters
    ]


def nearest_level(levels: list[Level], price: float) -> Level | None:
    if not levels:
        return None
    return min(levels, key=lambda l: abs(l.price - price))


def is_near_level(levels: list[Level], price: float, threshold_pct: float = 0.1) -> Level | None:
    n = nearest_level(levels, price)
    if n is None:
        return None
    return n if n.distance_pct(price) <= threshold_pct else None
