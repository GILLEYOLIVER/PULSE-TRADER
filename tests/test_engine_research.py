from __future__ import annotations
import json
import tempfile
import unittest
from dataclasses import asdict,replace
from datetime import timedelta
from pathlib import Path
from test_v2 import START,bar,signal
from trading_assistant.v2.backtest import run_backtest
from trading_assistant.v2.blind_testing import blind_replay
from trading_assistant.v2.data import SyntheticProvider,CSVProvider,CandleStore,export_csv,aggregate
from trading_assistant.v2.execution import PaperEngine
from trading_assistant.v2.indicators import snapshot
from trading_assistant.v2.learning import LearningMemory,HistoricalRotation
from trading_assistant.v2.ledger import Ledger,SimulationLedger
from trading_assistant.v2.market_data import fetch_binance,DataUnavailable
from trading_assistant.v2.ml import train_temporal,predict,features
from trading_assistant.v2.models import Instrument,Limits,ExecutionSettings
from trading_assistant.v2.strategy import Strategy
from trading_assistant.v2.suggestions import history_digest


class AccountingCase(unittest.TestCase):
    def test_provider_currency_blocks_a_misconfigured_usdt_instrument(self):
        ledger=Ledger();self.addCleanup(ledger.close)
        instrument=Instrument('BTCUSDT',1,.01,currency='BRL')
        engine=PaperEngine(ledger,instruments={'BTCUSDT':instrument},limits=replace(Limits(),allowed_symbols=('BTCUSDT',)))
        engine.on_bar(replace(bar(symbol='BTCUSDT'),source='BINANCE_SPOT_USDT'),False)
        order=engine.submit(signal(symbol='BTCUSDT'))
        self.assertEqual(order['qty'],0);self.assertIn('currency',order['message'])

    def test_moving_stop_is_tighter_and_only_applies_to_the_following_bar(self):
        ledger=Ledger();self.addCleanup(ledger.close)
        engine=PaperEngine(ledger,limits=replace(Limits(),capital=100000.),strategy=Strategy('ema_pullback'),
            costs=ExecutionSettings(fee_per_unit=0,spread_ticks=0,slippage_ticks=0))
        for i in range(70):engine.on_bar(bar(START+timedelta(minutes=i),price=1000+i),False)
        decision=replace(signal(ts=START+timedelta(minutes=70),price=1070,stop=1050,target=1200),strategy='ema_pullback')
        engine.submit(decision,'moving')
        engine.on_bar(bar(START+timedelta(minutes=70),price=1070,high=1071,low=1055),False)
        position=ledger.read()['positions']['moving'];new_stop=position['stop']
        self.assertGreater(new_stop,1055);self.assertEqual(position['initial_stop'],1050)
        engine.on_bar(bar(START+timedelta(minutes=71),price=1060,high=1062,low=1055),False)
        trade=ledger.read()['trades'][0]
        self.assertEqual(trade['exit_reason'],'STOP');self.assertEqual(trade['exit'],new_stop)
    def engine(self,**kwargs):
        ledger=Ledger();self.addCleanup(ledger.close)
        engine=PaperEngine(ledger,**kwargs);engine.on_bar(bar(),False)
        return engine,ledger

    def test_proportional_fees_use_actual_entry_and_exit_not_signal_prices(self):
        costs=ExecutionSettings(fee_per_unit=.1,fee_bps=10,spread_ticks=0,slippage_ticks=0)
        engine,ledger=self.engine(costs=costs)
        engine.submit(signal(),'fee');engine.on_bar(bar(START+timedelta(minutes=1)),False)
        engine.flatten(START+timedelta(minutes=2))
        trade=ledger.read()['trades'][0]
        expected=trade['qty']*(.2+(trade['entry']+trade['exit'])*trade['point_value']*.001)
        self.assertAlmostEqual(trade['fees'],expected)
        self.assertAlmostEqual(trade['net'],trade['gross']-expected)

    def test_short_restriction_and_currency_are_independent_risk_gates(self):
        specs={'WDO':Instrument('WDO',10,.5,allow_short=False)}
        engine,_=self.engine(instruments=specs,costs=ExecutionSettings(fee_per_unit=0))
        order=engine.submit(signal(side='SELL',stop=1002,target=990))
        self.assertEqual(order['status'],'REJECTED');self.assertIn('Short',order['message'])
        other=replace(specs['WDO'],currency='USDT')
        engine,_=self.engine(instruments={'WDO':other})
        self.assertIn('currency',engine.submit(signal())['message'])

    def test_net_reward_guard_can_refuse_a_gross_profitable_setup(self):
        engine,_=self.engine(limits=replace(Limits(),min_net_reward_r=1.5),
            costs=ExecutionSettings(fee_per_unit=5,spread_ticks=0,slippage_ticks=0))
        order=engine.submit(signal(target=1004))
        self.assertIn('Net reward',order['message']);self.assertEqual(order['qty'],0)

    def test_scaled_quantity_uses_provider_volume_in_base_units(self):
        specs={'WDO':Instrument('WDO',.01,.5,margin=10,volume_per_unit=.01)}
        engine,ledger=self.engine(instruments=specs,limits=replace(Limits(),max_contracts=100),
            costs=ExecutionSettings(fee_per_unit=0,spread_ticks=0,slippage_ticks=0))
        with ledger.transaction() as state:state['liquidity']['WDO']=1.
        engine.submit(signal(),'scaled');engine.on_bar(bar(START+timedelta(minutes=1)),False)
        self.assertEqual(ledger.read()['orders']['scaled']['filled_qty'],10)

    def test_legacy_open_position_restarts_with_new_neutral_defaults(self):
        engine,ledger=self.engine(costs=ExecutionSettings(fee_per_unit=0))
        engine.submit(signal(),'old');engine.on_bar(bar(START+timedelta(minutes=1)),False)
        with ledger.transaction() as state:
            state['config']['costs'].pop('fee_bps')
            state['config']['limits'].pop('min_net_reward_r');state['config']['limits'].pop('currency')
            for item in state['config']['instruments'].values():
                item.pop('allow_short');item.pop('volume_per_unit')
        PaperEngine(ledger,costs=ExecutionSettings(fee_per_unit=0))
        self.assertTrue(ledger.read()['positions'])
        with self.assertRaises(ValueError):PaperEngine(ledger,costs=ExecutionSettings(fee_per_unit=0,fee_bps=1))

    def test_fee_validation_rejects_nonfinite_and_negative(self):
        for value in (-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):ExecutionSettings(fee_bps=value).validate()

    def test_break_even_does_not_put_a_protective_stop_above_the_current_close(self):
        engine,ledger=self.engine(costs=ExecutionSettings(fee_per_unit=0,fee_bps=10,
            spread_ticks=0,slippage_ticks=0,break_even_r=.5))
        engine.submit(signal(),'be')
        engine.on_bar(bar(START+timedelta(minutes=1),close=1001.5,high=1002,low=999),False)
        position=next(iter(ledger.read()['positions'].values()))
        self.assertLess(position['stop'],1001.5)


class ResearchCorrectnessCase(unittest.TestCase):
    def test_ma_methods_need_warmup_and_produce_causal_protective_levels(self):
        bars=SyntheticProvider(count=600,seed=512).bars()
        count=0
        for name in ('sma_cross','ema_pullback'):
            strategy=Strategy(name)
            self.assertIsNone(strategy.evaluate(bars[:35]))
            for end in range(201,601):
                d=strategy.evaluate(bars[:end])
                if d and d.side!='WAIT':
                    count+=1
                    self.assertEqual(d.ts,bars[end-1].ts+timedelta(minutes=1))
                    self.assertTrue(d.stop<d.price<d.target if d.side=='BUY' else d.target<d.price<d.stop)
                    self.assertIn('ma_trend',d.indicators)
            prefix=bars[:300]
            self.assertEqual(strategy.evaluate(prefix),strategy.evaluate(bars[:300]))
        self.assertGreater(count,0)

    def test_blind_warmup_cannot_overlap_external_period(self):
        bars=SyntheticProvider(count=80).bars()
        with self.assertRaises(ValueError):
            blind_replay(iter(bars[50:]),warmup=bars[:60],strategy=Strategy(),limits=Limits(),
                costs=ExecutionSettings(),instruments={'WIN':Instrument('WIN',.2,5)})
    def test_fast_replay_matches_durable_state_and_all_orders(self):
        bars=SyntheticProvider(count=220,seed=631).bars()
        fast=run_backtest(bars);durable=run_backtest(bars,durable=True)
        self.assertEqual(fast,durable)

    def test_failed_memory_run_is_poisoned_instead_of_exposing_partial_state(self):
        ledger=SimulationLedger()
        with self.assertRaises(RuntimeError):
            with ledger.transaction() as state:state['emergency']=True;raise RuntimeError('injected')
        with self.assertRaises(ValueError):ledger.read()
        with self.assertRaises(ValueError):
            with ledger.transaction():pass

    def test_core_features_match_full_indicators(self):
        for size in (35,200,1000):
            bars=SyntheticProvider(count=size,seed=631).bars()
            full,core=snapshot(bars),snapshot(bars,full=False)
            for key,value in core.items():self.assertEqual(value,full[key])

    def test_future_suffix_cannot_change_prefix_decisions_or_orders(self):
        bars=SyntheticProvider(count=180,seed=88).bars();cut=100
        changed=bars[:cut]+[replace(b,open=b.open*.8,high=b.high*.8,low=b.low*.8,close=b.close*.8) for b in bars[cut:]]
        args=dict(strategy=Strategy('adaptive'),limits=replace(Limits(),allowed_strategies=('adaptive',)),
            costs=ExecutionSettings(),instruments={'WIN':Instrument('WIN',.2,5)})
        _,left=blind_replay(iter(bars),**args);_,right=blind_replay(iter(changed),**args)
        self.assertEqual(left[:cut],right[:cut])

    def test_enriched_model_reloads_predicts_and_matches_feature_schema(self):
        bars=SyntheticProvider(count=260).bars()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'model.json'
            model=train_temporal(bars,path,feature_set='regime_flow_v2')
            self.assertEqual(len(model['features']),14)
            self.assertEqual(len(model['weights']),15)
            self.assertFalse(model['execution_enabled'])
            self.assertFalse(model['probability_calibrated'])
            self.assertEqual(predict(model,bars),predict(json.loads(path.read_text()),bars))
            self.assertEqual(features(bars,'regime_flow_v2'),features(bars[-200:],'regime_flow_v2'))


class LearningAndDataCase(unittest.TestCase):
    def test_parameter_memory_can_seed_training_without_reading_blind_winners(self):
        with tempfile.TemporaryDirectory() as directory:
            memory=LearningMemory(directory)
            safe={'profile':'daily','winner':{'parameters':asdict(Strategy('breakout')),'risk_profile':'balanced'}}
            leaked={'profile':'daily','winner':{'parameters':asdict(Strategy('trend',99)),'risk_profile':'higher_risk'}}
            memory.append('SEALED_POLICY',safe);memory.append('BLIND_TEST',leaked)
            self.assertEqual(memory.parameter_priors('daily'),[safe['winner']])
    def test_rotation_uses_another_window_and_rejects_overlap(self):
        with tempfile.TemporaryDirectory() as directory:
            rotation=HistoricalRotation(directory)
            first=rotation.plan(('BTCUSDT',),300,as_of=START,test_days=7,training_days=21)
            rotation.reserve('one','BTCUSDT',300,first['test_start'],first['test_end'])
            second=rotation.plan(('BTCUSDT',),300,as_of=START,test_days=7,training_days=21)
            self.assertLessEqual(second['test_end'],first['test_start'])
            with self.assertRaises(ValueError):rotation.reserve('two','BTCUSDT',300,first['test_start'],first['test_end'])

    def test_learning_preserves_dataset_and_model_inside_software_data_directory(self):
        bars=SyntheticProvider(count=220).bars()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);model=train_temporal(bars,root/'export.json')
            memory=LearningMemory(root/'learning');record=memory.remember_model(bars,model,root/'export.json')['payload']
            saved=CSVProvider(memory.directory/record['dataset_path']).bars()
            self.assertEqual(saved,bars)
            self.assertEqual(json.loads((memory.directory/record['model_path']).read_text())['sha256'],model['sha256'])
            self.assertFalse(HistoricalRotation(memory.directory).available('WIN',60,'2026-01-05','2026-01-06'))
    def test_memory_keeps_blind_results_out_of_training_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            memory=LearningMemory(directory)
            memory.append('TRAIN',{'score':1});memory.append('BLIND_TEST',{'score':999})
            self.assertEqual([r['payload']['score'] for r in memory.training_records()],[1])
            self.assertEqual(len(memory.evaluations()),1)
            memory.training_path.write_text(memory.training_path.read_text().replace('"score": 1','"score": 9'))
            with self.assertRaises(ValueError):memory.training_records()

    def test_activity_survives_csv_aggregation_and_old_cache_rows(self):
        bars=[replace(bar(START+timedelta(minutes=i)),quote_volume=10000.,trades=10,taker_buy_volume=5000.) for i in range(5)]
        combined=aggregate(bars,300)[0]
        self.assertEqual(combined.trades,50);self.assertEqual(combined.taker_buy_volume,25000)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'bars.csv';export_csv(bars,path)
            self.assertEqual(CSVProvider(path).bars(),bars)
            store=CandleStore(Path(directory)/'cache.sqlite')
            original=bar();old=asdict(original);old['ts']=original.ts.isoformat()
            for key in ('trades','quote_volume','taker_buy_volume'):old.pop(key)
            store.db.execute('INSERT INTO candles VALUES(?,?,?,?,?)',(original.symbol,old['ts'],60,original.source,json.dumps(old)));store.db.commit()
            store.put([original]);self.assertEqual(store.load(original.symbol,60,original.source),[original])
            store.close()
        self.assertNotEqual(history_digest([bars[0]]),history_digest([replace(bars[0],trades=11)]))

    def test_binance_closed_data_validates_clock_and_preserves_activity(self):
        ts=int(START.timestamp()*1000)
        rows=[[ts,'100','102','99','101','10',ts+59999,'1000',12,'6','600','0']]
        def getter(*args,**kwargs):return rows
        market=fetch_binance('BTCUSDT',60,start=START,end=START+timedelta(minutes=1),getter=getter)
        self.assertEqual(market.bars[0].taker_buy_volume,6)
        self.assertEqual(market.bars[0].trades,12)
        rows[0][6]+=1
        with self.assertRaises(DataUnavailable):fetch_binance('BTCUSDT',60,start=START,end=START+timedelta(minutes=1),getter=getter)

    def test_impossible_activity_does_not_enter_a_candle(self):
        for change in ({'trades':1.5},{'taker_buy_volume':10001},{'quote_volume':-1}):
            with self.assertRaises(ValueError):replace(bar(),**change)
