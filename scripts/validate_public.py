"""Download documented public samples and record real-data research without touching paper exposure."""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from trading_assistant.v2.backtest import save_report
from trading_assistant.v2.company_context import fetch_company_context
from trading_assistant.v2.data import CandleStore
from trading_assistant.v2.market_data import fetch_market
from trading_assistant.v2.models import Limits,ExecutionSettings,INSTRUMENTS
from trading_assistant.v2.suggestions import merge_series
from trading_assistant.v2.validation import validate_history


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output-dir',default='reports/public-validation')
    parser.add_argument('--install-data',help='Optional application runtime directory: populate analysis catalog only')
    args=parser.parse_args()
    output=Path(args.output_dir);output.mkdir(parents=True,exist_ok=True)
    limits=replace(Limits(),capital=100000.,daily_loss=2000.,weekly_loss=5000.,monthly_loss=10000.,
                   daily_target=3000.,max_contracts=1000,max_positions=1,max_exposure=100000.)
    costs=ExecutionSettings(fee_per_unit=.01,spread_ticks=1.,slippage_ticks=1.)
    summaries=[]
    for symbol in ('PETR4','VALE3'):
        specs={**INSTRUMENTS,symbol:replace(INSTRUMENTS[symbol],margin=100.)}
        for seconds in (60,86400):
            market=fetch_market(symbol,seconds,window='2y' if seconds==86400 else '5d')
            market.save(output/'data')
            print(f'Downloaded {symbol} {seconds}s: {len(market.bars)} closed bars',flush=True)
            report=validate_history(market.bars,limits=limits,costs=costs,instruments=specs)
            report['scenario']='Explicit PAPER research assumptions; not user account capital, broker tariffs or official margin'
            report['provider_provenance']=market.provenance
            path=output/f'{symbol}-{seconds}-validation.json';save_report(report,path)
            summary={'symbol':symbol,'seconds':seconds,'candles':len(market.bars),'data_sha256':market.provenance['sha256'],
                     'selected_strategy':report['selected_strategy'],'test_metrics':report['test_metrics'],
                     'stress_metrics':report['stress_metrics'],'evidence_gate_passed':report['evidence_gate_passed'],
                     'probability_calibrated':report['ml']['probability_calibrated'],'verdict':report['verdict']}
            summaries.append(summary);print(json.dumps(summary,ensure_ascii=True),flush=True)
            if args.install_data:
                runtime=Path(args.install_data);runtime.mkdir(parents=True,exist_ok=True)
                store=CandleStore(runtime/'suggestions.sqlite')
                try:
                    existing={tuple(key):store.load(*key) for key in store.db.execute('SELECT DISTINCT symbol,seconds,source FROM candles')}
                    merge_series(existing,market.bars);store.put(market.bars)
                finally:store.close()
                models=runtime/'models';models.mkdir(exist_ok=True)
                save_report(report['ml'],models/f'{symbol}-{seconds}.json')
        context_dir=Path(args.install_data)/'company-context' if args.install_data else output/'company-context'
        context=fetch_company_context(symbol,context_dir)
        print(f"Company context {symbol}: {len(context['filings'])} filings, {len(context['dividends'])} dividend events",flush=True)
    save_report({'source':'brapi public samples + CVM IPE','mode':'RESEARCH_PAPER','results':summaries,
                 'notes':['No paper.sqlite exposure/configuration changed','No automatic strategy adoption or live orders']},output/'summary.json')


if __name__=='__main__':main()
