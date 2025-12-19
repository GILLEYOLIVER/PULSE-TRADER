from __future__ import annotations
import asyncio
import random
from datetime import datetime, timezone
from trader_tool.domain.models import Tick

class SimFeed:
    """Feed simulado: random walk + bid/ask sizes para testar imbalance."""
    def __init__(self, symbol: str = "WIN", start_price: float = 100_000.0, tick_size: float = 1.0):
        self.symbol = symbol
        self.price = start_price
        self.tick_size = tick_size

    async def stream(self):
        while True:
            step = random.choice([-3, -2, -1, 0, 1, 2, 3]) * self.tick_size
            self.price = max(self.tick_size, self.price + step)

            vol = random.randint(1, 20)
            bid = self.price - self.tick_size
            ask = self.price + self.tick_size
            bid_size = random.randint(50, 500)
            ask_size = random.randint(50, 500)

            now = datetime.now(timezone.utc)
            yield Tick(
                ts=now, symbol=self.symbol, price=float(self.price), volume=float(vol),
                bid=float(bid), ask=float(ask),
                bid_size=float(bid_size), ask_size=float(ask_size)
            )
            await asyncio.sleep(0.10)
