"""Contract: the two-job split workflow + reusable session script are wired
correctly so a full market day fits GitHub's per-job cap (CHG-20261127-1625).
PAPER-ONLY; no real orders."""
import os
import unittest
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github/workflows/cloud-ce-pe-paper-split.yml"
SCRIPT = ROOT / "scripts/run_paper_session.sh"


class SplitWorkflow(unittest.TestCase):
    def test_script_exists_executable_and_paper_only(self):
        self.assertTrue(SCRIPT.exists())
        self.assertTrue(os.access(SCRIPT, os.X_OK))
        src = SCRIPT.read_text()
        self.assertIn("cloud_paper_session", src)
        self.assertIn("RUN_SIDECARS", src)
        # guard: sidecar launches only when RUN_SIDECARS=1
        self.assertIn('if [ "$RUN_SIDECARS" = "1" ]', src)
        # never an order endpoint
        for forbidden in ("place_order", "place-order", "allow_live_orders=True"):
            self.assertNotIn(forbidden, src)

    @unittest.skipIf(yaml is None, "pyyaml not installed")
    def test_two_sequential_jobs_each_under_cap(self):
        d = yaml.safe_load(WF.read_text())
        jobs = d["jobs"]
        self.assertEqual(set(jobs), {"paper_morning", "paper_afternoon"})
        self.assertEqual(jobs["paper_afternoon"]["needs"], "paper_morning")
        self.assertIn("should_run", jobs["paper_afternoon"]["if"])
        for name, job in jobs.items():
            self.assertLessEqual(job["timeout-minutes"], 355, name)
        m, a = jobs["paper_morning"]["env"], jobs["paper_afternoon"]["env"]
        self.assertEqual((m["PAPER_SESSION_END"], m["PAPER_FLAT_BY"], str(m["RUN_SIDECARS"])),
                         ("1220", "1215", "1"))
        self.assertEqual((a["PAPER_SESSION_END"], a["PAPER_FLAT_BY"], str(a["RUN_SIDECARS"])),
                         ("1522", "1520", "0"))
        # morning end < afternoon end => real split, afternoon continues the day
        self.assertLess(m["PAPER_SESSION_END"], a["PAPER_SESSION_END"])

    @unittest.skipIf(yaml is None, "pyyaml not installed")
    def test_split_is_dispatch_only_until_validated(self):
        d = yaml.safe_load(WF.read_text())
        on = d.get(True, d.get("on"))
        self.assertIn("workflow_dispatch", on)
        self.assertNotIn("schedule", on if isinstance(on, dict) else {})


if __name__ == "__main__":
    unittest.main()
