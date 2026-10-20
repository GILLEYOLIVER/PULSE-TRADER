from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping

UTC = timezone.utc

def aware(ts: datetime) -> datetime:
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError("Timezone required (ISO 8601 with offset)")
    return ts.astimezone(UTC)

def finite(*values: float) -> bool:
    try:
        return all(type(v) in (int,float) and math.isfinite(v) for v in values)
    except OverflowError:
        return False

@dataclass(frozen=True)
class Bar:
    symbol: str
    ts: datetime  # opening timestamp; strategies see this only after close
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str = "SYNTHETIC"
    seconds: int = 60

    def __post_init__(self):
        aware(self.ts)
        if (not self.symbol or not self.source or not finite(self.open,self.high,self.low,self.close,self.volume)
            or self.low <= 0 or self.volume < 0 or self.low > min(self.open,self.close)
            or self.high < max(self.open,self.close) or type(self.seconds) is not int or self.seconds <= 0):
            raise ValueError("Invalid OHLCV candle")

@dataclass(frozen=True)
class Instrument:
    symbol: str
    point_value: float
    tick: float
    lot: int = 1
    margin: float = 1000.0  # simulation assumption, NOT broker margin
    currency: str = "BRL"
    expiry: str | None = None

    def __post_init__(self):
        if (not finite(self.point_value,self.tick,self.margin) or min(self.point_value,self.tick,self.margin) <= 0
            or type(self.lot) is not int or self.lot < 1):
            raise ValueError("Invalid instrument specification")

# Financial multipliers; margins are deliberately configurable paper assumptions.
INSTRUMENTS = {s:Instrument(s,p,t,l) for s,p,t,l in [
    ("WIN",0.2,5.,1),("IND",1.,5.,5),("WDO",10.,0.5,1),("DOL",50.,0.5,5),
    ("PETR4",1.,0.01,100),("VALE3",1.,0.01,100),
    ("BTC",1.,0.01,1),("ETH",1.,0.01,1)]}
# BTC/ETH denote user-supplied BRL spot series only; no futures/fx assumptions.

@dataclass(frozen=True)
class Decision:
    symbol: str
    side: str
    price: float
    stop: float
    target: float
    ts: datetime
    expires: datetime
    strategy: str
    reason: str
    indicators: Mapping[str,float] = field(default_factory=dict)
    confidence: float | None = None  # no calibrated model => unavailable

    @property
    def rr(self) -> float:
        return abs(self.target-self.price)/abs(self.price-self.stop) if self.stop != self.price else 0.

@dataclass(frozen=True)
class Limits:
    capital: float = 10000.
    risk_fraction: float = .005
    daily_loss: float = 200.
    weekly_loss: float = 500.
    monthly_loss: float = 1000.
    daily_target: float = 300.
    max_positions: int = 3
    max_contracts: int = 10
    max_trades: int = 20
    max_spread_ticks: float = 3.
    max_slippage_ticks: float = 2.
    max_exposure: float = 500000.
    consecutive_losses: int = 3
    cooldown_seconds: int = 900
    start_hour: int = 0
    end_hour: int = 24
    allowed_symbols: tuple[str,...] = tuple(INSTRUMENTS)
    allowed_strategies: tuple[str,...] = ("trend","breakout","pullback")
    max_data_age_seconds: int = 180

    def __post_init__(self):
        if isinstance(self.allowed_symbols,list): object.__setattr__(self,"allowed_symbols",tuple(self.allowed_symbols))
        if isinstance(self.allowed_strategies,list): object.__setattr__(self,"allowed_strategies",tuple(self.allowed_strategies))

    def validate(self):
        if (not isinstance(self.allowed_symbols,tuple) or not self.allowed_symbols
            or not isinstance(self.allowed_strategies,tuple) or not self.allowed_strategies
            or any(not isinstance(value,str) or not value for value in self.allowed_symbols+self.allowed_strategies)):
            raise ValueError("Authorized assets and strategies must be nonempty lists of names")
        counts = (self.max_positions,self.max_contracts,self.max_trades,self.consecutive_losses,
                  self.max_data_age_seconds,self.cooldown_seconds,self.start_hour,self.end_hour)
        if any(type(value) is not int for value in counts):
            raise ValueError("Counts and hours must be whole numbers")
        positive = (self.capital,self.daily_loss,self.weekly_loss,self.monthly_loss,self.daily_target,self.max_exposure)
        if not finite(*positive,self.risk_fraction,self.max_spread_ticks,self.max_slippage_ticks) or min(positive) <= 0:
            raise ValueError("Limits must be finite and positive")
        if not 0 < self.risk_fraction <= .02:
            raise ValueError("Risk per trade must be > 0 and <= 2%")
        if min(self.max_positions,self.max_contracts,self.max_trades,self.consecutive_losses,self.max_data_age_seconds) < 1:
            raise ValueError("Counts must be positive")
        if min(self.max_spread_ticks,self.max_slippage_ticks,self.cooldown_seconds) < 0 or not 0 <= self.start_hour < self.end_hour <= 24:
            raise ValueError("Invalid time or execution limits")

@dataclass(frozen=True)
class ExecutionSettings:
    spread_ticks: float = 1.
    slippage_ticks: float = 1.
    fee_per_unit: float = .5  # each side, simulation input, not broker tariff
    participation: float = .1
    latency_bars: int = 1
    trailing_atr: float = 0.
    break_even_r: float = 0.

    def validate(self):
        if (not finite(self.spread_ticks,self.slippage_ticks,self.fee_per_unit,self.participation,self.trailing_atr,self.break_even_r)
            or min(self.spread_ticks,self.slippage_ticks,self.fee_per_unit,self.trailing_atr,self.break_even_r) < 0
            or not 0 < self.participation <= 1 or type(self.latency_bars) is not int or self.latency_bars < 1):
            raise ValueError("Invalid paper execution settings")
