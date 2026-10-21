"""Repeatable CPU benchmark; synthetic input measures mechanics, never market quality."""
from __future__ import annotations
import argparse
import cProfile
import hashlib
import json
import statistics
import subprocess
import time
from pathlib import Path
from trading_assistant.v2.data import SyntheticProvider
from trading_assistant.v2.indicators import snapshot
from trading_assistant.v2.backtest import run_backtest, save_report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='reports/engine-upgrade/benchmark.json')
    parser.add_argument('--profile',action='store_true')
    parser.add_argument('--durable',action='store_true')
    args=parser.parse_args()
    bars=SyntheticProvider(count=1200,seed=183).bars()
    windows=[bars[max(0,index-999):index+1] for index in range(199,1200,10)]
    times=[];results=None
    for _ in range(3):
        start=time.perf_counter()
        results=[snapshot(window) for window in windows]
        times.append(time.perf_counter()-start)
    start=time.perf_counter();report=run_backtest(bars,durable=args.durable);elapsed=time.perf_counter()-start
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    if args.profile:
        profiler=cProfile.Profile();profiler.runcall(run_backtest,bars,durable=args.durable)
        profiler.dump_stats(str(output.with_suffix('.prof')))
    save_report({'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'snapshot_windows':len(windows),'snapshot_seconds':times,'snapshot_median_seconds':statistics.median(times),
        'backtest_bars':len(bars),'backtest_seconds':elapsed,'bars_per_second':len(bars)/elapsed,
        'metrics':report['metrics'],'orders_sha256':hashlib.sha256(json.dumps(report['orders'],sort_keys=True).encode()).hexdigest(),
        'snapshots':results,'input':'SyntheticProvider(seed=183,count=1200); no market-performance inference'},output)
    print(json.dumps({'snapshot_median_seconds':statistics.median(times),'backtest_seconds':elapsed,
        'bars_per_second':len(bars)/elapsed,'output':str(output)}),flush=True)


if __name__=='__main__':main()
