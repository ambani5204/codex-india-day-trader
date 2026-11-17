"""Offline durability tests; no credentials or network access."""
import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from deploy import private_journal_restore as restore
from deploy.firebase_live_publisher import snapshot

class CancellationRecoveryTests(unittest.TestCase):
    def test_restore_idempotent_and_preserves_prior_signals(self):
        day="2026-11-17"
        name=day+"_NIFTY_ADVANCED_old.jsonl"
        event={"event":"INDEX_SIGNAL","strategy":"OPENING_RANGE_BREAKOUT",
               "timestamp":"2026-11-17T10:00:00+05:30","session":"old"}
        raw=(json.dumps(event)+"\n").encode()
        listing=[{"type":"file","name":name,"size":len(raw)}]
        def api(path, token):
            if path.endswith("/contents/journals/"+day): return listing
            if path.endswith("/"+name): return {"content":base64.b64encode(raw).decode()}
            return {"private":True,"full_name":restore.DEST}
        with tempfile.TemporaryDirectory() as d, patch.object(restore,"SOURCE",Path(d)), patch("deploy.private_journal_restore.call",side_effect=api), patch("deploy.firebase_live_publisher.JOURNALS",Path(d)):
            self.assertEqual(restore.restore(day,token="test"),1)
            self.assertEqual(restore.restore(day,token="test"),1)
            data=snapshot("NIFTY","RUNNING","new",day=day)
            self.assertEqual(data["signals_count"],1)
            self.assertEqual(data["closed_trades"],0)

    def test_reject_archive_conflict(self):
        day="2026-11-17"
        name=day+"_NIFTY_ADVANCED_old.jsonl"
        raw=b'{"event":"INDEX_SIGNAL"}\n'
        def api(path,token):
            if path.endswith("/contents/journals/"+day):
                return [{"type":"file","name":name,"size":len(raw)}]
            if path.endswith("/"+name):
                return {"content":base64.b64encode(raw).decode()}
            return {"private":True,"full_name":restore.DEST}
        with tempfile.TemporaryDirectory() as d, patch.object(restore,"SOURCE",Path(d)), patch("deploy.private_journal_restore.call",side_effect=api):
            (Path(d)/name).write_text('{"event":"DIFFERENT"}\n')
            with self.assertRaises(RuntimeError):
                restore.restore(day,token="test")

if __name__=="__main__":
    unittest.main()
