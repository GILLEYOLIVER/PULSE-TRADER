from __future__ import annotations

import unittest
import json
from unittest.mock import patch
from dataclasses import asdict,replace
from datetime import timedelta

from test_v2 import START
from trading_assistant.v2.backtest import run_backtest
from trading_assistant.v2.data import SyntheticProvider
from trading_assistant.v2.models import Limits,ExecutionSettings,INSTRUMENTS
from trading_assistant.v2.strategy import Strategy
from trading_assistant.v2.blind_testing import blind_replay
from trading_assistant.v2.trade_learning import (TRADE_FEATURES,InsufficientTradeData,collect_trade_samples,
    fit_trade_model,score_trade,validate_trade_model)


class TradeLearningCase(unittest.TestCase):
    def samples(self,count=120):
        start=START-timedelta(days=3)
        return [{'signal_at':(start+timedelta(minutes=i*3)).isoformat(),
            'available_at':(start+timedelta(minutes=i*3+1)).isoformat(),
            'features':[float((1 if i%2 else -1)*(j+1)/20) for j in range(len(TRADE_FEATURES))],
            'label':i%2,'net':10. if i%2 else -10.,'trade_id':str(i)} for i in range(count)]

    def fit(self,samples=None):
        return fit_trade_model(self.samples() if samples is None else samples,parameters=asdict(Strategy()),
            symbol='WIN',seconds=60,source='SYNTHETIC',cutoff=START-timedelta(days=1),
            costs=ExecutionSettings(),instrument=INSTRUMENTS['WIN'],dataset_sha256='fixture')

    def test_model_is_deterministic_regularized_and_not_a_calibrated_probability(self):
        first=self.fit();second=self.fit()
        self.assertEqual(first,second)
        self.assertEqual(first['training_samples'],120)
        self.assertFalse(first['probability_calibrated'])
        validate_trade_model(first,asdict(Strategy()))
        self.assertEqual(len(first['weights']),len(TRADE_FEATURES)+1)

    def test_rounding_noise_in_constant_risk_features_is_not_amplified(self):
        samples=self.samples()
        for index,sample in enumerate(samples):sample['features'][-3]=1.5+(-1 if index%2 else 1)*1e-14
        model=self.fit(samples)
        self.assertEqual(model['stds'][-3],1e-6)
        self.assertLess(abs(model['weights'][-4]),1e-6)

    def test_future_labels_repeats_one_class_and_tiny_samples_cannot_train(self):
        future=self.samples();future[-1]['available_at']=(START+timedelta(days=1)).isoformat()
        with self.assertRaises(ValueError):self.fit(future)
        repeated=self.samples();repeated[-1]['signal_at']=repeated[0]['signal_at']
        with self.assertRaises(ValueError):self.fit(repeated)
        with self.assertRaises(InsufficientTradeData):self.fit(self.samples(20))
        one_class=self.samples()
        for sample in one_class:sample['label']=1
        with self.assertRaises(InsufficientTradeData):self.fit(one_class)

    def test_model_tampering_wrong_parameters_and_unsupported_thresholds_are_rejected(self):
        model=self.fit();changed={**model,'weights':[1.]*len(model['weights'])}
        with self.assertRaises(ValueError):Strategy(trade_filter=changed,trade_score_threshold=.6)
        with self.assertRaises(ValueError):Strategy(reward_r=3,trade_filter=model,trade_score_threshold=.6)
        for threshold in (-1,float('nan'),True,1.1):
            with self.assertRaises(ValueError):Strategy(trade_filter=model,trade_score_threshold=threshold)
        with self.assertRaises(ValueError):Strategy(trade_score_threshold=.6)

    def test_inference_refuses_training_times_and_incompatible_markets(self):
        bars=SyntheticProvider(count=100,seed=512).bars();model=self.fit()
        decision=Strategy().evaluate(bars)
        result=score_trade(model,decision,bars)
        self.assertTrue(0<result['score']<1);self.assertFalse(result['probability_calibrated'])
        old=replace(decision,ts=START-timedelta(days=2))
        with self.assertRaises(ValueError):score_trade(model,old,bars)
        with self.assertRaises(ValueError):score_trade(model,decision,[replace(b,source='BINANCE_SPOT_USDT') for b in bars])

    def test_model_warmup_builds_context_without_scoring_its_training_period(self):
        from trading_assistant.v2.learning import digest
        bars=SyntheticProvider(count=320,seed=512).bars();model=self.fit()
        model['training_cutoff']=bars[260].ts.isoformat()
        model['sha256']=digest({k:v for k,v in model.items() if k!='sha256'})
        strategy=Strategy(trade_filter=model,trade_score_threshold=.65)
        report,_=blind_replay(iter(bars[260:]),warmup=bars[:260],strategy=strategy,limits=Limits(),
            costs=ExecutionSettings(),instruments={'WIN':INSTRUMENTS['WIN']})
        self.assertTrue(report['passed']);self.assertEqual(report['warmup_bars'],260)

    def test_feature_capture_preserves_engine_results_and_labels_use_only_natural_exits(self):
        bars=SyntheticProvider(count=800,seed=512).bars()
        plain=run_backtest(bars)
        captured=run_backtest(bars,collect_trade_features=True)
        for key in ('metrics','trades','orders','equity'):self.assertEqual(plain[key],captured[key])
        samples,summary=collect_trade_samples(bars,Strategy(),Limits(),ExecutionSettings(),{'WIN':INSTRUMENTS['WIN']})
        self.assertTrue(samples)
        lookup={t['id']:t for t in captured['trades']}
        for sample in samples:
            trade=lookup[sample['trade_id']]
            self.assertNotEqual(trade['exit_reason'],'FLATTEN')
            self.assertEqual(sample['label'],int(trade['net']>0))
            self.assertEqual(sample['available_at'],trade['closed_at'])
            self.assertEqual(len(sample['features']),len(TRADE_FEATURES))
        self.assertEqual(summary['natural_labels']+summary['censored_forced_exits'],plain['metrics']['trades'])

    def test_forced_end_exit_remains_in_financial_metrics_but_is_not_a_natural_label(self):
        from trading_assistant.v2.models import Decision
        from trading_assistant.v2.indicators import snapshot
        class OneEntry(Strategy):
            def evaluate(self,bars):
                if len(bars)!=35:return None
                b=bars[-1];ts=b.ts+timedelta(seconds=b.seconds)
                return Decision(b.symbol,'BUY',b.close,b.close-10000,b.close+10000,ts,
                    ts+timedelta(minutes=3),'trend','fixture',snapshot(bars,full=False))
        bars=SyntheticProvider(count=80,seed=512).bars()
        spec=replace(INSTRUMENTS['WIN'],point_value=.0001,margin=1.)
        samples,summary=collect_trade_samples(bars,OneEntry(),Limits(),
            ExecutionSettings(fee_per_unit=0,spread_ticks=0,slippage_ticks=0),{'WIN':spec})
        self.assertEqual(summary['closed_trades'],1)
        self.assertEqual(summary['teacher_metrics']['trades'],1)
        self.assertEqual(summary['censored_forced_exits'],1)
        self.assertEqual(samples,[])

    def test_selected_model_is_materialized_then_survives_json_roundtrip(self):
        from scripts.research_cycle import materialize_candidate
        model=self.fit();winner={'parameters':asdict(Strategy()),'learning':{'threshold':.8}}
        history=SyntheticProvider(count=200).bars();cutoff=START-timedelta(days=1)
        with patch('scripts.research_cycle.fit_entry_filter',return_value=(model,{})) as fitter:
            parameters=materialize_candidate(winner,history,'fixture-output',cutoff)
            self.assertIs(fitter.call_args.args[0],history)
            self.assertEqual(fitter.call_args.args[-1],cutoff)
        restored=Strategy(**json.loads(json.dumps(parameters)))
        self.assertEqual(restored.trade_score_threshold,.8)
        self.assertEqual(restored.trade_filter['sha256'],model['sha256'])
