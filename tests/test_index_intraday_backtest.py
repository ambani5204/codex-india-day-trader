"""Index-only intraday replay: no options or executable index trades."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from india_trader.core import Bar, IST
from india_trader.index_intraday_backtest import (
    simulate_index_day, backtest_index_intraday, _exit_price)
from india_trader.upstox import INDICES

DAY=dt.date(2025,10,1)


def bar(day,minute,open_,high,low,close):
    origin=dt.datetime.combine(day,dt.time(9,15),IST)
    return Bar(origin+dt.timedelta(minutes=minute),open_,high,low,close,100)


def complete_day(day,scenario='target'):
    bars=[]
    for minute in range(0,360,5): # through 15:10 index candles
        if minute<15:
            o,h,l,c=100,101,99,100
        elif minute==15:
            o,h,l,c=102,104,102,103 # confirmed bullish breakout @09:35
        elif minute==20:
            if scenario=='target':
                o,h,l,c=103,108,102.8,106
            elif scenario=='ambiguous':
                o,h,l,c=103,108,100,102
            elif scenario=='gap':
                o,h,l,c=103,104,102,103
            else:
                o,h,l,c=103,104,102,103
        elif minute==25 and scenario=='gap':
            o,h,l,c=99,100,98,99
        else:
            o,h,l,c=103,103.5,102.5,103
        bars.append(bar(day,minute,o,h,l,c))
    return bars


class FakeReader:
    def __init__(self,days):
        self.days=days
        self.calls=0
    def historical_index_candles(self,key,start,end):
        self.calls+=1
        begin=dt.date.fromisoformat(start)
        finish=dt.date.fromisoformat(end)
        return [b for b in self.days.get(key,[]) if begin<=b.time.date()<=finish]


class IndexOnlyDayTests(unittest.TestCase):
    def test_next_candle_entry_and_chart_target_not_signal_close(self):
        result=simulate_index_day(complete_day(DAY),DAY,'SENSEX')
        self.assertEqual(result['status'],'OK')
        self.assertEqual(len(result['trades']),1)
        t=result['trades'][0]
        self.assertEqual(t['strategy'],'OPENING_RANGE_BREAKOUT')
        self.assertEqual(t['direction'],'BULL')
        self.assertEqual(t['entry'],103)
        self.assertEqual(t['entry_time'],dt.datetime(2025,10,1,9,35,tzinfo=IST).isoformat())
        self.assertGreater(t['exit'],t['entry'])
        self.assertEqual(t['exit_reason'],'TARGET')
        self.assertGreaterEqual(t['realized_r'],1.99)
        self.assertEqual(t['pattern'],'BREAKOUT')

    def test_same_bar_both_stop_and_target_chooses_stop(self):
        result=simulate_index_day(complete_day(DAY,'ambiguous'),DAY,'NIFTY')
        self.assertEqual(len(result['trades']),1)
        self.assertEqual(result['trades'][0]['exit_reason'],'STOP_FIRST_AMBIGUOUS')
        self.assertLess(result['trades'][0]['index_points'],0)
        self.assertLessEqual(result['trades'][0]['realized_r'],-.99)

    def test_gap_through_stop_exits_at_adverse_open_not_stop(self):
        result=simulate_index_day(complete_day(DAY,'gap'),DAY,'NIFTY')
        self.assertEqual(len(result['trades']),1)
        t=result['trades'][0]
        self.assertEqual(t['exit_reason'],'GAP_STOP')
        self.assertEqual(t['exit'],99)
        self.assertLess(t['realized_r'],-1)

    def test_missing_exit_candle_excludes_session_not_magic_fill(self):
        bars=[b for b in complete_day(DAY) if b.time.time()!=dt.time(14,55)]
        result=simulate_index_day(bars,DAY,'SENSEX')
        self.assertEqual(result['status'],'MISSING_EXIT_OR_SESSION_CANDLES')
        self.assertEqual(result['trades'],[])

    def test_fakeout_bad_chart_rr_skipped_not_forced_into_trade(self):
        bars=complete_day(DAY)
        fourth=bars[3]
        bars[3]=Bar(fourth.time,100.8,103,99.5,100.6,100)
        next_bar=bars[4]
        # Next opening is near the rejection close, not a favorable gap
        # back near the wick high; the midpoint target cannot pay 1.5R.
        bars[4]=Bar(next_bar.time,100.6,102,99.5,100,100)
        result=simulate_index_day(bars,DAY,'SENSEX')
        self.assertEqual(result['status'],'OK')
        self.assertGreater(result['rejections'].get('NEXT_OPEN_INVALIDATES_STOP_TARGET_OR_RR',0),0)
        self.assertFalse(any(t['strategy']=='OPENING_RANGE_FAKEOUT' for t in result['trades']))

    def test_adverse_slippage_reduces_r(self):
        base=simulate_index_day(complete_day(DAY),DAY,'SENSEX',slippage_points=0)
        slipped=simulate_index_day(complete_day(DAY),DAY,'SENSEX',slippage_points=.1)
        self.assertLess(slipped['trades'][0]['realized_r'],base['trades'][0]['realized_r'])

    def test_hypothetical_flat_exit_only_at_1510(self):
        pos={'direction':'BULL','stop':50,'target':200}
        bar_=bar(DAY,355,100,101,99,100)
        price,reason,when=_exit_price(pos,bar_,0)
        self.assertEqual((price,reason),(100,'TIME_EXIT'))
        self.assertEqual(when.hour,15)
        self.assertEqual(when.minute,10)


class IndexOnlyYearTests(unittest.TestCase):
    def test_auto_schedule_cache_and_no_pnl_claims(self):
        reader=FakeReader({INDICES['SENSEX']:complete_day(DAY)})
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            report=backtest_index_intraday(
                '2025-10-01','2025-10-03',reader=reader,
                cache_dir=folder/'cache',out=folder/'results.json')
            self.assertEqual(report['complete_sessions'],1)
            self.assertEqual(report['excluded_sessions'],2)
            self.assertEqual(report['overall']['trades'],1)
            self.assertEqual(report['overall']['wins'],1)
            self.assertGreater(report['overall']['sum_r'],0)
            self.assertEqual(report['by_strategy']['OPENING_RANGE_BREAKOUT']['trades'],1)
            self.assertEqual(report['net_options_pnl_inr'],None)
            self.assertEqual(report['net_index_order_pnl_inr'],None)
            self.assertTrue((folder/'results.json').exists())
            self.assertEqual(len(report['trades']),1)
            prior_calls=reader.calls
            backtest_index_intraday(
                '2025-10-01','2025-10-03',reader=reader,cache_dir=folder/'cache')
            self.assertEqual(reader.calls,prior_calls)
            parsed=json.loads((folder/'results.json').read_text())
            self.assertEqual(parsed['overall'],report['overall'])

    def test_bad_date_and_slippage_fail_closed(self):
        with self.assertRaises(ValueError):
            backtest_index_intraday('2025-10-02','2025-10-01')
        with self.assertRaises(ValueError):
            simulate_index_day(complete_day(DAY),DAY,'SENSEX',slippage_points=-1)


if __name__=='__main__':
    unittest.main()
