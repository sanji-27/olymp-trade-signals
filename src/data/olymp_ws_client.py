"""
Olymp Trade WebSocket client (UNOFFICIAL).

Reverse-engineered protocol used by community libs. The exact message schema
changes occasionally; all schema-specific code is isolated to _encode/_decode
so you have one place to patch if Olymp updates their protocol.

Auto-reconnects with exponential backoff. Surfaces ticks as Tick objects.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncIterator

import websockets
from loguru import logger
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from websockets.exceptions import ConnectionClosed, WebSocketException

from src.data.base_provider import DataProvider, Tick
from src.utils.exceptions import AuthenticationError, DataStaleError

OLYMP_WS_URL = "wss://ws.olymptrade.com/cabinet"
HEARTBEAT_INTERVAL = 25.0
STALE_DATA_TIMEOUT = 60.0


class OlympWebSocketClient(DataProvider):
    name = "olymp_ws"

    def __init__(self, ssid: str):
        if not ssid:
            raise ValueError("OLYMP_SSID is required")
        self._ssid = ssid
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._subscribed: set[str] = set()
        self._last_tick_at: float = 0.0
        self._tick_queue: asyncio.Queue[Tick] = asyncio.Queue(maxsize=10_000)
        self._tasks: list[asyncio.Task] = []
        self._stop_event = asyncio.Event()

    @property
    def is_connected(self) -> bool:
        return self._ws is not None and not self._ws.closed

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type((WebSocketException, OSError)),
        reraise=True,
    )
    async def connect(self) -> None:
        logger.info(f"[{self.name}] Connecting to {OLYMP_WS_URL}")
        self._ws = await websockets.connect(
            OLYMP_WS_URL,
            ping_interval=20,
            ping_timeout=20,
            max_size=2**22,
        )
        await self._authenticate()
        self._stop_event.clear()
        self._tasks = [
            asyncio.create_task(self._reader_loop(), name="olymp-reader"),
            asyncio.create_task(self._heartbeat_loop(), name="olymp-heartbeat"),
            asyncio.create_task(self._stale_watchdog(), name="olymp-watchdog"),
        ]
        logger.success(f"[{self.name}] Connected and authenticated")

    async def disconnect(self) -> None:
        logger.info(f"[{self.name}] Disconnecting")
        self._stop_event.set()
        for t in self._tasks:
            t.cancel()
        if self._ws and not self._ws.closed:
            await self._ws.close()
        self._tasks.clear()
        self._ws = None

    async def _authenticate(self) -> None:
        auth_msg = {
            "t": 2,
            "e": 11,
            "uuid": str(int(time.time() * 1000)),
            "d": {"token": self._ssid, "v": 18, "ct": "browser"},
        }
        await self._ws.send(json.dumps(auth_msg))
        try:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=10.0)
        except asyncio.TimeoutError:
            raise AuthenticationError("No auth response within 10s")
        msg = json.loads(raw)
        if msg.get("e") == 11 and msg.get("d", {}).get("isOk") is False:
            raise AuthenticationError(f"Auth rejected: {msg}")
        self._last_tick_at = time.time()

    async def subscribe(self, assets: list[str]) -> None:
        if not self.is_connected:
            raise ConnectionError("Connect before subscribing")
        for asset in assets:
            if asset in self._subscribed:
                continue
            sub_msg = {
                "t": 2,
                "e": 24,
                "uuid": f"sub-{asset}-{int(time.time()*1000)}",
                "d": {"asset": asset, "size": 1},
            }
            await self._ws.send(json.dumps(sub_msg))
            self._subscribed.add(asset)
            logger.debug(f"[{self.name}] subscribed -> {asset}")
            await asyncio.sleep(0.05)

    async def _reader_loop(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                tick = self._decode_tick(msg)
                if tick is not None:
                    self._last_tick_at = time.time()
                    try:
                        self._tick_queue.put_nowait(tick)
                    except asyncio.QueueFull:
                        logger.warning(f"[{self.name}] tick queue full -- dropping")
        except ConnectionClosed as e:
            logger.warning(f"[{self.name}] WS closed: {e}")
        except Exception as e:
            logger.exception(f"[{self.name}] reader crashed: {e}")

    async def _heartbeat_loop(self) -> None:
        while not self._stop_event.is_set():
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            if self._ws and not self._ws.closed:
                try:
                    await self._ws.send(json.dumps({"t": 0}))
                except Exception as e:
                    logger.warning(f"[{self.name}] heartbeat failed: {e}")

    async def _stale_watchdog(self) -> None:
        while not self._stop_event.is_set():
            await asyncio.sleep(10)
            if (
                self._last_tick_at
                and time.time() - self._last_tick_at > STALE_DATA_TIMEOUT
            ):
                logger.error(f"[{self.name}] no tick for {STALE_DATA_TIMEOUT}s -- forcing reconnect")
                if self._ws:
                    await self._ws.close()
                return

    @staticmethod
    def _decode_tick(msg: dict) -> Tick | None:
        """Patch this when Olymp Trade changes their schema."""
        if msg.get("e") != 24:
            return None
        d = msg.get("d") or {}
        asset = d.get("asset") or d.get("p")
        quotes = d.get("quotes") or [d]
        if not asset or not quotes:
            return None
        latest = quotes[-1]
        price = latest.get("price") or latest.get("p")
        ts = latest.get("time") or latest.get("t") or time.time()
        if price is None:
            return None
        return Tick(asset=asset, timestamp=float(ts), price=float(price), source="olymp_ws")

    async def stream(self) -> AsyncIterator[Tick]:
        while not self._stop_event.is_set():
            try:
                tick = await asyncio.wait_for(self._tick_queue.get(), timeout=5.0)
                yield tick
            except asyncio.TimeoutError:
                if (
                    self._last_tick_at
                    and time.time() - self._last_tick_at > STALE_DATA_TIMEOUT
                ):
                    raise DataStaleError(f"No ticks for {STALE_DATA_TIMEOUT}s")
                continue
