"""One or more bounded, resumable PAPER research cycles, with immutable champions."""
from __future__ import annotations

import argparse
import csv
import json
import multiprocessing
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict,replace
from datetime import datetime,timedelta
from pathlib import Path

from scripts.train_and_blind_test import assumptions,get_data
from trading_assistant.v2.blind_testing import blind_replay
from trading_assistant.v2.learning import HistoricalRotation,LearningMemory,digest
from trading_assistant.v2.models import UTC,Instrument
from trading_assistant.v2.research import (ChampionStore,aggregate_metrics,atomic_json,candidate_bank,
    development_result,development_slices,goal_evidence,plan_forward,promotion_decision,select_development,warmup_start)
from trading_assistant.v2.strategy import Strategy
from trading_assistant.v2.suggestions import history_digest
from trading_assistant.v2.trade_learning import (InsufficientTradeData,base_parameters,collect_trade_samples,fit_trade_model)


METHODS=('trend','breakout','pullback','adaptive','sma_cross','ema_pullback','mean_reversion')
GROUPS=('BTCUSDT:300','ETHUSDT:300','BNBUSDT:300','SOLUSDT:300',
    'BTCUSDT:3600','ETHUSDT:3600','BNBUSDT:3600','SOLUSDT:3600',
    'BTCUSDT:86400','ETHUSDT:86400','BNBUSDT:86400','SOLUSDT:86400')


def research_assumptions(symbol):
    limits,costs,specs=assumptions(symbol)
    if symbol in ('BNBUSDT','SOLUSDT'):
        unit=.001 if symbol=='BNBUSDT' else .01
        specs={symbol:Instrument(symbol,unit,.01,1,1.,'USDT',allow_short=False,volume_per_unit=unit)}
    # Compare all methods under the same conservative capital and risk, never tune risk to win a ranking.
    limits=replace(limits,risk_fraction=.0025,daily_loss=1000.,weekly_loss=2500.,monthly_loss=5000.,
        daily_target=1000.,allowed_strategies=METHODS,min_net_reward_r=.25)
    return limits,costs,specs


def development_task(task):
    bars,parameters,after=task;limits,costs,specs=research_assumptions(bars[0].symbol)
    reports=[]
    for lo,hi in development_slices(bars,after):
        report,_=blind_replay(iter(bars[lo:hi]),warmup=bars[max(0,lo-250):lo],
            strategy=Strategy(**parameters),limits=limits,costs=costs,instruments=specs,
            retain_trace=False,bootstrap=False)
        reports.append(report)
    return development_result(parameters,reports)


def fit_entry_filter(bars,parameters,directory,cutoff):
    base=base_parameters(parameters);strategy=Strategy(**base)
    limits,costs,specs=research_assumptions(bars[0].symbol)
    samples,diagnostics=collect_trade_samples(bars,strategy,limits,costs,specs)
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    atomic_json(directory/'labels.json',{'samples':samples,'teacher':diagnostics,'cutoff':cutoff.isoformat()})
    model=fit_trade_model(samples,parameters=asdict(strategy),symbol=bars[0].symbol,seconds=bars[0].seconds,
        source=bars[0].source,cutoff=cutoff,costs=costs,instrument=specs[bars[0].symbol],dataset_sha256=history_digest(bars))
    atomic_json(directory/'model.json',model)
    return model,diagnostics


def learned_development_task(task):
    bars,parameters,after,directory=task;thresholds=(.55,.65,.8,.9)
    reports={threshold:[] for threshold in thresholds};training=[]
    base=base_parameters(parameters);limits,costs,specs=research_assumptions(bars[0].symbol)
    for index,(lo,hi) in enumerate(development_slices(bars,after),1):
        try:model,diagnostics=fit_entry_filter(bars[:lo],base,Path(directory)/f'fold-{index}',bars[lo].ts)
        except InsufficientTradeData as error:
            result=[]
            for threshold in thresholds:
                row=development_result(base,[]);row.update(learning={'threshold':threshold,'kind':'trade_outcome_logistic'},
                    training_status='INSUFFICIENT_RESOLVED_TRADES',detail=str(error),training=training)
                result.append(row)
            return result
        training.append({'fold':index,'model_sha256':model['sha256'],'cutoff':model['training_cutoff'],
            'training_samples':model['training_samples'],'teacher':diagnostics})
        for threshold in thresholds:
            strategy=Strategy(**base,trade_filter=model,trade_score_threshold=threshold)
            report,_=blind_replay(iter(bars[lo:hi]),warmup=bars[max(0,lo-250):lo],strategy=strategy,
                limits=limits,costs=costs,instruments=specs,retain_trace=False,bootstrap=False)
            reports[threshold].append(report)
    result=[]
    for threshold in thresholds:
        row=development_result(base,reports[threshold]);row.update(learning={'threshold':threshold,'kind':'trade_outcome_logistic'},
            training_status='TEMPORAL_FOLDS_EVALUATED',training=training)
        result.append(row)
    return result


def materialize_candidate(winner,training,directory,cutoff):
    if not winner.get('learning'):return asdict(Strategy(**winner['parameters']))
    model,_=fit_entry_filter(training,winner['parameters'],Path(directory)/'trade-models'/'final',cutoff)
    return asdict(Strategy(**base_parameters(winner['parameters']),trade_filter=model,
        trade_score_threshold=winner['learning']['threshold']))


def external_run(bars,warmup,parameters,group,output,name,*,stress=False):
    limits,costs,specs=research_assumptions(bars[0].symbol)
    if stress:costs=replace(costs,fee_bps=costs.fee_bps*2,slippage_ticks=costs.slippage_ticks*2)
    result,_=blind_replay(iter(bars),warmup=warmup,strategy=Strategy(**parameters),limits=limits,
        costs=costs,instruments=specs,trace_path=output/'decisions'/(group.replace(':','-')+'-'+name+'.jsonl'))
    return result


def describe_rate(metrics):
    value=metrics['win_rate']
    return 'sem operações' if value is None or not metrics['trades'] else f'{value*100:.2f}% ({round(value*metrics["trades"])}/{metrics["trades"]})'


def write_report(output,summary):
    lines=['# Ciclo de pesquisa PAPER','',f"Rodada: {summary['cycle_id']}",'',
        f"Estado do lote: {summary.get('status','COMPLETED')}",'',
        'Meta: mais de 90% de operações lucrativas após custos, com confirmação em dados inéditos.',
        'As referências abaixo são das pesquisas; a sessão da interface não é alterada.','',
        '| Ativo / candle | Referência | Candidata congelada | Líquido candidata USDT | Decisão |',
        '|---|---:|---:|---:|---|']
    for row in summary['groups']:
        if 'external' not in row:
            lines.append(f"| {row['group']} | — | — | — | {row['status']} |")
            continue
        c=row['external']['metrics'];r=row['reference_external']['metrics']
        lines.append(f"| {row['group']} | {describe_rate(r)} | {describe_rate(c)} | {c['net']:.2f} | {row['decision']} |")
    lines+=['','## Evidência e limites','',
        f"Meta observada nesta rodada: **{'SIM' if summary['goal_reached'] else 'NÃO'}**.",
        'Porcentagens são operações reais de simulação em históricos públicos, não probabilidade de lucro futuro.',
        'Janelas antigas não voltam a contar como inéditas; sem operações não há acerto medido.',
        'Matrizes de desenvolvimento, protocolo congelado, dados e decisões ficam nesta pasta.',
        'Intervalos descritivos não corrigem todas as tentativas de pesquisa. Nenhuma ordem real é enviada.']
    (output/'RELATORIO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')


def run_group(group,args,store,state,code_id,rotation,memory,output,cycle_id):
    symbol,seconds_text=group.split(':');seconds=int(seconds_text)
    train_days=30 if seconds==300 else 365 if seconds==3600 else 365 if symbol in ('BTCUSDT','ETHUSDT') else 1460
    test_days=7 if seconds==300 else 21 if seconds==3600 else 90
    try:
        window=plan_forward(rotation,symbol,seconds,as_of=datetime.now(UTC),test_days=test_days,
            training_days=train_days,after=state['groups'].get(group,{}).get('last_external_end'))
    except ValueError as error:return {'group':group,'status':'WAITING_FOR_UNSEEN_DATA','detail':str(error)}
    limits,costs,specs=research_assumptions(symbol)
    settings={'limits':asdict(limits),'costs':asdict(costs),'instruments':{k:asdict(v) for k,v in specs.items()}}
    previous=state['groups'].get(group,{})
    parameters=asdict(Strategy(**store.version(previous['champion'])['parameters'])) if previous.get('champion') else asdict(Strategy())
    reference_id=store.register(group,parameters,code_id,settings)
    if previous.get('champion') and store.version(previous['champion'])['code_id']!=code_id:
        # Old source remains archived; do not count new-code results as old-version confirmations.
        rebased_from=previous['champion']
    else:rebased_from=None
    if not previous.get('champion'):
        store.set_champion(state,group,reference_id,'INITIAL_REFERENCE');store.save(state)
    count=previous.get('cycles',0)
    development_after=(parameters.get('trade_filter') or {}).get('training_cutoff')
    bank=candidate_bank(count,parameters,args.candidates)
    plan={'cycle_id':cycle_id,'group':group,'windows':window,'code_id':code_id,
        'reference_id':reference_id,'rebased_from':rebased_from,'candidate_parameters':bank,
        'assumptions':settings,'selection':'three chronological development folds; >=30 total trades, >=5 trades and positive aggregate net in each fold; Wilson lower bound first',
        'goal':'same version; >=3 distinct real windows; >=100 trades total; >90% each; positive net and double-cost stress',
        'promotion':'preselected challenger only; >=10 external trades; better net and nonworse accuracy than reference; positive double-cost net; drawdown <=10%',
        'desktop_adoption':False}
    plan['required_external_warmup_bars']=250
    plan['learned_entry_filter']={'bases':2,'thresholds':[.55,.65,.8,.9],
        'minimum_resolved_training_trades':100,'minimum_each_net_outcome':20,
        'fold_models_trained_only_before_validation':'labels must already be realized',
        'common_development_after':development_after,'score_is_calibrated_probability':False}
    group_dir=output/group.replace(':','-');group_dir.mkdir()
    atomic_json(group_dir/'protocol-before-data.json',plan)
    rotation.reserve(cycle_id,symbol,seconds,window['test_start'],window['test_end'])
    state['groups'][group]['last_external_end']=window['test_end'];store.save(state)
    print(group+': downloading development '+window['training_start']+' / '+window['test_start'],flush=True)
    training=get_data(symbol,seconds,window['training_start'],window['test_start'],group_dir,allow_gaps=True)
    if any(b.source!='BINANCE_SPOT_USDT' for b in training):raise ValueError('Unexpected research data origin')
    rotation.mark_development(symbol,seconds,window['training_start'],window['test_start'],history_digest(training))
    atomic_json(group_dir/'development-data.json',{'sha256':history_digest(training),'candles':len(training)})
    results=[]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for index,result in enumerate(pool.map(development_task,[(training,p,development_after) for p in bank]),1):
            results.append(result)
            print(f'{group}: development {index}/{len(bank)}; trades={result["aggregate"]["trades"]}; eligible={result["eligible"]}',flush=True)
        seeds=sorted((row for row in results if row['parameters'].get('trade_filter') is None and row['aggregate']['trades']>=30),
            key=lambda row:tuple(row['selection_key']),reverse=True)[:2]
        tasks=[(training,row['parameters'],development_after,group_dir/'trade-models'/digest(base_parameters(row['parameters']))) for row in seeds]
        for index,learned in enumerate(pool.map(learned_development_task,tasks),1):
            results.extend(learned)
            print(f'{group}: learned base {index}/{len(seeds)}; eligible thresholds={sum(row["eligible"] for row in learned)}',flush=True)
    reference=next(row for row in results if row['parameters']==parameters)
    winner,selection=select_development(results,reference)
    cutoff=datetime.fromisoformat(window['test_start']).replace(tzinfo=UTC)
    selected_parameters=materialize_candidate(winner,training,group_dir,cutoff)
    candidate_id=store.register(group,selected_parameters,code_id,settings)
    policy={**plan,'candidate_id':candidate_id,'selected_parameters':selected_parameters,
        'selection_status':selection,'development_sha256':history_digest(training),'selected_development':winner}
    policy['sha256']=digest(policy)
    # Immutable choice before the holdout is fetched. Both retained and rejected configurations are saved.
    atomic_json(group_dir/'frozen-policy.json',policy)
    atomic_json(group_dir/'development-matrix.json',results)
    memory.append_batch('VALIDATION',[{'profile':group,'cycle_id':cycle_id,**row} for row in results])
    memory.append('SEALED_POLICY',{'profile':group,'cycle_id':cycle_id,'winner':{'parameters':selected_parameters,
        'risk_profile':'fixed_conservative'},'policy_sha256':policy['sha256'],'candidate_id':candidate_id})
    with (group_dir/'COMPARACAO.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream,delimiter=';');writer.writerow(('parameters','learning','eligible','trades','wins','win_rate','net_USDT','drawdown_USDT'))
        for row in results:
            m=row['aggregate'];writer.writerow((json.dumps(row['parameters']),json.dumps(row.get('learning')),row['eligible'],m['trades'],m['wins'],m['win_rate'],m['net'],m['max_window_drawdown']))
    start=datetime.fromisoformat(window['test_start']).replace(tzinfo=UTC)
    context_start=warmup_start(start,seconds)
    full=get_data(symbol,seconds,context_start,window['test_end'],group_dir,allow_gaps=True)
    warmup=[b for b in full if b.ts<start][-250:];testing=[b for b in full if b.ts>=start]
    if len(warmup)<250:raise ValueError('Contexto anterior insuficiente; a avaliação não começa consumindo candles do teste como aquecimento')
    c=external_run(testing,warmup,selected_parameters,group,group_dir,'candidate')
    r=c if candidate_id==reference_id else external_run(testing,warmup,parameters,group,group_dir,'reference')
    s=external_run(testing,warmup,selected_parameters,group,group_dir,'double-costs',stress=True)
    rs=s if candidate_id==reference_id else external_run(testing,warmup,parameters,group,group_dir,'reference-double-costs',stress=True)
    promotion=promotion_decision(winner,c,r,s)
    if candidate_id==reference_id:promotion={'promoted':False,'reasons':['reference_already_selected']}
    confirmations=[]
    for version,report,stress,role in ((candidate_id,c,s,'candidate'),(reference_id,r,rs,'reference')):
        if any(row['version_id']==version for row in confirmations):continue
        confirmations.append({'group':group,'version_id':version,'start':window['test_start'],'end':window['test_end'],
            'cycle_id':cycle_id,'role':role,'real_history':all(b.source=='BINANCE_SPOT_USDT' for b in testing),
            'warmup_bars':len(warmup),'qualified_for_goal':len(warmup)>=250,
            'passed':all(x['passed'] for x in (report,stress)),'metrics':report['metrics'],'stress_net':stress['metrics']['net'],
            'stress_drawdown':stress['metrics']['max_drawdown'],'dataset_sha256':history_digest(testing)})
    active_version=candidate_id if promotion['promoted'] else reference_id
    evidence=goal_evidence([row for row in state['evaluations']+confirmations if row['version_id']==active_version])
    row={'group':group,'status':'COMPLETED','reference_id':reference_id,'candidate_id':candidate_id,
        'selection':selection,'development':winner,'external':c,'reference_external':r,'double_costs':s,
        'reference_double_costs':rs,'promotion':promotion,'goal':evidence,'development_candidates':len(results),
        'decision':'PROMOVIDA NA PESQUISA' if promotion['promoted'] else 'REFERÊNCIA PRESERVADA'}
    atomic_json(group_dir/'result.json',row)
    row['runtime_archive']=store.archive_run(group_dir)
    # Commit the research reference only after its complete data/report bundle was preserved.
    if promotion['promoted']:store.set_champion(state,group,candidate_id,'VALIDATION_AND_EXTERNAL_GATE_PASSED')
    elif rebased_from:store.set_champion(state,group,reference_id,'REFERENCE_PARAMETERS_REEVALUATED_ON_NEW_CODE')
    state['evaluations'].extend(confirmations)
    state['groups'][group]['cycles']=count+1
    state['groups'][group]['last_evidence']=evidence
    store.save(state)
    memory.append_batch('BLIND_TEST',[{'profile':group,'cycle_id':cycle_id,**row,'promotion':promotion} for row in confirmations])
    print(group+': external '+describe_rate(c['metrics'])+'; '+row['decision'],flush=True)
    return row


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cycles',type=int,choices=range(1,21),default=1)
    parser.add_argument('--workers',type=int,choices=(1,2,3,4),default=2)
    parser.add_argument('--candidates',type=int,choices=range(12,211),default=36)
    parser.add_argument('--groups',nargs='+',choices=GROUPS,default=list(GROUPS))
    parser.add_argument('--memory',default='runtime/aprendizado')
    parser.add_argument('--output',default='reports/research-cycles')
    parser.add_argument('--plan-only',action='store_true')
    parser.add_argument('--isolated-snapshot',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    root=Path(args.memory);store=ChampionStore(root/'ciclos');rotation=HistoricalRotation(root);memory=LearningMemory(root)
    if args.plan_only:
        for group in args.groups:
            symbol,seconds=group.split(':');seconds=int(seconds)
            try:
                window=plan_forward(rotation,symbol,seconds,as_of=datetime.now(UTC),test_days=7 if seconds==300 else 21 if seconds==3600 else 90,
                    training_days=30 if seconds==300 else 365 if seconds==3600 else 365 if symbol in ('BTCUSDT','ETHUSDT') else 1460,
                    after=store.state()['groups'].get(group,{}).get('last_external_end'))
                print(json.dumps({'group':group,'windows':window}),flush=True)
            except ValueError as error:print(json.dumps({'group':group,'waiting':str(error)}),flush=True)
        return
    sources={str(p):p.read_text(encoding='utf-8') for folder in ('trading_assistant/v2','scripts')
        for p in sorted(Path(folder).glob('*.py'))}
    sources['trading_assistant/__init__.py']=Path('trading_assistant/__init__.py').read_text(encoding='utf-8')
    sources.update({str(p):p.read_text(encoding='utf-8') for p in Path('.').glob('requirements*.txt')})
    if not args.isolated_snapshot:
        workspace=store.source_workspace(sources)
        command=[sys.executable,'-u','-m','scripts.research_cycle',*sys.argv[1:],'--isolated-snapshot',
            '--memory',str(root.resolve()),'--output',str(Path(args.output).resolve())]
        completed=subprocess.run(command,cwd=workspace)
        raise SystemExit(completed.returncode)
    with store.lock():
        code_id=store.archive_source(sources);state=store.state()
        for _ in range(args.cycles):
            cycle_id=datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')
            output=Path(args.output)/cycle_id;output.mkdir(parents=True)
            summary={'cycle_id':cycle_id,'code_id':code_id,'groups':[],'goal_reached':False,'mode':'PAPER','status':'IN_PROGRESS'}
            atomic_json(output/'batch-before-results.json',{'groups':args.groups,'technical_candidates_per_group':args.candidates,
                'maximum_trade_filter_candidates_per_group':8,
                'workers':args.workers,'code_id':code_id,'started_at':cycle_id})
            for group in args.groups:
                try:row=run_group(group,args,store,state,code_id,rotation,memory,output,cycle_id)
                except Exception as error:
                    row={'group':group,'status':'FAILED','error_type':type(error).__name__,'detail':str(error)}
                    print(json.dumps(row),flush=True)
                summary['groups'].append(row)
                # All tracked markets/profiles must qualify; one lucky asset cannot end the full mission.
                summary['goal_reached']=bool(state['groups']) and all(
                    state['groups'].get(g,{}).get('last_evidence',{}).get('observed_goal_reached',False)
                    and state['groups'][g]['last_evidence'].get('version_id')==state['groups'][g]['champion'] for g in GROUPS)
                atomic_json(output/'summary.json',summary);write_report(output,summary)
            state['completed_cycles']+=1;store.save(state)
            summary['status']='COMPLETED_WITH_ERRORS' if any(r['status']=='FAILED' for r in summary['groups']) else 'COMPLETED'
            atomic_json(output/'summary.json',summary);write_report(output,summary)
            atomic_json(store.directory/'latest.json',{'cycle_id':cycle_id,'report':str((output/'RELATORIO.md').resolve()),
                'summary':str((output/'summary.json').resolve()),'goal_reached':summary['goal_reached']})
            print(json.dumps({'cycle_id':cycle_id,'goal_reached':summary['goal_reached'],'report':str(output/'RELATORIO.md')}),flush=True)
            if summary['goal_reached'] or all(row['status']=='WAITING_FOR_UNSEEN_DATA' for row in summary['groups']):break


if __name__=='__main__':
    multiprocessing.freeze_support();main()
