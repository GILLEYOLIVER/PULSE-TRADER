from __future__ import annotations
import tempfile,unittest,json,asyncio
from pathlib import Path
from datetime import timedelta
from dataclasses import replace
from test_v2 import bar,signal,START
from trading_assistant.v2.models import Limits,ExecutionSettings
from trading_assistant.v2.execution import PaperEngine
from trading_assistant.v2.ledger import Ledger
from trading_assistant.v2.data import SyntheticProvider
from trading_assistant.v2.backtest import run_backtest
from trading_assistant.config import ExecutionConfig,AuditConfig
from trading_assistant.execution.order_router import OrderRouter
from trading_assistant.infra.audit import AuditLogger

class ExtraCase(unittest.TestCase):
    def test_legacy_live_disabled(self):
        for mode in ('live','REAL','LIVE'):
            with self.assertRaises(PermissionError):OrderRouter(ExecutionConfig(mode=mode))
        coro=OrderRouter(ExecutionConfig()).execute(None,None)
        try:
            with self.assertRaises(PermissionError):coro.send(None)
        finally:coro.close()
    def test_audit_redaction_datetime(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            path=Path(tmp)/'audit.log';a=AuditLogger(AuditConfig(path=str(path)))
            a.info('test',{'nested':{'api_key':'DO_NOT_LOG','password':'NEVER'},'when':START})
            text=path.read_text(encoding='utf8');self.assertNotIn('DO_NOT_LOG',text);self.assertNotIn('NEVER',text)
            self.assertEqual(json.loads(text)['payload']['nested']['api_key'],'[REDACTED]')
    def test_spread_and_slippage_block(self):
        for costs in (ExecutionSettings(spread_ticks=100),ExecutionSettings(slippage_ticks=100)):
            ledger=Ledger();e=PaperEngine(ledger,costs=costs);e.on_bar(bar(),False)
            self.assertEqual(e.submit(signal())['status'],'REJECTED');ledger.close()
    def test_hours_and_margin_block(self):
        for limits in (Limits(start_hour=10,end_hour=11),Limits(capital=100,risk_fraction=.005)):
            ledger=Ledger();e=PaperEngine(ledger,limits);e.on_bar(bar(),False)
            self.assertEqual(e.submit(signal())['status'],'REJECTED');ledger.close()
    def test_future_volume_does_not_determine_fill(self):
        states=[]
        for volume in (0,100000):
            ledger=Ledger();e=PaperEngine(ledger,costs=ExecutionSettings(spread_ticks=0,slippage_ticks=0,fee_per_unit=0))
            e.on_bar(bar(),False);e.submit(signal(),'x');e.on_bar(bar(START+timedelta(minutes=1),volume=volume),False)
            states.append(ledger.read()['orders']['x']['filled_qty']);ledger.close()
        self.assertEqual(states[0],states[1]);self.assertGreater(states[0],0)
    def test_missing_candles_cancel_entry_but_keep_protective_stop(self):
        ledger=Ledger();e=PaperEngine(ledger,costs=ExecutionSettings(spread_ticks=0,slippage_ticks=0,fee_per_unit=0))
        e.on_bar(bar(),False)
        e.submit(replace(signal(),expires=START+timedelta(minutes=20)),"pending")
        e.on_bar(bar(START+timedelta(minutes=10),price=995,high=997,low=994),False)
        state=ledger.read()
        self.assertEqual(state["orders"]["pending"]["status"],"CANCELLED")
        self.assertEqual(state["orders"]["pending"]["reserved_risk"],0.)
        self.assertEqual(ledger.db.execute("SELECT COUNT(*) FROM audit WHERE event='data_gap'").fetchone()[0],1)
        ledger.close()

        ledger=Ledger();e=PaperEngine(ledger,costs=ExecutionSettings(spread_ticks=0,slippage_ticks=0,fee_per_unit=0))
        e.on_bar(bar(),False);e.submit(signal(),"filled")
        e.on_bar(bar(START+timedelta(minutes=1)),False)
        e.on_bar(bar(START+timedelta(minutes=10),price=995,high=997,low=994),False)
        self.assertEqual(ledger.read()["trades"][0]["exit_reason"],"STOP")
        ledger.close()
    def test_explicit_expiry(self):
        from trading_assistant.v2.models import INSTRUMENTS
        specs=dict(INSTRUMENTS);specs['WDO']=replace(specs['WDO'],expiry='2026-01-05')
        ledger=Ledger();e=PaperEngine(ledger,instruments=specs);e.on_bar(bar(),False)
        self.assertIn('Expired contract',e.submit(signal())['message']);ledger.close()
    def test_portfolio_backtest_fails_explicitly(self):
        with self.assertRaisesRegex(ValueError,'one symbol'):
            run_backtest(SyntheticProvider('WIN',40).bars()+SyntheticProvider('WDO',40).bars())
    def test_later_day_resets_day_block_not_week(self):
        ledger=Ledger();e=PaperEngine(ledger)
        with ledger.transaction() as s:
            s['trades']=[{'closed_at':START.isoformat(),'net':-600}]
            s['blocks']['day:2026-01-05']='Loss limit reached'
        nextday=START+timedelta(days=1);e.on_bar(bar(nextday),False)
        o=e.submit(signal(ts=nextday+timedelta(minutes=1)))
        self.assertTrue(o['message'].startswith('week:'));ledger.close()
    def test_monthly_limit_after_new_week(self):
        ledger=Ledger();e=PaperEngine(ledger)
        with ledger.transaction() as s:s['trades']=[{'closed_at':START.isoformat(),'net':-1001}]
        later=START+timedelta(days=7);e.on_bar(bar(later),False)
        self.assertTrue(e.submit(signal(ts=later+timedelta(minutes=1)))['message'].startswith('month:'));ledger.close()
    def test_order_key_payload_conflict(self):
        ledger=Ledger();e=PaperEngine(ledger);e.on_bar(bar(),False);e.submit(signal(),'x')
        with self.assertRaises(ValueError):e.submit(replace(signal(),price=1001),'x')
        ledger.close()
    def test_real_equity_costs(self):
        report=run_backtest(SyntheticProvider(count=150).bars())
        self.assertAlmostEqual(sum(t['gross']-t['fees'] for t in report['trades']),report['metrics']['net'])
        self.assertEqual(report['equity'][-1],report['limits']['capital']+report['metrics']['net'])
