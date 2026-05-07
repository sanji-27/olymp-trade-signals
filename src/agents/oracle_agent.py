"""
The decision-maker. Combines all agent reports into one final signal verdict.
"""
from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from src.agents.base_agent import AgentReport


@dataclass
class FinalSignal:
    asset: str
    direction: str
    expiry_minutes: int
    confidence_pct: float
    reasons: list[str]
    position_size_usd: float
    metadata: dict


class OracleAgent:
    name = "oracle"

    def __init__(self, settings):
        self.settings = settings
        self.weights = settings.oracle.weights

    def decide(
        self,
        asset: str,
        expiry_minutes: int,
        reports: dict[str, AgentReport],
    ) -> FinalSignal | None:
        risk_report = reports.get("risk")
        if risk_report and risk_report.veto:
            logger.info(f"[oracle] {asset} {expiry_minutes}m vetoed by RISK: {risk_report.reasons}")
            return None

        for name, rep in reports.items():
            if rep.veto and (self.settings.oracle.risk_veto or name == "risk"):
                logger.info(f"[oracle] {asset} {expiry_minutes}m vetoed by {name}: {rep.reasons}")
                return None

        tech = reports.get("technical")
        if tech is None or tech.direction == "NEUTRAL":
            return None

        direction = tech.direction
        sent = reports.get("sentiment")
        if sent and sent.direction != "NEUTRAL" and sent.direction != direction:
            sentiment_alignment = -1.0
        elif sent and sent.direction == direction:
            sentiment_alignment = 1.0
        else:
            sentiment_alignment = 0.0

        mtf_alignment = tech.metadata.get("alignment_ratio", 0.0)

        regime = reports.get("regime")
        regime_conf = regime.confidence if regime else 0.5
        sent_conf   = sent.confidence if sent else 0.5

        weighted = (
            self.weights["technical"]            * tech.confidence
            + self.weights["regime"]             * regime_conf
            + self.weights["sentiment"]          * (sent_conf if sentiment_alignment >= 0 else (1 - sent_conf))
            + self.weights["multi_tf_alignment"] * mtf_alignment
        )

        if sentiment_alignment < 0:
            weighted *= 0.85

        confidence_pct = round(weighted * 100, 1)

        if confidence_pct < self.settings.signals.min_confidence_pct:
            logger.debug(
                f"[oracle] {asset} {expiry_minutes}m -> {direction} {confidence_pct}% "
                f"below threshold {self.settings.signals.min_confidence_pct}%"
            )
            return None

        reasons = []
        if tech.reasons:
            reasons.extend(tech.reasons[:2])
        if regime and regime.metadata.get("regime"):
            reasons.append(f"regime: {regime.metadata['regime']}")
        if sent and sentiment_alignment != 0:
            reasons.append(sent.reasons[0] if sent.reasons else "sentiment checked")
        if risk_report:
            reasons.append(risk_report.reasons[-1])

        position_size = (
            risk_report.metadata.get("position_size_usd", 0.0)
            if risk_report else 0.0
        )

        return FinalSignal(
            asset=asset,
            direction=direction,
            expiry_minutes=expiry_minutes,
            confidence_pct=confidence_pct,
            reasons=reasons,
            position_size_usd=position_size,
            metadata={
                "tech_confidence": tech.confidence,
                "regime_confidence": regime_conf,
                "sentiment_alignment": sentiment_alignment,
                "mtf_alignment": mtf_alignment,
            },
        )
