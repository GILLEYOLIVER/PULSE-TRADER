from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import asdict
from datetime import timedelta
from statistics import mean
from pathlib import Path
from unittest.mock import patch

from trading_assistant.v2.data import SyntheticProvider
from trading_assistant.v2.learning import digest
from trading_assistant.v2.models import ExecutionSettings,INSTRUMENTS,Decision
from trading_assistant.v2.strategy import Strategy
from trading_assistant.v2.trade_learning import (TRADE_FEATURES,LOGISTIC,LOGISTIC_NET,fit_trade_model,
    classification_only_model,score_trade,validate_trade_model)
from trading_assistant.v2.trade_learning import initial_risk_model
from scripts.research_cycle import materialize_candidate,learned_development_task
from trading_assistant.v2.research import atomic_json
import test_trade_learning
import test_research_cycle
from test_v2 import START


class NetScoreCase(unittest.TestCase):
    def samples(self,positive=1.,negative=-10.):
        rows=test_trade_learning.TradeLearningCase().samples(count=200)
        for i,sample in enumerate(rows):
            sample.update(features=[0.]*len(TRADE_FEATURES),label=int(i%5!=0),net=positive if i%5 else negative,
                initial_stop_cash=10.)
        return rows

    def fit(self,samples=None,net=True):
        return fit_trade_model(self.samples() if samples is None else samples,parameters=asdict(Strategy()),
            symbol='WIN',seconds=60,source='SYNTHETIC',cutoff=START-timedelta(days=1),costs=ExecutionSettings(),
            instrument=INSTRUMENTS['WIN'],dataset_sha256='fixture',with_net_head=net,risk_budget=10. if net else None)

    def score(self,model):
        bars=SyntheticProvider(count=200).bars();b=bars[-1];now=b.ts+timedelta(minutes=1)
        decision=Decision('WIN','BUY',b.close,b.close-100,b.close+200,now,now+timedelta(minutes=3),'trend','fixture')
        with patch('trading_assistant.v2.trade_learning.trade_features',return_value=[0.]*len(TRADE_FEATURES)):
            return score_trade(model,decision,bars),decision,bars

    def test_derived_classifier_is_bit_identical_and_does_not_share_mutable_weights(self):
        samples=self.samples();gated=self.fit(samples);plain=self.fit(samples,False)
        derived=classification_only_model(gated)
        self.assertEqual(derived,plain)
        self.assertEqual(gated['algorithm'],LOGISTIC_NET)
        self.assertEqual(derived['algorithm'],LOGISTIC)
        before=gated['weights'][0];derived['weights'][0]+=1
        self.assertEqual(gated['weights'][0],before)
        validate_trade_model(gated,asdict(Strategy()))

    def test_high_win_frequency_with_negative_cash_is_blocked_by_actual_strategy(self):
        model=self.fit();result,decision,bars=self.score(model)
        self.assertGreater(result['score'],.79)
        self.assertLess(result['net_score_r'],0)
        self.assertTrue(result['abstain']);self.assertFalse(result['net_gate_passed'])
        legacy,_,_=self.score(classification_only_model(model))
        self.assertFalse(legacy['abstain'])
        with patch.object(Strategy,'_technical_evaluate',return_value=decision),patch(
            'trading_assistant.v2.trade_learning.trade_features',return_value=[0.]*len(TRADE_FEATURES)):
            gated=Strategy(trade_filter=model,trade_score_threshold=.65).evaluate(bars)
            self.assertEqual(gated.side,'WAIT')
            self.assertEqual(gated.price,decision.price);self.assertEqual(gated.stop,decision.stop)
            self.assertEqual(gated.target,decision.target)
            self.assertEqual(gated.indicators['historical_net_gate_passed'],0)
            self.assertIsNone(gated.confidence)

    def test_positive_net_can_pass_while_zero_expectation_cannot_pass_on_rounding_noise(self):
        result,_,_=self.score(self.fit(self.samples(positive=10.,negative=-1.)))
        self.assertTrue(result['net_gate_passed']);self.assertFalse(result['abstain'])
        zero,_,_=self.score(self.fit(self.samples(positive=1.,negative=-4.)))
        self.assertFalse(zero['net_gate_passed']);self.assertTrue(zero['abstain'])
        self.assertFalse(result['probability_calibrated'])

    def test_negative_tail_is_not_trimmed_and_inconsistent_cash_labels_are_rejected(self):
        samples=self.samples();samples[0]['net']=-10000.
        model=self.fit(samples)
        self.assertEqual(model['training_samples'],len(samples))
        self.assertAlmostEqual(model['net_head']['target_mean_r'],mean(s['net']/10 for s in samples))
        samples[0]['net']=1.
        with self.assertRaisesRegex(ValueError,'disagrees'):self.fit(samples)
        samples[0]['net']=float('inf')
        with self.assertRaises(ValueError):self.fit(samples)

    def test_net_model_integrity_rejects_missing_head_bad_units_and_ignored_gate(self):
        original=self.fit()
        for mutation in ('missing','scale','weights','legacy','gate'):
            model=json.loads(json.dumps(original))
            if mutation=='missing':model.pop('net_head')
            elif mutation=='scale':model['net_head']['target_scale_r']=0
            elif mutation=='weights':model['net_head']['weights'].pop()
            elif mutation=='legacy':model['algorithm']=LOGISTIC
            else:model['net_head']['positive_gate_r']=-1
            model.pop('sha256');model['sha256']=digest(model)
            with self.assertRaises(ValueError):validate_trade_model(model)

    def test_sealed_net_winner_requests_a_frozen_net_model_before_external_data(self):
        model=self.fit();winner={'parameters':asdict(Strategy()),
            'learning':{'threshold':.65,'kind':'trade_outcome_logistic_net'}}
        bars=SyntheticProvider(count=200).bars()
        with patch('scripts.research_cycle.fit_entry_filter',return_value=(model,{})) as fit:
            parameters=materialize_candidate(winner,bars,'fixture',START)
            self.assertTrue(fit.call_args.kwargs['with_net_head'])
            self.assertEqual(parameters['trade_filter']['algorithm'],LOGISTIC_NET)

    def test_each_variant_records_the_checksum_of_the_model_it_actually_uses(self):
        samples=self.samples();model=self.fit(samples);baseline=classification_only_model(model)
        normalized=initial_risk_model(model,samples);bars=SyntheticProvider(count=500).bars()
        def fit(past,parameters,directory,cutoff,**kwargs):
            atomic_json(Path(directory)/'model.json',model)
            atomic_json(Path(directory)/'labels.json',{'samples':samples})
            return model,{'fixture':True}
        with tempfile.TemporaryDirectory() as directory,patch('scripts.research_cycle.fit_entry_filter',side_effect=fit),patch(
            'scripts.research_cycle.blind_replay',return_value=(test_research_cycle.report(),[])):
            rows=learned_development_task((bars,asdict(Strategy()),None,directory))
            self.assertEqual(len(rows),12)
            for row in rows:
                expected={'trade_outcome_logistic':baseline,'trade_outcome_logistic_net':model,
                    'trade_outcome_logistic_initial_risk':normalized}[row['learning']['kind']]
                for record in row['training']:
                    self.assertEqual(record['model_sha256'],expected['sha256'])
                    filename='model.json' if expected is model else 'initial-risk-model.json' if expected is normalized else 'classification-only-model.json'
                    saved=json.loads((Path(directory)/f"fold-{record['fold']}"/filename).read_text(encoding='utf-8'))
                    self.assertEqual(saved['sha256'],record['model_sha256'])


if __name__=='__main__':unittest.main()
