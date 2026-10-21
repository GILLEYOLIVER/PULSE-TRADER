from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import asdict,replace
from datetime import timedelta
from pathlib import Path
from statistics import mean
from unittest.mock import patch

import test_trade_learning
from test_v2 import START
from scripts.research_cycle import teacher_prefix_task,fit_entry_filter,materialize_candidate
from trading_assistant.v2.backtest import run_backtest
from trading_assistant.v2.data import SyntheticProvider
from trading_assistant.v2.learning import digest
from trading_assistant.v2.models import Decision,ExecutionSettings,INSTRUMENTS
from trading_assistant.v2.research import development_slices
from trading_assistant.v2.strategy import Strategy
from trading_assistant.v2.trade_learning import (LEGACY_TRADE_SET,MA_TRADE_SET,TRADE_FEATURES,
    MA_TRADE_FEATURES,trade_features,fit_trade_model,validate_trade_model,score_trade,
    classification_only_model,initial_risk_model)


class MAContextCase(unittest.TestCase):
    def history(self,count=260):
        return [replace(b,open=100.+i,high=102.+i,low=99.+i,close=101.+i)
            for i,b in enumerate(SyntheticProvider(count=count).bars())]

    def decision(self,bars,side='BUY'):
        b=bars[-1];ts=b.ts+timedelta(seconds=b.seconds)
        sign=1 if side=='BUY' else -1
        return Decision('WIN',side,b.close,b.close-sign*4,b.close+sign*8,ts,
            ts+timedelta(minutes=3),'trend','fixture',{'atr':2.})

    def vector(self,bars,side='BUY'):
        return trade_features(self.decision(bars,side),bars,ExecutionSettings(),INSTRUMENTS['WIN'],feature_set=MA_TRADE_SET)

    def samples(self):
        return [{**s,'features':s['features']+[float(i%3)/10]*8,'initial_stop_cash':10.}
            for i,s in enumerate(test_trade_learning.TradeLearningCase().samples())]

    def fit(self,samples=None,feature_set=MA_TRADE_SET):
        return fit_trade_model(self.samples() if samples is None else samples,parameters=asdict(Strategy()),
            symbol='WIN',seconds=60,source='SYNTHETIC',cutoff=START-timedelta(days=1),costs=ExecutionSettings(),
            instrument=INSTRUMENTS['WIN'],dataset_sha256='fixture',feature_set=feature_set,
            with_net_head=True,risk_budget=10.)

    def test_exact_legacy_prefix_and_directional_average_math(self):
        bars=self.history();decision=self.decision(bars);vector=self.vector(bars);short=self.vector(bars,'SELL')
        legacy=trade_features(decision,bars,ExecutionSettings(),INSTRUMENTS['WIN'])
        self.assertEqual(vector[:18],legacy);self.assertEqual(len(vector),len(MA_TRADE_FEATURES))
        closes=[b.close for b in bars]
        self.assertEqual(vector[18],(closes[-1]-mean(closes[-50:]))/2)
        self.assertEqual(vector[19],(closes[-1]-mean(closes[-200:]))/2)
        self.assertEqual(vector[20:22],[2.5,2.5]);self.assertEqual(vector[22],1.)
        self.assertEqual(vector[23],2/closes[-1]);self.assertEqual(vector[24],1.)
        self.assertEqual(vector[25],vector[18]*vector[21])
        self.assertEqual(short[18:22],[-v for v in vector[18:22]])

    def test_past_only_horizon_missing_context_and_signal_timestamp(self):
        bars=self.history();decision=self.decision(bars)
        # Observations before the declared 205-bar horizon cannot influence features.
        older=[replace(b,open=1.,high=2.,low=.5,close=1.) for b in bars[:-205]]+bars[-205:]
        self.assertEqual(self.vector(older),self.vector(bars))
        short=self.vector(bars[-100:]);self.assertEqual(short[19],0.);self.assertEqual(short[21],0.)
        self.assertEqual(short[24],0.)
        self.assertEqual(short[22],1.)  # Adjacent prices even before 201 observations exist.
        falling=[replace(b,close=500-i,open=500-i,high=501-i,low=499-i) for i,b in enumerate(bars[-100:])]
        self.assertEqual(self.vector(falling)[22],0.)
        with self.assertRaisesRegex(ValueError,'closed chronological'):
            trade_features(replace(decision,ts=decision.ts-timedelta(seconds=1)),bars,ExecutionSettings(),
                INSTRUMENTS['WIN'],feature_set=MA_TRADE_SET)
        with self.assertRaises(ValueError):self.vector([*bars[:-2],bars[-1],bars[-2]])

    def test_feature_capture_changes_neither_cash_nor_order_path_or_labels(self):
        bars=SyntheticProvider(count=800,seed=512).bars()
        old=run_backtest(bars,collect_trade_features=True)
        new=run_backtest(bars,collect_trade_features=True,trade_feature_set=MA_TRADE_SET)
        for key in ('metrics','orders','trades','equity'):self.assertEqual(old[key],new[key])
        self.assertTrue(new['trade_training_samples'])
        for before,after in zip(old['trade_training_samples'],new['trade_training_samples'],strict=True):
            self.assertEqual(after['features'][:18],before['features'])
            self.assertEqual({k:v for k,v in before.items() if k!='features'},
                {k:v for k,v in after.items() if k!='features'})

    def test_versioned_fit_all_three_models_and_old_model_identity(self):
        samples=self.samples();joint=self.fit(samples)
        for model in (joint,classification_only_model(joint),initial_risk_model(joint,samples)):
            validate_trade_model(json.loads(json.dumps(model)),asdict(Strategy()))
            self.assertEqual(model['schema'],2);self.assertEqual(model['feature_set'],MA_TRADE_SET)
            self.assertEqual(len(model['weights']),27)
            if 'net_head' in model:self.assertEqual(len(model['net_head']['weights']),27)
        old_samples=[{**s,'features':s['features'][:18]} for s in samples]
        explicit=self.fit(old_samples,LEGACY_TRADE_SET)
        default=fit_trade_model(old_samples,parameters=asdict(Strategy()),symbol='WIN',seconds=60,
            source='SYNTHETIC',cutoff=START-timedelta(days=1),costs=ExecutionSettings(),instrument=INSTRUMENTS['WIN'],
            dataset_sha256='fixture',with_net_head=True,risk_budget=10.)
        self.assertEqual(explicit,default);self.assertNotIn('feature_set',default)
        self.assertEqual(default['schema'],1);self.assertEqual(default['features'],list(TRADE_FEATURES))

    def test_schema_dimension_name_and_future_label_mismatch_are_rejected(self):
        model=self.fit()
        for changes in ({'schema':1},{'feature_set':LEGACY_TRADE_SET},{'features':list(TRADE_FEATURES)},
            {'features':list(reversed(MA_TRADE_FEATURES))}):
            changed={**model,**changes};changed['sha256']=digest({k:v for k,v in changed.items() if k!='sha256'})
            with self.assertRaises(ValueError):validate_trade_model(changed)
        with self.assertRaises(ValueError):self.fit(test_trade_learning.TradeLearningCase().samples())
        samples=self.samples();samples[-1]['available_at']=(START+timedelta(days=1)).isoformat()
        with self.assertRaises(ValueError):self.fit(samples)

    def test_inference_checks_all_205_observations_and_uses_versioned_vector(self):
        model=self.fit();bars=self.history();decision=self.decision(bars)
        with patch('trading_assistant.v2.trade_learning.trade_features',return_value=model['means']) as capture:
            result=score_trade(model,decision,bars)
            self.assertEqual(capture.call_args.kwargs['feature_set'],MA_TRADE_SET)
            self.assertFalse(result['probability_calibrated'])
        for index in (-205,-201,-1):
            bad=bars.copy();bad[index]=replace(bad[index],source='OTHER')
            with self.assertRaises(ValueError):score_trade(model,decision,bad)

    def test_teacher_cache_schema_checked_and_new_model_materialized(self):
        bars=SyntheticProvider(count=500).bars();parameters=asdict(Strategy());samples=self.samples()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch('scripts.research_cycle.collect_trade_samples',return_value=(samples,{'fixture':True})) as collect:
                prefix=teacher_prefix_task((bars,parameters,None,root/'prefix',MA_TRADE_SET))
                self.assertEqual(collect.call_args.kwargs['feature_set'],MA_TRADE_SET)
            lo=development_slices(bars)[0][0];cutoff=bars[lo].ts
            with patch('scripts.research_cycle.collect_trade_samples',side_effect=AssertionError('prefix replayed')):
                model,_=fit_entry_filter(bars[:lo],parameters,root/'cached',cutoff,
                    teacher_data=prefix['teacher_data'],feature_set=MA_TRADE_SET)
                self.assertEqual(model['feature_set'],MA_TRADE_SET)
                with self.assertRaisesRegex(ValueError,'feature schema'):
                    fit_entry_filter(bars[:lo],parameters,root/'wrong',cutoff,teacher_data=prefix['teacher_data'])
            winner={'parameters':parameters,'learning':{'threshold':.65,'kind':'trade_outcome_logistic',
                'feature_set':MA_TRADE_SET}}
            with patch('scripts.research_cycle.fit_entry_filter',return_value=(model,{})) as fit:
                materialized=materialize_candidate(winner,bars,root/'final',cutoff)
                self.assertEqual(fit.call_args.kwargs['feature_set'],MA_TRADE_SET)
                self.assertEqual(materialized['trade_filter']['sha256'],model['sha256'])


if __name__=='__main__':unittest.main()
