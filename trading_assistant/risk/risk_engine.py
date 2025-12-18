from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from trading_assistant.config import RiskConfig
from trading_assistant.core.models import OrderRequest, Signal
from trading_assistant.core.state import MarketState, RiskState


class RiskEngine:
    def __init__(self, config: RiskConfig) -> None:
        self.config = config

    def _reset_if_new_day(self, risk_state: RiskState) -> None:
        now = datetime.now(timezone.utc)
        if now.date() != risk_state.day_start.date():
            risk_state.day_start = now
            risk_state.trades_today = 0
            risk_state.pnl_today = 0.0

    def daily_limits_ok(self, risk_state: RiskState) -> bool:
        self._reset_if_new_day(risk_state)
        if risk_state.trades_today >= int(self.config.max_trades_per_day):
            return False
        max_loss_money = abs(float(self.config.max_daily_loss)) * float(self.config.capital)
        if float(risk_state.pnl_today) <= -max_loss_money:
            return False
        return True

    def size_position(self, signal: Signal, state: MarketState, risk_state: RiskState) -> Optional[OrderRequest]:
        if signal.side not in ("BUY", "SELL"):
            return None
        if not self.daily_limits_ok(risk_state):
            return None

        price = float(signal.price)
        stop_dist = abs(price - float(signal.sl))
        if stop_dist <= 0:
            return None

        risk_money = float(self.config.capital) * float(self.config.risk_per_trade)
        qty = risk_money / stop_dist
        if qty <= 0:
            return None

        risk_state.trades_today += 1

        return OrderRequest(
            symbol=signal.symbol,
            side=signal.side,
            qty=float(max(1.0, qty)),
            price=float(signal.price),
            sl=float(signal.sl),
            tp=float(signal.tp),
            ts=signal.ts,
            confidence=float(signal.confidence),
            reason=signal.reason,
        )
