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
