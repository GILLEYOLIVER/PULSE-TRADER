from __future__ import annotations

import json
import unittest
from copy import deepcopy
from dataclasses import asdict
from statistics import mean
from unittest.mock import patch

import test_net_score
from scripts.research_cycle import materialize_candidate
from trading_assistant.v2.backtest import run_backtest
from trading_assistant.v2.data import SyntheticProvider
from trading_assistant.v2.learning import digest
from trading_assistant.v2.models import ExecutionSettings
from trading_assistant.v2.strategy import Strategy
from trading_assistant.v2.trade_learning import (LOGISTIC_NET,LOGISTIC_INITIAL_RISK,
    classification_only_model,initial_risk_model,validate_trade_model)
from test_v2 import START


class InitialRiskCase(unittest.TestCase):
    def fixture(self):return test_net_score.NetScoreCase()

    def test_teacher_records_actual_initial_stop_cash_without_changing_execution(self):
        bars=SyntheticProvider(count=800,seed=512).bars();costs=ExecutionSettings(fee_bps=1.)
        plain=run_backtest(bars,costs=costs)
        captured=run_backtest(bars,costs=costs,collect_trade_features=True)
        for key in ('metrics','orders','trades','equity'):self.assertEqual(plain[key],captured[key])
        trades={t['id']:t for t in captured['trades']};self.assertTrue(captured['trade_training_samples'])
        for sample in captured['trade_training_samples']:
            t=trades[sample['trade_id']];direction=1 if t['side']=='BUY' else -1
            exit=t['initial_stop']-direction*(costs.spread_ticks/2+costs.slippage_ticks)*t['tick']
            expected=(t['entry']-exit)*direction*t['qty']*t['point_value']+t['entry_fee']
            expected+=t['qty']*(costs.fee_per_unit+exit*t['point_value']*costs.fee_bps/10000.)
            self.assertAlmostEqual(sample['initial_stop_cash'],expected)
            self.assertGreater(expected,0.);self.assertLessEqual(expected,50.+1e-7)

    def test_target_is_invariant_to_quantity_scaling_while_classifier_is_unchanged(self):
        f=self.fixture();samples=f.samples(positive=4.,negative=-10.);joint=f.fit(samples)
        normalized=initial_risk_model(joint,samples);scaled=deepcopy(samples)
        for i,s in enumerate(scaled):
            scale=.1 if i%2 else .7;s['net']*=scale;s['initial_stop_cash']*=scale
        scaled_joint=f.fit(scaled);scaled_model=initial_risk_model(scaled_joint,scaled)
        self.assertEqual(normalized['weights'],joint['weights'])
        self.assertEqual(normalized['weights'],scaled_model['weights'])
        self.assertEqual(classification_only_model(normalized),classification_only_model(joint))
        for key in ('target_mean_r','target_scale_r'):
            self.assertAlmostEqual(normalized['net_head'][key],scaled_model['net_head'][key])
        self.assertNotEqual(joint['net_head']['target_mean_r'],scaled_joint['net_head']['target_mean_r'])

    def test_negative_gap_tail_is_preserved_in_actual_risk_units(self):
        f=self.fixture();samples=f.samples();samples[0].update(net=-10000.,initial_stop_cash=2.)
        model=initial_risk_model(f.fit(samples),samples)
        self.assertAlmostEqual(model['net_head']['target_mean_r'],mean(s['net']/s['initial_stop_cash'] for s in samples))
        self.assertLess(model['net_head']['target_mean_r'],-20.)
        self.assertEqual(model['training_samples'],200)

    def test_missing_invalid_or_over_budget_risk_does_not_receive_a_fallback_target(self):
        f=self.fixture()
        for risk in (None,0.,-1.,True,float('nan'),float('inf'),10.1):
            samples=f.samples();samples[0]['initial_stop_cash']=risk
            # NaN/inf must be rejected by the canonical checked training-data hash itself.
            with self.assertRaises(ValueError):initial_risk_model(f.fit(samples),samples)
        samples=f.samples();samples[0].pop('initial_stop_cash')
        with self.assertRaises(ValueError):initial_risk_model(f.fit(samples),samples)

    def test_label_mismatch_and_target_unit_reinterpretation_are_rejected(self):
        f=self.fixture();samples=f.samples();joint=f.fit(samples)
        with self.assertRaises(ValueError):initial_risk_model(joint,samples[:-1])
        changed=deepcopy(samples);changed[0]['initial_stop_cash']=2.
        with self.assertRaises(ValueError):initial_risk_model(joint,changed)
        model=initial_risk_model(joint,samples)
        for algorithm,basis in ((LOGISTIC_NET,'initial_stop_cash'),(LOGISTIC_INITIAL_RISK,'risk_budget')):
            bad=deepcopy(model);bad.update(algorithm=algorithm);bad['net_head']['target_basis']=basis
            bad.pop('sha256');bad['sha256']=digest(bad)
            with self.assertRaises(ValueError):validate_trade_model(bad)

    def test_actual_risk_gate_is_unvalidated_and_only_blocks_entries(self):
        f=self.fixture();samples=f.samples(positive=4.,negative=-10.)
        model=initial_risk_model(f.fit(samples),samples)
        result,decision,bars=f.score(model)
        self.assertTrue(result['net_gate_passed']);self.assertFalse(result['probability_calibrated'])
        self.assertEqual(model['algorithm'],LOGISTIC_INITIAL_RISK)
        with patch.object(Strategy,'_technical_evaluate',return_value=decision),patch(
            'trading_assistant.v2.trade_learning.trade_features',return_value=[0.]*len(model['features'])):
            d=Strategy(trade_filter=model,trade_score_threshold=.65).evaluate(bars)
            self.assertEqual((d.price,d.stop,d.target),(decision.price,decision.stop,decision.target))
            self.assertIsNone(d.confidence)

    def test_final_candidate_materializes_the_declared_target_before_external_data(self):
        f=self.fixture();samples=f.samples();model=initial_risk_model(f.fit(samples),samples)
        winner={'parameters':asdict(Strategy()),'learning':{'threshold':.65,'kind':'trade_outcome_logistic_initial_risk'}}
        with patch('scripts.research_cycle.fit_entry_filter',return_value=(model,{})) as fit:
            parameters=materialize_candidate(winner,SyntheticProvider(count=200).bars(),'fixture',START)
            self.assertTrue(fit.call_args.kwargs['with_net_head']);self.assertTrue(fit.call_args.kwargs['with_initial_risk'])
            restored=Strategy(**json.loads(json.dumps(parameters)))
            self.assertEqual(restored.trade_filter['algorithm'],LOGISTIC_INITIAL_RISK)


if __name__=='__main__':unittest.main()
