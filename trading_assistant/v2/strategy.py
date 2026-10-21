from __future__ import annotations
import math
from dataclasses import dataclass
from datetime import timedelta
from .models import Bar,Decision,aware
from .indicators import snapshot
from .data import aggregate

@dataclass(frozen=True)
class Strategy:
    name: str = "trend"
    reward_r: float = 2.
    stop_atr: float = 1.5
    multi_timeframe: bool = False

    def __post_init__(self):
        if self.name not in ("trend","breakout","pullback"): raise ValueError("Unknown strategy")
        if not math.isfinite(self.reward_r) or not math.isfinite(self.stop_atr) or self.reward_r<=0 or self.stop_atr<=0:
            raise ValueError("Invalid strategy parameters")
        if type(self.multi_timeframe) is not bool: raise ValueError("Multi-timeframe must be boolean")

    def evaluate(self,bars: list[Bar]) -> Decision | None:
        if len(bars)<35: return None
        b=bars[-1]; ind=snapshot(bars)
        up=ind["ema_fast"]>ind["ema_slow"]
        side="WAIT"
        if ind["atr"]>0 and ind["volatility_ratio"]<=2.5:
            if self.name=="trend":
                if up and b.close>ind["ema_fast"] and 50<ind["rsi"]<80: side="BUY"
                elif not up and b.close<ind["ema_fast"] and 20<ind["rsi"]<50: side="SELL"
            elif self.name=="breakout":
                if b.close>ind["resistance"] and ind["relative_volume"]>=1.2: side="BUY"
                elif b.close<ind["support"] and ind["relative_volume"]>=1.2: side="SELL"
            else:
                if up and bars[-2].close<=ind["ema_fast"]<b.close: side="BUY"
                elif not up and bars[-2].close>=ind["ema_fast"]>b.close: side="SELL"
        if self.multi_timeframe and side!="WAIT":
            higher=aggregate(bars,b.seconds*5)
            if len(higher)<35: side="WAIT"
            else:
                higher_ind=snapshot(higher)
                if (higher_ind["ema_fast"]>higher_ind["ema_slow"]) != (side=="BUY"): side="WAIT"
        direction=1 if side!="SELL" else -1
        distance=max(ind["atr"]*self.stop_atr,b.close*.0001)
        ts=aware(b.ts)+timedelta(seconds=b.seconds)
        return Decision(b.symbol,side,b.close,b.close-direction*distance,b.close+direction*distance*self.reward_r,
            ts,ts+timedelta(seconds=b.seconds*3),self.name,
            f"{self.name}; EMA9={ind['ema_fast']:.2f}; EMA21={ind['ema_slow']:.2f}; RSI={ind['rsi']:.1f}; ATR={ind['atr']:.2f}; volatility={ind['volatility_ratio']:.2f}",ind)
