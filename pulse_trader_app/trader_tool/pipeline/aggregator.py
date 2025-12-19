from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from collections import deque
import math
from trader_tool.domain.models import Tick, Candle, Features

@dataclass
class _CandleBuilder:
    start: datetime
    o: float
    h: float
    l: float
    c: float
    v: float

class TickAggregator:
    """Agrega ticks em candles de N segundos + calcula features básicas."""
    def __init__(self, seconds: int = 1, window: int = 60):
        self.seconds = seconds
        self.window = window
        self._builders: dict[str, _CandleBuilder] = {}
        self._candles: dict[str, deque[Candle]] = {}

    def push_tick(self, tick: Tick) -> Candle | None:
        sym = tick.symbol
        if sym not in self._candles:
            self._candles[sym] = deque(maxlen=self.window)

        # arredonda para janela
        start = tick.ts - timedelta(seconds=tick.ts.second % self.seconds,
                                   microseconds=tick.ts.microsecond)
        b = self._builders.get(sym)

        if b is None or b.start != start:
            # fecha candle anterior
            if b is not None:
                c = Candle(ts=b.start, symbol=sym, seconds=self.seconds, o=b.o, h=b.h, l=b.l, c=b.c, v=b.v)
                self._candles[sym].append(c)
            # inicia novo
            self._builders[sym] = _CandleBuilder(start=start, o=tick.price, h=tick.price, l=tick.price, c=tick.price, v=tick.volume)
            return None

        # atualiza
        b.h = max(b.h, tick.price)
        b.l = min(b.l, tick.price)
        b.c = tick.price
        b.v += tick.volume
        self._builders[sym] = b
        return None

    def last_candles(self, symbol: str) -> list[Candle]:
        return list(self._candles.get(symbol, []))

    @staticmethod
    def _std(values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        m = sum(values) / len(values)
        v = sum((x - m) ** 2 for x in values) / (len(values) - 1)
        return math.sqrt(v)

    def compute_features(self, symbol: str, now: datetime, last_price: float, book_imbalance: float = 0.0, news_risk: float = 0.0) -> Features:
        candles = self.last_candles(symbol)
        closes = [c.c for c in candles[-30:]]
        ret_1 = 0.0
        if len(closes) >= 2 and closes[-2] != 0:
            ret_1 = (closes[-1] - closes[-2]) / closes[-2]

        # volatilidade simples (std de retornos)
        rets = []
        for i in range(1, len(closes)):
            if closes[i-1] != 0:
                rets.append((closes[i] - closes[i-1]) / closes[i-1])
        vol = self._std(rets[-20:])

        # ATR simplificado
        trs = []
        for c in candles[-20:]:
            trs.append(c.h - c.l)
        atr = sum(trs) / len(trs) if trs else 0.0

        return Features(
            ts=now, symbol=symbol, price=last_price,
            ret_1=ret_1, vol=vol, atr=atr,
            book_imbalance=book_imbalance, news_risk=news_risk
        )
