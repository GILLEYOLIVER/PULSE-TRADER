from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import asdict,replace
from pathlib import Path

from trading_assistant.v2.archived_replay import archived_replay,comparison_contract
from trading_assistant.v2.blind_testing import blind_replay
from trading_assistant.v2.data import SyntheticProvider
from trading_assistant.v2.models import ExecutionSettings,Limits,INSTRUMENTS
from trading_assistant.v2.research import ChampionStore
from trading_assistant.v2.strategy import Strategy
from trading_assistant.v2.research_history import MAX_RESEARCH_BARS
from scripts.research_cycle import window_sizes


class ArchivedReplayCase(unittest.TestCase):
    def sources(self):
        return {str(p):p.read_text(encoding='utf-8') for p in Path('trading_assistant/v2').glob('*.py')}

    def settings(self):
        return {'limits':asdict(Limits()),'costs':asdict(ExecutionSettings()),
            'instruments':{'WIN':asdict(INSTRUMENTS['WIN'])}}

    def test_original_source_is_executed_and_has_no_current_source_fallback(self):
        bars=SyntheticProvider(count=700,seed=512).bars();settings=self.settings()
        expected,_=blind_replay(iter(bars[250:]),warmup=bars[:250],strategy=Strategy(),limits=Limits(),
            costs=ExecutionSettings(),instruments={'WIN':INSTRUMENTS['WIN']})
        self.assertGreater(expected['order_count'],0)
        with tempfile.TemporaryDirectory() as directory:
            store=ChampionStore(Path(directory)/'store');sources=self.sources()
            code=store.archive_source(sources);version=store.register('WIN:60',asdict(Strategy()),code,settings)
            result=archived_replay(store,version,bars[250:],bars[:250],Path(directory)/'original')
            for key in ('metrics','checks','order_count','final_exits','trace_sha256'):
                self.assertEqual(result['normal'][key],expected[key])
            self.assertEqual(result['provenance']['algorithm_code_id'],code)
            name=next(key for key in sources if key.endswith('strategy.py'))
            sources[name]=sources[name].replace('decision=self._technical_evaluate(bars)',
                'return None\n        decision=self._technical_evaluate(bars)',1)
            different_code=store.archive_source(sources)
            different=store.register('WIN:60',asdict(Strategy()),different_code,settings)
            changed=archived_replay(store,different,bars[250:],bars[:250],Path(directory)/'changed')
            self.assertEqual(changed['normal']['order_count'],0)
            self.assertEqual(changed['stress']['order_count'],0)
            self.assertNotEqual(changed['normal']['trace_sha256'],result['normal']['trace_sha256'])
            path=store.directory/'code'/(code+'.json');path.write_text('{}',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'checksum'):
                archived_replay(store,version,bars[250:],bars[:250],Path(directory)/'tampered')

    def test_policy_limit_changes_are_explicit_but_risk_cost_changes_are_rejected(self):
        reference={'assumptions':json.loads(json.dumps(self.settings()))}
        candidate=self.settings();candidate['limits']['min_net_reward_r']=.25
        contract=comparison_contract(reference,candidate)
        self.assertEqual(set(contract['policy_limit_differences']),{'min_net_reward_r'})
        candidate['limits']['risk_fraction']=.1
        with self.assertRaisesRegex(ValueError,'risk limits'):comparison_contract(reference,candidate)
        candidate=self.settings();candidate['costs']['fee_bps']=10
        with self.assertRaisesRegex(ValueError,'costs'):comparison_contract(reference,candidate)
        candidate=self.settings();candidate['instruments']['WIN']['point_value']=10
        with self.assertRaisesRegex(ValueError,'instruments'):comparison_contract(reference,candidate)

    def test_rebases_do_not_replace_the_last_validated_version(self):
        with tempfile.TemporaryDirectory() as directory:
            store=ChampionStore(directory);state=store.state();group='WIN:60'
            code=store.archive_source({'strategy.py':'test fixture'})
            versions=[store.register(group,asdict(Strategy(reward_r=r)),code,self.settings()) for r in (1,2,3,4)]
            store.set_champion(state,group,versions[0],'INITIAL_REFERENCE')
            store.set_champion(state,group,versions[1],'REFERENCE_PARAMETERS_REEVALUATED_ON_NEW_CODE')
            self.assertEqual(store.validated_reference(state,group),versions[0])
            store.set_champion(state,group,versions[2],'VALIDATION_AND_EXTERNAL_GATE_PASSED')
            store.set_champion(state,group,versions[3],'REFERENCE_PARAMETERS_REEVALUATED_ON_NEW_CODE')
            self.assertEqual(store.validated_reference(state,group),versions[2])
            store.set_champion(state,group,versions[2],'RESTORED_ORIGINAL_ARCHIVED_REFERENCE')
            self.assertEqual(store.validated_reference(state,group),versions[2])
            store.set_champion(state,group,versions[1],'UNKNOWN_OVERRIDE')
            with self.assertRaises(ValueError):store.validated_reference(state,group)

    def test_segmented_training_and_external_windows_are_bounded(self):
        for symbol in ('BTCUSDT','SOLUSDT'):
            for seconds in (300,3600,86400):
                training,testing=window_sizes(symbol,seconds)
                self.assertLessEqual(training*86400/seconds,MAX_RESEARCH_BARS)
                self.assertLess((testing+1)*86400/seconds+250,10000)
        self.assertEqual(window_sizes('BTCUSDT',300),(90,28))
        self.assertEqual(window_sizes('BTCUSDT',3600),(540,90))


if __name__=='__main__':unittest.main()
