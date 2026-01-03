from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from trading_assistant.config import RiskConfig
from trading_assistant.core.models import OrderRequest, Signal
from trading_assistant.core.state import MarketState, RiskState


class RiskEngine:
    """
    Gestão de risco avançada (compatível com o pipeline atual).

    Mantém a assinatura original:
      RiskEngine(config.risk)
      size_position(signal, state, risk_state) -> Optional[OrderRequest]

    Upgrades:
    - position sizing adaptativo por ATR/volatilidade (atr vem do Signal.meta quando existir)
    - reduz tamanho quando news_impact está alto
    - reduz tamanho quando spread está alto (se o state tiver spread)
    """

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
        if price <= 0:
            return None

        # stop distance
        sl = float(signal.sl)
        stop_dist = abs(price - sl)

        # ATR/vol (se tiver no meta)
        atr = float(signal.meta.get("atr", 0.0) or 0.0) if hasattr(signal, "meta") else 0.0
        if atr <= 0:
            atr = max(price * 0.002, 1.0)

        # garante stop mínimo coerente
        stop_dist = max(stop_dist, atr * 0.75, price * 0.001)
        if stop_dist <= 0:
            return None

        # risco em dinheiro
        risk_money = float(self.config.capital) * float(self.config.risk_per_trade)
        if risk_money <= 0:
            return None

        base_qty = risk_money / stop_dist
        if base_qty <= 0:
            return None

        # ajustes adaptativos
        conf = float(getattr(signal, "confidence", 0.6) or 0.6)
        news = float(state.news_impact.get(signal.symbol, 0.0) or 0.0)
        spread = float(state.spreads.get(signal.symbol, 0.0) or 0.0)

        # fatores (clamp)
        conf_factor = 0.60 + min(0.80, max(0.0, conf))          # 0.60..1.40
        news_factor = 1.0 - min(0.60, max(0.0, news) * 0.18)    # 1.00..0.40  (news 0..3.5 aprox)
        spread_factor = 1.0 - min(0.50, max(0.0, spread) * 6.0) # 1.00..0.50

        qty = base_qty * conf_factor * news_factor * spread_factor

        # limites finais (mantém o "mínimo 1" do seu projeto)
        qty = float(max(1.0, qty))

        # contabiliza trade no dia (como o seu original)
        risk_state.trades_today += 1

        # motivo detalhado (vai para auditoria / logs)
        reason = (
            f"{signal.reason} | qty_base={base_qty:.2f} "
            f"| conf={conf:.2f}(x{conf_factor:.2f}) news={news:.2f}(x{news_factor:.2f}) "
            f"spread={spread:.4f}(x{spread_factor:.2f}) atr={atr:.4f} stop_dist={stop_dist:.4f}"
        )

        return OrderRequest(
            symbol=signal.symbol,
            side=signal.side,
            qty=float(qty),
            price=float(signal.price),
            sl=float(signal.sl),
            tp=float(signal.tp),
            ts=signal.ts,
            confidence=float(signal.confidence),
            reason=reason,
        )
