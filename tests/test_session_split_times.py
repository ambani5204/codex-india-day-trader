"""Contract tests: the paper worker and all sidecars honour PAPER_SESSION_END /
PAPER_FLAT_BY so the two-job morning/afternoon split can bound each half
(CHG-20261127-1610). Defaults preserve legacy 15:30/15:20-25 behaviour."""
import datetime as dt
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class EnvTimeHelper(unittest.TestCase):
    def test_env_time_parses_guards_and_defaults(self):
        import os
        from india_trader.core import env_time
        self.assertEqual(env_time("UNSET_X", dt.time(15, 30)), dt.time(15, 30))
        os.environ["T_X"] = "1215"
        try:
            self.assertEqual(env_time("T_X", dt.time(15, 30)), dt.time(12, 15))
        finally:
            os.environ.pop("T_X", None)
        for bad in ("1", "99", "2461", "abcd", "123"):
            os.environ["T_X"] = bad
            try:
                with self.assertRaises(ValueError):
                    env_time("T_X", dt.time(15, 30))
            finally:
                os.environ.pop("T_X", None)


class SidecarContract(unittest.TestCase):
    FILES = ["india_trader/advanced_forward.py",
             "india_trader/three_candle_live_sidecar.py",
             "india_trader/ema9_ema15_live_sidecar.py",
             "india_trader/ema9_v2_live_sidecar.py"]

    def test_each_worker_reads_session_end_and_flat_by(self):
        for rel in self.FILES:
            src = (ROOT / rel).read_text()
            with self.subTest(file=rel):
                self.assertIn("PAPER_SESSION_END", src)
                self.assertIn("PAPER_FLAT_BY", src)
                # the hard-coded 15:30 loop stop must be gone (now env-bounded)
                self.assertNotIn("time()<dt.time(15,30)", src)


if __name__ == "__main__":
    unittest.main()
