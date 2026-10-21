from __future__ import annotations
import hashlib
from dataclasses import asdict
from datetime import datetime,timedelta
from .models import Bar,Decision,ExecutionSettings,INSTRUMENTS,Instrument,Limits,aware
from .ledger import Ledger
from .risk import RiskManager
from .strategy import Strategy

class PaperEngine:
    """Only execution implementation shipped. No flag can enable real routing."""
    mode="PAPER"
    def __init__(self,ledger:Ledger,limits=None,costs=None,instruments=None,strategy=None,calendar=None):
        self.ledger=ledger
        self.limits=limits or Limits();self.costs=costs or ExecutionSettings()
        self.specs=dict(instruments or INSTRUMENTS)
        self.risk=RiskManager(self.limits,self.costs,calendar)
        self.calendar=calendar
        self.strategy=strategy or Strategy()
        self.history={};self.last_decision=None
        # Persist immutable assumptions and reject accidental reinterpretation of open positions.
        config={"strategy":asdict(self.strategy),"limits":asdict(self.limits),"costs":asdict(self.costs),"instruments":{k:asdict(v) for k,v in self.specs.items()}}
        if calendar is not None: config["calendar"]=calendar.to_config()
        import json
        config=json.loads(json.dumps(config))
        with ledger.transaction() as s:
            previous=s.get('config')
            if previous:
                previous={**previous,'strategy':asdict(Strategy(**previous['strategy'])),
                    'costs':asdict(ExecutionSettings(**previous['costs'])),
                    'limits':asdict(Limits(**previous['limits'])),
                    'instruments':{key:asdict(Instrument(**value)) for key,value in previous['instruments'].items()}}
                previous=json.loads(json.dumps(previous))
            if previous!=config and (s["positions"] or any(o["status"]=="NEW" for o in s["orders"].values())):
                raise ValueError("Open exposure requires identical saved configuration")
            s["config"]=config

    def _decision(self,o):
        return Decision(o["symbol"],o["side"],o["price"],o["stop"],o["target"],datetime.fromisoformat(o["signal_ts"]),
            datetime.fromisoformat(o["expires"]),o["strategy"],o["reason"])

    @staticmethod
    def decision_key(d):
        return hashlib.sha256(f"{d.symbol}|{d.strategy}|{aware(d.ts).isoformat()}|{d.side}".encode()).hexdigest()

    def submit(self,d:Decision,key=None,requested=None):
        key=key or self.decision_key(d)
        with self.ledger.transaction() as s:
            return self._submit(s,d,key,requested)

    def _submit(self,s,d,key,requested=None):
        if key in s["orders"]:
            old=s["orders"][key]
            if (old["symbol"],old["side"],old["price"],old["stop"],old["target"],
                old["signal_ts"],old["expires"],old["strategy"],old.get("requested_qty")) != (
                d.symbol,d.side,d.price,d.stop,d.target,d.ts.isoformat(),d.expires.isoformat(),d.strategy,requested):
                raise ValueError("Idempotency key reused for different order")
            return dict(old)
        spec=self.specs.get(d.symbol)
        qty,reason=self.risk.assess(s,d,spec,d.ts,requested=requested) if spec else (0,"Unknown instrument")
        order={"id":key,"symbol":d.symbol,"side":d.side,"price":d.price,"stop":d.stop,"target":d.target,
            "signal_ts":d.ts.isoformat(),"expires":d.expires.isoformat(),"created_at":d.ts.isoformat(),
            "regime":"volatile" if d.indicators.get("volatility_ratio",0)>2 else "trend" if d.indicators.get("trend_strength",0)>.5 else "range","strategy":d.strategy,"reason":d.reason,"source":s["last_sources"].get(d.symbol),"qty":qty,"filled_qty":0,"status":"NEW" if qty else "REJECTED",
            "message":reason,"requested_qty":requested,"bars_waited":0,"point_value":spec.point_value if spec else 0.,
            "margin":spec.margin if spec else 0.,"reserved_risk":0.}
        if qty:
            per_unit=abs(d.price-d.stop)*spec.point_value+self.costs.fee(d.price,spec.point_value)+self.costs.fee(d.stop,spec.point_value)+2*(self.costs.spread_ticks/2+self.costs.slippage_ticks)*spec.tick*spec.point_value
            order["reserved_risk"]=qty*per_unit
        s["orders"][key]=order
        self.ledger.audit(d.ts,"order_"+order["status"].lower(),{"id":key,"message":reason,"quantity":qty})
        return dict(order)

    def cancel(self,key,now):
        with self.ledger.transaction() as s:
            o=s["orders"][key]
            if o["status"]=="NEW":
                o["status"]="CANCELLED";o["reserved_risk"]=0.
                self._update_plan_order(s,o)
                self.ledger.audit(now,"order_cancelled",{"id":key})
            return dict(o)

    def _update_plan_order(self,s,order):
        if not order['id'].startswith('plan:'):return
        plan=s.get('analysis_plans',{}).get(order['id'][5:])
        if not plan:return
        status=order['status']
        plan['state']={'NEW':'ORDERED','FILLED':'EXECUTED','PARTIAL':'EXECUTED','CLOSED':'CLOSED'}.get(status,status)
        plan['quantity']=order.get('filled_qty',0) if status!='NEW' else order['qty']
        plan['risk_approved']=bool(plan['quantity']) and status not in ('REJECTED','CANCELLED')
        if order.get('filled_price') is not None:plan['actual_entry']=order['filled_price']

    def _check_plan_config(self,plan):
        import json
        canonical=lambda value:json.dumps(value,sort_keys=True)
        for key,current in (("limits",self.limits),("execution",self.costs),("parameters",self.strategy)):
            if canonical(plan[key])!=canonical(asdict(current)):
                raise ValueError("Configuração mudou desde a proposta; gere um novo plano")
        spec=self.specs.get(plan['analysis']['symbol'])
        if not spec or canonical(plan.get('instrument'))!=canonical(asdict(spec)):
            raise ValueError('Especificação do ativo mudou ou plano antigo; gere uma nova proposta')

    def arm_plan(self,key,now):
        """Bind a saved plan to the exact closed history, then use the central entry gate."""
        from .suggestions import history_digest
        now=aware(now)
        with self.ledger.transaction() as s:
            plan=s.get("analysis_plans",{}).get(key)
            if not plan: raise ValueError("Plano não encontrado")
            if plan["state"]!="PROPOSAL_ONLY": return dict(plan)
            if (plan.get('context') or {}).get('review_required') and not plan.get('context_ack'):
                raise ValueError('Revise os alertas corporativos antes de armar este plano')
            self._check_plan_config(plan)
            analysis=plan["analysis"];symbol=analysis["symbol"]
            history=self.history.get(symbol,[])
            if (not history or analysis.get("history_sha256")!=history_digest(history[-1000:])
                or s["last_sources"].get(symbol)!=analysis["source"]
                or s["last_bars"].get(symbol)!=analysis["closed_at"]
                or now!=datetime.fromisoformat(analysis["closed_at"])):
                raise ValueError("Carregue este histórico no replay e avance até o candle da análise antes de armar")
            expires=now+timedelta(seconds=analysis["seconds"]*3)
            d=Decision(symbol,analysis["side"],analysis["entry"],analysis["stop"],analysis["target"],now,expires,
                       analysis["strategy"],"Plano PAPER / "+analysis["reason"])
            spec=self.specs.get(symbol)
            qty,reason=self.risk.assess(s,d,spec,now) if spec else (0,"Unknown instrument")
            if not qty: raise ValueError("Risco bloqueou o plano: "+reason)
            plan.update(armed_at=now.isoformat(),expires=expires.isoformat(),preview_quantity=qty)
            if analysis["setup"]=="CONFIRMED":
                order=self._submit(s,d,"plan:"+key)
                plan.update(state="ORDERED" if order["status"]=="NEW" else "REJECTED",order_id=order["id"],
                            risk_approved=bool(order["qty"]),quantity=order["qty"])
            else:
                plan["state"]="ARMED"
            self.ledger.audit(now,"plan_armed",{"id":key,"state":plan["state"]})
            return dict(plan)

    def cancel_plan(self,key,now):
        with self.ledger.transaction() as s:
            plan=s["analysis_plans"][key]
            order=s["orders"].get(plan.get("order_id"))
            if order and order["status"] in ("FILLED","PARTIAL","CLOSED"):
                raise ValueError("Plano já executado; use o gerenciamento de posições PAPER")
            if order and order["status"]=="NEW":
                order["status"]="CANCELLED";order["reserved_risk"]=0.
            plan["state"]="CANCELLED"
            self.ledger.audit(now,"plan_cancelled",{"id":key})

    def process_plans(self):
        from .indicators import snapshot
        with self.ledger.transaction() as s:
            for key,plan in s.get("analysis_plans",{}).items():
                if plan["state"]!="ARMED": continue
                a=plan["analysis"];history=self.history.get(a["symbol"],[])
                if not history: continue
                b=history[-1];now=aware(b.ts)+timedelta(seconds=b.seconds)
                if now<=datetime.fromisoformat(plan["armed_at"]): continue
                if now>datetime.fromisoformat(plan["expires"]):
                    plan["state"]="EXPIRED";self.ledger.audit(now,"plan_expired",{"id":key});continue
                try:self._check_plan_config(plan)
                except ValueError:
                    plan["state"]="STALE";self.ledger.audit(now,"plan_stale",{"id":key});continue
                if b.source!=a["source"] or b.seconds!=a["seconds"]: continue
                confirmed=b.close>=a["entry"] if a["side"]=="BUY" else b.close<=a["entry"]
                if not confirmed or len(history)<35 or snapshot(history)["relative_volume"]<1.2: continue
                if self.strategy.multi_timeframe:
                    check=Strategy(a['strategy'],self.strategy.reward_r,self.strategy.stop_atr,True).evaluate(history)
                    if not check or check.side!=a['side']:continue
                d=Decision(b.symbol,a["side"],b.close,a["stop"],a["target"],now,
                           datetime.fromisoformat(plan["expires"]),a["strategy"],"Gatilho confirmado / plano PAPER")
                order=self._submit(s,d,"plan:"+key)
                plan.update(state="ORDERED" if order["status"]=="NEW" else "REJECTED",order_id=order["id"],
                            risk_approved=bool(order["qty"]),quantity=order["qty"])
                self.ledger.audit(now,"plan_triggered",{"id":key,"order_id":order["id"],"state":plan["state"]})

    def emergency(self,now,enabled=True):
        with self.ledger.transaction() as s:
            s["emergency"]=bool(enabled)
            if enabled:
                for o in s["orders"].values():
                    if o["status"]=="NEW":
                        o["status"]="CANCELLED";o["reserved_risk"]=0.;self._update_plan_order(s,o)
            self.ledger.audit(now,"emergency",{"enabled":bool(enabled),"open_positions":len(s["positions"]),"effect":"block entries; protective exits continue"})

    def connection(self,connected,now):
        with self.ledger.transaction() as s:
            s["connected"]=bool(connected)
            if not connected:
                for o in s["orders"].values():
                    if o["status"]=="NEW":
                        o["status"]="CANCELLED";o["reserved_risk"]=0.;self._update_plan_order(s,o)
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
        qty=min(qty,o["qty"],int(s.get("liquidity",{}).get(b.symbol,0)/spec.volume_per_unit*self.costs.participation)//spec.lot*spec.lot)
        if qty<spec.lot:
            o["status"]="REJECTED";o["message"]=reason if reason!="Approved" else "Insufficient simulated liquidity"
        else:
            o["filled_qty"]=qty;o["filled_price"]=price;o["filled_at"]=b.ts.isoformat();o["status"]="FILLED" if qty==o["qty"] else "PARTIAL"
            o["cancelled_qty"]=o["qty"]-qty  # IOC remainder canceled; never fills on another bar
            s["positions"][o["id"]]={"id":o["id"],"symbol":o["symbol"],"side":o["side"],"qty":qty,
                "entry":price,"stop":o["stop"],"initial_stop":o["stop"],"target":o["target"],"point_value":spec.point_value,
                "tick":spec.tick,"margin":spec.margin,"entry_fee":self.costs.fee(price,spec.point_value,qty),
                "opened_at":b.ts.isoformat(),"strategy":o["strategy"],"regime":o.get("regime","unknown"),"source":b.source}
        o["reserved_risk"]=0.
        self._update_plan_order(s,o)
        self.ledger.audit(b.ts,"execution",{"id":o["id"],"status":o["status"],"message":reason,"filled":qty})

    def _close(self,s,p,price,reason,ts):
        direction=1 if p["side"]=="BUY" else -1
        adverse=(self.costs.slippage_ticks+self.costs.spread_ticks/2)*p["tick"]
        price-=direction*adverse
        if price<=0: raise ValueError("Exit price invalid")
        gross=(price-p["entry"])*direction*p["qty"]*p["point_value"]
        fees=p["entry_fee"]+self.costs.fee(price,p['point_value'],p['qty'])
        trade={**p,"exit":price,"closed_at":ts.isoformat(),"exit_reason":reason,"gross":gross,"fees":fees,"net":gross-fees}
        s["trades"].append(trade)
        del s["positions"][p["id"]]
        s["orders"][p["id"]]["status"]="CLOSED"
        self._update_plan_order(s,s['orders'][p['id']])
        s["loss_streak"]=s["loss_streak"]+1 if trade["net"]<0 else 0
        if s["loss_streak"]>=self.limits.consecutive_losses:
            s["cooldown_until"]=(ts+timedelta(seconds=self.limits.cooldown_seconds)).isoformat()
            s["loss_streak"]=0
        self.ledger.audit(ts,"position_closed",trade)

    def on_bar(self,b:Bar,automatic=True,*,evaluate_signal=True):
        """Process one completed candle, preserving the single-symbol API."""
        return self.on_bars([b],automatic,evaluate_signal=evaluate_signal)[0]

    def on_bars(self,bars,automatic=True,*,evaluate_signal=True):
        """Process synchronized candles; entries see every open, never a current close."""
        if type(evaluate_signal) is not bool or automatic and not evaluate_signal:
            raise ValueError('History-only context cannot execute automatic entries')
        bars=sorted(list(bars),key=lambda b:b.symbol)
        if not bars: raise ValueError("No candles")
        if len({b.symbol for b in bars})!=len(bars) or len({(b.ts,b.seconds) for b in bars})!=1:
            raise ValueError("Candles must have unique symbols and synchronized intervals")
        if any(b.symbol not in self.specs for b in bars):
            raise ValueError("Unknown instrument; configure explicitly")
        with self.ledger.transaction() as s:
            if not s["connected"]: return [None]*len(bars)
            replays=[]
            for b in bars:
                previous=s["last_bars"].get(b.symbol)
                if previous and aware(b.ts)<datetime.fromisoformat(previous):
                    if s["last_ohlcv"].get(b.symbol)!=self._bar_key(b):
                        raise ValueError("Out-of-order/revised candle")
                    replays.append(b.symbol)
            if replays:
                if len(replays)==len(bars): return [None]*len(bars)
                raise ValueError("Partial replay of synchronized candles")
            sources=s["last_sources"]
            for b in bars:
                previous=s["last_bars"].get(b.symbol)
                if b.symbol in sources and sources[b.symbol]!=b.source and any(p["symbol"]==b.symbol for p in s["positions"].values()):
                    raise ValueError("Cannot change data source with an open position")
                sources[b.symbol]=b.source
                if previous and (b.ts-datetime.fromisoformat(previous)).total_seconds()>self.limits.max_data_age_seconds:
                    for o in s["orders"].values():
                        if o["symbol"]==b.symbol and o["status"]=="NEW":
                            expired=b.ts>datetime.fromisoformat(o["expires"])
                            o["status"]="REJECTED" if expired else "CANCELLED"
                            o["message"]="Expired signal" if expired else "Missing candles before next open"
                            o["reserved_risk"]=0.
                            self._update_plan_order(s,o)
                    s.setdefault("liquidity",{}).pop(b.symbol,None)
                    self.ledger.audit(b.ts,"data_gap",{"symbol":b.symbol,"previous_close":previous,
                                                        "next_open":b.ts.isoformat(),"entries_cancelled":True})
                s["marks"][b.symbol]=b.open
                s["last_bars"][b.symbol]=b.ts.isoformat()
            self.risk.block_reason(s,bars[0].ts)
            by_symbol={b.symbol:b for b in bars}
            for o in sorted(list(s["orders"].values()),key=lambda o:(o["symbol"],o["id"])):
                b=by_symbol.get(o["symbol"])
                if b is not None and o["status"]=="NEW":
                    if sources[b.symbol]!=o.get("source",b.source):
                        o["status"]="REJECTED";o["message"]="Data source changed";o["reserved_risk"]=0.
                        self._update_plan_order(s,o)
                    elif b.ts>=datetime.fromisoformat(o["signal_ts"]): self._fill(s,o,b)
            for b in bars:
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
                            rate=self.costs.fee_bps/10000.
                            slip=(self.costs.slippage_ticks+self.costs.spread_ticks/2)*p['tick']
                            # Solve fee(entry)+fee(exit)+price P&L=0, including adverse exit.
                            if direction>0 and rate>=1:continue
                            exit_price=(p['entry']*(direction+rate)+2*self.costs.fee_per_unit/p['point_value'])/(direction-rate)
                            candidate=exit_price+direction*slip
                            if (buy and candidate<b.close) or (not buy and candidate>b.close):
                                p["stop"]=max(p["stop"],candidate) if buy else min(p["stop"],candidate)
                        history=self.history.get(b.symbol,[])
                        if self.costs.trailing_atr and len(history)>=35:
                            from .indicators import snapshot
                            a=snapshot(history)["atr"]
                            candidate=b.close-direction*self.costs.trailing_atr*a
                            p["stop"]=max(p["stop"],candidate) if buy else min(p["stop"],candidate)
                        if p['strategy'] in ('sma_cross','ema_pullback') and len(history)>=50:
                            from .indicators import ema,snapshot
                            from statistics import mean
                            closed=history+[b]
                            values=[row.close for row in closed]
                            moving=mean(values[-50:]) if p['strategy']=='sma_cross' else ema(values,21)
                            buffer=snapshot(closed,full=False)['atr']*self.strategy.stop_atr*.5
                            candidate=moving-direction*buffer
                            # A protective moving stop only tightens, after this candle closes.
                            if candidate>0 and ((buy and candidate<b.close) or (not buy and candidate>b.close)):
                                p['stop']=max(p['stop'],candidate) if buy else min(p['stop'],candidate)
            for b in bars:
                s["marks"][b.symbol]=b.close
                s["last_bars"][b.symbol]=(b.ts+timedelta(seconds=b.seconds)).isoformat()
                s["last_ohlcv"][b.symbol]=self._bar_key(b)
                s.setdefault("liquidity",{})[b.symbol]=b.volume
                s["sequence"]+=1
            self.risk.block_reason(s,bars[0].ts+timedelta(seconds=bars[0].seconds))
        decisions=[]
        for b in bars:
            history=self.history.setdefault(b.symbol,[])
            history.append(b)
            del history[:-self.strategy.history_limit]
            decisions.append(self.strategy.evaluate(history) if evaluate_signal else None)
        self.last_decision=decisions[-1]
        if automatic:
            self.process_plans()
            for d in decisions:
                if d and d.side!="WAIT": self.submit(d)
        return decisions

    @staticmethod
    def _bar_key(b):
        row=[b.ts.isoformat(),b.open,b.high,b.low,b.close,b.volume,b.source,b.seconds]
        return row+b.activity() if any(value is not None for value in b.activity()) else row

    def flatten(self,now):
        """Paper liquidation at latest marks, with configured adverse exit costs."""
        with self.ledger.transaction() as s:
            for o in s["orders"].values():
                if o["status"]=="NEW":
                    o["status"]="CANCELLED";o["reserved_risk"]=0.;self._update_plan_order(s,o)
            for p in list(s["positions"].values()): self._close(s,p,s["marks"][p["symbol"]],"FLATTEN",now)
