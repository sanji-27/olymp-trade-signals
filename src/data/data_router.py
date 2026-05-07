"""
Single entry point for market data.
Tries Olymp WS first; if it fails or auth is missing, falls back to yfinance.
Yields normalized Ticks regardless of source.
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

from loguru import logger

from src.data.base_provider import DataProvider, Tick
from src.data.fallback_provider import FallbackProvider
from src.data.olymp_ws_client import OlympWebSocketClient
from src.utils.exceptions import AuthenticationError, DataStaleError


class DataRouter(DataProvider):
    name = "router"

    def __init__(self, ssid: str, alpha_vantage_key: str = ""):
        self._ssid = ssid
        self._av_key = alpha_vantage_key
        self._assets: list[str] = []
        self._active: DataProvider | None = None
        self._stop_event = asyncio.Event()

    @property
    def is_connected(self) -> bool:
        return self._active is not None and self._active.is_connected

    async def connect(self) -> None:
        if self._ssid:
            try:
                primary = OlympWebSocketClient(self._ssid)
                await primary.connect()
                self._active = primary
                logger.success("[router] using Olymp WS (primary)")
                return
            except (AuthenticationError, ConnectionError, OSError) as e:
                logger.warning(f"[router] primary failed: {e} -- switching to fallback")

        fallback = FallbackProvider(self._av_key)
        await fallback.connect()
        self._active = fallback
        logger.warning("[router] using FALLBACK provider -- degraded mode")

    async def disconnect(self) -> None:
        self._stop_event.set()
        if self._active:
            await self._active.disconnect()

    async def subscribe(self, assets: list[str]) -> None:
        self._assets = assets
        if self._active:
            await self._active.subscribe(assets)

    async def stream(self) -> AsyncIterator[Tick]:
        while not self._stop_event.is_set():
            if not self._active:
                await self.connect()
                await self.subscribe(self._assets)
            try:
                async for tick in self._active.stream():
                    yield tick
            except DataStaleError as e:
                logger.warning(f"[router] {e} -- reconnecting active")
                await self._active.disconnect()
                self._active = None
            except Exception as e:
                logger.exception(f"[router] stream error: {e}")
                if self._active:
                    await self._active.disconnect()
                self._active = None
                await asyncio.sleep(5)
