"""Offline tests for scheduled research, never a trading execution test."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from india_trader.forward_monitor import (
    FROZEN_FORWARD_START, monitor_forward_simple)
from india_trader.nightly_forward import run_nightly
from india_trader.research_review import (
    KIND, TITLE, MARKER, render_review_markdown, upsert_review_issue)


def fake_metrics(trades=35, pf=1.3, net=3.5):
    return {
        "trades": trades, "net_win_rate_pct": 42 if trades else None,
        "gross_total_r": 9.0 if trades else 0,
        "fee_drag_total_r": 5.5 if trades else 0,
        "average_fee_drag_r": .16 if trades else None,
        "estimated_futures_proxy_gross_inr": 10000 if trades else 0,
        "net_total_r": net if trades else 0,
        "net_avg_r": net / trades if trades else None,
        "net_profit_factor": pf if trades else None,
        "net_max_drawdown_r": -7 if trades else 0,
        "estimated_futures_proxy_total_inr": 4500 if trades else 0,
        "estimated_futures_proxy_charges_inr": 5500 if trades else 0,
    }


def fake_result(days, policy, slippage):
    if policy is None:
        return {"excluded": {"NO_MARKET_CANDLES": 1},
                "signals": 80, "rejections": {}, "metrics": fake_metrics()}
    m = (fake_metrics(net=1.8, pf=1.2) if slippage>=2 else
         fake_metrics(net=3.5, pf=1.3))
    return {"excluded": {"NO_MARKET_CANDLES": 1},
            "signals": 80,
            "rejections": {"SIDEWAYS_EFFICIENCY_RATIO": 12,
                           "STRATEGY_DISABLED_IN_RESEARCH": 20},
            "metrics": m}


class FrozenForwardTests(unittest.TestCase):
    def test_zero_forward_days_waits_without_market_data(self):
        result = monitor_forward_simple(
            end="2026-11-12", _asof_date=dt.date(2026,11,13))
        self.assertEqual(result["status"], "AWAITING_FIRST_FORWARD_DATE")
        self.assertEqual(result["complete_market_sessions"],0)
        self.assertEqual(result["results"],[])
        self.assertFalse(result["safe_to_scale_or_deploy"])
        self.assertTrue(result["requires_human_approval"])

    def test_forward_start_is_frozen_and_today_unfinished_is_rejected(self):
        with self.assertRaises(ValueError):
            monitor_forward_simple(start="2026-11-12",end="2026-11-12",
                                   _asof_date=dt.date(2026,11,13))
        with self.assertRaises(ValueError):
            monitor_forward_simple(end="2026-11-13",
                                   _asof_date=dt.date(2026,11,13))

    def test_one_positive_stressed_proxy_is_still_human_review_only(self):
        d=dt.date(2026,11,13)
        days=[d+dt.timedelta(days=i) for i in range(50)]
        sessions=[{"day":date,"market":"NIFTY","bars":[]}
                  for date in days]
        with tempfile.TemporaryDirectory() as tmp, patch(
             "india_trader.forward_monitor._load_sessions",
             return_value=sessions), patch(
             "india_trader.forward_monitor._replay_subset",
             side_effect=fake_result):
            path=Path(tmp)/"forward.json"
            r=monitor_forward_simple(end="2027-01-01",
                                     out=path,_asof_date=dt.date(2027,1,2))
            self.assertEqual(r["status"],
                "REVIEW_PAPER_ONLY_HYPOTHESIS_NOT_DEPLOYMENT_APPROVAL")
            self.assertEqual(r["complete_market_sessions"],49)
            self.assertEqual(r["coverage_pct"],98.0)
            self.assertEqual(len(r["results"]),4)
            self.assertTrue(all(p["qualified_proxy_only_for_human_review"]
                                for p in r["results"]))
            self.assertFalse(r["safe_to_scale_or_deploy"])
            self.assertIsNone(r["actual_executable_futures_or_options_pnl_inr"])
            self.assertEqual(json.loads(path.read_text())["status"],r["status"])

    def test_missing_valid_sessions_never_passes_on_optimistic_trades(self):
        d=dt.date(2026,11,13)
        sessions=[{"day":d+dt.timedelta(days=i),"market":"SENSEX","bars":[]}
                  for i in range(40)]
        def low_coverage(sessions,days,policy,slippage):
            return {"excluded":{"NO_MARKET_CANDLES":20},
                    "metrics":fake_metrics(), "signals":70, "rejections":{}}
        with patch("india_trader.forward_monitor._load_sessions",
                   return_value=sessions), patch(
                   "india_trader.forward_monitor._replay_subset",
                   side_effect=low_coverage):
            report=monitor_forward_simple(end="2027-01-01",
                                          _asof_date=dt.date(2027,1,2))
        self.assertEqual(report["status"],"INSUFFICIENT_MARKET_DATA_COVERAGE")
        self.assertFalse(any(x["qualified_proxy_only_for_human_review"]
                             for x in report["results"]))


class NightlySafetyTests(unittest.TestCase):
    def test_missing_token_is_explicit_error_artifact_not_zero_pnl(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"blocked.json"
            r,exit_code=run_nightly(out,token="")
            self.assertEqual(exit_code,2)
            self.assertEqual(r["status"],
                             "NOT_RUN_MISSING_UPSTOX_ANALYTICS_TOKEN")
            self.assertNotIn("results",r)
            self.assertEqual(json.loads(out.read_text())["status"],r["status"])

    def test_upstox_exception_text_not_leaked(self):
        with tempfile.TemporaryDirectory() as tmp,patch(
             "india_trader.nightly_forward.monitor_forward_simple",
             side_effect=RuntimeError("PRIVATE_TOKEN_ABC123")):
            out=Path(tmp)/"blocked.json"
            r,exit_code=run_nightly(out,token="not-an-actual-secret")
            self.assertEqual(exit_code,2)
            self.assertEqual(r["status"],
                             "DATA_UNAVAILABLE_OR_AUTHENTICATION_FAILED")
            self.assertNotIn("PRIVATE_TOKEN",out.read_text())


class ReviewIssueTests(unittest.TestCase):
    def sample_report(self):
        return {
            "kind": KIND,"status":"COLLECTING_PROSPECTIVE_EVIDENCE",
            "forward_freeze_date":"2026-11-13",
            "through_completed_calendar_date":"2026-12-31",
            "complete_market_sessions":21,"expected_weekday_sessions":23,
            "coverage_pct":91.3,
            "results":[{
                "playbook":"ORB_TREND_1_5R",
                "forward":fake_metrics(trades=5,net=-1.4,pf=.7),
                "double_slippage_stress":fake_metrics(
                    trades=5,net=-2,pf=.6),
                "qualified_proxy_only_for_human_review":False,
                "first_blocking_rejections":{"SIDEWAYS_EFFICIENCY_RATIO":15},
            }],
            "proposed_investigations_for_human_review":[
                "Collect more complete post-freeze sessions."],
        }

    def test_issue_is_explicitly_unapproved_and_evidence_based(self):
        body=render_review_markdown(
            self.sample_report(),
            "https://github.com/ambani5204/codex-india-day-trader/actions/runs/1")
        self.assertIn(MARKER,body)
        self.assertIn("SIDEWAYS_EFFICIENCY_RATIO",body)
        self.assertIn("Not qualified",body)
        self.assertIn("NOT approval",body)
        self.assertIn("no",body.lower())
        self.assertIn("2026-11-13",body)

    def test_never_publish_non_research_or_failed_token_report(self):
        with self.assertRaises(ValueError):
            render_review_markdown({"kind":"other","status":"OK"})
        report=self.sample_report()
        report["status"]="DATA_UNAVAILABLE_OR_AUTHENTICATION_FAILED"
        with self.assertRaises(ValueError):
            render_review_markdown(report)

    def test_first_publish_creates_later_publish_updates_same_issue(self):
        calls=[]
        def mocked_api(token,path,method="GET",body=None):
            calls.append((method,path,body))
            if method=="GET":
                return [] if len(calls)<=1 else [{
                    "title":TITLE,"body":MARKER,
                    "number":17,
                }]
            return {"number":17,
                    "html_url":"https://github.com/ambani5204/codex-india-day-trader/issues/17"}
        with patch("india_trader.research_review._api_request",
                   side_effect=mocked_api):
            first=upsert_review_issue(
                self.sample_report(),"ambani5204/codex-india-day-trader","test")
            second=upsert_review_issue(
                self.sample_report(),"ambani5204/codex-india-day-trader","test")
        self.assertEqual(first["action"],"created")
        self.assertEqual(second["action"],"updated")
        self.assertEqual([x[0] for x in calls],["GET","POST","GET","PATCH"])
        self.assertIn("/issues/17",calls[-1][1])


if __name__=="__main__":
    unittest.main()
