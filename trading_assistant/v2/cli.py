from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from .data import CSVProvider,SyntheticProvider,export_csv,CandleStore,aggregate
from .backtest import run_backtest,save_report,walk_forward,sensitivity
from .strategy import Strategy

def main(argv=None):
    p=argparse.ArgumentParser(description="PULSE-TRADER PAPER only; no live routing")
    p.add_argument("command",choices=("backtest","demo","train","walk-forward","sensitivity","diagnose"))
    p.add_argument("--csv");p.add_argument("--symbol",default="WIN");p.add_argument("--bars",type=int,default=1000)
    p.add_argument("--seed",type=int,default=42);p.add_argument("--seconds",type=int,default=60)
    p.add_argument("--strategy",choices=("trend","breakout","pullback"),default="trend")
    p.add_argument("--output",default="reports/latest.json")
    a=p.parse_args(argv)
    if a.command=="diagnose":
        import importlib.util,sqlite3,sys,tkinter
        root=tkinter.Tk();root.withdraw();root.update();root.destroy()
        print(json.dumps({"python":sys.version,"sqlite":sqlite3.sqlite_version,"tk":"OK","customtkinter":bool(importlib.util.find_spec("customtkinter")),"live":"DISABLED"},indent=2));return
    bars=CSVProvider(a.csv).bars() if a.csv else SyntheticProvider(a.symbol,a.bars,a.seed,a.seconds).bars()
    if len({b.symbol for b in bars})!=1: raise ValueError("CLI backtest supports one asset per run; split multi-asset CSV")
    if a.command=="train":
        from .ml import train_temporal
        Path(a.output).parent.mkdir(parents=True,exist_ok=True)
        report=train_temporal(bars,a.output)
    elif a.command=="sensitivity":
        report={"mode":"PAPER","source":bars[0].source,"sensitivity":sensitivity(bars)};save_report(report,a.output)
    elif a.command=="walk-forward":
        report={"mode":"PAPER","folds":walk_forward(bars),"source":bars[0].source};save_report(report,a.output)
    else:
        report=run_backtest(bars,Strategy(a.strategy));save_report(report,a.output)
        if a.command=="demo": export_csv(bars,Path(a.output).with_suffix(".csv"))
    print(json.dumps(report.get("metrics",report.get("test",{"folds":len(report["folds"])} if "folds" in report else {"grid_points":len(report.get("sensitivity",[]))})),indent=2))
    print("PAPER / source: "+bars[0].source+" / report: "+str(Path(a.output).resolve()))

if __name__=="__main__": main()
