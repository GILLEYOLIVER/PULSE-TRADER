from __future__ import annotations
import hashlib
import json
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
from .data import export_csv
from .execution import PaperEngine
from .ledger import Ledger
from .models import Limits,ExecutionSettings
from .strategy import Strategy

def metrics(trades,capital,equity=None):
    results=[t["net"] for t in trades]
    gains=sum(max(0,x) for x in results);losses=-sum(min(0,x) for x in results)
    peak=capital;dd=0.;balance=capital
    curve=equity if equity is not None else []
    if equity is None:
        for net in results: balance+=net;curve.append(balance)
    for value in curve: peak=max(peak,value);dd=max(dd,peak-value)
    return {"trades":len(results),"win_rate":sum(x>0 for x in results)/len(results) if results else 0.,
        "profit_factor":gains/losses if losses else None,"expectancy":sum(results)/len(results) if results else 0.,
        "net":sum(results),"fees":sum(t["fees"] for t in trades),"max_drawdown":dd,
        "return_fraction":sum(results)/capital,"profit_factor_note":"undefined without losing trades" if not losses else ""}

def run_backtest(bars,strategy=None,limits=None,costs=None,calendar=None):
    if not bars: raise ValueError("No data")
    if len({b.symbol for b in bars})!=1: raise ValueError("Synchronized portfolio backtesting not implemented; use one symbol per run")
    previous={};sources={};timeframes={}
    for b in bars:
        if b.symbol in previous and b.ts<previous[b.symbol]: raise ValueError("Overlapping or unsorted history")
        if b.symbol in sources and sources[b.symbol]!=b.source: raise ValueError("Mixed source per symbol")
        if b.symbol in timeframes and timeframes[b.symbol]!=b.seconds: raise ValueError("Mixed timeframes per symbol")
        previous[b.symbol]=b.ts+timedelta(seconds=b.seconds);sources[b.symbol]=b.source;timeframes[b.symbol]=b.seconds
    if bars!=sorted(bars,key=lambda b:(b.ts,b.symbol)): raise ValueError("Globally unsorted history")
    ledger=Ledger();engine=PaperEngine(ledger,limits,costs,strategy=strategy,calendar=calendar)
    equity=[]
    digest=hashlib.sha256()
    for b in bars:
        digest.update(json.dumps(engine._bar_key(b)+[b.symbol],separators=(",",":")).encode())
        engine.on_bar(b)
        state=ledger.read()
        _,unrealized,_=engine.risk.period_pnl(state,b.ts+timedelta(seconds=b.seconds))
        equity.append(engine.limits.capital+sum(t["net"] for t in state["trades"])+unrealized)
    end=max(b.ts+timedelta(seconds=b.seconds) for b in bars)
    engine.flatten(end)
    state=ledger.read()
    equity.append(engine.limits.capital+sum(t["net"] for t in state["trades"]))
    first,last=bars[0],bars[-1]
    same=[b for b in bars if b.symbol==first.symbol]
    spec=engine.specs[first.symbol]
    # Non-leveraged one-lot price benchmark; not equivalent risk to the strategy.
    benchmark=(same[-1].close-same[0].open)*spec.point_value*spec.lot-2*spec.lot*engine.costs.fee_per_unit
    result={"version":2,"mode":"BACKTEST_PAPER","data_sha256":digest.hexdigest(),"sources":sources,
        "bars":len(bars),"start":first.ts.isoformat(),"end":end.isoformat(),"strategy":engine.strategy.name,
        "parameters":{"reward_r":engine.strategy.reward_r,"stop_atr":engine.strategy.stop_atr,"multi_timeframe":engine.strategy.multi_timeframe},
        "calendar":calendar.to_config() if calendar is not None else None,
        "limits":asdict(engine.limits),"execution":asdict(engine.costs),"metrics":metrics(state["trades"],engine.limits.capital,equity),
        "benchmark":{"symbol":first.symbol,"one_lot_buy_hold_net":benchmark,"note":"one lot, no rollover; not risk matched"},
        "by_regime":{regime:metrics([t for t in state["trades"] if t["regime"]==regime],engine.limits.capital) for regime in ("trend","range","volatile")},
        "by_strategy":{engine.strategy.name:metrics(state["trades"],engine.limits.capital)},
        "orders":list(state["orders"].values()),"trades":state["trades"],"equity":equity,
        "limitations":["Synthetic results are not market evidence","OHLC cannot determine intrabar path; stop first",
            "Fees and margins are simulation inputs","No queue priority, auction, exchange halts, tax or official rollover modelling"]}
    ledger.close()
    return result

def temporal_split(bars,train=.6,validation=.2):
    if not 0<train<1 or not 0<validation<1 or train+validation>=1: raise ValueError("Invalid split")
    # Split by timestamps so all assets at a timestamp stay in the same partition.
    stamps=sorted({b.ts for b in bars})
    a=int(len(stamps)*train);b=int(len(stamps)*(train+validation))
    if not 0<a<b<len(stamps): raise ValueError("Insufficient history")
    return tuple([x for x in bars if lo<=x.ts<hi] for lo,hi in ((stamps[0],stamps[a]),(stamps[a],stamps[b]),(stamps[b],stamps[-1]+timedelta(days=1))))

def walk_forward(bars,train_bars=200,test_bars=100,calendar=None):
    if train_bars<35 or test_bars<35: raise ValueError("Windows too short")
    if len({b.symbol for b in bars})!=1: raise ValueError("Walk-forward currently supports one symbol")
    folds=[]
    for split in range(train_bars,len(bars)-test_bars+1,test_bars):
        training=bars[split-train_bars:split];testing=bars[split:split+test_bars]
        candidates=[run_backtest(training,Strategy("trend",reward_r=r),calendar=calendar) for r in (1.5,2.,2.5)]
        best=max(candidates,key=lambda r:r["metrics"]["net"])
        result=run_backtest(testing,Strategy("trend",reward_r=best["parameters"]["reward_r"]),calendar=calendar)
        folds.append({"train_end":training[-1].ts.isoformat(),"test_start":testing[0].ts.isoformat(),"selected_reward_r":best["parameters"]["reward_r"],"test_metrics":result["metrics"]})
    return folds

def save_report(report,path):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False),encoding="utf-8")


def sensitivity(bars,calendar=None):
    """Fixed parameter grid only; not a signal that any candidate should be deployed."""
    return [{"reward_r":rr,"stop_atr":stop,"metrics":run_backtest(bars,Strategy("trend",rr,stop),calendar=calendar)["metrics"]}
        for rr in (1.5,2.,2.5) for stop in (1.,1.5,2.)]
