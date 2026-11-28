"""Phase 7: versioned read-only API contract + read-only guarantee."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from india_trader import read_api


class ReadAPI(unittest.TestCase):
    def _journal(self, rows):
        d = Path(tempfile.mkdtemp())
        with (d / "2026-11-30_NIFTY_x.jsonl").open("w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        return str(d)

    def test_envelope_versioned_and_valid(self):
        d = self._journal([
            {"event": "SESSION_START", "session": "s", "market": "NIFTY", "capital": 15000, "mode": "p"},
            {"event": "OPTION_PAPER_CLOSED", "strategy": "EMA_9_15", "symbol": "X",
             "time": "2026-11-30T09:35:00+05:30", "entry_price": 100, "exit_price": 150, "net_pnl_inr": 3000},
            {"event": "SESSION_SUMMARY", "session": "s", "market": "NIFTY", "status": "COMPLETE", "summary": {}},
        ])
        env = read_api.get(d, "2026-11-30")
        self.assertEqual(env["api_version"], read_api.API_VERSION)
        self.assertEqual(read_api.validate(env), [])
        self.assertEqual(env["status"], "COMPLETE")

    def test_empty_is_valid_no_session(self):
        env = read_api.get(tempfile.mkdtemp(), "2026-11-30")
        self.assertEqual(read_api.validate(env), [])
        self.assertEqual(env["status"], "NO_SESSION")

    def test_validate_catches_bad_envelope(self):
        self.assertTrue(read_api.validate({"api_version": "999"}))

    def test_accessors(self):
        d = self._journal([
            {"event": "SESSION_START", "session": "s", "market": "N", "capital": 1, "mode": "p"},
            {"event": "OPTION_PAPER_CLOSED", "strategy": "S4_buffer_breakout", "symbol": "X",
             "time": "2026-11-30T10:00:00+05:30", "entry_price": 10, "exit_price": 20, "net_pnl_inr": 650},
        ])
        self.assertEqual(read_api.status(d), "RUNNING")
        self.assertAlmostEqual(read_api.day_pnl(d), 650.0)
        self.assertEqual(read_api.strategy_pnl(d), {"S4_buffer_breakout": 650.0})

    def test_is_read_only_no_files_created(self):
        d = self._journal([{"event": "SESSION_START", "session": "s", "market": "N", "capital": 1, "mode": "p"}])
        before = set(os.listdir(d))
        read_api.get(d)
        read_api.status(d)
        self.assertEqual(set(os.listdir(d)), before)  # no writes


if __name__ == "__main__":
    unittest.main()
