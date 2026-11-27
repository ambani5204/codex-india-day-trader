import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from deploy import cloud_paper_session as session

class TerminalProvenanceTests(unittest.TestCase):
    def test_terminal_cases(self):
        day = "2026-11-24"
        for stamp, trailing, expected in [
            (day+"T15:30:00+05:30", False, "COMPLETE"),
            (day+"T10:00:00+00:00", False, "COMPLETE"),
            (day+"T15:29:59+05:30", False, "FAILED_OR_INCOMPLETE"),
            (day+"T15:30:00", False, "FAILED_OR_INCOMPLETE"),
            ("2026-11-25T15:30:00+05:30", False, "FAILED_OR_INCOMPLETE"),
            (None, False, "FAILED_OR_INCOMPLETE"),
            (day+"T15:30:00+05:30", True, "FAILED_OR_INCOMPLETE"),
        ]:
            with self.subTest(stamp=stamp, trailing=trailing), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / (day+"_NIFTY_synthetic.jsonl")
                events = [{"event":"SESSION_SUMMARY","timestamp":stamp}]
                if trailing:
                    events.append({"event":"INDEX_SIGNAL"})
                path.write_text("\n".join(map(json.dumps, events)), encoding="utf-8")
                with patch.object(session, "JOURNALS", Path(folder)):
                    self.assertEqual(session.summarize(day,"NIFTY",0,"READY")["status"], expected)


class TerminalProvenanceEndAwareTests(unittest.TestCase):
    def test_session_certifies_against_recorded_end(self):
        day = "2026-11-24"
        cases = [
            # (stamp, session_end_ist, expected_status)
            (day+"T12:20:00+05:30", "12:20", "COMPLETE"),   # morning half, reached its end
            (day+"T12:19:59+05:30", "12:20", "FAILED_OR_INCOMPLETE"),  # ended early
            (day+"T15:20:00+05:30", "15:20", "COMPLETE"),   # afternoon half
            (day+"T15:20:00+05:30", None,    "FAILED_OR_INCOMPLETE"),  # legacy default 15:30 not reached
            (day+"T15:30:00+05:30", None,    "COMPLETE"),   # legacy full day
        ]
        for stamp, end, expected in cases:
            with self.subTest(stamp=stamp, end=end), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / (day+"_NIFTY_synthetic.jsonl")
                summary = {"event": "SESSION_SUMMARY", "timestamp": stamp}
                if end is not None:
                    summary["session_end_ist"] = end
                path.write_text(json.dumps(summary), encoding="utf-8")
                with patch.object(session, "JOURNALS", Path(folder)):
                    self.assertEqual(session.summarize(day, "NIFTY", 0, "READY")["status"], expected)


if __name__ == "__main__":
    unittest.main()
