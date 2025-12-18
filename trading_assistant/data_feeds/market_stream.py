from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from random import random
from threading import Event
from typing import AsyncIterator, Dict, Optional

from trading_assistant.config import MarketFeedConfig
from trading_assistant.core.models import Candle


@dataclass
class MockMarketConnector:
    config: MarketFeedConfig

    async def stream_candles(self, stop_event: Optional[Event] = None) -> AsyncIterator[Candle]:
        prices: Dict[str, float] = {s: 100.0 + random() * 10.0 for s in self.config.symbols}

        while True:
            if stop_event and stop_event.is_set():
                return

            for symbol in self.config.symbols:
                if stop_event and stop_event.is_set():
                    return

                last = prices[symbol]
                change = (random() - 0.5) * 0.6
                close = max(0.01, last + change)
                high = max(last, close) + random() * 0.2
                low = min(last, close) - random() * 0.2
                open_ = last
                vol = 100 + random() * 50
                prices[symbol] = close

                yield Candle(
                    symbol=symbol,
                    ts=datetime.now(timezone.utc),
                    open=float(open_),
                    high=float(high),
                    low=float(low),
                    close=float(close),
                    volume=float(vol),
                )

            await _sleep_interruptible(self.config.timeframe_seconds, stop_event=stop_event)


async def _sleep_interruptible(seconds: int, stop_event: Optional[Event] = None) -> None:
    import asyncio
    total = max(1, int(seconds))
    step = 0.1
    slices = int(total / step)
    for _ in range(max(1, slices)):
        if stop_event and stop_event.is_set():
            return
        await asyncio.sleep(step)
