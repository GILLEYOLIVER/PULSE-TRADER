from __future__ import annotations
import unittest
from dataclasses import replace
from datetime import timedelta
from urllib.parse import urlparse,parse_qs

from test_v2 import START,bar
from trading_assistant.v2.chart_data import available_periods,chart_series
from trading_assistant.v2.data import aggregate
from trading_assistant.v2.data_center import provider_periods
from trading_assistant.v2.market_data import fetch_binance,fetch_market,DataUnavailable


class ChartSecondsCase(unittest.TestCase):
    def test_periods_never_offer_finer_data_than_the_source(self):
        self.assertEqual(tuple(available_periods(1).values()),(1,5,10,15,30,60,300,900))
        self.assertEqual(tuple(available_periods(60).values()),(60,300,900))
        self.assertNotIn(1,available_periods(5).values())
        self.assertEqual(available_periods(86400),{'Diário':86400})
        self.assertIn('1 s',provider_periods('binance'))
        self.assertNotIn('1 s',provider_periods('brapi'))
        self.assertNotIn('5 min',provider_periods('mercado_bitcoin'))

    def test_cached_chart_keeps_exact_emas_and_invalidates_revised_content(self):
        bars=tuple(replace(bar(START+timedelta(seconds=i),price=200+i,high=202+i,low=198+i),seconds=1) for i in range(40))
        prepared=chart_series(bars,1)
        self.assertIs(prepared,chart_series(tuple(bars),1))
        self.assertEqual(prepared[0],bars)
        self.assertEqual(prepared[1][:8],(None,)*8)
        self.assertEqual(prepared[2][:20],(None,)*20)
        for index,value in enumerate(prepared[1][8:],8):self.assertAlmostEqual(value,bars[index].close-4)
        for index,value in enumerate(prepared[2][20:],20):self.assertAlmostEqual(value,bars[index].close-10)
        revised=bars[:6]+(replace(bars[6],close=bars[6].close+1),)+bars[7:]
        changed=chart_series(revised,1)
        self.assertIsNot(changed,prepared)
        self.assertNotEqual(changed[1],prepared[1])
        self.assertEqual(chart_series(bars,1),prepared)

    def test_seconds_aggregation_preserves_activity_and_omits_missing_buckets(self):
        bars=[replace(bar(START+timedelta(seconds=i)),seconds=1,quote_volume=1000.,trades=3,taker_buy_volume=6.) for i in range(74)]
        grouped=aggregate(bars,15)
        self.assertEqual(len(grouped),4)
        self.assertEqual(grouped[0].quote_volume,15000)
        self.assertEqual(grouped[0].trades,45)
        self.assertEqual(grouped[0].taker_buy_volume,90)
        missing=bars[:7]+bars[8:]
        self.assertEqual(len(aggregate(missing,15)),3)
        self.assertEqual(aggregate(missing,15)[0].ts,START+timedelta(seconds=15))
        with self.assertRaises(ValueError):aggregate([bar()],15)


def seconds_getter(url,**kwargs):
    query=parse_qs(urlparse(url).query)
    assert query['interval']==['1s']
    start=int(query['startTime'][0]);end=int(query['endTime'][0]);limit=int(query['limit'][0])
    return [[ts,'100','102','99','101','10',ts+999,'1000',3,'6','600','0']
            for ts in list(range(start,end+1,1000))[:limit]]


class SecondsProviderCase(unittest.TestCase):
    def test_one_second_source_enforces_exact_close_clock(self):
        result=fetch_binance('BTCUSDT',1,start=START,end=START+timedelta(seconds=3),getter=seconds_getter)
        self.assertEqual(len(result.bars),3)
        self.assertTrue(all(b.seconds==1 for b in result.bars))
        def wrong_clock(url,**kwargs):
            rows=seconds_getter(url);rows[0][6]+=1;return rows
        with self.assertRaises(DataUnavailable):
            fetch_binance('BTCUSDT',1,start=START,end=START+timedelta(seconds=3),getter=wrong_clock)

    def test_last_hour_is_aggregated_from_closed_seconds_without_future_data(self):
        now=START+timedelta(hours=1,microseconds=900000)
        for seconds in (1,5,10,15,30):
            with self.subTest(seconds=seconds):
                market=fetch_market('BTCUSDT',seconds,provider='binance',window='1h',now=now,getter=seconds_getter)
                self.assertEqual(len(market.bars),3600//seconds)
                self.assertTrue(all(b.seconds==seconds and b.ts+timedelta(seconds=seconds)<=now for b in market.bars))
                self.assertEqual(market.bars[0].trades,3*seconds)
                self.assertEqual(market.provenance['base_candles'],3600)
                self.assertEqual(market.provenance['base_seconds'],1)
                self.assertFalse(market.provenance['live_quotes'])

    def test_missing_native_second_is_rejected_and_window_is_explicit(self):
        def missing(url,**kwargs):return seconds_getter(url)[1:]
        with self.assertRaises(DataUnavailable):
            fetch_market('BTCUSDT',15,provider='binance',window='1h',now=START+timedelta(hours=1),getter=missing)
        with self.assertRaises(ValueError):
            fetch_market('BTCUSDT',15,provider='binance',window='5d',getter=seconds_getter)
        with self.assertRaises(ValueError):fetch_market('PETR4',15,provider='brapi',getter=seconds_getter)


if __name__=='__main__':unittest.main()
