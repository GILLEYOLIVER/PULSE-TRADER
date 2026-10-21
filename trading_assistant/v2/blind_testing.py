"""Evaluator-owned replay. The engine receives a closed bar, never scenario labels or future bars."""
from __future__ import annotations
import json
import math
import random
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
from .backtest import metrics
from .execution import PaperEngine
from .ledger import SimulationLedger
from .learning import digest


def block_bootstrap(values,*,samples=500,block=5,seed=317):
    """Descriptive moving-block interval; small samples never qualify a strategy."""
    if not values:return {'count':0,'mean_interval_95':None,'enough_trades':False}
    rng=random.Random(seed);size=len(values);block=min(block,size);means=[]
    for _ in range(samples):
        draw=[]
        while len(draw)<size:
            start=rng.randrange(size)
            draw.extend(values[(start+offset)%size] for offset in range(block))
        means.append(sum(draw[:size])/size)
    means.sort()
    return {'count':size,'block':block,'samples':samples,'seed':seed,
        'mean_interval_95':[means[int(samples*.025)],means[min(samples-1,int(samples*.975))]],
        'enough_trades':size>=30,'limitation':'Descriptive interval under block resampling; not proof of future performance'}


def blind_replay(stream,*,strategy,limits,costs,instruments,trace_path=None,warmup=(),retain_trace=True,bootstrap=True):
    if trace_path is not None and not retain_trace:raise ValueError('An audit export requires retaining decisions')
    ledger=SimulationLedger()
    engine=PaperEngine(ledger,limits,costs,instruments,strategy)
    prior=None;warmup_count=0
    for item in warmup:
        engine.on_bar(item,automatic=False,evaluate_signal=False);prior=item;warmup_count+=1
    trace=[];previous_orders={};checked_fills=set();known_trades=0;equity=[];bars_seen=0;realized=0.
    checks={'closed_information_only':True,'unique_fills':True,'fees_reconcile':True,
        'initial_risk_within_budget':True,'instrument_permissions':True}
    # No list/len/index interface is exposed to PaperEngine; consume one item at a time.
    last=None
    for item in iter(stream):
        bars_seen+=1
        if last is None and prior is not None and prior.ts+timedelta(seconds=prior.seconds)>item.ts:
            raise ValueError('Warmup overlaps the blind evaluation')
        last=item
        decision=engine.on_bar(item)
        state=ledger.read()
        boundary=item.ts+timedelta(seconds=item.seconds)
        if decision:checks['closed_information_only'] &= decision.ts==boundary
        changes=[]
        for key,order in state['orders'].items():
            signature=(order['status'],order.get('filled_qty'),order.get('filled_price'))
            if retain_trace and previous_orders.get(key)!=signature:
                changes.append({name:order.get(name) for name in ('id','symbol','side','status','message','qty','filled_qty','filled_at','signal_ts')})
                previous_orders[key]=signature
            fill=(key,order.get('filled_qty'),order.get('filled_price'),order.get('stop'))
            if order.get('filled_qty') and fill not in checked_fills:
                checked_fills.add(fill)
                spec=instruments[order['symbol']]
                entry=order['filled_price'];qty=order['filled_qty']
                loss=costs.stop_loss(entry,order['stop'],order['side'],spec.point_value,spec.tick,qty)
                checks['initial_risk_within_budget'] &= loss<=limits.capital*limits.risk_fraction+1e-7
                checks['instrument_permissions'] &= (order['side']!='SELL' or spec.allow_short) and spec.currency==limits.currency
        new=state['trades'][known_trades:];known_trades=len(state['trades'])
        realized+=sum(t['net'] for t in new)
        for trade in new:
            checks['fees_reconcile'] &= math.isclose(trade['gross']-trade['fees'],trade['net'],abs_tol=1e-7)
            checks['fees_reconcile'] &= math.isclose(trade['fees'],costs.fee(trade['entry'],trade['point_value'],trade['qty'])
                +costs.fee(trade['exit'],trade['point_value'],trade['qty']),abs_tol=1e-7)
        _,unrealized,_=engine.risk.period_pnl(state,boundary)
        equity.append(limits.capital+realized+unrealized)
        if retain_trace:trace.append({'closed_at':boundary.isoformat(),'observations_seen':warmup_count+bars_seen,
            'signal':None if decision is None else {'side':decision.side,'reason':decision.reason,
                'entry':decision.price,'stop':decision.stop,'target':decision.target,'inputs':dict(decision.indicators)},
            'order_changes':changes,'exits':[{'id':t['id'],'reason':t['exit_reason'],'net':t['net']} for t in new],
            'positions':len(state['positions']),'emergency':state['emergency']})
    if last is None:raise ValueError('Empty blind stream')
    engine.flatten(last.ts+timedelta(seconds=last.seconds))
    state=ledger.read()
    checks['unique_fills']=len({t['id'] for t in state['trades']})==len(state['trades'])
    for trade in state['trades']:
        checks['fees_reconcile'] &= math.isclose(trade['gross']-trade['fees'],trade['net'],abs_tol=1e-7)
        checks['fees_reconcile'] &= math.isclose(trade['fees'],costs.fee(trade['entry'],trade['point_value'],trade['qty'])
            +costs.fee(trade['exit'],trade['point_value'],trade['qty']),abs_tol=1e-7)
    # Flatten can create an exit after the last observed candle; preserve it explicitly.
    final_exits=[{'id':t['id'],'reason':t['exit_reason'],'net':t['net']} for t in state['trades'][known_trades:]]
    equity.append(limits.capital+sum(t['net'] for t in state['trades']))
    result={'mode':'BLIND_PAPER_EVALUATION','bars':bars_seen,'warmup_bars':warmup_count,'parameters':asdict(strategy),
        'metrics':metrics(state['trades'],limits.capital,equity),'checks':checks,
        'passed':all(checks.values()),'trace_sha256':digest(trace) if retain_trace else None,'final_exits':final_exits,
        'order_count':len(state['orders']),'rejected_orders':sum(o['status']=='REJECTED' for o in state['orders'].values()),
        'reason_counts':{},'execution_enabled':False}
    result['uncertainty']=block_bootstrap([trade['net'] for trade in state['trades']]) if bootstrap else {'calculated':False}
    for order in state['orders'].values():
        if order['status']=='REJECTED':
            reason=order['message'];result['reason_counts'][reason]=result['reason_counts'].get(reason,0)+1
    if trace_path:
        path=Path(trace_path);path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('w',encoding='utf-8') as out:
            for row in trace:out.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
        result['trace_path']=str(path)
    ledger.close()
    return result,trace
