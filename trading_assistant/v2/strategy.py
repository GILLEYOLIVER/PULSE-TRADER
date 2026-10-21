from __future__ import annotations
import math
from statistics import mean
from dataclasses import dataclass,replace
from datetime import timedelta
from .models import Bar,Decision,aware
from .indicators import snapshot,ema
from .data import aggregate

@dataclass(frozen=True)
class Strategy:
    name: str = "trend"
    reward_r: float = 2.
    stop_atr: float = 1.5
    multi_timeframe: bool = False
    min_trend_atr: float = 0.
    min_efficiency: float = 0.
    min_relative_volume: float = 0.
    max_entry_atr: float = 0.
    require_trend_slope: bool = False

    def __post_init__(self):
        if self.name not in ("trend","breakout","pullback","adaptive","sma_cross","ema_pullback","mean_reversion"): raise ValueError("Unknown strategy")
        if not math.isfinite(self.reward_r) or not math.isfinite(self.stop_atr) or self.reward_r<=0 or self.stop_atr<=0:
            raise ValueError("Invalid strategy parameters")
        if type(self.multi_timeframe) is not bool: raise ValueError("Multi-timeframe must be boolean")
        filters=(self.min_trend_atr,self.min_efficiency,self.min_relative_volume,self.max_entry_atr)
        if any(type(x) not in (int,float) or not math.isfinite(x) or x<0 for x in filters) or self.min_efficiency>1:
            raise ValueError('Invalid causal entry filters')
        if type(self.require_trend_slope) is not bool:raise ValueError('Slope filter must be boolean')

    def evaluate(self,bars: list[Bar]) -> Decision | None:
        decision=self._evaluate(bars)
        if decision is None or decision.side=='WAIT' or not any((self.min_trend_atr,self.min_efficiency,
            self.min_relative_volume,self.max_entry_atr,self.require_trend_slope)):return decision
        ind=dict(decision.indicators);b=bars[-1];a=ind['atr'];direction=1 if decision.side=='BUY' else -1
        movement=sum(abs(y.close-x.close) for x,y in zip(bars[-21:-1],bars[-20:]))
        efficiency=abs(b.close-bars[-21].close)/movement if movement else 0.
        distance=abs(b.close-ind['ema_fast'])/a if a else float('inf')
        slope=ema([row.close for row in bars],50)-ema([row.close for row in bars[:-3]],50) if len(bars)>=53 else 0.
        reasons=[]
        if ind['trend_strength']<self.min_trend_atr:reasons.append('separação das médias insuficiente')
        if efficiency<self.min_efficiency:reasons.append('mercado sem direção suficiente')
        if ind['relative_volume']<self.min_relative_volume:reasons.append('volume insuficiente')
        if self.max_entry_atr and distance>self.max_entry_atr:reasons.append('entrada afastada da média')
        if self.require_trend_slope and (len(bars)<53 or direction*slope<=0):reasons.append('inclinação EMA50 não confirma')
        ind.update(entry_efficiency=efficiency,entry_distance_atr=distance,ema50_slope=slope)
        return replace(decision,side='WAIT' if reasons else decision.side,indicators=ind,
            reason=decision.reason+'; filtros: '+(', '.join(reasons) if reasons else 'confirmados'))

    def _evaluate(self,bars: list[Bar]) -> Decision | None:
        if self.name=='mean_reversion':return self._mean_reversion(bars)
        if self.name in ('sma_cross','ema_pullback'):return self._moving_average(bars)
        if len(bars)<35: return None
        b=bars[-1]; ind=snapshot(bars,full=False)
        up=ind["ema_fast"]>ind["ema_slow"]
        side="WAIT"
        if ind["atr"]>0 and ind["volatility_ratio"]<=2.5:
            if self.name=="trend":
                if up and b.close>ind["ema_fast"] and 50<ind["rsi"]<80: side="BUY"
                elif not up and b.close<ind["ema_fast"] and 20<ind["rsi"]<50: side="SELL"
            elif self.name=="breakout":
                if b.close>ind["resistance"] and ind["relative_volume"]>=1.2: side="BUY"
                elif b.close<ind["support"] and ind["relative_volume"]>=1.2: side="SELL"
            elif self.name=='pullback':
                if up and bars[-2].close<=ind["ema_fast"]<b.close: side="BUY"
                elif not up and bars[-2].close>=ind["ema_fast"]>b.close: side="SELL"
            else:
                movement=sum(abs(y.close-x.close) for x,y in zip(bars[-21:-1],bars[-20:]))
                efficiency=abs(b.close-bars[-21].close)/movement if movement else 0.
                flow=2*b.taker_buy_volume/b.volume-1 if b.taker_buy_volume is not None and b.volume else 0.
                ind.update(efficiency=efficiency,flow_imbalance=flow,flow_available=float(b.taker_buy_volume is not None))
                if efficiency>=.2 and ind['relative_volume']>=.7 and ind['volatility_ratio']<=1.8:
                    if up and b.close>ind['ema_fast'] and 50<ind['rsi']<72 and flow>=-.15:side='BUY'
                    elif not up and b.close<ind['ema_fast'] and 28<ind['rsi']<50 and flow<=.15:side='SELL'
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
            f"{self.name}; EMA9={ind['ema_fast']:.2f}; EMA21={ind['ema_slow']:.2f}; RSI={ind['rsi']:.1f}; ATR={ind['atr']:.2f}; volatility={ind['volatility_ratio']:.2f}"
            +(f"; efficiency={ind.get('efficiency',0):.3f}; flow={ind.get('flow_imbalance',0):.3f}; action={side}" if self.name=='adaptive' else ''),ind)

    def _mean_reversion(self,bars):
        """Candidate: oversold pullback inside a rising SMA200, with a finite ATR stop."""
        if len(bars)<205:return None
        closes=[b.close for b in bars];b=bars[-1];ind=snapshot(bars,full=False)
        trend=mean(closes[-200:]);prior_trend=mean(closes[-205:-5]);target_mean=mean(closes[-5:])
        changes=[y-x for x,y in zip(closes[-201:-1],closes[-200:])]
        gain=mean(max(0.,x) for x in changes[:2]);loss=mean(max(0.,-x) for x in changes[:2])
        for change in changes[2:]:
            gain=(gain+max(0.,change))/2;loss=(loss+max(0.,-change))/2
        rsi2=100-100/(1+gain/loss) if loss else 100. if gain else 50.
        a=ind['atr'];side='WAIT'
        if a>0 and ind['volatility_ratio']<=2.5 and ind['relative_volume']>=.5:
            if b.close>trend>prior_trend and rsi2<10 and target_mean>b.close:side='BUY'
            elif b.close<trend<prior_trend and rsi2>90 and target_mean<b.close:side='SELL'
        direction=-1 if side=='SELL' else 1
        structure=min(row.low for row in bars[-5:]) if direction>0 else max(row.high for row in bars[-5:])
        distance=max(a*self.stop_atr,abs(b.close-structure)+a*.25,b.close*.0001)
        if distance>3*a:side='WAIT'
        reward=min(distance*self.reward_r,abs(target_mean-b.close))
        if reward<=0:side='WAIT'
        ind.update(rsi2=rsi2,sma200=trend,sma200_slope=trend-prior_trend,target_mean5=target_mean)
        ts=aware(b.ts)+timedelta(seconds=b.seconds)
        return Decision(b.symbol,side,b.close,b.close-direction*distance,b.close+direction*reward,
            ts,ts+timedelta(seconds=b.seconds*3),self.name,
            f'mean_reversion; RSI2={rsi2:.2f}; SMA200={trend:.4f}; média5={target_mean:.4f}; '
            f'stop estrutural/ATR limitado a 3 ATR; action={side}',ind)

    def _moving_average(self,bars):
        simple=self.name=='sma_cross'
        fast_period,slow_period,trend_period=(20,50,200) if simple else (9,21,50)
        if len(bars)<trend_period+1:return None
        b=bars[-1];closes=[row.close for row in bars]
        def average(values,period):return mean(values[-period:]) if simple else ema(values,period)
        fast=average(closes,fast_period);slow=average(closes,slow_period);trend=average(closes,trend_period)
        prior_fast=average(closes[:-1],fast_period);prior_slow=average(closes[:-1],slow_period)
        ind=snapshot(bars,full=False);a=ind['atr'];side='WAIT'
        upward=(prior_fast<=prior_slow and fast>slow) if simple else (closes[-2]<=prior_fast and b.close>fast)
        downward=(prior_fast>=prior_slow and fast<slow) if simple else (closes[-2]>=prior_fast and b.close<fast)
        if a>0 and ind['volatility_ratio']<=2.5 and ind['relative_volume']>=.5:
            if upward and b.close>trend and fast>slow:side='BUY'
            elif downward and b.close<trend and fast<slow:side='SELL'
        direction=-1 if side=='SELL' else 1
        ma_stop=slow-direction*a*self.stop_atr*.5
        distance=max(abs(b.close-ma_stop),a*self.stop_atr*.5,b.close*.0001)
        if distance>a*self.stop_atr*2:side='WAIT'
        if self.multi_timeframe and side!='WAIT':
            higher=aggregate(bars,b.seconds*5)
            if len(higher)<trend_period:side='WAIT'
            else:
                values=[row.close for row in higher]
                aligned=average(values,fast_period)>average(values,slow_period)
                if aligned!=(side=='BUY'):side='WAIT'
        reward=self.reward_r*(1.25 if a and abs(fast-slow)/a>=.8 else 1.)
        ind.update(ma_fast=fast,ma_slow=slow,ma_trend=trend,ma_fast_period=fast_period,
            ma_slow_period=slow_period,ma_trend_period=trend_period,target_r=reward)
        ts=aware(b.ts)+timedelta(seconds=b.seconds)
        return Decision(b.symbol,side,b.close,b.close-direction*distance,b.close+direction*distance*reward,
            ts,ts+timedelta(seconds=b.seconds*3),self.name,
            f"{self.name}; {'SMA' if simple else 'EMA'}{fast_period}={fast:.4f}; "
            f"média{slow_period}={slow:.4f}; filtro{trend_period}={trend:.4f}; ATR={a:.4f}; "
            f"stop pela média com buffer de volatilidade; alvo={reward:.2f}R; action={side}",ind)
