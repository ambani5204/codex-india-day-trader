"""GitHub Contents API line-wraps Base64 journal payloads."""
import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from deploy import private_journal_restore as restore

class GitHubWrappedBase64Test(unittest.TestCase):
    def test_restore_line_wrapped_base64_and_reject_corruption(self):
        day="2026-11-17"
        name=day+"_NIFTY_ADVANCED_093142917559.jsonl"
        raw=b'{"event":"SESSION_START"}\n{"event":"INDEX_SIGNAL"}\n'
        encoded=base64.b64encode(raw).decode()
        wrapped=encoded[:24]+"\n"+encoded[24:48]+"\n"+encoded[48:]
        repo={"private":True,"full_name":restore.DEST}
        listing=[{"name":name,"type":"file","size":len(raw)}]
        def fake_call(path,token):
            if path.endswith("/"+restore.DEST):return repo
            if path.endswith("/"+day):return listing
            return {"content":wrapped,"encoding":"base64"}
        with tempfile.TemporaryDirectory() as temp,patch.object(restore,"SOURCE",Path(temp)),patch.object(restore,"call",side_effect=fake_call):
            self.assertEqual(restore.restore(day=day,token="test"),1)
            self.assertEqual((Path(temp)/name).read_bytes(),raw)
            self.assertEqual(restore.restore(day=day,token="test"),1)
            def bad_call(path,token):
                result=fake_call(path,token)
                return {"content":wrapped+"!","encoding":"base64"} if "contents/journals/"+day+"/"+name in path else result
            with patch.object(restore,"call",side_effect=bad_call):
                with self.assertRaises(ValueError):
                    restore.restore(day=day,token="test")
if __name__=="__main__":
    unittest.main()
