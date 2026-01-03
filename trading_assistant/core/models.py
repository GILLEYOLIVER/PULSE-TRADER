from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass(slots=True)
class Candle:
    symbol: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(slots=True)
class NewsItem:
    ts: datetime
    title: str
    source: str
    url: str = ""
    language: str = ""
    sentiment: float = 0.0   # -1..+1
    impact: float = 0.0      # 0..1
    tickers: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)
    symbols_hint: List[str] = field(default_factory=list)


@dataclass(slots=True)
class Signal:
    symbol: str
    side: str              # BUY/SELL/WAIT
    price: float
    sl: float
    tp: float
    confidence: float      # 0..1
    reason: str
    ts: datetime
    meta: Dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class OrderRequest:
    symbol: str
    side: str              # BUY/SELL
    qty: float
    price: float
    sl: float
    tp: float
    ts: datetime
    confidence: float
    reason: str


@dataclass(slots=True)
class ExecutionReport:
    symbol: str
    side: str
    qty: float
    status: str
    filled_price: float
    ts: datetime
    mode: str
    reason: str = ""
    raw: Optional[Dict[str, object]] = None
