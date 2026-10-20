from __future__ import annotations
import math
from datetime import datetime
from .models import Decision,Instrument,Limits,ExecutionSettings,aware,finite
from .session import local_time

class RiskManager:
    def __init__(self,limits: Limits,costs: ExecutionSettings,calendar=None):
        limits.validate();costs.validate()
        self.limits,self.costs,self.calendar=limits,costs,calendar

    def period_pnl(self,s,now):
        day=local_time(now).date(); week=day.isocalendar()[:2]
        pnl={"day":0.,"week":0.,"month":0.}
        for trade in s["trades"]:
            d=local_time(datetime.fromisoformat(trade["closed_at"])).date()
            if d==day: pnl["day"]+=trade["net"]
            if d.isocalendar()[:2]==week: pnl["week"]+=trade["net"]
            if (d.year,d.month)==(day.year,day.month): pnl["month"]+=trade["net"]
        # Entry fees are immediately charged; remaining liquidation costs also reserved.
        unrealized=0.;worst=0.
        for p in s["positions"].values():
            direction=1 if p["side"]=="BUY" else -1
            mark=s["marks"].get(p["symbol"],p["entry"])
            unrealized+=(mark-p["entry"])*direction*p["qty"]*p["point_value"]-p["entry_fee"]-p["qty"]*self.costs.fee_per_unit
            distance=max(0,(mark-p["stop"])*direction)
            worst+=distance*p["qty"]*p["point_value"]+p["qty"]*(self.costs.slippage_ticks+self.costs.spread_ticks/2)*p["tick"]*p["point_value"]
        return pnl,unrealized,worst

    def block_reason(self,s,now):
        l=self.limits
        if s["emergency"]: return "Emergency stop persists until explicit local reset"
        if not s["connected"]: return "Connection state unknown"
        if any(not finite(v) or v<=0 for v in s["marks"].values()): return "Invalid mark"
        # Unknown marks or changed data source must not value existing exposure.
        if any(p["symbol"] not in s["marks"] for p in s["positions"].values()): return "Missing position valuation"
        for p in s["positions"].values():
            last=s["last_bars"].get(p["symbol"])
            if not last or (now-datetime.fromisoformat(last)).total_seconds()>l.max_data_age_seconds: return "Stale position valuation"
        pnl,unrealized,worst=self.period_pnl(s,now)
        day=local_time(now).date();keys={"day":str(day),"week":str(day.isocalendar()[:2]),"month":day.strftime("%Y-%m")}
        for period,limit in (("day",l.daily_loss),("week",l.weekly_loss),("month",l.monthly_loss)):
            key=period+":"+keys[period]
            if pnl[period]+unrealized<=-limit: s["blocks"][key]="Loss limit reached"
            if key in s["blocks"]: return period+": "+s["blocks"][key]
        target="target:"+keys["day"]
        if pnl["day"]+unrealized>=l.daily_target: s["blocks"][target]="Daily target reached"
        if target in s["blocks"]: return s["blocks"][target]
        if s["cooldown_until"] and now<datetime.fromisoformat(s["cooldown_until"]): return "Consecutive loss cooldown"
        if not l.start_hour<=local_time(now).hour<l.end_hour: return "Outside configured hours"
        return None

    def assess(self,s,d:Decision,spec:Instrument,now:datetime,entry=None,requested=None,exclude=None):
        now=aware(now);l=self.limits;c=self.costs
        # Validate again because UI/config callers can mutate dataclass instances.
        l.validate();c.validate()
        reason=self.block_reason(s,now)
        if reason: return 0,reason
        if d.symbol!=spec.symbol or d.symbol not in l.allowed_symbols or d.strategy not in l.allowed_strategies: return 0,"Asset or strategy not authorized"
        if self.calendar is not None and not self.calendar.is_open(now,d.symbol):
            return 0,"Outside user-verified session or calendar unavailable"
        if d.side not in ("BUY","SELL") or not finite(d.price,d.stop,d.target) or min(d.price,d.stop,d.target)<=0: return 0,"Invalid decision"
        if not aware(d.ts)<=now<=aware(d.expires): return 0,"Expired or future signal"
        last=s["last_bars"].get(d.symbol)
        if not last or not 0<=(now-datetime.fromisoformat(last)).total_seconds()<=l.max_data_age_seconds: return 0,"Stale or missing market data"
        if c.spread_ticks>l.max_spread_ticks or c.slippage_ticks>l.max_slippage_ticks: return 0,"Spread or slippage exceeds limit"
        if spec.expiry and local_time(now).date()>=datetime.fromisoformat(spec.expiry).date(): return 0,"Expired contract"
        entry=d.price if entry is None else entry
        if not finite(entry) or entry<=0: return 0,"Invalid entry price"
        direction=1 if d.side=="BUY" else -1
        if (entry-d.stop)*direction<=0 or (d.target-entry)*direction<=0: return 0,"Stop or target on wrong side of entry"
        pending=[o for k,o in s["orders"].items() if k!=exclude and o["status"] == "NEW"]
        positions=list(s["positions"].values())
        if any(p["symbol"]==d.symbol for p in positions) or any(o["symbol"]==d.symbol for o in pending): return 0,"Existing exposure for symbol"
        if len(positions)+len(pending)>=l.max_positions: return 0,"Maximum positions"
        day=local_time(now).date()
        today=sum(local_time(datetime.fromisoformat(o.get("filled_at",o["created_at"]))).date()==day for o in s["orders"].values() if o["status"] in ("FILLED","PARTIAL","CLOSED"))
        if today+len(pending)>=l.max_trades: return 0,"Daily trade count"
        cash_risk=abs(entry-d.stop)*spec.point_value+2*c.fee_per_unit+(c.spread_ticks/2+c.slippage_ticks)*spec.tick*spec.point_value
        # At submission reserve entry slippage too; at execution entry already contains it.
        if entry==d.price: cash_risk+=(c.spread_ticks/2+c.slippage_ticks)*spec.tick*spec.point_value
        pnl,unrealized,worst=self.period_pnl(s,now)
        reserved=sum(o["reserved_risk"] for o in pending)
        budget=min(l.capital*l.risk_fraction,l.daily_loss+pnl["day"]+unrealized-worst-reserved,
            l.weekly_loss+pnl["week"]+unrealized-worst-reserved,l.monthly_loss+pnl["month"]+unrealized-worst-reserved)
        qty=math.floor(max(0,budget)/cash_risk/spec.lot)*spec.lot
        used_margin=sum(p["margin"]*p["qty"] for p in positions)+sum(o["margin"]*o["qty"] for o in pending)
        balance=l.capital+sum(t["net"] for t in s["trades"])+unrealized
        qty=min(qty,math.floor(max(0,balance-used_margin)/spec.margin/spec.lot)*spec.lot,l.max_contracts//spec.lot*spec.lot)
        exposure=sum(abs(s["marks"].get(p["symbol"],p["entry"])*p["qty"]*p["point_value"]) for p in positions)+sum(o["price"]*o["qty"]*o["point_value"] for o in pending)
        qty=min(qty,math.floor(max(0,l.max_exposure-exposure)/(entry*spec.point_value)/spec.lot)*spec.lot)
        if requested is not None:
            if not finite(requested) or requested<spec.lot or requested%spec.lot: return 0,"Invalid lot quantity"
            if requested>qty: return 0,"Requested quantity exceeds risk budget"
            qty=int(requested)
        return (qty,"Approved") if qty>=spec.lot else (0,"Budget below minimum lot")
