"""Reproducible synthetic accounting stress; never market/accuracy evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import Counter
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path

from trading_assistant.v2.execution import PaperEngine
from trading_assistant.v2.ledger import SimulationLedger
from trading_assistant.v2.models import Bar,Decision,ExecutionSettings,Instrument,Limits


def run(cases=10000,seed=20261021):
    if type(cases) is not int or not 1<=cases<=100000:raise ValueError('Cases must be 1..100000')
    rng=random.Random(seed);counts=Counter();rejections=Counter();failures=[];examples=[];largest=0.
    start=datetime(2026,1,5,12,tzinfo=timezone.utc)
    for index in range(cases):
        side='BUY' if index%2==0 else 'SELL';direction=1 if side=='BUY' else -1
        tick=rng.choice((.0001,.01,.1,.5,5.));quote=rng.uniform(1000,100000)*tick
        distance=max(12*tick,quote*.01)*rng.uniform(.5,3.)
        stop=quote-direction*distance;target=quote+direction*distance*2.5
        spec=Instrument('WDO',rng.choice((.0001,.01,.2,1.,10.,50.)),tick,
            lot=rng.choice((1,5,100)),margin=rng.choice((.1,1.,100.)))
        costs=ExecutionSettings(spread_ticks=rng.choice((0.,.5,1.,3.)),
            slippage_ticks=rng.choice((0.,.25,1.,2.)),fee_per_unit=rng.choice((0.,.001,.5,2.5)),
            fee_bps=rng.choice((0.,1.,10.,50.)),participation=1.)
        budget=rng.uniform(25,10000)
        limits=replace(Limits(),capital=1000000.,risk_fraction=budget/1000000.,
            daily_loss=20000.,weekly_loss=50000.,monthly_loss=100000.,daily_target=20000.,
            max_contracts=1000000,max_exposure=2000000.,min_net_reward_r=rng.choice((0.,.25,1.)))
        opened=quote+rng.uniform(-.2,.2)*distance
        # Both sides receive ordinary stop touches and deliberate adverse exit gaps.
        gap=index%20 in (0,1)
        ledger=SimulationLedger()
        def bar(n,price,high=None,low=None):
            return Bar('WDO',start+timedelta(minutes=n),price,
                price if high is None else high,price if low is None else low,price,
                1e12,'SYNTHETIC_CASH_STRESS',60)
        def net_at(entry,exit,qty):
            # Independent arithmetic, without the production pricing/cashflow helpers.
            fees=qty*(2*costs.fee_per_unit+(entry+exit)*spec.point_value*costs.fee_bps/10000.)
            return (exit-entry)*direction*qty*spec.point_value-fees,fees
        try:
            engine=PaperEngine(ledger,limits,costs,{'WDO':spec})
            engine.on_bar(bar(0,quote),False)
            d=Decision('WDO',side,quote,stop,target,start+timedelta(minutes=1),
                start+timedelta(minutes=4),'trend','synthetic accounting stress')
            order=engine.submit(d);adverse=(costs.spread_ticks/2+costs.slippage_ticks)*tick
            if not order['qty']:
                counts['submission_rejected']+=1;rejections[order['message']]+=1;continue
            forecast=(math.ceil((quote+direction*adverse)/tick) if direction>0
                else math.floor((quote+direction*adverse)/tick))*tick
            expected_reserve=-net_at(forecast,stop-direction*adverse,order['qty'])[0]
            assert math.isclose(order['reserved_risk'],expected_reserve,abs_tol=1e-7,rel_tol=1e-10)
            assert expected_reserve<=budget+1e-7
            assert math.isclose(order['reserved_exposure'],forecast*order['qty']*spec.point_value,rel_tol=1e-12)
            counts['reservations_checked']+=1
            engine.on_bar(bar(1,opened),False)
            state=ledger.read()
            if not state['positions']:
                counts['fill_rejected']+=1;rejections[state['orders'][order['id']]['message']]+=1;continue
            p=next(iter(state['positions'].values()));qty=p['qty'];entry=p['entry']
            assert qty%spec.lot==0 and 0<qty<=min(order['qty'],limits.max_contracts)
            assert entry*qty*spec.point_value<=limits.max_exposure+1e-7
            assert qty*spec.margin<=limits.capital+1e-7
            stop_net,_=net_at(entry,stop-direction*adverse,qty)
            target_net,_=net_at(entry,target-direction*adverse,qty)
            assert target_net/(-stop_net)>=limits.min_net_reward_r-1e-10 or not limits.min_net_reward_r
            assert state['orders'][order['id']]['reserved_exposure']==0.
            assert state['orders'][order['id']]['reserved_risk']==0.
            # No gap in ordinary cases; open remains between entry and stop.
            exit_open=stop-direction*distance*4 if gap else (opened+stop)/2
            engine.on_bar(bar(2,exit_open,high=max(exit_open,stop+tick),low=min(exit_open,stop-tick)),False)
            trade=ledger.read()['trades'][0]
            exit_quote=min(exit_open,stop) if direction>0 else max(exit_open,stop)
            expected_net,expected_fees=net_at(entry,exit_quote-direction*adverse,qty)
            assert trade['exit_reason']=='STOP'
            assert math.isclose(trade['net'],expected_net,abs_tol=1e-7,rel_tol=1e-10)
            assert math.isclose(trade['fees'],expected_fees,abs_tol=1e-7,rel_tol=1e-10)
            counts[side.lower()+'_closed']+=1
            if gap:
                counts['exit_gaps_checked']+=1
                if -trade['net']>budget+1e-7:counts['gap_losses_above_budget_preserved']+=1
            else:
                assert -trade['net']<=budget+1e-7
                counts['ordinary_stops_within_budget']+=1
                largest=max(largest,-trade['net']/budget)
            if len(examples)<6:examples.append({'index':index,'side':side,'exit_gap':gap,
                'budget':budget,'quantity':qty,'entry':entry,'stop':stop,'exit':trade['exit'],
                'fees':trade['fees'],'net':trade['net']})
        except Exception as error:
            failures.append({'index':index,'side':side,'error':repr(error),'quote':quote,
                'stop':stop,'tick':tick,'budget':budget})
        finally:ledger.close()
    root=Path(__file__).resolve().parents[1]
    paths=[Path(__file__).resolve()]+[root/'trading_assistant'/'v2'/name
        for name in ('models.py','risk.py','execution.py','blind_testing.py','ledger.py')]
    return {'ok':not failures,'purpose':'SYNTHETIC_ACCOUNTING_ONLY_NOT_MARKET_EVIDENCE',
        'created_at':datetime.now(timezone.utc).isoformat(),'seed':seed,'cases':cases,
        'counts':dict(counts),'rejections':dict(rejections),'failures':failures,
        'maximum_ordinary_loss_to_budget':largest,'examples':examples,
        'source_sha256':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases',type=int,default=10000);parser.add_argument('--seed',type=int,default=20261021)
    parser.add_argument('--output',type=Path,default=Path('reports/numeric-risk-stress.json'))
    args=parser.parse_args();report=run(args.cases,args.seed)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('ok','purpose','cases','counts','rejections','maximum_ordinary_loss_to_budget')}))
    if not report['ok']:raise SystemExit(1)


if __name__=='__main__':main()
