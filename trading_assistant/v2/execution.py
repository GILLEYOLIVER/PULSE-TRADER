from __future__ import annotations
import hashlib
from dataclasses import asdict
from datetime import datetime,timedelta
from .models import Bar,Decision,ExecutionSettings,INSTRUMENTS,Limits,aware
from .ledger import Ledger
from .risk import RiskManager
from .strategy import Strategy

class PaperEngine:
    """Only execution implementation shipped. No flag can enable real routing."""
    mode="PAPER"
    def __init__(self,ledger:Ledger,limits=None,costs=None,instruments=None,strategy=None):
        self.ledger=ledger
        self.limits=limits or Limits();self.costs=costs or ExecutionSettings()
        self.specs=dict(instruments or INSTRUMENTS)
        self.risk=RiskManager(self.limits,self.costs)
        self.strategy=strategy or Strategy()
        self.history={};self.last_decision=None
        # Persist immutable assumptions and reject accidental reinterpretation of open positions.
        config={"strategy":{"name":self.strategy.name,"reward_r":self.strategy.reward_r,"stop_atr":self.strategy.stop_atr,"multi_timeframe":self.strategy.multi_timeframe},"limits":asdict(self.limits),"costs":asdict(self.costs),"instruments":{k:asdict(v) for k,v in self.specs.items()}}
        import json
        config=json.loads(json.dumps(config))
        with ledger.transaction() as s:
            if s.get("config")!=config and (s["positions"] or any(o["status"]=="NEW" for o in s["orders"].values())):
                raise ValueError("Open exposure requires identical saved configuration")
            s["config"]=config

    def _decision(self,o):
        return Decision(o["symbol"],o["side"],o["price"],o["stop"],o["target"],datetime.fromisoformat(o["signal_ts"]),
            datetime.fromisoformat(o["expires"]),o["strategy"],o["reason"])

    def submit(self,d:Decision,key=None,requested=None):
        key=key or hashlib.sha256(f"{d.symbol}|{d.strategy}|{aware(d.ts).isoformat()}|{d.side}".encode()).hexdigest()
        with self.ledger.transaction() as s:
            if key in s["orders"]:
                old=s["orders"][key]
                if (old["symbol"],old["side"],old["price"],old["signal_ts"]) != (d.symbol,d.side,d.price,d.ts.isoformat()):
                    raise ValueError("Idempotency key reused for different order")
                return dict(old)
            spec=self.specs.get(d.symbol)
            qty,reason=self.risk.assess(s,d,spec,d.ts,requested=requested) if spec else (0,"Unknown instrument")
            order={"id":key,"symbol":d.symbol,"side":d.side,"price":d.price,"stop":d.stop,"target":d.target,
                "signal_ts":d.ts.isoformat(),"expires":d.expires.isoformat(),"created_at":d.ts.isoformat(),
                "regime":"volatile" if d.indicators.get("volatility_ratio",0)>2 else "trend" if d.indicators.get("trend_strength",0)>.5 else "range","strategy":d.strategy,"reason":d.reason,"source":s["last_sources"].get(d.symbol),"qty":qty,"filled_qty":0,"status":"NEW" if qty else "REJECTED",
                "message":reason,"bars_waited":0,"point_value":spec.point_value if spec else 0.,
                "margin":spec.margin if spec else 0.,"reserved_risk":0.}
            if qty:
                per_unit=abs(d.price-d.stop)*spec.point_value+2*self.costs.fee_per_unit+2*(self.costs.spread_ticks/2+self.costs.slippage_ticks)*spec.tick*spec.point_value
                order["reserved_risk"]=qty*per_unit
            s["orders"][key]=order
            self.ledger.audit(d.ts,"order_"+order["status"].lower(),{"id":key,"message":reason,"quantity":qty})
            return dict(order)

    def cancel(self,key,now):
        with self.ledger.transaction() as s:
            o=s["orders"][key]
            if o["status"]=="NEW":
                o["status"]="CANCELLED";o["reserved_risk"]=0.
                self.ledger.audit(now,"order_cancelled",{"id":key})
            return dict(o)

    def emergency(self,now,enabled=True):
        with self.ledger.transaction() as s:
            s["emergency"]=bool(enabled)
            if enabled:
                for o in s["orders"].values():
                    if o["status"]=="NEW": o["status"]="CANCELLED";o["reserved_risk"]=0.
            self.ledger.audit(now,"emergency",{"enabled":bool(enabled),"open_positions":len(s["positions"]),"effect":"block entries; protective exits continue"})

    def connection(self,connected,now):
        with self.ledger.transaction() as s:
            s["connected"]=bool(connected)
            if not connected:
                for o in s["orders"].values():
                    if o["status"]=="NEW": o["status"]="CANCELLED";o["reserved_risk"]=0.
            self.ledger.audit(now,"connection",{"connected":bool(connected)})

    def _fill(self,s,o,b):
        o["bars_waited"]+=1
        if o["bars_waited"]<self.costs.latency_bars: return
        spec=self.specs[o["symbol"]];direction=1 if o["side"]=="BUY" else -1
        slip=(self.costs.spread_ticks/2+self.costs.slippage_ticks)*spec.tick
        # Adverse tick rounding.
        import math
        raw=b.open+direction*slip
        price=(math.ceil(raw/spec.tick) if direction>0 else math.floor(raw/spec.tick))*spec.tick
        d=self._decision(o)
        qty,reason=self.risk.assess(s,d,spec,b.ts,entry=price,exclude=o["id"])
        qty=min(qty,o["qty"],int(s.get("liquidity",{}).get(b.symbol,0)*self.costs.participation)//spec.lot*spec.lot)
        if qty<spec.lot:
            o["status"]="REJECTED";o["message"]=reason if reason!="Approved" else "Insufficient simulated liquidity"
        else:
            o["filled_qty"]=qty;o["filled_price"]=price;o["filled_at"]=b.ts.isoformat();o["status"]="FILLED" if qty==o["qty"] else "PARTIAL"
            o["cancelled_qty"]=o["qty"]-qty  # IOC remainder canceled; never fills on another bar
            s["positions"][o["id"]]={"id":o["id"],"symbol":o["symbol"],"side":o["side"],"qty":qty,
                "entry":price,"stop":o["stop"],"initial_stop":o["stop"],"target":o["target"],"point_value":spec.point_value,
                "tick":spec.tick,"margin":spec.margin,"entry_fee":qty*self.costs.fee_per_unit,
                "opened_at":b.ts.isoformat(),"strategy":o["strategy"],"regime":o.get("regime","unknown"),"source":b.source}
        o["reserved_risk"]=0.
        self.ledger.audit(b.ts,"execution",{"id":o["id"],"status":o["status"],"message":reason,"filled":qty})

    def _close(self,s,p,price,reason,ts):
        direction=1 if p["side"]=="BUY" else -1
        adverse=(self.costs.slippage_ticks+self.costs.spread_ticks/2)*p["tick"]
        price-=direction*adverse
        if price<=0: raise ValueError("Exit price invalid")
        gross=(price-p["entry"])*direction*p["qty"]*p["point_value"]
        fees=p["entry_fee"]+p["qty"]*self.costs.fee_per_unit
        trade={**p,"exit":price,"closed_at":ts.isoformat(),"exit_reason":reason,"gross":gross,"fees":fees,"net":gross-fees}
        s["trades"].append(trade)
        del s["positions"][p["id"]]
        s["orders"][p["id"]]["status"]="CLOSED"
        s["loss_streak"]=s["loss_streak"]+1 if trade["net"]<0 else 0
        if s["loss_streak"]>=self.limits.consecutive_losses:
            s["cooldown_until"]=(ts+timedelta(seconds=self.limits.cooldown_seconds)).isoformat()
            s["loss_streak"]=0
        self.ledger.audit(ts,"position_closed",trade)

    def on_bar(self,b:Bar,automatic=True):
        """One completed candle. Risk at open cannot see its close/high/low."""
        if b.symbol not in self.specs: raise ValueError("Unknown instrument; configure explicitly")
        with self.ledger.transaction() as s:
            if not s["connected"]: return None
            previous=s["last_bars"].get(b.symbol)
            if previous and aware(b.ts)<datetime.fromisoformat(previous):
                # Exact replay ignored; revised historical candle is rejected.
                if s["last_ohlcv"].get(b.symbol)==self._bar_key(b): return None
                raise ValueError("Out-of-order/revised candle")
            sources=s["last_sources"]
            if b.symbol in sources and sources[b.symbol]!=b.source and any(p["symbol"]==b.symbol for p in s["positions"].values()):
                raise ValueError("Cannot change data source with an open position")
            sources[b.symbol]=b.source
            # Reconcile at current open before entries (no lookahead sizing).
            s["marks"][b.symbol]=b.open
            s["last_bars"][b.symbol]=b.ts.isoformat()
            self.risk.block_reason(s,b.ts)
            for o in list(s["orders"].values()):
                if o["status"]=="NEW" and o["symbol"]==b.symbol:
                    if sources[b.symbol]!=o.get("source",b.source):
                        o["status"]="REJECTED";o["message"]="Data source changed"
                    elif b.ts>=datetime.fromisoformat(o["signal_ts"]): self._fill(s,o,b)
            # Stops first when both barriers touched; gaps stop at worse open.
            for p in list(s["positions"].values()):
                if p["symbol"]!=b.symbol: continue
                buy=p["side"]=="BUY"
                hit_stop=b.low<=p["stop"] if buy else b.high>=p["stop"]
                hit_target=b.high>=p["target"] if buy else b.low<=p["target"]
                if hit_stop:
                    self._close(s,p,min(b.open,p["stop"]) if buy else max(b.open,p["stop"]),"STOP",b.ts+timedelta(seconds=b.seconds))
                elif hit_target:
                    self._close(s,p,p["target"],"TARGET",b.ts+timedelta(seconds=b.seconds))
                else:
                    # Adjustments apply NEXT bar; never retrospectively to this bar.
                    direction=1 if buy else -1
                    r=abs(p["entry"]-p["initial_stop"])
                    if self.costs.break_even_r and (b.close-p["entry"])*direction>=r*self.costs.break_even_r:
                        candidate=p["entry"]+direction*2*self.costs.fee_per_unit/p["point_value"]
                        p["stop"]=max(p["stop"],candidate) if buy else min(p["stop"],candidate)
                    history=self.history.get(b.symbol,[])
                    if self.costs.trailing_atr and len(history)>=35:
                        from .indicators import snapshot
                        a=snapshot(history)["atr"]
                        candidate=b.close-direction*self.costs.trailing_atr*a
                        p["stop"]=max(p["stop"],candidate) if buy else min(p["stop"],candidate)
            s["marks"][b.symbol]=b.close
            s["last_bars"][b.symbol]=(b.ts+timedelta(seconds=b.seconds)).isoformat()
            s["last_ohlcv"][b.symbol]=self._bar_key(b)
            s.setdefault("liquidity",{})[b.symbol]=b.volume
            s["sequence"]+=1
            self.risk.block_reason(s,b.ts+timedelta(seconds=b.seconds))
        history=self.history.setdefault(b.symbol,[])
        history.append(b)
        del history[:-1000]
        d=self.strategy.evaluate(history)
        self.last_decision=d
        if automatic and d and d.side!="WAIT":
            self.submit(d)
        return d

    @staticmethod
    def _bar_key(b):
        return [b.ts.isoformat(),b.open,b.high,b.low,b.close,b.volume,b.source,b.seconds]

    def flatten(self,now):
        """Paper liquidation at latest marks, with configured adverse exit costs."""
        with self.ledger.transaction() as s:
            for o in s["orders"].values():
                if o["status"]=="NEW": o["status"]="CANCELLED";o["reserved_risk"]=0.
            for p in list(s["positions"].values()): self._close(s,p,s["marks"][p["symbol"]],"FLATTEN",now)
