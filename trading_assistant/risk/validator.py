from __future__ import annotations

from trading_assistant.config import ValidatorConfig
from trading_assistant.core.models import OrderRequest
from trading_assistant.core.state import MarketState, RiskState


class TradeValidator:
    def __init__(self, config: ValidatorConfig) -> None:
        self.config = config

    def is_trade_allowed(self, order: OrderRequest, state: MarketState, risk_state: RiskState) -> bool:
        spread = float(state.spreads.get(order.symbol, 0.0))
        if spread > float(self.config.max_spread):
            return False

        news_impact = float(state.news_impact.get(order.symbol, 0.0))
        if news_impact >= float(self.config.max_news_impact):
            return False

        return True
