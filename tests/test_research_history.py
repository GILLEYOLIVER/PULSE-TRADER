from __future__ import annotations

import tempfile
import unittest
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import patch

from trading_assistant.v2.models import Bar,UTC
from trading_assistant.v2.market_data import MarketSnapshot,fetch_binance
from trading_assistant.v2.research_history import get_research_history,checked_json
from trading_assistant.v2.suggestions import history_digest


class ResearchHistoryCase(unittest.TestCase):
    start=datetime(2024,1,1,tzinfo=UTC)

    def source(self,missing=(),bad_symbol=False,fail_call=None):
        calls=[]
        def fetcher(symbol,seconds,*,start,end,allow_gaps):
            calls.append((start,end));self.assertTrue(allow_gaps)
            if len(calls)==fail_call:raise ValueError('transient fixture outage')
            count=int((end-start).total_seconds())//seconds;bars=[];gaps=[]
            for i in range(count):
                ts=start+timedelta(seconds=seconds*i);index=int((ts-self.start).total_seconds())//seconds
                if index in missing:
                    first=int(ts.timestamp()*1000)
                    gaps.append({'first_missing_ms':first,'next_available_ms':first+seconds*1000,'candles':1})
                else:bars.append(Bar('ETHUSDT' if bad_symbol else symbol,ts,100.,102.,99.,101.,1000.,'BINANCE_SPOT_USDT',seconds,100000.,10,500.))
            return MarketSnapshot(bars,{'candles':len(bars),'expected_candles':count,'missing_candles':count-len(bars),
                'sha256':history_digest(bars),'gaps':gaps,'abbreviated_candles':[],'mode':'READ_ONLY'})
        return fetcher,calls

    def load(self,directory,fetcher,*,count=100,chunk=30):
        return get_research_history('BTCUSDT',60,self.start,self.start+timedelta(minutes=count),directory,
            fetcher=fetcher,chunk_bars=chunk)

    def test_chunks_are_contiguous_disjoint_bounded_and_cache_is_verified_without_network(self):
        fetcher,calls=self.source()
        with tempfile.TemporaryDirectory() as directory:
            bars=self.load(directory,fetcher)
            self.assertEqual(len(bars),100);self.assertEqual(len(calls),4)
            self.assertTrue(all((b-a).total_seconds()<=30*60 for a,b in calls))
            self.assertTrue(all(a[1]==b[0] for a,b in zip(calls,calls[1:])))
            again=self.load(directory,lambda *a,**k:self.fail('cache attempted network'))
            self.assertEqual(bars,again)
            manifest=next(Path(directory).glob('data/research-*/manifest.json'))
            metadata,_=checked_json(manifest)
            self.assertEqual(metadata['sha256'],history_digest(bars))
            self.assertEqual(metadata['expected_candles'],100)
            self.assertEqual(len(metadata['parts']),4)

    def test_partial_download_reuses_completed_chunks_after_failure(self):
        fetcher,calls=self.source(fail_call=2)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,'outage'):self.load(directory,fetcher)
            self.assertEqual(len(list(Path(directory).glob('data/research-*/part-*/manifest.json'))),1)
            retry,new_calls=self.source()
            bars=self.load(directory,retry)
            self.assertEqual(len(bars),100);self.assertEqual(len(new_calls),3)
            self.assertEqual(new_calls[0][0],self.start+timedelta(minutes=30))

    def test_whole_interval_gap_limit_does_not_pad_or_reject_a_short_local_outage(self):
        # One chunk lacks 10%, but the full request lacks only 3%. All three
        # timestamps remain absent; completeness is never manufactured.
        fetcher,_=self.source(missing={30,31,32})
        with tempfile.TemporaryDirectory() as directory:
            bars=self.load(directory,fetcher)
            self.assertEqual(len(bars),97)
            self.assertFalse(any(b.ts==self.start+timedelta(minutes=31) for b in bars))
            manifest=next(Path(directory).glob('data/research-*/manifest.json'))
            metadata,_=checked_json(manifest)
            self.assertEqual(metadata['missing_candles'],3)
            self.assertEqual(len(metadata['gaps']),3)

    def test_excessive_missing_data_and_wrong_market_are_preserved_but_not_accepted(self):
        fetcher,_=self.source(missing=set(range(6)))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,'5%'):self.load(directory,fetcher)
            self.assertTrue(list(Path(directory).glob('data/research-*/rejection.json')))
            self.assertFalse(list(Path(directory).glob('data/research-*/manifest.json')))
            self.assertEqual(len(list(Path(directory).rglob('*.csv'))),4)
        fetcher,_=self.source(bad_symbol=True)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,'incompatible'):self.load(directory,fetcher)

    def test_corrupt_manifest_or_csv_does_not_trigger_silent_redownload(self):
        for corrupt in ('manifest','csv'):
            with tempfile.TemporaryDirectory() as directory:
                fetcher,_=self.source();self.load(directory,fetcher)
                path=next(Path(directory).glob('data/research-*/part-0001/manifest.json' if corrupt=='manifest' else 'data/research-*/part-0001/*.csv'))
                path.write_text('{}' if corrupt=='manifest' else 'corrupt',encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'checksum'):
                    self.load(directory,lambda *a,**k:self.fail('corruption attempted network'))

    def test_low_disk_stops_before_fetch_and_keeps_existing_parts(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('trading_assistant.v2.research_history.shutil.disk_usage') as usage:
                usage.return_value.free=10
                with self.assertRaisesRegex(ValueError,'free space'):
                    self.load(directory,lambda *a,**k:self.fail('insufficient space attempted network'))

    def test_bounds_and_future_data_are_rejected_without_loosening_normal_provider_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            for count in (0,100001):
                with self.assertRaises(ValueError):self.load(directory,None,count=count)
            with self.assertRaises(ValueError):get_research_history('BTCUSDT',60,self.start,
                datetime.now(UTC)+timedelta(days=1),directory)
            with self.assertRaises(ValueError):fetch_binance('BTCUSDT',60,start=self.start,
                end=self.start+timedelta(minutes=10001),getter=lambda *a,**k:self.fail('normal limit changed'))


if __name__=='__main__':unittest.main()
