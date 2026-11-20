"""Offline regression for EMA9/15 silent zero-exit without a journal."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from india_trader import ema9_ema15_live_sidecar as sidecar

class TestEmaJournalContract(unittest.TestCase):
    def test_eligible_zero_exit_without_journal_is_failure(self):
        fixed = dt.datetime(2026, 11, 20, 10, 30, tzinfo=sidecar.IST)
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(sidecar, "OUT", Path(directory)), patch.object(sidecar, "run", return_value=None):
                with patch.object(sidecar.dt, "datetime") as clock:
                    clock.now.return_value = fixed
                    with self.assertRaisesRegex(RuntimeError, "EMA9_15_NO_JOURNAL"):
                        sidecar.main()
    def test_eligible_nonempty_journal_is_accepted(self):
        fixed = dt.datetime(2026, 11, 20, 10, 30, tzinfo=sidecar.IST)
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/"2026-11-20.jsonl").write_text('{"event":"SESSION_START"}\n')
            with patch.object(sidecar, "OUT", Path(directory)), patch.object(sidecar, "run", return_value=None):
                with patch.object(sidecar.dt, "datetime") as clock:
                    clock.now.return_value = fixed
                    sidecar.main()
    def test_outside_window_can_skip_without_journal(self):
        fixed = dt.datetime(2026, 11, 20, 15, 0, tzinfo=sidecar.IST)
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(sidecar, "OUT", Path(directory)), patch.object(sidecar, "run", return_value=None):
                with patch.object(sidecar.dt, "datetime") as clock:
                    clock.now.return_value = fixed
                    sidecar.main()

if __name__ == "__main__":
    unittest.main()
