"""CHG-20261123-A2-1457: destructive cleanup must fail before DELETE."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from deploy import phase0_backed_up_cleanup as c


class FakeSession:
    def __init__(self):
        self.deletes = []
    def delete(self, *args, **kwargs):
        self.deletes.append((args, kwargs))
        raise AssertionError("No DELETE permitted")


class CleanupAllowlistTests(unittest.TestCase):
    def test_unauthorized_duplicate_date_aborts_plan(self):
        with patch.object(c, "client", return_value=FakeSession()), \
             patch.object(c, "get_history", return_value=[{"market": "NIFTY", "date_ist": "2026-11-13"}]), \
             patch.object(c, "duplicate_history_keys", return_value=[("2026-11-13", "NIFTY")]):
            self.assertEqual(c.plan(), 4)

    def test_unauthorized_document_aborts_before_any_delete(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            backup = Path(tmp) / "backup.json"
            digest = Path(tmp) / "digest.txt"
            payload = {"project": c.PROJECT, "dates": ["2026-11-14"],
                       "records": {k: [] for k in c.COLLECTIONS}}
            payload["records"]["paper_evaluations"] = [{
                "name": c.BASE.removeprefix("https://firestore.googleapis.com/v1/") + "/paper_evaluations/2026-11-15",
                "updateTime": "2026-11-15T00:00:00Z"}]
            backup.write_text(json.dumps(payload))
            digest.write_text(hashlib.sha256(backup.read_bytes()).hexdigest())
            session = FakeSession()
            with patch.object(c, "BACKUP", backup), \
                 patch.object(c, "client", return_value=session):
                # The digest path is fixed in the implementation; run in a
                # temporary working directory to avoid touching repository files.
                import os
                cwd = os.getcwd()
                try:
                    os.chdir(tmp)
                    Path("phase0_cleanup_digest.txt").write_text(digest.read_text())
                    with self.assertRaises(RuntimeError):
                        c.apply()
                finally:
                    os.chdir(cwd)
            self.assertEqual(session.deletes, [])


if __name__ == "__main__":
    unittest.main()
