"""
Base class for all reasoning agents.
Each agent receives a MarketContext and returns an AgentReport.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from loguru import logger


@dataclass
class MarketContext:
    asset: str
    primary_tf: int
    candles: dict[int, pd.DataFrame]
    current_price: float
    timestamp: datetime
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentReport:
    agent: str
    direction: str = "NEUTRAL"
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)
    veto: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class BaseAgent(ABC):
    name: str = "base"

    def __init__(self, settings):
        self.settings = settings

    async def evaluate(self, ctx: MarketContext) -> AgentReport:
        try:
            return await self._evaluate(ctx)
        except Exception as e:
            logger.exception(f"[{self.name}] crashed on {ctx.asset} {ctx.primary_tf}m: {e}")
            return AgentReport(
                agent=self.name,
                direction="NEUTRAL",
                confidence=0.0,
                reasons=[f"agent error: {type(e).__name__}"],
                veto=False,
            )

    @abstractmethod
    async def _evaluate(self, ctx: MarketContext) -> AgentReport: ...
