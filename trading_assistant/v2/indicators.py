from __future__ import annotations

import math
from statistics import mean, pstdev
from .models import Bar

def ema(values,period):
    if period < 1 or len(values)<period: raise ValueError("Insufficient EMA history")
    value=mean(values[:period]);k=2/(period+1)
    for v in values[period:]: value+=k*(v-value)
    return value

def snapshot(bars: list[Bar],period=14,*,full=True) -> dict[str,float]:
    if len(bars)<35 or period<1: raise ValueError("At least 35 closed candles required")
    c=[b.close for b in bars];v=[b.volume for b in bars]
    recent=bars[-(period*2+1):]
    tr=[max(b.high-b.low,abs(b.high-a.close),abs(b.low-a.close)) for a,b in zip(recent,recent[1:])]
    changes=[b-a for a,b in zip(c,c[1:])][-period:]
    gain=mean(max(x,0) for x in changes);loss=mean(max(-x,0) for x in changes)
    rsi=100-100/(1+gain/loss) if loss else 100. if gain else 50.
    a=mean(tr[-period:])
    prior_a=mean(tr[-period*2:-period]) if len(tr)>=period*2 else a
    support=min(b.low for b in bars[-21:-1]);resistance=max(b.high for b in bars[-21:-1])
    e9,e21=ema(c,9),ema(c,21)
    previous_volume=mean(v[-21:-1])
    result={"ema_fast":e9,"ema_slow":e21,"rsi":rsi,"atr":a,
        "support":support,"resistance":resistance,"momentum":c[-1]-c[-11],
        "relative_volume":v[-1]/previous_volume if previous_volume else 0.,
        "volatility_ratio":a/prior_a if prior_a else 1.,
        "consolidation":float(resistance-support<a*3),"trend_strength":abs(e9-e21)/a if a else 0.}
    if not full:return result
    def ema_series(values,period):
        result=[None]*(period-1)
        value=mean(values[:period]);result.append(value);k=2/(period+1)
        for v in values[period:]:value+=k*(v-value);result.append(value)
        return result
    fast,slow=ema_series(c,12),ema_series(c,26)
    macds=[fast[i]-slow[i] for i in range(25,len(c))]
    typical=[(b.high+b.low+b.close)/3 for b in bars]
    # Session VWAP reset using Sao Paulo local day.
    from .session import local_time
    day=local_time(bars[-1].ts).date()
    session=[i for i,b in enumerate(bars) if local_time(b.ts).date()==day]
    vol=sum(v[i] for i in session)
    mid=mean(c[-20:]);sd=pstdev(c[-20:])
    result.update({"sma":mid,
        "macd":macds[-1],"macd_signal":ema(macds,9),"atr":a,
        "vwap":sum(typical[i]*v[i] for i in session)/vol if vol else c[-1],
        "bollinger_upper":mid+2*sd,"bollinger_lower":mid-2*sd,
    })
    return result
