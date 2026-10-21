"""Fixed train/selection/blind protocol, public data, two CPU workers, local learning memory."""
from __future__ import annotations
import argparse
import json
import multiprocessing
import subprocess
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict,replace
from datetime import datetime,timedelta
from pathlib import Path

from trading_assistant.v2.backtest import run_backtest,save_report
from trading_assistant.v2.blind_testing import blind_replay
from trading_assistant.v2.data import CSVProvider
from trading_assistant.v2.learning import LearningMemory,digest
from trading_assistant.v2.market_data import fetch_binance
from trading_assistant.v2.ml import train_temporal
from trading_assistant.v2.models import UTC,Limits,ExecutionSettings,Instrument
from trading_assistant.v2.strategy import Strategy
from trading_assistant.v2.suggestions import history_digest


def assumptions(symbol):
    unit=.0001 if symbol=='BTCUSDT' else .001
    reserve=15. if symbol=='BTCUSDT' else 10.
    limits=replace(Limits(),currency='USDT',capital=100000.,daily_loss=2000.,weekly_loss=5000.,
        monthly_loss=10000.,daily_target=3000.,max_positions=1,max_contracts=1000000,
        max_exposure=100000.,allowed_symbols=(symbol,),allowed_strategies=('trend','breakout','pullback','adaptive'),
        min_net_reward_r=1.1)
    costs=ExecutionSettings(fee_per_unit=0.,fee_bps=10.,spread_ticks=1.,slippage_ticks=1.)
    specs={symbol:Instrument(symbol,unit,.01,1,reserve,'USDT',allow_short=False,volume_per_unit=unit)}
    return limits,costs,specs


def candidate_run(task):
    bars,name,reward=task
    limits,costs,specs=assumptions(bars[0].symbol)
    a,b=int(len(bars)*.6),int(len(bars)*.8)
    folds=[run_backtest(part,Strategy(name,reward),limits,costs,instruments=specs)['metrics']
        for part in (bars[a:b],bars[b:])]
    return {'parameters':asdict(Strategy(name,reward)), 'folds':folds,
        'score':sum(row['net']-.1*row['max_drawdown'] for row in folds),
        'trades':sum(row['trades'] for row in folds)}


def train_policy(bars,profile,output,memory,workers,code):
    data_sha=history_digest(bars)
    # Reuse only an identical development dataset/protocol; external evaluations are never read here.
    existing=[row['payload'] for row in memory.training_records() if row['kind']=='SEALED_POLICY'
        and row['payload'].get('dataset_sha256')==data_sha and row['payload'].get('code_id')==code]
    if existing:return existing[-1]
    tasks=[(bars,name,reward) for name in ('trend','breakout','pullback','adaptive') for reward in (1.5,2.,2.5)]
    if workers>1:
        with ProcessPoolExecutor(max_workers=workers) as pool:results=list(pool.map(candidate_run,tasks))
    else:results=[candidate_run(task) for task in tasks]
    for result in results:memory.append('VALIDATION',{'profile':profile,'dataset_sha256':data_sha,'code_id':code,**result})
    winner=max(results,key=lambda row:row['score'] if row['trades']>=5 else float('-inf'))
    model_path=output/(profile+'-model-v2.json')
    model=train_temporal(bars,model_path,feature_set='regime_flow_v2')
    memory.remember_model(bars,model,model_path)
    legacy=train_temporal(bars,output/(profile+'-model-baseline.json'))
    policy={'schema':1,'profile':profile,'code_id':code,'dataset_sha256':data_sha,
        'development_last_open':bars[-1].ts.isoformat(),'parameters':winner['parameters'],
        'selection_rule':'maximum sum(validation net - 0.1 * drawdown) across two chronological folds, >=5 trades',
        'candidates':results,'model_sha256':model['sha256'],
        'model_comparison':{'legacy':legacy['test'],'enriched':model['test']},
        'candidate_only':True,'automatic_adoption':False}
    policy['sha256']=digest(policy)
    memory.append('SEALED_POLICY',policy)
    save_report(policy,output/(profile+'-policy.json'))
    registry=memory.directory/'policies';registry.mkdir(exist_ok=True)
    save_report(policy,registry/(profile+'-'+policy['sha256'][:12]+'.json'))
    return policy


def get_data(symbol,seconds,start,end,output,*,allow_gaps=False):
    name=f'{symbol}-{seconds}-{start}-{end}'
    cache=output/'data'/name
    cache.mkdir(parents=True,exist_ok=True)
    manifest=cache/'manifest.json'
    if manifest.exists():
        provenance=json.loads(manifest.read_text(encoding='utf-8'))
        if provenance.get('missing_candles',0) and not allow_gaps:raise ValueError('Cached history has disclosed gaps; explicit permission required')
        bars=CSVProvider(cache/provenance['csv']).bars()
        if history_digest(bars)!=provenance['sha256']:raise ValueError('Dataset cache checksum mismatch')
        return bars
    market=fetch_binance(symbol,seconds,start=datetime.fromisoformat(start).replace(tzinfo=UTC),
        end=datetime.fromisoformat(end).replace(tzinfo=UTC),allow_gaps=allow_gaps)
    if market.provenance['missing_candles']/market.provenance['expected_candles']>.05:
        raise ValueError('Mais de 5% do intervalo sem candles; janela não qualifica e não será preenchida')
    path=market.save(cache)
    save_report({**market.provenance,'csv':path.name},manifest)
    print(f'Download {symbol} {seconds}s: {len(market.bars)} candles',flush=True)
    return market.bars


def perturb(bars,kind):
    # Evaluator-only transformation. Generic source hides the scenario identity from the engine.
    result=[];cut=len(bars)//2
    for index,b in enumerate(bars):
        if kind=='missing_bars' and cut<=index<cut+5:continue
        factor=.88 if kind=='gap_down' and index>=cut else 1.12 if kind=='gap_up' and index>=cut else 1.
        if kind=='false_breakout' and cut<=index<cut+3:factor=1.035
        row=replace(b,open=b.open*factor,high=b.high*factor,low=b.low*factor,close=b.close*factor,
            quote_volume=None if b.quote_volume is None else b.quote_volume*factor,source='EVALUATION_STREAM')
        if kind=='volume_drought' and cut<=index<cut+24:
            row=replace(row,volume=0.,quote_volume=0.,trades=0,taker_buy_volume=0.)
        if kind=='wide_wick' and index==cut:
            row=replace(row,low=row.low*.85,high=row.high*1.15)
        if kind=='hostile_flow' and cut<=index<cut+48:row=replace(row,taker_buy_volume=0.)
        result.append(row)
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='reports/engine-upgrade/blind')
    parser.add_argument('--memory',default='runtime/aprendizado')
    parser.add_argument('--workers',type=int,choices=(1,2,3,4),default=2)
    parser.add_argument('--supplemental-exposure',action='store_true',help='Reuse frozen policies, add ETH adverse scenarios and cost stress; never retrain')
    args=parser.parse_args()
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    memory=LearningMemory(args.memory)
    sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    # Include uncommitted tracked changes, so a development run has an exact code fingerprint.
    paths=sorted(path for folder in ('trading_assistant/v2','scripts') for path in Path(folder).glob('*.py'))
    code=sha+':'+digest({str(path):path.read_text(encoding='utf-8') for path in paths})
    if args.supplemental_exposure:
        supplemental(output,memory,code)
        return
    daily=get_data('BTCUSDT',86400,'2020-01-01','2026-01-01',output)
    intraday=get_data('BTCUSDT',300,'2025-09-01','2025-09-16',output)
    daily_train=[b for b in daily if b.ts.year<2024]
    intra_cut=datetime(2025,9,10,tzinfo=UTC)
    intra_train=[b for b in intraday if b.ts<intra_cut]
    policies={profile:train_policy(bars,profile,output,memory,args.workers,code)
        for profile,bars in (('daily',daily_train),('intraday',intra_train))}
    # Holdout and another asset are touched only after both policies are frozen.
    eth_daily=get_data('ETHUSDT',86400,'2024-01-01','2026-01-01',output)
    eth_intraday=get_data('ETHUSDT',300,'2025-09-10','2025-09-16',output)
    cases=[('btc_daily_real','daily',[b for b in daily if b.ts.year>=2024],'real_history'),
        ('eth_daily_real','daily',eth_daily,'real_history'),
        ('btc_intraday_real','intraday',[b for b in intraday if b.ts>=intra_cut],'real_history'),
        ('eth_intraday_real','intraday',eth_intraday,'real_history')]
    base=[b for b in intraday if b.ts>=intra_cut]
    cases += [(kind,'intraday',perturb(base,kind),'synthetic_perturbation_of_real_history')
        for kind in ('gap_down','gap_up','missing_bars','volume_drought','wide_wick','false_breakout','hostile_flow')]
    save_report({'code_id':code,'policies':{key:value['sha256'] for key,value in policies.items()},
        'cases':[{'name':name,'profile':profile,'sha256':history_digest(bars),'type':kind} for name,profile,bars,kind in cases]},output/'sealed-evaluation-manifest.json')
    results=[]
    for name,profile,bars,kind in cases:
        limits,costs,specs=assumptions(bars[0].symbol)
        variants={'baseline':Strategy('trend'),'trained':Strategy(**policies[profile]['parameters']),'adaptive':Strategy('adaptive')}
        for variant,strategy in variants.items():
            report,trace=blind_replay(iter(bars),strategy=strategy,limits=limits,costs=costs,instruments=specs,
                trace_path=output/'decisions'/f'{name}-{variant}.jsonl')
            report.update(case=name,variant=variant,data_type=kind,profile=profile,code_id=code,
                dataset_sha256=history_digest(bars),policy_sha256=policies[profile]['sha256'])
            memory.append('BLIND_TEST',report)
            save_report(report,output/(name+'-'+variant+'.json'))
            results.append(report)
        print(f'Blind case {name}: '+str([r['metrics']['trades'] for r in results[-3:]])+' trades',flush=True)
    # Suffix independence: a new evaluator changes only future candles, then compares prefix decisions.
    altered=perturb(base,'gap_down');cut=len(base)//2
    args2=dict(strategy=Strategy(**policies['intraday']['parameters']),limits=assumptions(base[0].symbol)[0],
        costs=assumptions(base[0].symbol)[1],instruments=assumptions(base[0].symbol)[2])
    _,left=blind_replay(iter(perturb(base,'normal')),**args2)
    _,right=blind_replay(iter(altered),**args2)
    prefix_equal=left[:cut]==right[:cut]
    summary={'code_id':code,'passed':all(row['passed'] for row in results) and prefix_equal,
        'scenarios':len(cases),'runs':len(results),'decisions':sum(row['bars'] for row in results),
        'future_suffix_does_not_change_past_decisions':prefix_equal,'results':results,
        'automatic_adoption':False,'user_paper_session_changed':False,
        'assumptions':'USDT, spot BUY-only, units 0.0001 BTC / 0.001 ETH, 10 bps per side, fixed capital reserve per unit; research assumptions, not official exchange filters or tariffs'}
    save_report(summary,output/'summary.json')
    print(json.dumps({key:value for key,value in summary.items() if key!='results'}),flush=True)
    if not summary['passed']:raise SystemExit(1)


def supplemental(output,memory,code):
    policies={}
    for profile in ('daily','intraday'):
        policy=json.loads((output/(profile+'-policy.json')).read_text(encoding='utf-8'))
        value=dict(policy);expected=value.pop('sha256')
        if digest(value)!=expected:raise ValueError('Frozen policy checksum mismatch')
        policies[profile]=policy
    base=get_data('ETHUSDT',300,'2025-09-10','2025-09-16',output)
    results=[]
    for kind in ('normal','gap_down','gap_up','missing_bars','volume_drought','wide_wick','false_breakout','hostile_flow'):
        bars=perturb(base,kind);limits,costs,specs=assumptions('ETHUSDT')
        for variant,strategy in {'baseline':Strategy('trend'),'trained':Strategy(**policies['intraday']['parameters']),'adaptive':Strategy('adaptive')}.items():
            result,_=blind_replay(iter(bars),strategy=strategy,limits=limits,costs=costs,instruments=specs,
                trace_path=output/'decisions'/f'supplemental-{kind}-{variant}.jsonl')
            result.update(case='supplemental_eth_'+kind,variant=variant,code_id=code,
                dataset_sha256=history_digest(bars),policy_sha256=policies['intraday']['sha256'],
                purpose='Additional exposure coverage; parameters frozen before original evaluation; no retuning')
            memory.append('BLIND_TEST',result);results.append(result)
        print(f'Supplemental ETH {kind}: '+str([row['metrics']['trades'] for row in results[-3:]]),flush=True)
    for symbol,seconds,start,end,profile in (
        ('BTCUSDT',86400,'2024-01-01','2026-01-01','daily'),
        ('ETHUSDT',86400,'2024-01-01','2026-01-01','daily'),
        ('BTCUSDT',300,'2025-09-10','2025-09-16','intraday'),
        ('ETHUSDT',300,'2025-09-10','2025-09-16','intraday')):
        bars=get_data(symbol,seconds,start,end,output)
        limits,costs,specs=assumptions(symbol)
        costs=replace(costs,fee_bps=costs.fee_bps*2,slippage_ticks=costs.slippage_ticks*2)
        result,_=blind_replay(iter(bars),strategy=Strategy(**policies[profile]['parameters']),
            limits=limits,costs=costs,instruments=specs,trace_path=output/'decisions'/f'stress-{symbol}-{seconds}.jsonl')
        result.update(case=f'stress_{symbol}_{seconds}',variant='trained_double_costs',code_id=code,
            dataset_sha256=history_digest(bars),policy_sha256=policies[profile]['sha256'])
        memory.append('BLIND_TEST',result);results.append(result)
    summary={'mode':'ADDITIONAL_FROZEN_POLICY_QUALIFICATION','code_id':code,
        'passed':all(row['passed'] for row in results),'runs':len(results),
        'decisions':sum(row['bars'] for row in results),'results':results,
        'parameters_changed':False,'training_performed':False,'automatic_adoption':False}
    save_report(summary,output/'supplemental-summary.json')
    print(json.dumps({key:value for key,value in summary.items() if key!='results'}),flush=True)
    if not summary['passed']:raise SystemExit(1)


if __name__=='__main__':
    multiprocessing.freeze_support()
    main()
