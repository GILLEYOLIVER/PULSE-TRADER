"""Compare CPU worker counts on known data; never a new market evaluation."""
from __future__ import annotations

import argparse
import multiprocessing
import statistics
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path

from scripts.research_cycle import development_task
from trading_assistant.v2.data import CSVProvider
from trading_assistant.v2.learning import digest
from trading_assistant.v2.research import atomic_json,candidate_bank
from trading_assistant.v2.strategy import Strategy
from trading_assistant.v2.suggestions import history_digest


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',required=True)
    parser.add_argument('--output',default='reports/research-workers-benchmark.json')
    args=parser.parse_args()
    bars=CSVProvider(args.data).bars()[:6000]
    if len(bars)<3000:raise ValueError('At least 3,000 known candles required for the CPU measurement')
    parameters=candidate_bank(0,asdict(Strategy()),8,allow_multi_timeframe=True)
    output=Path(args.output);runs=[]
    result={'kind':'KNOWN_DATA_PROCESSING_BENCHMARK_NOT_GOAL_EVIDENCE','source':str(Path(args.data).resolve()),
        'dataset_sha256':history_digest(bars),'candles':len(bars),'tasks':len(parameters),
        'schedule':[2,4,4,2],'runs':runs,'parameters':parameters,
        'source_sha256':digest({str(p):p.read_text(encoding='utf-8') for folder in ('trading_assistant/v2','scripts')
            for p in Path(folder).glob('*.py')})}
    atomic_json(output,result)
    for workers in result['schedule']:
        start=time.perf_counter()
        with ProcessPoolExecutor(max_workers=workers) as pool:
            rows=list(pool.map(development_task,[(bars,p,None) for p in parameters]))
        run={'workers':workers,'seconds':time.perf_counter()-start,'results_sha256':digest(rows)}
        runs.append(run);atomic_json(output,result);print(run,flush=True)
    result['identical_financial_results']=len({r['results_sha256'] for r in runs})==1
    medians={workers:statistics.median(r['seconds'] for r in runs if r['workers']==workers) for workers in (2,4)}
    result['median_seconds']=medians;result['four_worker_speedup']=medians[2]/medians[4]
    result['recommended_workers']=4 if result['identical_financial_results'] and result['four_worker_speedup']>=1.15 else 2
    atomic_json(output,result);print({k:result[k] for k in ('identical_financial_results','median_seconds','four_worker_speedup','recommended_workers')},flush=True)
    if not result['identical_financial_results']:raise ValueError('Parallel counts changed financial results')


if __name__=='__main__':
    multiprocessing.freeze_support();main()
