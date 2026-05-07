"""
Loads config.yaml and .env into a single typed Settings object.
Use:  from config.settings import settings
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class AccountConfig(BaseModel):
    balance_usd: float
    currency: str = "USD"


class AssetsConfig(BaseModel):
    forex: list[str] = Field(default_factory=list)
    composites: list[str] = Field(default_factory=list)
    otc: list[str] = Field(default_factory=list)

    @property
    def all(self) -> list[str]:
        return self.forex + self.composites + self.otc


class TimeframesConfig(BaseModel):
    expiries_minutes: list[int]
    context_tfs: list[int]


class RiskConfig(BaseModel):
    risk_per_trade_pct: float
    max_daily_drawdown_pct: float
    consecutive_loss_limit: int
    asset_cooldown_minutes: int
    blackout_hours_utc: list[int]
    news_blackout_minutes: int


class SignalsConfig(BaseModel):
    min_confidence_pct: float
    max_signals_per_day: int
    warmup_bars: int


class IndicatorsConfig(BaseModel):
    ema_periods: list[int]
    rsi_period: int
    rsi_oversold: float
    rsi_overbought: float
    macd_fast: int
    macd_slow: int
    macd_signal: int
    bb_period: int
    bb_std: float
    stoch_k: int
    stoch_d: int
    stoch_smooth: int
    atr_period: int
    adx_period: int
    adx_trending_threshold: float


class RegimeConfig(BaseModel):
    trending_adx_min: float
    ranging_bb_width_max: float
    volatile_atr_multiplier: float


class NewsConfig(BaseModel):
    rss_feeds: list[str]
    high_impact_keywords: list[str]


class OracleConfig(BaseModel):
    weights: dict[str, float]
    risk_veto: bool

    @field_validator("weights")
    @classmethod
    def weights_sum_to_one(cls, v: dict[str, float]) -> dict[str, float]:
        total = sum(v.values())
        if not 0.99 <= total <= 1.01:
            raise ValueError(f"Oracle weights must sum to 1.0, got {total}")
        return v


class TelegramConfig(BaseModel):
    send_signals: bool
    send_status_updates: bool
    weekly_report_day: str
    weekly_report_hour_utc: int


class LoggingConfig(BaseModel):
    level: str = "INFO"
    rotation_mb: int = 50
    retention_days: int = 30


class DatabaseConfig(BaseModel):
    path: str


class Settings(BaseModel):
    account: AccountConfig
    assets: AssetsConfig
    timeframes: TimeframesConfig
    risk: RiskConfig
    signals: SignalsConfig
    indicators: IndicatorsConfig
    regime: RegimeConfig
    news: NewsConfig
    oracle: OracleConfig
    telegram: TelegramConfig
    logging: LoggingConfig
    database: DatabaseConfig

    olymp_ssid: str = Field(default="", repr=False)
    telegram_bot_token: str = Field(default="", repr=False)
    telegram_chat_id: str = Field(default="", repr=False)
    alpha_vantage_key: str = Field(default="", repr=False)
    openai_api_key: str = Field(default="", repr=False)

    @classmethod
    def load(cls, yaml_path: Path | None = None) -> "Settings":
        yaml_path = yaml_path or (PROJECT_ROOT / "config" / "config.yaml")
        with open(yaml_path, "r", encoding="utf-8") as f:
            raw: dict[str, Any] = yaml.safe_load(f)

        return cls(
            **raw,
            olymp_ssid=os.getenv("OLYMP_SSID", ""),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            alpha_vantage_key=os.getenv("ALPHA_VANTAGE_KEY", ""),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        )

    def validate_runtime(self) -> list[str]:
        warnings = []
        if not self.olymp_ssid:
            warnings.append("OLYMP_SSID empty -> primary WS disabled, fallback only")
        if not self.telegram_bot_token or not self.telegram_chat_id:
            warnings.append("Telegram creds missing -> signals will only be logged")
        if not self.alpha_vantage_key and not self.olymp_ssid:
            warnings.append("No data source! Set OLYMP_SSID or ALPHA_VANTAGE_KEY")
        return warnings


settings = Settings.load()
