from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from random import random
from typing import Optional

from trading_assistant.config import ExecutionConfig
from trading_assistant.core.models import ExecutionReport, OrderRequest
from trading_assistant.core.state import MarketState


class OrderRouter:
    def __init__(self, config: ExecutionConfig) -> None:
        self.config = config

    async def execute(self, order: OrderRequest, state: MarketState) -> ExecutionReport:
        # paper fill com slippage simples
        ref = float(order.price)
        slip = (float(self.config.slippage_bps) / 10000.0) * ref
        # aleatório dentro da banda
        fill = ref + slip * (1 if order.side == "BUY" else -1) * (0.5 + random() * 0.5)

        return ExecutionReport(
            symbol=order.symbol,
            side=order.side,
            qty=float(order.qty),
            status="FILLED" if self.config.mode == "paper" else "QUEUED",
            filled_price=float(fill),
            ts=datetime.utcnow(),
            mode=self.config.mode,
            reason=order.reason,
            raw={"order": asdict(order)},
        )
