from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from trader_tool.domain.models import Signal, ApprovedTrade, Side, RiskLimits

@dataclass
class RiskState:
    day: date
    pnl_today: float = 0.0
    stops_in_row: int = 0
    cooldown_until: datetime | None = None

class RiskManager:
    """Aplica regras: risco por trade, max loss diário, cooldown por sequência."""
    def __init__(self, limits: RiskLimits):
        self.limits = limits
        self.state = RiskState(day=date.today())

    def _roll_day(self, now: datetime):
        if now.date() != self.state.day:
            self.state = RiskState(day=now.date())

    def update_pnl(self, now: datetime, realized_pnl: float, was_stop: bool = False):
        self._roll_day(now)
        self.state.pnl_today += realized_pnl
        if was_stop:
            self.state.stops_in_row += 1
            if self.state.stops_in_row >= self.limits.max_stops_in_row:
                self.state.cooldown_until = now + timedelta(minutes=self.limits.cooldown_minutes)
        else:
            # qualquer gain zera sequência
            if realized_pnl > 0:
                self.state.stops_in_row = 0

    def approve(self, signal: Signal, last_price: float, atr: float) -> ApprovedTrade | None:
        now = signal.ts
        self._roll_day(now)

        # só aprova BUY/SELL
        if signal.side in (Side.WAIT,):
            return None

        # cooldown
        if self.state.cooldown_until and now < self.state.cooldown_until:
            return None

        # max loss diário (negativo)
        max_daily_loss = - (self.limits.capital * (self.limits.max_daily_loss_pct / 100.0))
        if self.state.pnl_today <= max_daily_loss:
            return None

        # Stop técnico: baseado em ATR (mínimo 1 tick)
        stop_dist = max(self.limits.tick_size, atr * 0.8)
        if signal.side == Side.BUY:
            stop_price = last_price - stop_dist
            target_price = last_price + stop_dist * 1.2
        else:
            stop_price = last_price + stop_dist
            target_price = last_price - stop_dist * 1.2

        # risco por contrato = distância do stop * tick_value
        risk_per_contract = abs(last_price - stop_price) * self.limits.tick_value
        if risk_per_contract <= 0:
            return None

        risk_amount = self.limits.capital * (self.limits.risk_per_trade_pct / 100.0)

        contracts = int(risk_amount // risk_per_contract)
        contracts = max(0, min(contracts, self.limits.max_contracts))

        # se não dá 1 contrato, WAIT
        if contracts < 1:
            return None

        return ApprovedTrade(
            ts=now,
            symbol=signal.symbol,
            side=signal.side,
            contracts=contracts,
            entry_hint=last_price,
            stop_price=stop_price,
            target_price=target_price,
            risk_amount=risk_amount,
            rationale=signal.rationale,
            meta={"confidence": signal.confidence, **(signal.meta or {})}
        )
