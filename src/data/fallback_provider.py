"""
Fallback when the Olymp WS is unavailable.
Uses yfinance for forex (free, no key) and Alpha Vantage as a secondary.

Limitations:
  - Polling only (1-minute resolution at best)
  - Cannot serve OTC pairs (those only exist on Olymp)
  - Cannot serve composites (proprietary to Olymp)
"""
from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator

import yfinance as yf
from loguru import logger

from src.data.base_provider import DataProvider, Tick

POLL_SECONDS = 30.0
UNSUPPORTED_SUFFIXES = ("_OTC",)
UNSUPPORTED_SYMBOLS = {"ASIA_COMPOSITE", "COMMODITY_COMPOSITE", "CRYPTO_COMPOSITE"}


class FallbackProvider(DataProvider):
    name = "fallback_yf"

    def __init__(self, alpha_vantage_key: str = ""):
        self._av_key = alpha_vantage_key
        self._assets: list[str] = []
        self._connected = False
        self._stop_event = asyncio.Event()
        self._tick_queue: asyncio.Queue[Tick] = asyncio.Queue(maxsize=1000)
        self._poller_task: asyncio.Task | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True
        self._stop_event.clear()
        logger.info(f"[{self.name}] ready (polling every {POLL_SECONDS}s)")

    async def disconnect(self) -> None:
        self._stop_event.set()
        if self._poller_task:
            self._poller_task.cancel()
        self._connected = False

    async def subscribe(self, assets: list[str]) -> None:
        supported = []
        for a in assets:
            if a in UNSUPPORTED_SYMBOLS or any(a.endswith(s) for s in UNSUPPORTED_SUFFIXES):
                logger.warning(f"[{self.name}] cannot serve {a} -- skipped")
                continue
            supported.append(a)
        self._assets = supported
        if self._poller_task is None or self._poller_task.done():
            self._poller_task = asyncio.create_task(self._poll_loop(), name="fallback-poller")

    async def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            for asset in self._assets:
                try:
                    price = await asyncio.to_thread(self._fetch_price, asset)
                    if price is not None:
                        tick = Tick(
                            asset=asset,
                            timestamp=time.time(),
                            price=price,
                            source=self.name,
                        )
                        try:
                            self._tick_queue.put_nowait(tick)
                        except asyncio.QueueFull:
                            pass
                except Exception as e:
                    logger.warning(f"[{self.name}] {asset} fetch failed: {e}")
            await asyncio.sleep(POLL_SECONDS)

    @staticmethod
    def _fetch_price(asset: str) -> float | None:
        symbol = asset if "=" in asset else f"{asset}=X"
        try:
            data = yf.Ticker(symbol).history(period="1d", interval="1m")
            if data.empty:
                return None
            return float(data["Close"].iloc[-1])
        except Exception:
            return None

    async def stream(self) -> AsyncIterator[Tick]:
        while not self._stop_event.is_set():
            try:
                tick = await asyncio.wait_for(self._tick_queue.get(), timeout=10.0)
                yield tick
            except asyncio.TimeoutError:
                continue
