from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    WAIT = "WAIT"

@dataclass(frozen=True)
class Tick:
    ts: datetime
    symbol: str
    price: float
    volume: float = 0.0
    # opcionais (se tiver ProfitDLL book/tinybook)
    bid: float | None = None
    ask: float | None = None
    bid_size: float | None = None
    ask_size: float | None = None

@dataclass(frozen=True)
class Candle:
    ts: datetime
    symbol: str
    seconds: int
    o: float
    h: float
    l: float
    c: float
    v: float

@dataclass(frozen=True)
class NewsEvent:
    ts: datetime
    source: str
    title: str
    url: str | None = None
    tags: tuple[str, ...] = ()
    impact: float = 0.0  # 0..1
    meta: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class Features:
    ts: datetime
    symbol: str
    price: float
    ret_1: float
    vol: float
    atr: float
    book_imbalance: float = 0.0
    news_risk: float = 0.0

@dataclass(frozen=True)
class Signal:
    ts: datetime
    symbol: str
    side: Side
    confidence: float
    rationale: str
    stop_price: float | None = None
    target_price: float | None = None
    meta: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class ApprovedTrade:
    ts: datetime
    symbol: str
    side: Side
    contracts: int
    entry_hint: float
    stop_price: float
    target_price: float | None
    risk_amount: float
    rationale: str
    meta: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class Fill:
    ts: datetime
    symbol: str
    side: Side
    contracts: int
    price: float
    fees: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)

@dataclass
class Position:
    symbol: str
    contracts: int = 0
    avg_price: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    last_price: float = 0.0

@dataclass(frozen=True)
class RiskLimits:
    capital: float
    risk_per_trade_pct: float
    max_daily_loss_pct: float
    max_contracts: int
    max_stops_in_row: int
    cooldown_minutes: int
    tick_value: float
    tick_size: float
    slippage_ticks: int
