"""
Tick -> OHLCV converter for multiple timeframes simultaneously.
Each asset/TF pair has its own rolling DataFrame capped at MAX_BARS rows.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

import pandas as pd
from loguru import logger

from src.data.base_provider import Tick

MAX_BARS = 500


class CandleBuilder:
    def __init__(self, timeframes_minutes: list[int]):
        self.tfs = sorted(set(timeframes_minutes))
        self._candles: dict[str, dict[int, pd.DataFrame]] = defaultdict(
            lambda: {tf: self._empty_df() for tf in self.tfs}
        )
        self._building: dict[str, dict[int, dict | None]] = defaultdict(
            lambda: {tf: None for tf in self.tfs}
        )

    @staticmethod
    def _empty_df() -> pd.DataFrame:
        return pd.DataFrame(
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        ).astype({
            "timestamp": "datetime64[ns, UTC]",
            "open": "float64", "high": "float64",
            "low": "float64", "close": "float64",
            "volume": "int64",
        })

    @staticmethod
    def _bar_start(ts: float, tf_minutes: int) -> datetime:
        epoch_min = int(ts // 60)
        floored_min = epoch_min - (epoch_min % tf_minutes)
        return datetime.fromtimestamp(floored_min * 60, tz=timezone.utc)

    def add_tick(self, tick: Tick) -> list[tuple[str, int]]:
        closed: list[tuple[str, int]] = []
        for tf in self.tfs:
            bar_start = self._bar_start(tick.timestamp, tf)
            current = self._building[tick.asset][tf]

            if current is None:
                self._building[tick.asset][tf] = self._new_bar(bar_start, tick.price)
            elif current["timestamp"] == bar_start:
                current["high"] = max(current["high"], tick.price)
                current["low"]  = min(current["low"], tick.price)
                current["close"] = tick.price
                current["volume"] += 1
            else:
                self._commit(tick.asset, tf, current)
                closed.append((tick.asset, tf))
                self._building[tick.asset][tf] = self._new_bar(bar_start, tick.price)

        return closed

    @staticmethod
    def _new_bar(start: datetime, price: float) -> dict:
        return {
            "timestamp": start,
            "open": price, "high": price,
            "low": price, "close": price,
            "volume": 1,
        }

    def _commit(self, asset: str, tf: int, bar: dict) -> None:
        df = self._candles[asset][tf]
        new_row = pd.DataFrame([bar])
        df = pd.concat([df, new_row], ignore_index=True)
        if len(df) > MAX_BARS:
            df = df.iloc[-MAX_BARS:].reset_index(drop=True)
        self._candles[asset][tf] = df
        logger.trace(f"closed {asset} {tf}m @ {bar['close']}")

    def get_candles(self, asset: str, tf_minutes: int) -> pd.DataFrame:
        return self._candles[asset][tf_minutes].copy()

    def is_warmed_up(self, asset: str, tf_minutes: int, min_bars: int) -> bool:
        return len(self._candles[asset][tf_minutes]) >= min_bars
