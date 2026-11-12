"""Offline tests for year historical Upstox index replay: no options fills invented."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from india_trader.core import Bar,IST
from india_trader.historical_backtest import annual_signal_backtest,replay_signal_day
from india_trader.intraday_lab import intraday_signal
from india_trader.upstox import UpstoxReader,UpstoxError,INDICES


def sample_day(day,breakout=True):
    origin=dt.datetime.combine(day,dt.time(9,15),IST)
    bars=[]
    for offset in range(0,325,5):
        t=origin+dt.timedelta(minutes=offset)
        p=100 if offset<15 else (102 if breakout else 100)
        bars.append(Bar(t,p,p+1,p-1,p,1000))
    return bars


class Reader:
    def __init__(self):
        self.calls=[]
    def historical_index_candles(self,key,start,end):
        self.calls.append((key,start,end))
        if key==INDICES['SENSEX']:
            return sample_day(dt.date(2025,10,1))
        return []


class HistoricalReplayTests(unittest.TestCase):
    def test_same_closed_bar_signal_function_used_no_lookahead(self):
        day=dt.date(2025,10,1)
        bars=sample_day(day)
        candidates,status=replay_signal_day(bars,day)
        self.assertEqual(status,'OK')
        expected=intraday_signal(bars,dt.datetime(2025,10,1,9,35,1,tzinfo=IST))
        self.assertEqual(candidates[0]['strategy'],expected['strategy'])
        self.assertEqual(candidates[0]['bar'],expected['bar'])
        self.assertEqual(candidates[0]['direction'],expected['direction'])
        self.assertEqual(candidates[0]['confirmed_at'],expected['confirmed_at'])

    def test_missing_opening_index_bars_fail_closed(self):
        day=dt.date(2025,10,1)
        candidates,status=replay_signal_day(sample_day(day)[1:],day)
        self.assertEqual(status,'MISSING_OPENING_BARS')
        self.assertEqual(candidates,[])

    def test_missing_intra_day_candle_fail_closed(self):
        day=dt.date(2025,10,1)
        bars=[b for b in sample_day(day) if b.time.time()!=dt.time(10,15)]
        candidates,status=replay_signal_day(bars,day)
        self.assertEqual(status,'MISSING_INTRADAY_CANDLES')
        self.assertEqual(candidates,[])

    def test_auto_weekday_schedule_and_reproducible_cached_data(self):
        fake=Reader()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            report=annual_signal_backtest('2025-10-01','2025-10-03','AUTO',
                reader=fake,cache_dir=path/'cache',out=path/'report.json')
            self.assertEqual(report['days_analyzed'],3)
            self.assertEqual(report['days_with_complete_bars'],1)
            self.assertEqual(report['missing_or_incomplete_days'],2)
            self.assertEqual(report['candidate_signals'],1)
            self.assertEqual(report['signals'][0]['market'],'SENSEX')
            self.assertEqual(report['signals'][0]['strategy'],'OPENING_RANGE_BREAKOUT')
            self.assertIsNone(report['net_options_pnl'])
            self.assertIsNone(report['option_trades'])
            self.assertTrue((path/'report.json').exists())
            self.assertEqual(len(fake.calls),2)
            second=annual_signal_backtest('2025-10-01','2025-10-03','AUTO',
                reader=fake,cache_dir=path/'cache')
            self.assertEqual(len(fake.calls),2) # Historical API not called again
            self.assertEqual(second['signals'],report['signals'])

    def test_upstox_reader_historical_path_and_no_bad_dates(self):
        api=UpstoxReader(token='MOCK_ONLY')
        date='2025-10-01T09:15:00+05:30'
        with patch.object(api,'get',return_value={'candles':[[date,100,101,99,100,1000,0]]}) as get:
            bars=api.historical_index_candles(INDICES['SENSEX'],'2025-10-01','2025-10-01')
        self.assertEqual(len(bars),1)
        self.assertEqual(bars[0].close,100)
        self.assertIn('/v3/historical-candle/',get.call_args.args[0])
        self.assertIn('/minutes/5/2025-10-01/2025-10-01',get.call_args.args[0])
        with self.assertRaises(UpstoxError):
            api.historical_index_candles(INDICES['NIFTY'],'2025-10-01','2025-11-15')

    def test_date_guard_blocks_unsupported_future_replay(self):
        with self.assertRaises(ValueError):
            annual_signal_backtest('2025-10-01','2027-01-01',reader=Reader())


if __name__=='__main__':
    unittest.main()
