"""Main async loop: data -> agents -> oracle -> notifier."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from loguru import logger

from src.agents.base_agent import MarketContext
from src.agents.data_agent import DataAgent
from src.agents.oracle_agent import OracleAgent, FinalSignal
from src.agents.regime_agent import RegimeAgent
from src.agents.risk_agent import RiskAgent
from src.agents.sentiment_agent import SentimentAgent
from src.agents.technical_agent import TechnicalAgent
from src.data.candle_builder import CandleBuilder
from src.data.data_router import DataRouter


class SignalEngine:
    def __init__(self, settings, db, notifier):
        self.settings = settings
        self.db = db
        self.notifier = notifier

        self.router = DataRouter(settings.olymp_ssid, settings.alpha_vantage_key)
        self.builder = CandleBuilder(
            timeframes_minutes=sorted(set(
                settings.timeframes.expiries_minutes + settings.timeframes.context_tfs
            ))
        )
        self.data_agent      = DataAgent(settings)
        self.technical_agent = TechnicalAgent(settings)
        self.regime_agent    = RegimeAgent(settings)
        self.sentiment_agent = SentimentAgent(settings)
        self.risk_agent      = RiskAgent(settings, db)
        self.oracle          = OracleAgent(settings)

        self._paused = False
        self._stop = asyncio.Event()
        self._eval_lock = asyncio.Lock()

    def pause(self):  self._paused = True
    def resume(self): self._paused = False

    async def start(self):
        await self.router.connect()
        await self.router.subscribe(self.settings.assets.all)
        logger.success("engine started")

        async for tick in self.router.stream():
            if self._stop.is_set():
                break
            closed = self.builder.add_tick(tick)
            for asset, tf in closed:
                if tf in self.settings.timeframes.expiries_minutes:
                    asyncio.create_task(self._evaluate(asset, tf, tick.price))

    async def stop(self):
        self._stop.set()
        await self.router.disconnect()

    async def _evaluate(self, asset: str, tf: int, price: float):
        if self._paused:
            return
        async with self._eval_lock:
            try:
                candles = {}
                needed = set(self.settings.timeframes.expiries_minutes
                             + self.settings.timeframes.context_tfs)
                for t in needed:
                    df = self.builder.get_candles(asset, t)
                    if not df.empty:
                        candles[t] = df

                ctx = MarketContext(
                    asset=asset,
                    primary_tf=tf,
                    candles=candles,
                    current_price=price,
                    timestamp=datetime.now(timezone.utc),
                )

                data_rep = await self.data_agent.evaluate(ctx)
                if data_rep.veto:
                    return

                tech_rep, regime_rep, sent_rep, risk_rep = await asyncio.gather(
                    self.technical_agent.evaluate(ctx),
                    self.regime_agent.evaluate(ctx),
                    self.sentiment_agent.evaluate(ctx),
                    self.risk_agent.evaluate(ctx),
                )

                reports = {
                    "data": data_rep,
                    "technical": tech_rep,
                    "regime": regime_rep,
                    "sentiment": sent_rep,
                    "risk": risk_rep,
                }
                signal = self.oracle.decide(asset, tf, reports)
                if signal:
                    await self._dispatch(signal, reports)
            except Exception as e:
                logger.exception(f"evaluate {asset} {tf}m failed: {e}")

    async def _dispatch(self, sig: FinalSignal, reports: dict):
        sig_id = await self.db.save_signal(sig, reports)
        self.risk_agent.mark_signal_sent(sig.asset)
        await self.notifier.send_signal(sig, sig_id)
        logger.success(f"SIGNAL #{sig_id} {sig.asset} {sig.direction} {sig.expiry_minutes}m {sig.confidence_pct}%")
