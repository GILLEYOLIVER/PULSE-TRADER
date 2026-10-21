"""Explain closed outcomes; propose bounded development experiments, never live corrections."""
from __future__ import annotations

import math
from collections import Counter


def review_closed_trades(trades,*,costs=None,risk_budget=None):
    ids=set()
    for trade in trades:
        values=[trade.get(k) for k in ('gross','fees','net')]
        if (any(type(v) not in (int,float) or not math.isfinite(v) for v in values)
            or values[1]<0 or not math.isclose(values[0]-values[1],values[2],abs_tol=1e-7,rel_tol=1e-12)):
            raise ValueError('Closed-trade cash does not reconcile; repair accounting before research')
        if trade['id'] in ids:raise ValueError('Repeated closed trade cannot inflate an error review')
        ids.add(trade['id'])
    wins=[t for t in trades if t['net']>0];losses=[t for t in trades if t['net']<=0]
    gross=sum(t['gross'] for t in trades);fees=sum(t['fees'] for t in trades);net=sum(t['net'] for t in trades)
    average_win=sum(t['net'] for t in wins)/len(wins) if wins else None
    average_loss=-sum(t['net'] for t in losses)/len(losses) if losses else None
    break_even=(average_loss/(average_win+average_loss)
        if average_win is not None and average_loss is not None and average_win+average_loss>0 else None)
    gaps=[]
    if costs is not None:
        for trade in trades:
            if trade['exit_reason']!='STOP':continue
            expected=costs.exit_price(trade['stop'],trade['side'],trade['tick'])
            direction=1 if trade['side']=='BUY' else -1
            if direction*(trade['exit']-expected)<-1e-7:gaps.append(trade['id'])
    regimes={}
    for name in sorted({t.get('regime','unknown') for t in trades}):
        subset=[t for t in trades if t.get('regime','unknown')==name]
        regimes[name]={'trades':len(subset),'wins':sum(t['net']>0 for t in subset),'net':sum(t['net'] for t in subset)}
    findings=[]
    if trades and gross<=0:findings.append('NONPOSITIVE_GROSS_AFTER_EXECUTION')
    if gross>0 and net<=0:findings.append('COMMISSIONS_ERASE_GROSS_EDGE')
    rate=len(wins)/len(trades) if trades else None
    if break_even is not None and rate<break_even:findings.append('WIN_RATE_BELOW_OBSERVED_NET_BREAK_EVEN')
    if gaps:findings.append('ADVERSE_STOP_GAPS')
    if len(trades)<30:findings.append('INSUFFICIENT_SAMPLE_FOR_EXPERIMENT_PRIORITY')
    hypotheses=[]
    # These are predeclared members of the existing bounded grid. No new loss/risk gate.
    if len(trades)>=30:
        if any(k in findings for k in ('COMMISSIONS_ERASE_GROSS_EDGE','WIN_RATE_BELOW_OBSERVED_NET_BREAK_EVEN')):
            hypotheses.append('REWARD_COST_BALANCE')
        if 'NONPOSITIVE_GROSS_AFTER_EXECUTION' in findings:hypotheses.append('ENTRY_SELECTIVITY')
    return {'schema':1,'purpose':'POST_CLOSE_DIAGNOSTIC_NOT_CAUSAL_PROOF_OR_FORECAST',
        'trades':len(trades),'wins':len(wins),'nonpositive':len(losses),'win_rate':rate,
        'gross_after_spread_slippage':gross,'commissions':fees,'net':net,
        'mean_winner_net':average_win,'mean_nonpositive_loss':average_loss,
        'observed_net_break_even_win_rate':break_even,
        'positive_gross_but_nonpositive_net':sum(t['gross']>0 and t['net']<=0 for t in trades),
        'exits':dict(Counter(t['exit_reason'] for t in trades)),
        'losing_stop_exits':sum(t['exit_reason']=='STOP' and t['net']<0 for t in trades),
        'adverse_stop_gap_ids':gaps,
        'losses_above_initial_budget':sum(t['net']<-risk_budget-1e-7 for t in trades) if risk_budget is not None else None,
        'by_recorded_regime':regimes,'findings':findings,'development_hypotheses':hypotheses,
        'limitation':'Break-even and groups describe this sample only; outcomes cannot identify every loss cause. Fees and gaps remain real losses.'}


def development_priorities(reports):
    """Development-only feedback, kept outside feature vectors and external selection."""
    allowed=('REWARD_COST_BALANCE','ENTRY_SELECTIVITY')
    return [name for name in allowed if any(name in r.get('outcome_review',{}).get('development_hypotheses',[]) for r in reports)]
