"""Two bounded development rounds; moving averages, risk profiles and fresh external evaluation."""
from __future__ import annotations
import argparse
import csv
import json
import multiprocessing
import subprocess
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict,replace
from datetime import datetime
from pathlib import Path

from scripts.train_and_blind_test import assumptions,get_data
from trading_assistant.v2.backtest import run_backtest,save_report
from trading_assistant.v2.blind_testing import blind_replay
from trading_assistant.v2.learning import LearningMemory,HistoricalRotation,digest
from trading_assistant.v2.ml import train_temporal
from trading_assistant.v2.models import UTC
from trading_assistant.v2.strategy import Strategy
from trading_assistant.v2.suggestions import history_digest

PROFILES=(('conservative',.0025,.01,.01),('balanced',.005,.02,.02),('higher_risk',.01,.03,.03))
METHODS=('trend','breakout','pullback','adaptive','sma_cross','ema_pullback')


def risk_profile(symbol,profile):
    limits,costs,specs=assumptions(symbol)
    _,risk,loss,target=next(row for row in PROFILES if row[0]==profile)
    limits=replace(limits,risk_fraction=risk,daily_loss=limits.capital*loss,
        weekly_loss=limits.capital*loss*2.5,monthly_loss=limits.capital*loss*5,
        daily_target=limits.capital*target,allowed_strategies=METHODS)
    return limits,costs,specs


def score_candidate(task):
    bars,parameters,profile,round_number=task
    limits,costs,specs=risk_profile(bars[0].symbol,profile)
    start=int(len(bars)*.6);middle=int(len(bars)*.8)
    strategy=Strategy(**parameters);folds=[]
    for lo,hi in ((start,middle),(middle,len(bars))):
        warmup=bars[max(0,lo-250):lo]
        # Use warmup without orders; never include a future label or candle.
        report,_=blind_replay(iter(bars[lo:hi]),warmup=warmup,strategy=strategy,
            limits=limits,costs=costs,instruments=specs)
        if not report['passed']:raise ValueError('Development risk/cost invariant failed')
        folds.append(report['metrics'])
    trades=sum(row['trades'] for row in folds)
    net=sum(row['net'] for row in folds)
    wins=sum(row['win_rate']*row['trades'] for row in folds)
    drawdown=max(row['max_drawdown'] for row in folds)
    return {'round':round_number,'parameters':parameters,'risk_profile':profile,'folds':folds,
        'trades':trades,'win_rate':wins/trades if trades else None,'net':net,'max_drawdown':drawdown,
        'score':net-.1*drawdown,'enough_development_trades':trades>=10}


def select_policy(bars,profile,output,memory,workers,code):
    dataset=history_digest(bars)
    tasks=[(bars,asdict(Strategy(method,reward,stop)),risk[0],1)
        for method in METHODS for reward in (1.5,2.,3.) for stop in (1.,2.) for risk in PROFILES]
    seen={digest([task[1],task[2]]) for task in tasks}
    for prior in memory.parameter_priors(profile):
        key=digest([prior['parameters'],prior['risk_profile']])
        if key not in seen and prior['risk_profile'] in {row[0] for row in PROFILES}:
            Strategy(**prior['parameters'])
            tasks.append((bars,prior['parameters'],prior['risk_profile'],1));seen.add(key)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        coarse=[]
        for index,row in enumerate(pool.map(score_candidate,tasks),1):
            coarse.append(row)
            if index%18==0:print(f'{profile}: development round 1 {index}/{len(tasks)}',flush=True)
        eligible=[row for row in coarse if row['enough_development_trades']]
        if not eligible:raise ValueError('No candidate has enough development trades; increase development history')
        best=max(eligible,key=lambda row:row['score'])
        p=best['parameters']
        tasks=[(bars,{**p,'reward_r':reward,'stop_atr':stop},best['risk_profile'],2)
            for reward in (p['reward_r']-.25,p['reward_r'],p['reward_r']+.25)
            for stop in (p['stop_atr']-.25,p['stop_atr'],p['stop_atr']+.25)]
        fine=list(pool.map(score_candidate,tasks))
    refined=max((row for row in fine if row['enough_development_trades']),key=lambda row:row['score'])
    improvement=refined['score']-best['score']
    winner=refined if improvement>max(10.,abs(best['score'])*.01) else best
    all_rows=coarse+fine
    for row in all_rows:memory.append('VALIDATION',{'iteration':'moving_average_goals_v1','profile':profile,
        'code_id':code,'dataset_sha256':dataset,**row})
    model_path=output/(profile+'-enriched-model.json')
    model=train_temporal(bars,model_path,feature_set='regime_flow_v2')
    memory.remember_model(bars,model,model_path)
    policy={'schema':1,'profile':profile,'code_id':code,'dataset_sha256':dataset,
        'development_last_open':bars[-1].ts.isoformat(),'winner':winner,
        'round1_candidates':len(coarse),'round2_candidates':len(fine),
        'refinement_improvement':improvement,'refinement_accepted':winner is refined,
        'model_sha256':model['sha256'],'automatic_adoption':False,
        'previous_test_periods_retired_to_development':True}
    policy['sha256']=digest(policy);memory.append('SEALED_POLICY',policy)
    save_report(policy,output/(profile+'-frozen-policy.json'))
    with (output/(profile+'-development-matrix.csv')).open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.writer(stream,delimiter=';')
        writer.writerow(('round','method','target_R','stop_ATR','risk_profile','trades','win_rate_percent','net_USDT','drawdown_USDT','score'))
        for row in all_rows:
            writer.writerow((row['round'],row['parameters']['name'],row['parameters']['reward_r'],row['parameters']['stop_atr'],
                row['risk_profile'],row['trades'],None if row['win_rate'] is None else row['win_rate']*100,
                row['net'],row['max_drawdown'],row['score']))
    return policy


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='reports/engine-upgrade/goals')
    parser.add_argument('--memory',default='runtime/aprendizado')
    parser.add_argument('--workers',type=int,choices=(1,2,3,4),default=2)
    parser.add_argument('--fixed-history',action='store_true',help='Repeat original periods for regression only; default rotates disjoint historical evaluation windows')
    parser.add_argument('--plan-only',action='store_true',help='Show fresh windows without downloads, training or reservations')
    args=parser.parse_args()
    output=Path(args.output)/datetime.now(UTC).strftime('cycle-%Y%m%dT%H%M%S%f')
    output.mkdir(parents=True,exist_ok=True)
    memory=LearningMemory(args.memory)
    rotation=HistoricalRotation(args.memory)
    from datetime import timedelta
    for record in memory.training_records():
        if record['kind']=='TRAIN':
            data=record['payload']
            if all(key in data for key in ('symbol','seconds','first','last')):
                first=datetime.fromisoformat(data['first']).date().isoformat()
                end=(datetime.fromisoformat(data['last'])+timedelta(seconds=data['seconds'])).date().isoformat()
                rotation.mark_development(data['symbol'],data['seconds'],first,end,data.get('dataset_sha256',record['sha256']))
    if args.fixed_history:
        windows={'daily':{'training_start':'2020-01-01','test_start':'2026-01-01','test_end':'2026-10-01'},
            'intraday':{'training_start':'2025-09-01','test_start':'2025-10-01','test_end':'2025-10-16'}}
    else:
        windows={}
        for profile,seconds,test_days,training_days in (('daily',86400,180,1460),('intraday',300,7,21)):
            try:windows[profile]=rotation.plan(('BTCUSDT','ETHUSDT'),seconds,as_of=datetime.now(UTC),
                test_days=test_days,training_days=training_days)
            except ValueError as error:print(f'{profile}: {error}',flush=True)
    if args.plan_only:
        print(json.dumps({'available_windows':windows,'training_performed':False,'reserved':False}),flush=True)
        return
    if not windows:raise ValueError('Aguarde dados novos antes de repetir uma avaliação independente')
    code=digest({str(path):path.read_text(encoding='utf-8') for folder in ('trading_assistant/v2','scripts')
        for path in sorted(Path(folder).glob('*.py'))})
    protocol={'iteration':'moving_average_goals_v1','code_sha256':code,'methods':METHODS,'profiles':PROFILES,
        'coarse_targets_R':[1.5,2.,3.],'coarse_stops_ATR':[1.,2.],
        'budget_per_timeframe':'108 coarse + up to 3 priors from training memory + 9 refinement candidates; two workers; one external qualification',
        'external_periods':windows,'regression_only':args.fixed_history,
        'external_symbols':['BTCUSDT','ETHUSDT'],'promotion':'No automatic adoption; enough trades, positive net/stress, uncertainty and independent evidence required',
        'old_evaluations':'2024-2025 daily and September 2025 intraday are now development; never reported as fresh external evidence'}
    save_report(protocol,output/'protocol-before-training.json')
    if not args.fixed_history:
        run_id=datetime.now(UTC).isoformat()
        for profile,seconds in (('daily',86400),('intraday',300)):
            if profile not in windows:continue
            for symbol in ('BTCUSDT','ETHUSDT'):
                rotation.reserve(run_id,symbol,seconds,windows[profile]['test_start'],windows[profile]['test_end'])
    training={profile:get_data('BTCUSDT',seconds,windows[profile]['training_start'],
        '2025-09-16' if args.fixed_history and profile=='intraday' else windows[profile]['test_start'],output)
        for profile,seconds in (('daily',86400),('intraday',300)) if profile in windows}
    for profile,seconds in (('daily',86400),('intraday',300)):
        if profile not in windows:continue
        rotation.mark_development('BTCUSDT',seconds,windows[profile]['training_start'],
            windows[profile]['test_start'],'development-'+code)
    policies={profile:select_policy(bars,profile,output,memory,args.workers,code) for profile,bars in training.items()}
    results=[]
    from datetime import timedelta
    for profile,seconds in (('daily',86400),('intraday',300)):
        if profile not in windows:continue
        start,end=windows[profile]['test_start'],windows[profile]['test_end']
        warmup_start=(datetime.fromisoformat(start)-timedelta(days=250 if seconds==86400 else 1)).date().isoformat()
        policy=policies[profile]
        for symbol in ('BTCUSDT','ETHUSDT'):
            data=get_data(symbol,seconds,warmup_start,end,output)
            cutoff=datetime.fromisoformat(start).replace(tzinfo=UTC)
            past=[row for row in data if row.ts<cutoff][-250:]
            test=[row for row in data if row.ts>=cutoff]
            limits,costs,specs=risk_profile(symbol,policy['winner']['risk_profile'])
            variants={'baseline':Strategy('trend'),'selected':Strategy(**policy['winner']['parameters']),
                'sma_20_50_200':Strategy('sma_cross'),'ema_9_21_50':Strategy('ema_pullback')}
            for name,strategy in variants.items():
                report,_=blind_replay(iter(test),warmup=past,strategy=strategy,limits=limits,costs=costs,instruments=specs,
                    trace_path=output/'decisions'/f'{profile}-{symbol}-{name}.jsonl')
                report.update(iteration='moving_average_goals_v1',profile=profile,symbol=symbol,variant=name,
                    dataset_sha256=history_digest(test),code_sha256=code,policy_sha256=policy['sha256'],
                    accounting_currency='USDT',risk_profile=policy['winner']['risk_profile'])
                memory.append('BLIND_TEST',report);results.append(report)
            stress,_=blind_replay(iter(test),warmup=past,strategy=variants['selected'],limits=limits,
                costs=replace(costs,fee_bps=costs.fee_bps*2,slippage_ticks=costs.slippage_ticks*2),instruments=specs,
                trace_path=output/'decisions'/f'{profile}-{symbol}-stress.jsonl')
            stress.update(iteration='moving_average_goals_v1',profile=profile,symbol=symbol,variant='selected_double_costs',
                code_sha256=code,policy_sha256=policy['sha256'],dataset_sha256=history_digest(test),accounting_currency='USDT')
            memory.append('BLIND_TEST',stress);results.append(stress)
            print(f'External qualification {profile} {symbol}: '+str([(r['variant'],r['metrics']['trades'],round(r['metrics']['net'],2)) for r in results[-5:]]),flush=True)
    summary={'iteration':'moving_average_goals_v1','code_sha256':code,'passed':all(row['passed'] for row in results),
        'development_candidates':sum(row['round1_candidates']+row['round2_candidates'] for row in policies.values()),'external_runs':len(results),'external_decisions':sum(row['bars'] for row in results),
        'results':results,'automatic_adoption':False,'retuned_on_external_results':False}
    save_report(summary,output/'summary.json')
    print(json.dumps({key:value for key,value in summary.items() if key!='results'}),flush=True)
    if not summary['passed']:raise SystemExit(1)


if __name__=='__main__':
    multiprocessing.freeze_support()
    main()
