from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Deque, Dict, List

from trading_assistant.core.models import Candle, NewsItem


@dataclass
class MarketState:
    """
    Estado central de mercado compartilhado pela pipeline.

    Compatível com o projeto atual + upgrades:
    - mantém métodos originais: update_candle, set_spread, update_news, set_news_impact, get_last_candles
    - adiciona: set_orderbook + orderbook_imbalance (microestrutura)
    """
    candles: Dict[str, Deque[Candle]] = field(default_factory=dict)
    last_price: Dict[str, float] = field(default_factory=dict)

    spreads: Dict[str, float] = field(default_factory=dict)

    # Livro de ofertas (opcional)
    orderbooks: Dict[str, dict] = field(default_factory=dict)
    orderbook_imbalance: Dict[str, float] = field(default_factory=dict)

    # Notícias
    news_recent: Deque[NewsItem] = field(default_factory=lambda: deque(maxlen=200))
    news_impact: Dict[str, float] = field(default_factory=dict)

    def update_candle(self, candle: Candle) -> None:
        dq = self.candles.get(candle.symbol)
        if dq is None:
            dq = deque(maxlen=500)
            self.candles[candle.symbol] = dq
        dq.append(candle)
        self.last_price[candle.symbol] = float(candle.close)

    def set_spread(self, symbol: str, spread: float) -> None:
        self.spreads[symbol] = float(spread)

    # ===== compatível com pipeline original =====
    def update_news(self, item: NewsItem) -> None:
        # mantemos "mais recentes primeiro" como no seu state original
        self.news_recent.appendleft(item)

    def set_news_impact(self, symbol: str, score: float) -> None:
        self.news_impact[symbol] = float(score)

    def get_last_candles(self, symbol: str, n: int = 100) -> List[Candle]:
        dq = self.candles.get(symbol)
        if not dq:
            return []
        return list(dq)[-n:]

    # ===== upgrade: microestrutura / book =====
    def set_orderbook(self, symbol: str, book: dict) -> None:
        """
        Guarda o livro e calcula:
        - imbalance (−1..+1) usando os top níveis
        - spread (best ask - best bid), quando disponível
        """
        self.orderbooks[symbol] = book

        try:
            asks = book.get("asks", []) or []
            bids = book.get("bids", []) or []
            top = min(8, len(asks), len(bids))
            if top <= 0:
                self.orderbook_imbalance[symbol] = 0.0
                return

            ask_qty = sum(float(asks[i].get("qty", 0.0)) for i in range(top))
            bid_qty = sum(float(bids[i].get("qty", 0.0)) for i in range(top))
            denom = max(1e-9, ask_qty + bid_qty)
            self.orderbook_imbalance[symbol] = float((bid_qty - ask_qty) / denom)

            # spread
            try:
                best_ask = float(asks[0].get("price", 0.0))
                best_bid = float(bids[0].get("price", 0.0))
                if best_ask and best_bid:
                    self.spreads[symbol] = float(best_ask - best_bid)
            except Exception:
                pass
        except Exception:
            self.orderbook_imbalance[symbol] = 0.0


@dataclass
class RiskState:
    day_start: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    trades_today: int = 0
    pnl_today: float = 0.0
