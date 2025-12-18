from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Deque, Dict, List, Optional

from trading_assistant.core.models import Candle, NewsItem


@dataclass
class MarketState:
    candles: Dict[str, Deque[Candle]] = field(default_factory=dict)
    last_price: Dict[str, float] = field(default_factory=dict)
    spreads: Dict[str, float] = field(default_factory=dict)
    news_recent: Deque[NewsItem] = field(default_factory=lambda: deque(maxlen=200))
    news_impact: Dict[str, float] = field(default_factory=dict)

    def update_candle(self, candle: Candle) -> None:
        dq = self.candles.setdefault(candle.symbol, deque(maxlen=500))
        dq.append(candle)
        self.last_price[candle.symbol] = float(candle.close)

    def set_spread(self, symbol: str, spread: float) -> None:
        self.spreads[symbol] = float(spread)

    def update_news(self, item: NewsItem) -> None:
        self.news_recent.appendleft(item)

    def set_news_impact(self, symbol: str, score: float) -> None:
        self.news_impact[symbol] = float(score)

    def get_last_candles(self, symbol: str, n: int = 100) -> List[Candle]:
        dq = self.candles.get(symbol)
        if not dq:
            return []
        return list(dq)[-n:]


@dataclass
class RiskState:
    day_start: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    trades_today: int = 0
    pnl_today: float = 0.0
