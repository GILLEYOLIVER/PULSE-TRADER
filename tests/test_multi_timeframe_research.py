from __future__ import annotations

import unittest
from dataclasses import asdict,replace
from datetime import datetime,timedelta

from trading_assistant.v2.models import UTC,Bar
from trading_assistant.v2.strategy import Strategy
from trading_assistant.v2.research import RESEARCH_WARMUP,candidate_bank,warmup_start
from trading_assistant.v2.execution import PaperEngine
from trading_assistant.v2.ledger import SimulationLedger
from scripts.research_cycle import window_sizes


class MultiTimeframeResearchCase(unittest.TestCase):
    def history(self,opposing=False):
        start=datetime(2025,1,1,tzinfo=UTC);out=[]
        for i in range(1024):
            price=(2500-i*2 if i<800 else 1000+(i-800)*.5) if opposing else 1000+i*.5
            out.append(Bar('WIN',start+timedelta(minutes=i),price,price+1,price-1,price,1000))
        last=out[-1].close
        out[-1]=replace(out[-1],open=last-.5,high=last+.5,low=last-10.5,close=last-9.5)
        return out

    def test_mean_reversion_multitimeframe_flag_rejects_an_opposing_long_regime(self):
        bars=self.history(opposing=True)
        plain=Strategy('mean_reversion',.5,1.5).evaluate(bars)
        filtered=Strategy('mean_reversion',.5,1.5,multi_timeframe=True).evaluate(bars)
        self.assertEqual(plain.side,'BUY')
        self.assertEqual(filtered.side,'WAIT')
        self.assertEqual(filtered.indicators['higher_trend_confirmed'],0)
        for key in ('price','stop','target'):self.assertEqual(getattr(plain,key),getattr(filtered,key))

    def test_aligned_both_directions_preserve_a_bounded_stop_and_target(self):
        for mirror in (False,True):
            bars=self.history()
            if mirror:bars=[replace(b,open=4000-b.open,high=4000-b.low,low=4000-b.high,close=4000-b.close) for b in bars]
            plain=Strategy('mean_reversion',.5,1.5).evaluate(bars)
            filtered=Strategy('mean_reversion',.5,1.5,multi_timeframe=True).evaluate(bars)
            self.assertEqual(filtered.side,'SELL' if mirror else 'BUY')
            self.assertEqual(filtered.indicators['higher_trend_confirmed'],1)
            self.assertLessEqual(abs(filtered.price-filtered.stop),3*filtered.indicators['atr'])
            for key in ('price','stop','target'):self.assertEqual(getattr(plain,key),getattr(filtered,key))

    def test_incomplete_higher_bucket_never_supplies_its_close(self):
        bars=self.history();strategy=Strategy('mean_reversion',.5,1.5,multi_timeframe=True)
        decision=strategy.evaluate(bars)
        self.assertLess(decision.indicators['higher_available_at'],decision.ts.timestamp())
        # Last base candle is in an incomplete five-candle bucket. Its known
        # base close may affect the entry, but cannot change the higher averages.
        altered=[*bars[:-1],replace(bars[-1],close=bars[-1].close+.1)]
        other=strategy.evaluate(altered)
        self.assertEqual(other.side,'BUY')
        for key in ('higher_sma50','higher_sma200','higher_available_at'):
            self.assertEqual(decision.indicators[key],other.indicators[key])
        prefix=[*bars,replace(bars[-1],ts=bars[-1].ts+timedelta(minutes=1))]
        self.assertEqual(strategy.evaluate(prefix[:len(bars)]),decision)

    def test_engine_retains_enough_context_at_unaligned_edges_without_warmup_orders(self):
        bars=self.history();policy=Strategy('mean_reversion',.5,1.5,multi_timeframe=True)
        self.assertEqual(policy.evaluate(bars[-1000:]).side,'WAIT')
        self.assertEqual(policy.evaluate(bars).side,'BUY')
        ledger=SimulationLedger();self.addCleanup(ledger.close)
        engine=PaperEngine(ledger,strategy=policy)
        for b in bars:engine.on_bar(b,automatic=False,evaluate_signal=False)
        self.assertEqual(len(engine.history['WIN']),1024)
        self.assertEqual(engine.strategy.evaluate(engine.history['WIN']).side,'BUY')
        self.assertEqual(ledger.read()['orders'],{})
        self.assertEqual(Strategy().history_limit,1000)
        self.assertEqual(Strategy('sma_cross',multi_timeframe=True).history_limit,1024)

    def test_future_grid_changes_are_bounded_diverse_and_opt_in(self):
        reference=asdict(Strategy())
        legacy=candidate_bank(0,reference,36)
        self.assertTrue(all(not p['multi_timeframe'] for p in legacy))
        for cycle in (0,1):
            bank=candidate_bank(cycle,reference,36,allow_multi_timeframe=True)
            self.assertEqual(bank[0],reference)
            self.assertEqual(len(bank),36)
            self.assertEqual({p['multi_timeframe'] for p in bank},{False,True})
            self.assertEqual(bank,candidate_bank(cycle,reference,36,allow_multi_timeframe=True))

    def test_larger_context_and_future_windows_fit_the_provider_limit(self):
        start=datetime(2026,1,1,tzinfo=UTC)
        for seconds in (300,3600,86400):
            prior=datetime.fromisoformat(warmup_start(start,seconds,RESEARCH_WARMUP)).replace(tzinfo=UTC)
            _,days=window_sizes('SOLUSDT',seconds)
            requested=((start+timedelta(days=days))-prior).total_seconds()/seconds
            self.assertLessEqual(requested,10000)
            self.assertGreaterEqual((start-prior).total_seconds()/seconds,RESEARCH_WARMUP)


if __name__=='__main__':unittest.main()
