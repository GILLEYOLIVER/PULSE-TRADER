from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
import unittest
from dataclasses import asdict,replace
from datetime import datetime,timedelta
from pathlib import Path

from trading_assistant.v2.data import SyntheticProvider
from trading_assistant.v2.learning import HistoricalRotation
from trading_assistant.v2.models import UTC,ExecutionSettings,Limits
from trading_assistant.v2.research import (ChampionStore,aggregate_metrics,candidate_bank,development_result,
    goal_evidence,plan_forward,promotion_decision,select_development,wilson,warmup_start,development_slices)
from trading_assistant.v2.strategy import Strategy
from trading_assistant.v2.execution import PaperEngine
from trading_assistant.v2.ledger import Ledger
from trading_assistant.v2.blind_testing import blind_replay
from trading_assistant.v2.models import Instrument
from trading_assistant.v2.market_data import fetch_binance,DataUnavailable
from test_v2 import START,bar,signal


def report(trades=20,wins=12,net=100.,drawdown=50.,passed=True):
    return {'passed':passed,'metrics':{'trades':trades,'win_rate':wins/trades if trades else 0.,
        'net':net,'fees':3.,'max_drawdown':drawdown,'expectancy':net/trades if trades else 0.}}


def confirmation(index,*,wins=38,trades=40,version='a'*64,real=True):
    start=START+timedelta(days=index*7)
    return {'version_id':version,'real_history':real,'passed':True,'start':start.date().isoformat(),
        'end':(start+timedelta(days=7)).date().isoformat(),'metrics':report(trades,wins)['metrics'],
        'stress_net':25.,'stress_drawdown':100.}


class MetricsCase(unittest.TestCase):
    def test_rate_is_weighted_by_trades_and_empty_runs_do_not_inflate_it(self):
        combined=aggregate_metrics([report(10,9),report(90,9),report(0,0,0)])
        self.assertEqual(combined['win_rate'],.18)
        self.assertEqual(combined['wins'],18)
        self.assertIsNone(aggregate_metrics([report(0,0,0)])['win_rate'])

    def test_wilson_exposes_uncertainty_in_tiny_perfect_samples(self):
        self.assertLess(wilson(3,3)[0],.5)
        self.assertGreater(wilson(970,1000)[0],.9)
        with self.assertRaises(ValueError):wilson(4,3)

    def test_no_goal_for_three_wins_or_one_window_or_exactly_ninety(self):
        self.assertFalse(goal_evidence([confirmation(0,wins=3,trades=3)])['observed_goal_reached'])
        self.assertFalse(goal_evidence([confirmation(0,wins=100,trades=100)])['observed_goal_reached'])
        self.assertFalse(goal_evidence([confirmation(i,wins=36) for i in range(3)])['observed_goal_reached'])

    def test_goal_needs_real_disjoint_unchanged_version_and_positive_stress(self):
        rows=[confirmation(i) for i in range(3)]
        self.assertTrue(goal_evidence(rows)['observed_goal_reached'])
        self.assertFalse(goal_evidence([confirmation(i,real=False) for i in range(3)])['observed_goal_reached'])
        with self.assertRaises(ValueError):goal_evidence([rows[0],rows[0]])
        with self.assertRaises(ValueError):goal_evidence([rows[0],confirmation(1,version='b'*64)])
        rows[2]['stress_net']=-1
        self.assertFalse(goal_evidence(rows)['observed_goal_reached'])
        rows[2]['stress_net']=25.;rows[2]['qualified_for_goal']=False
        self.assertFalse(goal_evidence(rows)['observed_goal_reached'])

    def test_development_rejects_one_bad_fold_and_requires_operation_counts(self):
        p=asdict(Strategy());good=development_result(p,[report() for _ in range(3)])
        self.assertTrue(good['eligible'])
        self.assertFalse(development_result(p,[report(),report(),report(net=-1)])['eligible'])
        self.assertFalse(development_result(p,[report(3,3) for _ in range(3)])['eligible'])
        selected,status=select_development([development_result(p,[report(1,1)])],good)
        self.assertIs(selected,good)
        self.assertEqual(status,'INSUFFICIENT_CONSISTENT_DEVELOPMENT')

    def test_promotion_rejects_high_accuracy_with_losses_or_cost_failure(self):
        d={'eligible':True};reference=report(20,10,net=50.)
        self.assertFalse(promotion_decision(d,report(20,19,net=-10),reference,report())['promoted'])
        self.assertFalse(promotion_decision(d,report(20,19),reference,report(net=-1))['promoted'])
        self.assertFalse(promotion_decision({'eligible':False},report(20,19),reference,report())['promoted'])
        self.assertTrue(promotion_decision(d,report(20,19),reference,report())['promoted'])


class VersionsAndTimeCase(unittest.TestCase):
    def test_common_development_folds_cannot_precede_the_reference_model(self):
        bars=SyntheticProvider(count=500).bars()
        cutoff=bars[350].ts.isoformat()
        folds=development_slices(bars,cutoff)
        self.assertEqual(folds,[(350,400),(400,450),(450,500)])
        self.assertEqual(development_slices(bars,bars[450].ts.isoformat()),[])

    def test_batched_learning_keeps_the_hash_chain_and_refuses_partial_invalid_input(self):
        from trading_assistant.v2.learning import LearningMemory
        with tempfile.TemporaryDirectory() as directory:
            memory=LearningMemory(directory)
            rows=memory.append_batch('VALIDATION',[{'score':1},{'score':2}])
            self.assertEqual(rows[1]['previous'],rows[0]['sha256'])
            before=memory.training_path.read_bytes()
            with self.assertRaises(ValueError):memory.append_batch('VALIDATION',[{'score':3},{'score':float('nan')}])
            self.assertEqual(memory.training_path.read_bytes(),before)
            self.assertEqual(len(memory.training_records()),2)
            memory.append_batch('BLIND_TEST',[{'score':999}])
            self.assertEqual(len(memory.training_records()),2)
            self.assertEqual(len(memory.evaluations()),1)

    def test_warmup_duration_scales_with_timeframe_and_has_no_test_bars(self):
        for seconds in (300,3600,86400):
            first=datetime.fromisoformat(warmup_start(START,seconds)).replace(tzinfo=UTC)
            self.assertGreaterEqual((START-first).total_seconds()/seconds,250)
            self.assertLess(first,START)
        self.assertGreaterEqual((START-datetime.fromisoformat(warmup_start(START,3600)).replace(tzinfo=UTC)).days,11)
        with self.assertRaises(ValueError):warmup_start(START,True)

    def test_child_interpreter_imports_frozen_package_and_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            store=ChampionStore(directory)
            sources={str(p):p.read_text(encoding='utf-8') for folder in ('trading_assistant/v2','scripts')
                for p in Path(folder).glob('*.py')}
            sources['trading_assistant/__init__.py']=Path('trading_assistant/__init__.py').read_text()
            workspace=store.source_workspace(sources)
            child=subprocess.run([sys.executable,'-c',
                'import json; import trading_assistant.v2.strategy as s; import scripts.research_cycle as r; print(json.dumps([s.__file__,r.__file__]))'],
                cwd=workspace,capture_output=True,text=True,check=True)
            for filename in json.loads(child.stdout):self.assertTrue(Path(filename).is_relative_to(workspace))

    def test_frozen_workspace_and_runtime_bundle_preserve_source_data_and_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);store=ChampionStore(root/'learning')
            sources={'package/module.py':'value = 1\n'}
            old=store.source_workspace(sources)
            newer=store.source_workspace({'package/module.py':'value = 2\n'})
            self.assertNotEqual(old,newer)
            self.assertEqual((old/'package/module.py').read_text(),'value = 1\n')
            with self.assertRaises(ValueError):store.source_workspace({'../escape.py':'bad'})
            run=root/'reports'/'cycle-1'/'BTCUSDT-300'
            (run/'data').mkdir(parents=True)
            (run/'data/prices.csv').write_text('actual test fixture\n')
            (run/'result.json').write_text('{"promoted": false}')
            archive=Path(store.archive_run(run))
            self.assertTrue(archive.is_relative_to(store.directory))
            with zipfile.ZipFile(archive) as saved:
                self.assertIsNone(saved.testzip())
                self.assertIn('data/prices.csv',saved.namelist())
                self.assertEqual(saved.read('result.json'),b'{"promoted": false}')
            with self.assertRaises(ValueError):store.archive_run(run)

    def test_immutable_versions_preserve_both_champions_and_detect_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            store=ChampionStore(directory);state=store.state();group='BTCUSDT:300'
            code=store.archive_source({'strategy.py':'first source'})
            first=store.register(group,asdict(Strategy()),code,{'allowed':('a','b')})
            second=store.register(group,asdict(Strategy(min_efficiency=.3)),code,{})
            self.assertEqual(first,store.register(group,asdict(Strategy()),code,{'allowed':('a','b')}))
            store.set_champion(state,group,first,'INITIAL');store.set_champion(state,group,second,'IMPROVED')
            store.save(state);self.assertEqual(store.state()['groups'][group]['champion'],second)
            self.assertEqual(store.version(first)['parameters']['min_efficiency'],0.)
            with self.assertRaises(ValueError):store.set_champion(state,'ETHUSDT:300',first,'WRONG_ASSET')
            store.set_champion(state,group,first,'ROLLBACK');store.save(state)
            self.assertEqual(len(store.state()['groups'][group]['history']),3)
            p=Path(directory)/'versions'/(second+'.json');p.write_text('{}')
            with self.assertRaises(ValueError):store.version(second)

    def test_lock_and_state_checksum_stop_concurrent_or_corrupted_cycles(self):
        with tempfile.TemporaryDirectory() as directory:
            store=ChampionStore(directory)
            with store.lock():
                with self.assertRaises(ValueError):
                    with store.lock():pass
            self.assertFalse((Path(directory)/'cycle.lock').exists())
            store.save(store.state());text=store.state_path.read_text().replace('"completed_cycles": 0','"completed_cycles": 9')
            store.state_path.write_text(text)
            with self.assertRaises(ValueError):store.state()

    def test_rotation_advances_past_training_and_never_rewinds_after_learning(self):
        with tempfile.TemporaryDirectory() as directory:
            rotation=HistoricalRotation(directory);now=datetime(2018,3,1,tzinfo=UTC)
            first=plan_forward(rotation,'BTCUSDT',300,as_of=now,test_days=7,training_days=21)
            rotation.mark_development('BTCUSDT',300,first['training_start'],first['test_start'],'train')
            rotation.reserve('one','BTCUSDT',300,first['test_start'],first['test_end'])
            later=plan_forward(rotation,'BTCUSDT',300,as_of=now,test_days=7,training_days=21,after=first['test_end'])
            self.assertGreaterEqual(later['test_start'],first['test_end'])
            with self.assertRaises(ValueError):plan_forward(rotation,'BTCUSDT',300,as_of=now,
                test_days=7,training_days=21,after='2018-04-01')

    def test_candidate_rotation_is_fixed_diverse_and_retains_reference(self):
        reference=asdict(Strategy('breakout',2.25,1.75))
        first=candidate_bank(0,reference,36);second=candidate_bank(1,reference,36)
        self.assertEqual(first,candidate_bank(0,reference,36))
        self.assertEqual(first[0],reference)
        self.assertNotEqual(first,second)
        self.assertGreater(len({p['reward_r'] for p in first}),2)
        self.assertTrue(any(p['require_trend_slope'] for p in first))
        self.assertEqual(len({json.dumps(p,sort_keys=True) for p in first}),36)


class FilterCase(unittest.TestCase):
    def test_mean_reversion_uses_past_trend_oversold_pullback_and_bounded_stop(self):
        bars=[bar(START+timedelta(minutes=i),price=1000+i) for i in range(210)]
        bars[-1]=replace(bars[-1],open=1208,high=1209,low=1191,close=1192)
        strategy=Strategy('mean_reversion',.5,1.5)
        self.assertIsNone(strategy.evaluate(bars[:204]))
        decision=strategy.evaluate(bars)
        self.assertEqual(decision.side,'BUY')
        self.assertLess(decision.stop,decision.price);self.assertGreater(decision.target,decision.price)
        self.assertLessEqual(decision.price-decision.stop,3*decision.indicators['atr'])
        self.assertLessEqual(decision.target,decision.indicators['target_mean5'])
        self.assertLess(decision.indicators['rsi2'],10)

    def test_metrics_only_replay_has_identical_costs_trades_checks_and_drawdown(self):
        bars=SyntheticProvider(count=450,seed=512).bars()
        args=dict(strategy=Strategy(min_efficiency=.2),limits=Limits(),costs=ExecutionSettings(),
            instruments={'WIN':Instrument('WIN',.2,5)})
        full,trace=blind_replay(iter(bars),**args)
        fast,empty=blind_replay(iter(bars),**args,retain_trace=False,bootstrap=False)
        for key in ('metrics','checks','bars','order_count','rejected_orders','final_exits','reason_counts'):
            self.assertEqual(full[key],fast[key])
        self.assertEqual(len(trace),450);self.assertEqual(empty,[])
        with self.assertRaises(ValueError):blind_replay(iter(bars),**args,retain_trace=False,trace_path='audit.jsonl')

    def test_disclosed_gaps_are_never_padded_and_bad_clocks_remain_invalid(self):
        ts=int(START.timestamp()*1000)
        def candle(offset):
            return [ts+offset*60000,'100','102','99','101','10',ts+(offset+1)*60000-1,'1000',12,'6','600','0']
        rows=[candle(0),candle(2)]
        def getter(*args,**kwargs):return rows
        args=dict(symbol='BTCUSDT',seconds=60,start=START,end=START+timedelta(minutes=3),getter=getter)
        with self.assertRaises(DataUnavailable):fetch_binance(**args)
        market=fetch_binance(**args,allow_gaps=True)
        self.assertEqual(len(market.bars),2)
        self.assertEqual(market.provenance['missing_candles'],1)
        self.assertEqual(market.bars[1].ts,START+timedelta(minutes=2))
        rows[0][6]-=1000
        abbreviated=fetch_binance(**args,allow_gaps=True)
        self.assertEqual(len(abbreviated.provenance['abbreviated_candles']),1)
        self.assertEqual(abbreviated.bars[0].seconds,60)
        self.assertEqual(abbreviated.bars[0].ts,START)
        rows[1][6]+=1
        with self.assertRaises(DataUnavailable):fetch_binance(**args,allow_gaps=True)

    def test_filter_is_causal_and_neutral_defaults_preserve_existing_decisions(self):
        bars=SyntheticProvider(count=260,seed=512).bars();base=Strategy()
        self.assertEqual(base.evaluate(bars),base._evaluate(bars))
        strict=Strategy(min_relative_volume=1e6)
        active=[i for i in range(60,len(bars)) if base.evaluate(bars[:i]).side!='WAIT']
        self.assertTrue(active)
        prefix=bars[:active[0]];filtered=strict.evaluate(prefix)
        self.assertEqual(filtered.side,'WAIT');self.assertIn('volume insuficiente',filtered.reason)
        altered=prefix+[replace(b,open=b.open*2,close=b.close*2,high=b.high*2,low=b.low*2) for b in bars[active[0]:]]
        self.assertEqual(filtered,strict.evaluate(altered[:len(prefix)]))

    def test_saved_filters_are_part_of_open_exposure_identity_and_legacy_is_compatible(self):
        ledger=Ledger();self.addCleanup(ledger.close)
        engine=PaperEngine(ledger,costs=ExecutionSettings(fee_per_unit=0))
        engine.on_bar(bar(),False);engine.submit(signal(),'position')
        engine.on_bar(bar(START+timedelta(minutes=1)),False)
        with ledger.transaction() as state:
            for key in ('min_trend_atr','min_efficiency','min_relative_volume','max_entry_atr','require_trend_slope'):
                state['config']['strategy'].pop(key)
        PaperEngine(ledger,costs=engine.costs)
        with self.assertRaises(ValueError):PaperEngine(ledger,costs=engine.costs,strategy=Strategy(min_efficiency=.3))

    def test_invalid_filter_values_are_refused(self):
        for p in ({'min_efficiency':1.1},{'min_trend_atr':float('nan')},{'max_entry_atr':-1},
            {'min_relative_volume':True},{'require_trend_slope':1}):
            with self.assertRaises(ValueError):Strategy(**p)
