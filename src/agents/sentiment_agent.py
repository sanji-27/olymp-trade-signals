"""
Lightweight news sentiment + high-impact event detection.
Pulls RSS feeds (no API key needed) and flags blackout windows.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from time import mktime

import feedparser
from loguru import logger

from src.agents.base_agent import AgentReport, BaseAgent, MarketContext

CACHE_TTL_SECONDS = 300


@dataclass
class NewsItem:
    title: str
    summary: str
    published: datetime
    feed: str


class SentimentAgent(BaseAgent):
    name = "sentiment"

    def __init__(self, settings):
        super().__init__(settings)
        self._cache: list[NewsItem] = []
        self._cache_ts: float = 0.0
        self._lock = asyncio.Lock()

    async def _evaluate(self, ctx: MarketContext) -> AgentReport:
        items = await self._get_news()
        if not items:
            return AgentReport(
                agent=self.name,
                direction="NEUTRAL",
                confidence=0.5,
                reasons=["no news feeds available -- neutral"],
            )

        relevant = self._filter_relevant(items, ctx.asset)

        now = datetime.now(timezone.utc)
        blackout_min = self.settings.risk.news_blackout_minutes
        blackout_hits = []
        for item in relevant:
            mins_to_event = (item.published - now).total_seconds() / 60
            if -blackout_min <= mins_to_event <= blackout_min:
                if self._is_high_impact(item):
                    blackout_hits.append(item)

        if blackout_hits:
            return AgentReport(
                agent=self.name,
                direction="NEUTRAL",
                confidence=0.0,
                veto=True,
                reasons=[f"high-impact news blackout: {blackout_hits[0].title[:80]}"],
                metadata={"blackout_count": len(blackout_hits)},
            )

        score = self._score_sentiment(relevant, ctx.asset)
        if score > 0.15:
            direction, confidence = "CALL", min(1.0, 0.5 + abs(score))
            reasons = [f"news leans bullish (score {score:+.2f})"]
        elif score < -0.15:
            direction, confidence = "PUT", min(1.0, 0.5 + abs(score))
            reasons = [f"news leans bearish (score {score:+.2f})"]
        else:
            direction, confidence = "NEUTRAL", 0.5
            reasons = [f"news neutral (score {score:+.2f})"]

        if relevant:
            reasons.append(f"checked {len(relevant)} relevant items")

        return AgentReport(
            agent=self.name,
            direction=direction,
            confidence=confidence,
            reasons=reasons,
            metadata={"sentiment_score": score, "items_checked": len(relevant)},
        )

    async def _get_news(self) -> list[NewsItem]:
        async with self._lock:
            now = datetime.now(timezone.utc).timestamp()
            if now - self._cache_ts < CACHE_TTL_SECONDS and self._cache:
                return self._cache
            self._cache = await asyncio.to_thread(self._fetch_all_feeds)
            self._cache_ts = now
            return self._cache

    def _fetch_all_feeds(self) -> list[NewsItem]:
        items: list[NewsItem] = []
        for url in self.settings.news.rss_feeds:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:30]:
                    pub = entry.get("published_parsed") or entry.get("updated_parsed")
                    pub_dt = (
                        datetime.fromtimestamp(mktime(pub), tz=timezone.utc)
                        if pub else datetime.now(timezone.utc)
                    )
                    items.append(NewsItem(
                        title=entry.get("title", ""),
                        summary=entry.get("summary", ""),
                        published=pub_dt,
                        feed=url,
                    ))
            except Exception as e:
                logger.warning(f"[{self.name}] feed {url} failed: {e}")
        return items

    @staticmethod
    def _filter_relevant(items: list[NewsItem], asset: str) -> list[NewsItem]:
        if "_" in asset:
            tokens = [asset.split("_")[0]]
        elif len(asset) == 6:
            tokens = [asset[:3], asset[3:]]
        else:
            tokens = [asset]
        regex = re.compile("|".join(tokens), re.IGNORECASE)
        return [i for i in items if regex.search(i.title + " " + i.summary)]

    def _is_high_impact(self, item: NewsItem) -> bool:
        text = (item.title + " " + item.summary).lower()
        return any(kw.lower() in text for kw in self.settings.news.high_impact_keywords)

    @staticmethod
    def _score_sentiment(items: list[NewsItem], asset: str) -> float:
        if not items:
            return 0.0
        bull_words = {"surge", "rally", "gains", "rises", "strong", "bullish", "boost",
                      "beats", "upgrade", "positive", "growth", "soars", "jumps"}
        bear_words = {"falls", "drops", "tumbles", "weak", "bearish", "decline",
                      "miss", "downgrade", "negative", "slumps", "plunges", "fears"}
        score = 0.0
        for item in items:
            text = (item.title + " " + item.summary).lower()
            score += sum(1 for w in bull_words if w in text)
            score -= sum(1 for w in bear_words if w in text)
        normalized = score / (len(items) * 3)
        return max(-1.0, min(1.0, normalized))
