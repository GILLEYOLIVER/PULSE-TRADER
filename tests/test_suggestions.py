from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from test_v2 import START, bar
from trading_assistant.v2.data import SyntheticProvider
from trading_assistant.v2.ledger import Ledger
from trading_assistant.v2.models import Limits, ExecutionSettings
from trading_assistant.v2.strategy import Strategy
from trading_assistant.v2.suggestions import analyze_series, matches_profile, merge_series, save_plan


def directional(direction=1, symbol="WDO", seconds=60):
    return [bar(START+timedelta(seconds=i*seconds), price=1000+direction*i,
                symbol=symbol) for i in range(70)]


class SuggestionsCase(unittest.TestCase):
    def test_both_profiles_and_directions(self):
        for profile, seconds in (("intraday", 60), ("swing", 86400)):
            for direction, trend in ((1, "UP"), (-1, "DOWN")):
                with self.subTest(profile=profile, direction=direction):
                    bars = [replace(b, seconds=seconds) for b in directional(direction, seconds=seconds)]
                    result = analyze_series(bars, profile, as_of=bars[-1].ts+timedelta(seconds=seconds))
                    self.assertEqual(result.trend, trend)
                    self.assertIsNotNone(result.entry)
                    if direction == 1:
                        self.assertLess(result.stop, result.entry)
                        self.assertLess(result.entry, result.target)
                    else:
                        self.assertLess(result.target, result.entry)
                        self.assertLess(result.entry, result.stop)
                    self.assertTrue(result.reason)
                    self.assertTrue(result.condition)
                    record = result.to_dict()
                    self.assertIsNone(record['confidence'])
                    self.assertFalse(record['probability_calibrated'])
                    self.assertFalse(record['execution_enabled'])
                    self.assertEqual(record['source'], 'SYNTHETIC')

    def test_no_lookahead_from_open_or_future_candles(self):
        bars = directional()
        cutoff = bars[-1].ts+timedelta(seconds=30)
        expected = analyze_series(bars[:-1], 'intraday', as_of=cutoff)
        revised = bars[:-1]+[replace(bars[-1], open=100000, high=110000, low=90000, close=105000)]
        revised.append(replace(revised[-1], ts=bars[-1].ts+timedelta(minutes=1), close=106000))
        self.assertEqual(analyze_series(revised, 'intraday', as_of=cutoff), expected)

    def test_flat_or_short_history_does_not_invent_entry(self):
        flat = [bar(START+timedelta(minutes=i), high=1000, low=1000) for i in range(50)]
        result = analyze_series(flat, 'intraday', as_of=flat[-1].ts+timedelta(minutes=1))
        self.assertEqual(result.trend, 'FLAT')
        self.assertIsNone(result.entry)
        short = analyze_series(flat[:20], 'intraday', as_of=flat[-1].ts)
        self.assertEqual(short.trend, 'UNKNOWN')
        self.assertEqual(short.candles, 20)
        self.assertIsNone(short.stop)
        ledger = Ledger()
        try:
            with self.assertRaises(ValueError):
                save_plan(ledger, short, saved_at=START, limits=Limits(), costs=ExecutionSettings(), parameters=Strategy())
        finally:
            ledger.close()

    def test_cross_file_overlap_or_revision_does_not_replace_catalog(self):
        bars = directional()
        original = {('WDO', 60, 'SYNTHETIC'): bars[:40]}
        combined = merge_series(original, bars[35:])
        self.assertEqual(len(next(iter(combined.values()))), 70)
        for changed in (replace(bars[39], close=bars[39].close+.1),
                        replace(bars[39], ts=bars[39].ts+timedelta(seconds=30))):
            with self.assertRaises(ValueError):
                merge_series(original, [changed])
        self.assertEqual(original[('WDO', 60, 'SYNTHETIC')], bars[:40])

    def test_profiles_do_not_relabel_intraday_as_daily(self):
        self.assertTrue(matches_profile(300, 'intraday'))
        self.assertTrue(matches_profile(86400, 'swing'))
        self.assertFalse(matches_profile(300, 'swing'))
        with self.assertRaises(ValueError):
            analyze_series(directional(), 'swing')

    def test_invalid_series_is_rejected(self):
        bars = directional()
        for last in (replace(bars[-1], symbol='WIN'), replace(bars[-1], source='OTHER'),
                     replace(bars[-1], seconds=300), replace(bars[-1], ts=bars[-2].ts)):
            with self.subTest(last=last), self.assertRaises(ValueError):
                analyze_series(bars[:-1]+[last], 'intraday')

    def test_unknown_instrument_keeps_direction_without_trade_plan(self):
        result = analyze_series(directional(symbol='UNCONFIGURED'), 'intraday', as_of=START+timedelta(days=1))
        self.assertEqual(result.trend, 'UP')
        self.assertIsNone(result.entry)
        self.assertIn('especificação', result.condition)

    def test_saved_plan_is_durable_idempotent_and_never_an_order(self):
        suggestion = analyze_series(directional(), 'intraday', as_of=START+timedelta(days=1))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'paper.sqlite'
            ledger = Ledger(path)
            args = dict(saved_at=START+timedelta(days=1), limits=Limits(), costs=ExecutionSettings(), parameters=Strategy())
            first = save_plan(ledger, suggestion, **args)
            second = save_plan(ledger, suggestion, **{**args, 'saved_at': START+timedelta(days=2)})
            self.assertEqual(first['id'], second['id'])
            self.assertEqual(first['saved_at'], second['saved_at'])
            self.assertEqual(ledger.db.execute("SELECT COUNT(*) FROM audit WHERE event='analysis_plan_saved'").fetchone()[0], 1)
            self.assertFalse(ledger.read()['orders'])
            self.assertFalse(ledger.read()['positions'])
            ledger.close()
            ledger = Ledger(path)
            try:
                saved = ledger.read()['analysis_plans'][first['id']]
                self.assertEqual(saved['analysis']['data_sha256'], suggestion.data_sha256)
                self.assertFalse(saved['risk_approved'])
                self.assertIsNone(saved['quantity'])
                self.assertEqual(saved['risk_budget'], 50)
                json.dumps(saved, allow_nan=False)
            finally:
                ledger.close()

    def test_provenance_and_tick_rounding_are_preserved(self):
        bars = SyntheticProvider('WDO', 90, seed=7).bars()
        result = analyze_series(bars, 'intraday', as_of=bars[-1].ts+timedelta(minutes=1))
        if result.entry is not None:
            for price in (result.entry, result.stop, result.target):
                self.assertAlmostEqual(price/.5, round(price/.5))
        changed = [replace(b, source='AUTHORIZED_USER_EXPORT') for b in bars]
        authorized = analyze_series(changed, 'intraday', as_of=changed[-1].ts+timedelta(minutes=1))
        self.assertEqual(authorized.source, 'AUTHORIZED_USER_EXPORT')
        self.assertNotEqual(result.data_sha256, authorized.data_sha256)


if __name__ == '__main__':
    unittest.main()
