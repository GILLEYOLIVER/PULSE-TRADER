from __future__ import annotations

import csv
import hashlib
import io
import json
import tempfile
import threading
import time
import unittest
import zipfile
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from test_v2 import START, bar
from test_suggestions import directional
from trading_assistant.v2.backups import create_backup, restore_backup
from trading_assistant.v2.company_context import company_filings, summarize_context
from trading_assistant.v2.data import SyntheticProvider
from trading_assistant.v2.execution import PaperEngine
from trading_assistant.v2.jobs import BackgroundJobs
from trading_assistant.v2.ledger import Ledger
from trading_assistant.v2.market_data import fetch_market, read_profit_csv, DataUnavailable
from trading_assistant.v2.models import ExecutionSettings
from trading_assistant.v2.suggestions import analyze_series, save_plan
from trading_assistant.v2.validation import validate_history


class MarketCase(unittest.TestCase):
    def test_brapi_retains_raw_ohlc_and_excludes_unfinished_candle(self):
        def getter(url,**kwargs):
            rows=[dict(date=int((START+timedelta(minutes=i)).timestamp()),open=100,high=102,low=99,close=101,adjustedClose=50,volume=1000) for i in range(2)]
            return {'results':[{'symbol':'PETR4','data':{'usedInterval':'1m','historicalDataPrice':rows}}]}
        with patch.dict('os.environ',{'BRAPI_TOKEN':''}):
            result=fetch_market('PETR4',60,window='5d',now=START+timedelta(seconds=90),getter=getter)
        self.assertEqual(len(result.bars),1)
        self.assertEqual(result.bars[0].close,101)
        self.assertEqual(result.bars[0].source,'BRAPI_RAW')
        self.assertFalse(result.provenance['live_quotes'])

    def test_provider_timeframe_or_entitlement_mismatch_fails(self):
        with self.assertRaises(DataUnavailable):
            fetch_market('PETR4',60,getter=lambda *a,**k:{'results':[{'symbol':'PETR4','data':{'usedInterval':'1d'}}]})
        with patch.dict('os.environ',{'BRAPI_TOKEN':''}),self.assertRaises(DataUnavailable):
            fetch_market('WIN')

    def test_crypto_is_brl_and_requires_equal_arrays(self):
        payload={'t':[int(START.timestamp())],'o':['100'],'h':['102'],'l':['99'],'c':['101'],'v':['10']}
        result=fetch_market('BTC',60,provider='mercado_bitcoin',now=START+timedelta(minutes=1),getter=lambda *a,**k:payload)
        self.assertEqual(result.bars[0].source,'MERCADO_BITCOIN_BRL')
        payload['v']=[]
        with self.assertRaises(DataUnavailable):
            fetch_market('BTC',60,provider='mercado_bitcoin',getter=lambda *a,**k:payload)

    def test_profit_converter_handles_locale_order_clock_and_quantity(self):
        text='Ativo;Data;Hora;Abertura;Máxima;Mínima;Fechamento;Volume Financeiro;Volume Quantidade\nWDO;05/01/2026;09:02;1.000,50;1.002,00;999,00;1.001,00;999999;1.234\nWDO;05/01/2026;09:01;1.000,50;1.002,00;999,00;1.001,00;999999;1.234\n'
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'profit.csv';path.write_bytes(text.encode('cp1252'))
            rows=read_profit_csv(path,seconds=60,timestamp_kind='close')
            self.assertEqual(rows[0].ts,START)
            self.assertEqual(rows[0].open,1000.5)
            self.assertEqual(rows[0].volume,1234)
            self.assertLess(rows[0].ts,rows[1].ts)
            path.write_text(text.replace(';Volume Quantidade','').replace(';1.234',''),encoding='utf-8')
            with self.assertRaises(ValueError):read_profit_csv(path)


class PlansCase(unittest.TestCase):
    def setUp(self):
        self.ledger=Ledger()
        self.engine=PaperEngine(self.ledger,costs=ExecutionSettings(spread_ticks=0,slippage_ticks=0,fee_per_unit=0))
        self.bars=directional()
        for item in self.bars:self.engine.on_bar(item,False)
        self.now=self.bars[-1].ts+timedelta(minutes=1)
        self.suggestion=analyze_series(self.bars,'intraday',as_of=self.now)

    def tearDown(self):self.ledger.close()

    def save(self,suggestion=None,**kwargs):
        return save_plan(self.ledger,suggestion or self.suggestion,saved_at=self.now,
                         limits=self.engine.limits,costs=self.engine.costs,parameters=self.engine.strategy,**kwargs)

    def test_conditional_plan_fills_only_after_trigger_and_risk_gate(self):
        plan=self.save();self.assertEqual(self.engine.arm_plan(plan['id'],self.now)['state'],'ARMED')
        self.assertFalse(self.ledger.read()['orders'])
        trigger=self.suggestion.entry+.5
        self.engine.on_bar(bar(self.now,price=trigger,high=trigger+1,low=trigger-1,volume=20000),False)
        self.engine.process_plans()
        state=self.ledger.read();order=state['orders']['plan:'+plan['id']]
        self.assertEqual(order['status'],'NEW');self.assertEqual(order['filled_qty'],0)
        self.engine.process_plans();self.assertEqual(len(self.ledger.read()['orders']),1)
        self.engine.on_bar(bar(self.now+timedelta(minutes=1),price=trigger,high=trigger+1,low=trigger-1),False)
        order=self.ledger.read()['orders']['plan:'+plan['id']]
        self.assertGreater(order['filled_qty'],0)
        self.assertEqual(order['filled_at'],(self.now+timedelta(minutes=1)).isoformat())
        self.assertEqual(self.ledger.read()['analysis_plans'][plan['id']]['state'],'EXECUTED')

    def test_confirmed_plan_and_order_are_one_transaction_and_idempotent(self):
        suggestion=replace(self.suggestion,setup='CONFIRMED',entry=self.bars[-1].close)
        plan=self.save(suggestion)
        first=self.engine.arm_plan(plan['id'],self.now)
        second=self.engine.arm_plan(plan['id'],self.now)
        self.assertEqual(first,second)
        state=self.ledger.read()
        self.assertEqual(state['analysis_plans'][plan['id']]['order_id'],'plan:'+plan['id'])
        self.assertEqual(len(state['orders']),1)
        self.assertFalse(state['positions'])

    def test_emergency_or_wrong_history_cannot_arm(self):
        plan=self.save()
        self.engine.emergency(self.now,True)
        with self.assertRaisesRegex(ValueError,'Risco'):self.engine.arm_plan(plan['id'],self.now)
        self.engine.emergency(self.now,False)
        self.engine.on_bar(bar(self.now,price=1070),False)
        with self.assertRaisesRegex(ValueError,'histórico'):self.engine.arm_plan(plan['id'],self.now+timedelta(minutes=1))
        self.assertFalse(self.ledger.read()['orders'])

    def test_fill_rechecks_risk_after_plan_approval(self):
        plan=self.save(replace(self.suggestion,setup='CONFIRMED',entry=self.bars[-1].close))
        self.engine.arm_plan(plan['id'],self.now)
        with self.ledger.transaction() as state:state['blocks']['day:2026-01-05']='Loss limit reached'
        self.engine.on_bar(bar(self.now,price=1069),False)
        state=self.ledger.read()
        self.assertEqual(state['orders']['plan:'+plan['id']]['status'],'REJECTED')
        self.assertEqual(state['analysis_plans'][plan['id']]['state'],'REJECTED')
        self.assertFalse(state['positions'])

    def test_changed_instrument_invalidates_plan(self):
        plan=self.save();specs=dict(self.engine.specs);specs['WDO']=replace(specs['WDO'],margin=1200)
        engine=PaperEngine(self.ledger,costs=self.engine.costs,instruments=specs);engine.history=self.engine.history
        with self.assertRaisesRegex(ValueError,'Especificação'):engine.arm_plan(plan['id'],self.now)

    def test_daily_native_period_is_not_dropped_by_utc_alignment(self):
        from trading_assistant.v2.data import aggregate
        daily=[replace(item,seconds=86400,ts=START.replace(hour=3)+timedelta(days=i)) for i,item in enumerate(self.bars)]
        self.assertEqual(aggregate(daily,86400),daily)

    def test_expiry_and_context_review_block_entry(self):
        plan=self.save(context={'review_required':True},context_ack=False)
        with self.assertRaisesRegex(ValueError,'alertas'):self.engine.arm_plan(plan['id'],self.now)
        plan=self.save(context={'review_required':True},context_ack=True)
        self.engine.arm_plan(plan['id'],self.now)
        self.engine.on_bar(bar(self.now+timedelta(minutes=4),price=1070),False)
        self.engine.process_plans()
        self.assertEqual(self.ledger.read()['analysis_plans'][plan['id']]['state'],'EXPIRED')
        self.assertFalse(self.ledger.read()['orders'])

    def test_changed_configuration_invalidates_armed_plan(self):
        plan=self.save();self.engine.arm_plan(plan['id'],self.now)
        replacement=PaperEngine(self.ledger,limits=replace(self.engine.limits,weekly_loss=550),costs=self.engine.costs)
        replacement.history=self.engine.history
        replacement.on_bar(bar(self.now,price=1070),False);replacement.process_plans()
        self.assertEqual(self.ledger.read()['analysis_plans'][plan['id']]['state'],'STALE')


class BackupCase(unittest.TestCase):
    def test_online_backup_restores_orders_blocks_and_plans(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);data=root/'runtime';ledger=Ledger(data/'paper.sqlite')
            with ledger.transaction() as state:
                state['emergency']=True;state['analysis_plans']={'one':{'state':'ARMED'}}
            archive=root/'backup.zip';create_backup(data,archive)
            target=root/'restored';restore_backup(archive,target)
            restored=Ledger(target/'paper.sqlite')
            try:
                self.assertTrue(restored.read()['emergency'])
                self.assertEqual(restored.read()['analysis_plans'],{'one':{'state':'ARMED'}})
                with self.assertRaises(ValueError):restore_backup(archive,target)
            finally:restored.close();ledger.close()

    def test_restore_rejects_tampering_and_path_traversal_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name,raw,expected in (('../outside',b'hello',hashlib.sha256(b'hello').hexdigest()),('file',b'hello','bad')):
                archive=root/'bad.zip'
                with zipfile.ZipFile(archive,'w') as bundle:
                    bundle.writestr('manifest.json',json.dumps({'version':1,'files':{name:expected}}))
                    bundle.writestr('data/'+name,raw)
                with self.assertRaises(ValueError):restore_backup(archive,root/'restored')
                self.assertFalse((root/'restored').exists())


class ContextAndResearchCase(unittest.TestCase):
    def test_current_context_is_excluded_from_past_replay(self):
        context={'available_at':(START+timedelta(days=1)).isoformat(),'fundamentals':{'profitMargins':-.2}}
        self.assertFalse(summarize_context(context,as_of=START)['included'])
        result=summarize_context(context,as_of=START+timedelta(days=2))
        self.assertTrue(result['review_required']);self.assertTrue(result['included'])

    def test_filings_are_only_available_after_publication_day(self):
        raw=io.BytesIO()
        with zipfile.ZipFile(raw,'w') as archive:
            archive.writestr('events.csv','CNPJ_Companhia;Data_Entrega;Categoria;Assunto;Link_Download\n12.345.678/0001-90;2026-01-05;Fato Relevante;Teste de publicação;https://example.com/document\n')
        self.assertFalse(company_filings(raw.getvalue(),'12345678000190',START))
        self.assertEqual(len(company_filings(raw.getvalue(),'12345678000190',START+timedelta(days=1))),1)

    def test_validation_has_separate_holdout_and_never_promotes_synthetic(self):
        bars=SyntheticProvider('WIN',250).bars()
        report=validate_history(bars,now=bars[-1].ts+timedelta(minutes=1))
        self.assertLess(report['partitions']['validation_end'],report['partitions']['test_start'])
        self.assertFalse(report['evidence_gate_passed'])
        self.assertFalse(report['ml']['probability_calibrated'])
        self.assertFalse(report['execution_enabled'])


if __name__=='__main__':unittest.main()
