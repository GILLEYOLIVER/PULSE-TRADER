"""Reproducible chronological research, with a final holdout never used for selection."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from .backtest import run_backtest, save_report
from .ml import train_temporal
from .models import UTC, aware, Limits, ExecutionSettings
from .strategy import Strategy
from .suggestions import validate_series


def validate_history(bars, *, limits=None, costs=None, calendar=None, instruments=None, now=None):
    cutoff=aware(now or datetime.now(UTC))
    bars=[b for b in bars if aware(b.ts)+timedelta(seconds=b.seconds)<=cutoff]
    validate_series(bars)
    if len(bars)<200: raise ValueError('Validação requer ao menos 200 candles encerrados de uma série')
    limits,costs=limits or Limits(),costs or ExecutionSettings()
    limits.validate();costs.validate()
    a,b=int(len(bars)*.6),int(len(bars)*.8)
    training,selection,holdout=bars[:a],bars[a:b],bars[b:]
    # Selection uses validation only. The test report is generated once after selecting the template.
    candidates=[]
    for name in limits.allowed_strategies:
        strategy=Strategy(name)
        result=run_backtest(selection,strategy,limits,costs,calendar,instruments)
        candidates.append({'strategy':name,'validation_metrics':result['metrics']})
    best=max(candidates,key=lambda candidate:candidate['validation_metrics']['net'])
    final=run_backtest(holdout,Strategy(best['strategy']),limits,costs,calendar,instruments)
    stress=run_backtest(holdout,Strategy(best['strategy']),limits,
                        ExecutionSettings(**{**asdict(costs),'slippage_ticks':costs.slippage_ticks*2,'fee_per_unit':costs.fee_per_unit*2}),calendar,instruments)
    with TemporaryDirectory() as directory:
        model=train_temporal(bars,Path(directory)/'model.json')
    real=all(not any(marker in row.source.upper() for marker in ('SYNTH','DEMO','MOCK')) for row in bars)
    enough=final['metrics']['trades']>=30
    evidence=real and enough and best['validation_metrics']['net']>0 and final['metrics']['net']>0 and stress['metrics']['net']>0
    return {'mode':'RESEARCH_PAPER','source':bars[0].source,'symbol':bars[0].symbol,'candles':len(bars),
            'cutoff':cutoff.isoformat(),'data_sha256':final['data_sha256'],
            'partitions':{'train_end':training[-1].ts.isoformat(),'validation_start':selection[0].ts.isoformat(),
                          'validation_end':selection[-1].ts.isoformat(),'test_start':holdout[0].ts.isoformat(),
                          'counts':[len(training),len(selection),len(holdout)]},
            'selection_rule':'maximum validation net; test never selects strategy',
            'candidates':candidates,'selected_strategy':best['strategy'],'test_metrics':final['metrics'],
            'stress_metrics':stress['metrics'],'limits':asdict(limits),'execution':asdict(costs),
            'instruments':{key:asdict(value) for key,value in (instruments or {}).items()},
            'ml':model,'historical_non_synthetic':real,'evidence_gate_passed':evidence,
            'automatic_adoption':False,'execution_enabled':False,
            'verdict':'Evidência preliminar; exige acompanhamento prospectivo PAPER' if evidence else 'Sem evidência suficiente para promover a estratégia',
            'limitations':['30 operações no holdout é apenas um filtro mínimo, não prova estatística de vantagem',
                'Retorno de preço; proventos, impostos, aluguel e ajuste diário não estão contabilizados',
                'Margens e taxas são premissas configuradas; OHLC não reconstrói fila ou caminho intrabar',
                'Contexto financeiro atual não entra no backtest histórico; sem vazamento de snapshots atuais']}
