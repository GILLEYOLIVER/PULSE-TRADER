from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from random import random, choice, randint, uniform
from threading import Event
from typing import AsyncIterator, Dict, Optional

from trading_assistant.config import MarketFeedConfig
from trading_assistant.core.models import Candle


@dataclass
class _Regime:
    drift: float
    vol: float
    left: int


@dataclass
class MockMarketConnector:
    """Gerador de candles (mock) com regimes.

    Objetivo: gerar movimentos mais realistas para o motor criar BUY/SELL,
    sem "saber" para onde o mercado vai.
    """

    config: MarketFeedConfig

    async def stream_candles(self, stop_event: Optional[Event] = None) -> AsyncIterator[Candle]:
        prices: Dict[str, float] = {s: 100.0 + random() * 10.0 for s in self.config.symbols}
        regimes: Dict[str, _Regime] = {s: _new_regime() for s in self.config.symbols}

        while True:
            if stop_event and stop_event.is_set():
                return

            for symbol in self.config.symbols:
                if stop_event and stop_event.is_set():
                    return

                reg = regimes[symbol]
                if reg.left <= 0:
                    reg = _new_regime()
                    regimes[symbol] = reg

                reg.left -= 1

                last = prices[symbol]
                # choques ocasionais (simula notícias/abertura)
                shock = 0.0
                if random() < 0.03:
                    shock = uniform(-3.5, 3.5) * (reg.vol / 1.0)

                change = reg.drift + (random() - 0.5) * reg.vol + shock
                close = max(0.01, last + change)

                high = max(last, close) + random() * (reg.vol * 0.6)
                low = min(last, close) - random() * (reg.vol * 0.6)
                open_ = last
                vol = 100 + random() * 80

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


def _new_regime() -> _Regime:
    kind = choice(["up", "down", "side"])
    left = randint(40, 180)
    vol = uniform(0.4, 1.8)

    if kind == "up":
        drift = uniform(0.03, 0.12)
    elif kind == "down":
        drift = -uniform(0.03, 0.12)
    else:
        drift = uniform(-0.02, 0.02)

    return _Regime(drift=float(drift), vol=float(vol), left=int(left))


async def _sleep_interruptible(seconds: int, stop_event: Optional[Event] = None) -> None:
    import asyncio

    total = max(1, int(seconds))
    step = 0.1
    slices = int(total / step)
    for _ in range(max(1, slices)):
        if stop_event and stop_event.is_set():
            return
        await asyncio.sleep(step)
