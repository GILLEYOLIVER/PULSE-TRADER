from __future__ import annotations
import asyncio
import json
import math
import tempfile
import unittest
from dataclasses import replace
from datetime import date,datetime,time,timedelta
from pathlib import Path
from trading_assistant.v2.models import *
from trading_assistant.v2.data import *
from trading_assistant.v2.indicators import snapshot,ema
from trading_assistant.v2.strategy import Strategy
from trading_assistant.v2.ledger import Ledger
from trading_assistant.v2.execution import PaperEngine
from trading_assistant.v2.backtest import run_backtest,temporal_split,walk_forward
from trading_assistant.v2.integrations import RicoProfitAdapter
from trading_assistant.v2.ml import train_temporal,predict
from trading_assistant.v2.session import SessionCalendar

START=datetime(2026,1,5,12,tzinfo=UTC)

def bar(ts=START,price=1000.,high=None,low=None,close=None,symbol="WDO",volume=10000):
    return Bar(symbol,ts,price,high if high is not None else price+1,low if low is not None else price-1,close if close is not None else price,volume,"SYNTHETIC")

def signal(ts=START+timedelta(minutes=1),price=1000.,stop=998.,target=1010.,side="BUY",symbol="WDO"):
    return Decision(symbol,side,price,stop,target,ts,ts+timedelta(minutes=3),"trend","test")

class PaperCase(unittest.TestCase):
    def setUp(self):
        self.ledger=Ledger();self.engine=PaperEngine(self.ledger,costs=ExecutionSettings(spread_ticks=0,slippage_ticks=0,fee_per_unit=0))
        self.engine.on_bar(bar(),automatic=False)
    def tearDown(self): self.ledger.close()
    def test_contract_multiplier_and_no_minimum_override(self):
        o=self.engine.submit(signal());self.assertEqual(o["qty"],2)
        other=replace(signal(),symbol="WIN",price=1000,stop=500,target=2000)
        self.engine.on_bar(bar(symbol="WIN"),False)
        o=self.engine.submit(other);self.assertEqual(o["status"],"REJECTED")
    def test_no_trade_count_until_execution(self):
        self.engine.submit(signal(),"one")
        self.assertEqual(len(self.ledger.read()["trades"]),0)
        self.assertEqual(self.ledger.read()["orders"]["one"]["status"],"NEW")
    def test_idempotency(self):
        self.engine.submit(signal(),"same");self.engine.submit(signal(),"same")
        self.engine.on_bar(bar(START+timedelta(minutes=1)),False)
        self.assertEqual(len(self.ledger.read()["positions"]),1)
        self.assertEqual(len(self.ledger.read()["orders"]),1)
    def test_stop_before_target(self):
        self.engine.submit(signal(),"x")
        self.engine.on_bar(bar(START+timedelta(minutes=1),high=1015,low=995),False)
        t=self.ledger.read()["trades"][0];self.assertEqual(t["exit_reason"],"STOP");self.assertEqual(t["exit"],998)
    def test_gap_stop(self):
        self.engine.submit(signal(),"x");self.engine.on_bar(bar(START+timedelta(minutes=1)),False)
        self.engine.on_bar(bar(START+timedelta(minutes=2),price=990),False)
        self.assertEqual(self.ledger.read()["trades"][0]["exit"],990)
    def test_sell_target(self):
        self.engine.submit(signal(stop=1002,target=990,side="SELL"))
        self.engine.on_bar(bar(START+timedelta(minutes=1),high=1001,low=989),False)
        self.assertGreater(self.ledger.read()["trades"][0]["net"],0)
    def test_manual_over_budget_rejected(self):
        self.assertEqual(self.engine.submit(signal(),requested=100)["status"],"REJECTED")
    def test_partial_fill_ioc(self):
        with self.ledger.transaction() as s:s["liquidity"]["WDO"]=10
        self.engine.submit(signal(),"x")
        self.engine.on_bar(bar(START+timedelta(minutes=1),volume=10000),False)
        o=self.ledger.read()["orders"]["x"]
        self.assertEqual(o["status"],"PARTIAL");self.assertEqual(o["filled_qty"],1);self.assertEqual(o["cancelled_qty"],1)
    def test_zero_liquidity_reject(self):
        with self.ledger.transaction() as s:s["liquidity"]["WDO"]=0
        self.engine.submit(signal(),"x");self.engine.on_bar(bar(START+timedelta(minutes=1),volume=10000),False)
        self.assertEqual(self.ledger.read()["orders"]["x"]["status"],"REJECTED")
    def test_cancel(self):
        self.engine.submit(signal(),"x");self.engine.cancel("x",START)
        self.engine.on_bar(bar(START+timedelta(minutes=1)),False)
        self.assertFalse(self.ledger.read()["positions"])
    def test_emergency(self):
        self.engine.emergency(START)
        self.assertEqual(self.engine.submit(signal())["status"],"REJECTED")
    def test_disconnect_and_reconnect(self):
        self.engine.submit(signal(),"x");self.engine.connection(False,START)
        self.engine.on_bar(bar(START+timedelta(minutes=1)),False)
        self.assertFalse(self.ledger.read()["positions"])
        self.engine.connection(True,START);self.assertEqual(self.ledger.read()["orders"]["x"]["status"],"CANCELLED")
    def test_expired(self):
        self.engine.submit(signal(ts=START+timedelta(minutes=1)),"x")
        self.engine.on_bar(bar(START+timedelta(minutes=10)),False)
        self.assertEqual(self.ledger.read()["orders"]["x"]["status"],"REJECTED")
    def test_daily_weekly_monthly_limits(self):
        for period,amount in (("day",-201),("week",-501),("month",-1001)):
            with self.ledger.transaction() as s:
                s["trades"]=[{"closed_at":START.isoformat(),"net":amount}]
            self.assertIn("limit",self.engine.submit(signal(),period)["message"])
    def test_daily_target_blocks(self):
        with self.ledger.transaction() as s:s["trades"]=[{"closed_at":START.isoformat(),"net":301}]
        self.assertEqual(self.engine.submit(signal())["status"],"REJECTED")
    def test_stale_data(self):
        d=signal(ts=START+timedelta(minutes=20))
        self.assertIn("Stale",self.engine.submit(d)["message"])
    def test_loss_limits_include_open_exposure(self):
        self.engine.submit(signal(),"x");self.engine.on_bar(bar(START+timedelta(minutes=1)),False)
        with self.ledger.transaction() as s:
            s["trades"]=[{"closed_at":START.isoformat(),"net":-195}]
        self.engine.on_bar(bar(START+timedelta(minutes=1),symbol="WIN"),False)
        self.assertEqual(self.engine.submit(signal(symbol="WIN",ts=START+timedelta(minutes=2),stop=980))["status"],"REJECTED")
    def test_invalid_numbers(self):
        for price in (float('nan'),float('inf'),-1,True):
            with self.assertRaises(ValueError): bar(price=price)
        with self.assertRaises(ValueError):replace(bar(),open="1000")
        with self.assertRaises(ValueError): Limits(risk_fraction=float('nan')).validate()
        with self.assertRaises(ValueError): Limits(capital=True).validate()
        with self.assertRaises(ValueError): Limits(capital=10**400).validate()
        with self.assertRaises(ValueError): ExecutionSettings(fee_per_unit=True).validate()
    def test_fractional_or_boolean_execution_counts_rejected(self):
        for settings in (Limits(max_contracts=1.5),Limits(max_trades=True),Limits(start_hour=9.5)):
            with self.subTest(settings=settings),self.assertRaises(ValueError):
                settings.validate()
        ledger=Ledger()
        try:
            with self.assertRaises(ValueError):PaperEngine(ledger,Limits(max_contracts=1.5))
        finally:ledger.close()
        for settings in (ExecutionSettings(latency_bars=1.5),ExecutionSettings(latency_bars=True)):
            with self.subTest(settings=settings),self.assertRaises(ValueError): settings.validate()
        with self.assertRaises(ValueError): replace(bar(),seconds=60.5)
        with self.assertRaises(ValueError): replace(INSTRUMENTS["WIN"],lot=1.5)
        with self.assertRaises(ValueError): Strategy(reward_r=float("nan"))
        with self.assertRaises(ValueError): Limits(allowed_symbols="WIN").validate()
    def test_saved_risk_assumptions_are_immutable(self):
        with self.assertRaises(AttributeError):self.engine.limits.max_contracts=100
        with self.assertRaises(AttributeError):self.engine.costs.fee_per_unit=0
        with self.assertRaises(AttributeError):self.engine.strategy.name="breakout"
        calendar=SessionCalendar({date(2026,1,5)},verified=True)
        with self.assertRaises(AttributeError):calendar.holidays.add(date(2026,1,6))
    def test_duplicate_candle_ignored(self):
        self.engine.on_bar(bar(),False);self.assertEqual(self.ledger.read()["sequence"],1)
        with self.assertRaises(ValueError):self.engine.on_bar(bar(close=1000.5),False)
    def test_atomic_rollback(self):
        original=self.engine._fill
        def fail(*args): original(*args);raise RuntimeError("injected after fill")
        self.engine.submit(signal(),"x");self.engine._fill=fail
        with self.assertRaises(RuntimeError):self.engine.on_bar(bar(START+timedelta(minutes=1)),False)
        self.assertFalse(self.ledger.read()["positions"])
        self.assertEqual(self.ledger.read()["orders"]["x"]["status"],"NEW")
    def test_restart_positions_and_blocks(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            path=Path(tmp)/"state.db"
            ledger=Ledger(path);e=PaperEngine(ledger,costs=self.engine.costs)
            e.on_bar(bar(),False);e.submit(signal(),"x");e.on_bar(bar(START+timedelta(minutes=1)),False);e.emergency(START);ledger.close()
            ledger=Ledger(path);e=PaperEngine(ledger,costs=self.engine.costs)
            self.assertTrue(ledger.read()["emergency"]);self.assertEqual(len(ledger.read()["positions"]),1)
            e.on_bar(bar(START+timedelta(minutes=2),price=990),False)
            self.assertEqual(len(ledger.read()["trades"]),1);ledger.close()
    def test_changed_configuration_rejected_with_exposure(self):
        self.engine.submit(signal());self.engine.on_bar(bar(START+timedelta(minutes=1)),False)
        with self.assertRaises(ValueError):PaperEngine(self.ledger,Limits(capital=20000))
    def test_unauthorized(self):
        self.assertIn("authorized",self.engine.submit(replace(signal(),strategy="unknown"))["message"])
    def test_user_verified_session_blocks_entries_but_keeps_exits(self):
        holiday=SessionCalendar({date(2026,1,5)},verified=True)
        ledger=Ledger();engine=PaperEngine(ledger,calendar=holiday)
        engine.on_bar(bar(),False)
        self.assertIn("session",engine.submit(signal())["message"])
        ledger.close()

        calendar=SessionCalendar(verified=True)
        self.assertEqual(SessionCalendar.from_config(calendar.to_config()),calendar)
        ledger=Ledger();engine=PaperEngine(ledger,calendar=calendar,
            costs=ExecutionSettings(spread_ticks=0,slippage_ticks=0,fee_per_unit=0))
        engine.on_bar(bar(),False);engine.submit(signal(),"session-order")
        engine.on_bar(bar(START+timedelta(minutes=1)),False)
        self.assertEqual(len(ledger.read()["positions"]),1)
        with self.assertRaises(ValueError):PaperEngine(ledger,calendar=SessionCalendar())
        engine.on_bar(bar(datetime(2026,1,5,21,tzinfo=UTC),price=990),False)
        self.assertEqual(ledger.read()["trades"][0]["exit_reason"],"STOP")
        ledger.close()
    def test_no_future_open_fill(self):
        self.engine.submit(signal(),"x")
        self.engine.on_bar(bar(START+timedelta(minutes=1),price=1003,low=1002,high=1004,close=1004),False)
        self.assertEqual(self.ledger.read()["orders"]["x"]["filled_price"],1003)
    def test_no_real_adapter(self):
        for method in ("submit","cancel","positions","balances","reconcile"):
            with self.assertRaises(PermissionError):getattr(RicoProfitAdapter(),method)(None)

class AnalysisCase(unittest.TestCase):
    def test_ema_constant(self):self.assertEqual(ema([3]*20,9),3)
    def test_indicators_flat(self):
        s=snapshot([bar(START+timedelta(minutes=i),high=1000,low=1000) for i in range(40)])
        self.assertEqual(s["rsi"],50);self.assertEqual(s["atr"],0);self.assertEqual(s["vwap"],1000)
    def test_no_lookahead_strategy(self):
        bars=SyntheticProvider(count=300).bars();strategy=Strategy()
        self.assertEqual(strategy.evaluate(bars[:100]),strategy.evaluate(bars[:100]))
        self.assertGreaterEqual(strategy.evaluate(bars[:100]).ts,bars[99].ts+timedelta(seconds=60))
        self.assertIsNone(strategy.evaluate(bars[:100]).confidence)
    def test_aggregate_only_complete(self):
        bars=SyntheticProvider(count=9).bars()
        higher=aggregate(bars,300)
        self.assertEqual(len(higher),1);self.assertEqual(higher[0].volume,sum(b.volume for b in bars[:5]))
    def test_csv_and_persistence(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            path=Path(tmp)/"history.csv";bars=SyntheticProvider(count=20).bars();export_csv(bars,path)
            self.assertEqual(CSVProvider(path).bars(),bars)
            store=CandleStore(Path(tmp)/"data.db");store.put(bars);store.put(bars);self.assertEqual(store.load("WIN"),bars);store.close()
    def test_csv_reject_timezone_duplicate_unsorted(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            path=Path(tmp)/"history.csv";bars=SyntheticProvider(count=3).bars()
            for rows in ([bars[0],bars[0]],list(reversed(bars))):
                export_csv(rows,path)
                with self.assertRaises(ValueError):CSVProvider(path).bars()
            with self.assertRaises(ValueError):replace(bars[0],ts=bars[0].ts.replace(tzinfo=None))
    def test_csv_reject_mixed_source_or_timeframe(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            path=Path(tmp)/"history.csv";bars=SyntheticProvider(count=2).bars()
            for changed in ({"source":"OTHER_EXPORT"},{"seconds":300}):
                with self.subTest(changed=changed):
                    export_csv([bars[0],replace(bars[1],**changed)],path)
                    with self.assertRaisesRegex(ValueError,"Mixed source or timeframe"):
                        CSVProvider(path).bars()
    def test_backtest_reproducible(self):
        bars=SyntheticProvider(count=250).bars()
        a=run_backtest(bars);b=run_backtest(bars)
        self.assertEqual(a,b);self.assertTrue(a["trades"])
        for t in a["trades"]: self.assertGreaterEqual(t["closed_at"],t["opened_at"])
    def test_temporal_partitions(self):
        a,b,c=temporal_split(SyntheticProvider(count=300).bars())
        self.assertLess(a[-1].ts,b[0].ts);self.assertLess(b[-1].ts,c[0].ts)
    def test_ml_pipeline_and_checksum(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            bars=SyntheticProvider(count=300).bars();m=train_temporal(bars,Path(tmp)/"model.json")
            self.assertFalse(m["execution_enabled"]);self.assertIsNone(predict(m,bars)["confidence"])
            mixed=bars.copy();mixed[-1]=replace(mixed[-1],source="OTHER_EXPORT")
            with self.assertRaises(ValueError):predict(m,mixed)
            with self.assertRaises(ValueError):train_temporal(mixed,Path(tmp)/"invalid.json")
            m["weights"][0]+=1
            with self.assertRaises(ValueError):predict(m,bars)
    def test_calendar_requires_verified_holidays(self):
        self.assertFalse(SessionCalendar().is_open(START,"WIN"))
        self.assertTrue(SessionCalendar().is_open(START,"BTC"))
        with self.assertRaises(ValueError):SessionCalendar(start=time(18),end=time(9),verified=True)

if __name__=="__main__":unittest.main()
