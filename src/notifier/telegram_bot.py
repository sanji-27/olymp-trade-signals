"""Telegram notifier with command handlers and WIN/LOSS reply tracking."""
from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

from src.agents.oracle_agent import FinalSignal


class TelegramNotifier:
    def __init__(self, settings, db, engine_ref=None):
        self.settings = settings
        self.db = db
        self.engine = engine_ref
        self.chat_id = settings.telegram_chat_id
        self.app: Application | None = None
        self._signal_msg_map: dict[int, int] = {}

    async def start(self):
        if not self.settings.telegram_bot_token or not self.chat_id:
            logger.warning("telegram disabled (missing token/chat_id)")
            return
        self.app = Application.builder().token(self.settings.telegram_bot_token).build()
        self.app.add_handler(CommandHandler("status", self._cmd_status))
        self.app.add_handler(CommandHandler("stats",  self._cmd_stats))
        self.app.add_handler(CommandHandler("pause",  self._cmd_pause))
        self.app.add_handler(CommandHandler("resume", self._cmd_resume))
        self.app.add_handler(CommandHandler("risk",   self._cmd_risk))
        self.app.add_handler(MessageHandler(filters.REPLY & filters.TEXT, self._on_reply))
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()
        logger.success("telegram started")

    async def stop(self):
        if self.app:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()

    def attach_engine(self, engine):
        self.engine = engine

    async def send_signal(self, sig: FinalSignal, sig_id: int):
        if not self.app or not self.settings.telegram.send_signals:
            return
        emoji = "[CALL]" if sig.direction == "CALL" else "[PUT]"
        text = (
            f"{emoji} *SIGNAL #{sig_id}*\n"
            f"================\n"
            f"*Asset:* `{sig.asset}`\n"
            f"*Direction:* *{sig.direction}*\n"
            f"*Expiry:* {sig.expiry_minutes} min\n"
            f"*Confidence:* {sig.confidence_pct}%\n"
            f"*Position:* ${sig.position_size_usd:.2f}\n\n"
            f"*Why:*\n" + "\n".join(f"- {r}" for r in sig.reasons[:4]) +
            f"\n\n_Reply WIN or LOSS after expiry._"
        )
        msg = await self.app.bot.send_message(
            chat_id=self.chat_id, text=text, parse_mode=ParseMode.MARKDOWN
        )
        self._signal_msg_map[msg.message_id] = sig_id

    async def send_text(self, text: str):
        if self.app:
            await self.app.bot.send_message(self.chat_id, text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_status(self, update: Update, _):
        connected = self.engine and self.engine.router.is_connected
        paused = self.engine and self.engine._paused
        today = await self.db.get_daily_stats(datetime.now(timezone.utc).date())
        await update.message.reply_text(
            f"*Status*\n"
            f"Connection: {'OK' if connected else 'DOWN'}\n"
            f"Paused: {'YES' if paused else 'NO'}\n"
            f"Signals today: {today.get('signals_count', 0)}\n"
            f"Day P/L: {today.get('daily_pnl_pct', 0):+.2f}%",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def _cmd_stats(self, update: Update, _):
        stats = await self.db.get_weekly_stats()
        await update.message.reply_text(
            f"*Last 7 days*\n"
            f"Signals: {stats['count']}\n"
            f"Wins: {stats['wins']} | Losses: {stats['losses']}\n"
            f"Win rate: {stats['win_rate']:.1f}%\n"
            f"Expectancy: {stats['expectancy']:+.2f}%",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def _cmd_pause(self, update: Update, _):
        if self.engine: self.engine.pause()
        await update.message.reply_text("Signals paused")

    async def _cmd_resume(self, update: Update, _):
        if self.engine: self.engine.resume()
        await update.message.reply_text("Signals resumed")

    async def _cmd_risk(self, update: Update, _):
        ra = self.engine.risk_agent if self.engine else None
        if not ra:
            return
        await update.message.reply_text(
            f"*Risk*\n"
            f"Signals today: {ra._signals_today}/{self.settings.signals.max_signals_per_day}\n"
            f"Day P/L: {ra._daily_pnl_pct:+.2f}%\n"
            f"Consecutive losses: {ra._consecutive_losses}",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def _on_reply(self, update: Update, _):
        replied = update.message.reply_to_message
        if not replied or replied.message_id not in self._signal_msg_map:
            return
        sig_id = self._signal_msg_map[replied.message_id]
        text = update.message.text.strip().upper()
        if text not in ("WIN", "LOSS"):
            return
        won = text == "WIN"
        pnl_pct = (
            self.settings.risk.risk_per_trade_pct * 0.8 if won
            else -self.settings.risk.risk_per_trade_pct
        )
        await self.db.record_outcome(sig_id, won, pnl_pct)
        if self.engine:
            self.engine.risk_agent.update_outcome(won, pnl_pct)
        await update.message.reply_text(f"{'WIN' if won else 'LOSS'} #{sig_id} logged")
