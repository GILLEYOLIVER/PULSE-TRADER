from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import research_cycle
from trading_assistant.v2.data import SyntheticProvider
from trading_assistant.v2.learning import HistoricalRotation,LearningMemory
from trading_assistant.v2.market_data import (http_bytes,DataUnavailable,TransientDataUnavailable,ProviderBackoffRequired)
from trading_assistant.v2.research import ChampionStore,development_result
from trading_assistant.v2.research_history import research_json_response,check_research_source,record_provider_backoff


class ImmediatePool:
    def __init__(self,**kwargs):pass
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def map(self,fn,tasks):return map(fn,tasks)


class ProviderRecoveryCase(unittest.TestCase):
    def test_only_transient_failures_are_retried_with_a_bounded_same_url(self):
        with patch('trading_assistant.v2.research_history.json_response',side_effect=[TransientDataUnavailable('offline'),{}]) as read,patch(
            'trading_assistant.v2.research_history.time.sleep') as sleep:
            self.assertEqual(research_json_response('fixture://same-read'),{})
            self.assertEqual(read.call_count,2);self.assertEqual(sleep.call_count,1)
            self.assertTrue(all(call.args==('fixture://same-read',) for call in read.call_args_list))
        for error in (ProviderBackoffRequired('429'),DataUnavailable('bad data')):
            with patch('trading_assistant.v2.research_history.json_response',side_effect=error) as read:
                with self.assertRaises(type(error)):research_json_response('fixture://same-read')
                self.assertEqual(read.call_count,1)

    def test_retry_exhaustion_preserves_the_transient_error(self):
        with patch('trading_assistant.v2.research_history.json_response',side_effect=TransientDataUnavailable('offline')) as read,patch(
            'trading_assistant.v2.research_history.time.sleep'):
            with self.assertRaises(TransientDataUnavailable):research_json_response('fixture://same-read')
            self.assertEqual(read.call_count,3)

    def test_http_rate_limits_and_permissions_are_not_treated_as_transport_retries(self):
        for code,kind in ((418,ProviderBackoffRequired),(429,ProviderBackoffRequired),(503,TransientDataUnavailable),(403,DataUnavailable)):
            error=urllib.error.HTTPError('https://fixture.invalid/',code,'fixture',{'Retry-After':'123'},None)
            with patch('urllib.request.urlopen',side_effect=error):
                with self.assertRaises(kind) as raised:http_bytes('https://fixture.invalid/')
                if code==403:self.assertNotIsInstance(raised.exception,TransientDataUnavailable)
                if code in (418,429):self.assertEqual(raised.exception.retry_after_seconds,123)

    def test_saved_provider_deadline_prevents_even_a_ping_until_it_expires(self):
        with tempfile.TemporaryDirectory() as directory:
            error=ProviderBackoffRequired('429',123);record_provider_backoff(directory,error)
            path=Path(directory)/'provider-backoff.json';before=path.read_bytes()
            with patch('trading_assistant.v2.research_history.research_json_response',side_effect=AssertionError('ping during cooldown')):
                with self.assertRaises(ProviderBackoffRequired) as raised:check_research_source(directory)
                record_provider_backoff(directory,raised.exception)
                self.assertEqual(path.read_bytes(),before)
            with patch('trading_assistant.v2.research_history.time.time',return_value=error.retry_not_before_epoch+1),patch(
                'trading_assistant.v2.research_history.research_json_response',return_value={}) as read:
                check_research_source(directory);self.assertEqual(read.call_count,1)

    def group_fixture(self,root):
        store=ChampionStore(root/'memory'/'ciclos');state=store.state();code=store.archive_source({'fixture.py':''})
        rotation=HistoricalRotation(root/'memory');memory=LearningMemory(root/'memory')
        output=root/'reports'/'cycle';output.mkdir(parents=True)
        args=SimpleNamespace(candidates=12,workers=1)
        return store,state,code,rotation,memory,output,args

    def test_failed_training_download_does_not_reserve_an_external_window(self):
        with tempfile.TemporaryDirectory() as directory:
            store,state,code,rotation,memory,output,args=self.group_fixture(Path(directory))
            with patch('scripts.research_cycle.get_research_history',side_effect=TransientDataUnavailable('offline')):
                with self.assertRaises(TransientDataUnavailable):
                    research_cycle.run_group('BTCUSDT:300',args,store,state,code,rotation,memory,output,'cycle')
            plan=json.loads((output/'BTCUSDT-300'/'protocol-before-data.json').read_text(encoding='utf-8'))
            window=plan['windows']
            self.assertTrue(rotation.available('BTCUSDT',300,window['test_start'],window['test_end']))
            self.assertNotIn('last_external_end',state['groups']['BTCUSDT:300'])

    def test_external_failure_after_frozen_choice_keeps_the_window_consumed(self):
        with tempfile.TemporaryDirectory() as directory:
            store,state,code,rotation,memory,output,args=self.group_fixture(Path(directory))
            bars=[replace(b,source='BINANCE_SPOT_USDT') for b in SyntheticProvider('BTCUSDT',count=500,seconds=300).bars()]
            with patch('scripts.research_cycle.get_research_history',side_effect=[bars,TransientDataUnavailable('offline')]),patch(
                'scripts.research_cycle.ProcessPoolExecutor',ImmediatePool),patch(
                'scripts.research_cycle.development_task',side_effect=lambda task:development_result(task[1],[])):
                with self.assertRaises(TransientDataUnavailable):
                    research_cycle.run_group('BTCUSDT:300',args,store,state,code,rotation,memory,output,'cycle')
            policy=output/'BTCUSDT-300'/'frozen-policy.json';self.assertTrue(policy.exists())
            window=json.loads(policy.read_text(encoding='utf-8'))['windows']
            self.assertFalse(rotation.available('BTCUSDT',300,window['test_start'],window['test_end']))
            self.assertEqual(state['groups']['BTCUSDT:300']['last_external_end'],window['test_end'])

    def main_fixture(self,directory,probe_error=False):
        root=Path(directory);memory=root/'memory';output=root/'reports'
        arguments=['research_cycle','--isolated-snapshot','--cycles','2','--workers','1',
            '--groups','BTCUSDT:300','ETHUSDT:300','--memory',str(memory),'--output',str(output)]
        with patch('sys.argv',arguments),patch('scripts.research_cycle.check_research_source',
            side_effect=TransientDataUnavailable('offline') if probe_error else None),patch(
            'scripts.research_cycle.run_group',side_effect=TransientDataUnavailable('offline')) as group:
            research_cycle.main();count=group.call_count
        summaries=list(output.glob('*/summary.json'));self.assertEqual(len(summaries),1)
        summary=json.loads(summaries[0].read_text(encoding='utf-8'))
        self.assertEqual(summary['status'],'DEFERRED_PROVIDER_UNAVAILABLE')
        self.assertFalse(summary['goal_reached'])
        self.assertEqual(ChampionStore(memory/'ciclos').state()['deferred_cycles'],1)
        return summary,count

    def test_unavailable_provider_probe_defers_every_group_without_starting_it(self):
        with tempfile.TemporaryDirectory() as directory:
            summary,count=self.main_fixture(directory,True)
            self.assertEqual(count,0)
            self.assertTrue(all(r['status']=='DEFERRED_PROVIDER_UNAVAILABLE' for r in summary['groups']))

    def test_mid_batch_transient_error_defers_unstarted_groups_and_further_cycles(self):
        with tempfile.TemporaryDirectory() as directory:
            summary,count=self.main_fixture(directory)
            self.assertEqual(count,1)
            self.assertEqual(summary['groups'][0]['status'],'FAILED')
            self.assertEqual(summary['groups'][1]['status'],'DEFERRED_PROVIDER_UNAVAILABLE')


if __name__=='__main__':unittest.main()
