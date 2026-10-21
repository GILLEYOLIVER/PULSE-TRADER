from __future__ import annotations

import tempfile
import unittest
from dataclasses import asdict,replace
from pathlib import Path
from unittest.mock import patch

from scripts.research_cycle import teacher_prefix_task,fit_entry_filter
from trading_assistant.v2.data import SyntheticProvider
from trading_assistant.v2.research import development_slices
from trading_assistant.v2.strategy import Strategy
from trading_assistant.v2.trade_learning import training_sample_health
import test_trade_learning


class TeacherPreflightCase(unittest.TestCase):
    def test_teacher_uses_only_prefix_before_first_validation_and_records_insufficiency(self):
        bars=SyntheticProvider(count=500).bars();parameters=asdict(Strategy())
        samples=test_trade_learning.TradeLearningCase().samples(count=30)
        with tempfile.TemporaryDirectory() as directory:
            with patch('scripts.research_cycle.collect_trade_samples',return_value=(samples,{'fixture':True})) as collect:
                row=teacher_prefix_task((bars,parameters,None,directory))
                prefix=collect.call_args.args[0]
                self.assertEqual(prefix,bars[:development_slices(bars)[0][0]])
                self.assertLess(prefix[-1].ts,bars[len(prefix)].ts)
                self.assertEqual(row['prefix_cutoff'],bars[len(prefix)].ts.isoformat())
                self.assertFalse(row['eligible']);self.assertEqual(row['sample_health']['samples'],30)
                self.assertTrue(Path(row['path']).is_file())

    def test_selected_prefix_reuse_produces_identical_model_and_rejects_mismatched_data(self):
        bars=SyntheticProvider(count=500).bars();parameters=asdict(Strategy())
        samples=test_trade_learning.TradeLearningCase().samples();diagnostics={'fixture':True}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch('scripts.research_cycle.collect_trade_samples',return_value=(samples,diagnostics)):
                row=teacher_prefix_task((bars,parameters,None,root/'prefix'))
                self.assertTrue(row['eligible'])
                lo=development_slices(bars)[0][0];cutoff=bars[lo].ts
                expected,_=fit_entry_filter(bars[:lo],parameters,root/'ordinary',cutoff)
            with patch('scripts.research_cycle.collect_trade_samples',side_effect=AssertionError('prefix replayed')):
                cached,_=fit_entry_filter(bars[:lo],parameters,root/'cached',cutoff,teacher_data=row['teacher_data'])
                self.assertEqual(cached,expected)
                changed=[*bars[:lo-1],replace(bars[lo-1],volume=123456.)]
                with self.assertRaisesRegex(ValueError,'another dataset'):
                    fit_entry_filter(changed,parameters,root/'wrong',cutoff,teacher_data=row['teacher_data'])
                with self.assertRaisesRegex(ValueError,'another dataset'):
                    fit_entry_filter(bars[:lo],asdict(Strategy(reward_r=3)),root/'wrong-policy',cutoff,teacher_data=row['teacher_data'])

    def test_prefix_health_uses_same_recent_sample_and_class_rules_as_model_fit(self):
        samples=test_trade_learning.TradeLearningCase().samples()
        self.assertTrue(training_sample_health(samples)['eligible'])
        self.assertFalse(training_sample_health(samples[:99])['eligible'])
        one_class=[{**sample,'label':1} for sample in samples]
        self.assertFalse(training_sample_health(one_class)['eligible'])
        many=[{**samples[0],'signal_at':f'{i:06d}','label':int(i>=100)} for i in range(3200)]
        self.assertEqual(training_sample_health(many)['samples'],3000)
        self.assertFalse(training_sample_health(many)['eligible'])


if __name__=='__main__':unittest.main()
