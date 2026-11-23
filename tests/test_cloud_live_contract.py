"""Offline checks for live paper schedule, session gates, and completion truthfulness."""
import datetime as dt
import json
import os
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from zoneinfo import ZoneInfo
from deploy import cloud_session_gate as gate

ROOT = Path(__file__).resolve().parents[1]
IST = ZoneInfo("Asia/Kolkata")

class LivePaperContract(TestCase):
    def test_0900_weekday_cron_is_present(self):
        yaml=(ROOT/".github/workflows/cloud-ce-pe-paper.yml").read_text()
        self.assertIn('cron: "30,45 3 * * 1-5"',yaml)
        self.assertIn('cron: "0,15,30,45 4 * * 1-5"',yaml)
        self.assertIn('cron: "0,15,30 5 * * 1-5"',yaml)

    def test_skipped_workflow_is_explicit_without_failing_ci(self):
        yaml=(ROOT/".github/workflows/cloud-ce-pe-paper.yml").read_text()
        step=yaml.split("      - name: Report duplicate or inactive paper session explicitly")[1].split("      - name: Offline safety and unit tests")[0]
        self.assertIn("SKIPPED",step)
        self.assertIn("MARKET_CLOSED_OR_DUPLICATE",step)
        self.assertNotIn("exit 1",step)
        self.assertNotIn("NO_LIVE_SESSION",step)

    def test_1530_monitoring_contract(self):
        files=["india_trader/advanced_forward.py","india_trader/ema9_v2_live_sidecar.py",
               "india_trader/three_candle_live_sidecar.py","india_trader/ema9_ema15_live_sidecar.py"]
        for filename in files:
            source=(ROOT/filename).read_text()
            with self.subTest(filename=filename):
                self.assertIn("dt.time(15,30)",source)
        cloud=(ROOT/"deploy/cloud_paper_session.py").read_text()
        # Controller allows worker finalization after the 15:30 market cutoff.
        self.assertIn("dt.time(15, 32)",cloud)

    def test_cloud_controller_deadline_is_executable(self):
        import ast
        source=(ROOT/"deploy/cloud_paper_session.py").read_text()
        tree=ast.parse(source)
        assignments=[node for node in ast.walk(tree) if isinstance(node,ast.Assign)
                     and any(isinstance(target,ast.Name) and target.id=="deadline"
                             for target in node.targets)]
        self.assertEqual(len(assignments),1)
        self.assertIn("dt.time(15, 32)",ast.get_source_segment(source,assignments[0]))

    def test_previous_success_without_worker_is_not_session(self):
        response={"jobs":[{"steps":[{"name":"Prevent duplicate market-day sessions across retry triggers","conclusion":"success"},
                                     {"name":"Run live option-quote CE/PE paper session (read only)","conclusion":"skipped"}]}]}
        class Reply:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self):return json.dumps(response).encode()
        with patch.object(gate.urllib.request,"urlopen",return_value=Reply()):
            self.assertFalse(gate.completed_run_executed_session("owner/repo",123,"token"))
            response["jobs"][0]["steps"][1]["conclusion"]="success"
            self.assertTrue(gate.completed_run_executed_session("owner/repo",123,"token"))

    def test_failed_or_cancelled_executed_worker_is_not_auto_retried(self):
        for conclusion in ("failure", "cancelled", "success"):
            with self.subTest(conclusion=conclusion):
                previous = {"id": 12, "status": "completed", "conclusion": conclusion}
                with patch.object(gate, "completed_run_executed_session", return_value=True) as executed:
                    self.assertTrue(gate.prior_run_blocks_new_session(previous, "owner/repo", "test"))
                    executed.assert_called_once_with("owner/repo", 12, "test")

    def test_gate_only_or_startup_failed_run_may_retry(self):
        for conclusion in ("success", "failure", "cancelled"):
            with self.subTest(conclusion=conclusion):
                previous = {"id": 12, "status": "completed", "conclusion": conclusion}
                with patch.object(gate, "completed_run_executed_session", return_value=False):
                    self.assertFalse(gate.prior_run_blocks_new_session(previous, "owner/repo", "test"))

    def test_active_previous_run_blocks_without_remote_lookup(self):
        with patch.object(gate, "completed_run_executed_session",
                          side_effect=AssertionError("premature lookup")):
            self.assertTrue(gate.prior_run_blocks_new_session(
                {"id": 12, "status": "in_progress"}, "owner/repo", "test"))

    def test_gate_time_contract(self):
        source=(ROOT/"deploy/cloud_session_gate.py").read_text()
        self.assertIn("dt.time(15, 25)",source)
        self.assertIn("completed_run_executed_session",source)
