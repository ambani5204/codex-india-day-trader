"""Offline, isolated Git source rollback drill; does not touch any real repository."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "rollback"
ID = "CHG-20261120-9999"


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          text=True, capture_output=True).stdout.strip()


class GitRollbackGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        git(self.root, "init", "-q")
        git(self.root, "config", "user.name", "ALGOBANI rollback test")
        git(self.root, "config", "user.email", "rollback-test@invalid.example")
        self.file = self.root / "config.txt"
        self.file.write_text("safe baseline\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "baseline")
        self.file.write_text("proposed update\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "change under test")
        self.changed_commit = git(self.root, "rev-parse", "HEAD")
        manifest = self.root / "ops" / "rollback_manifest.json"
        manifest.parent.mkdir()
        manifest.write_text(json.dumps({"schema_version": 1, "changes": {
            ID: {"kind": "git-only", "commit": self.changed_commit}
        }}), encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "register rollback change")
        self.pre_rollback_head = git(self.root, "rev-parse", "HEAD")

    def run_rollback(self, change_id=ID):
        return subprocess.run([sys.executable, str(SCRIPT),
            "--repo", str(self.root), "--to", change_id], text=True,
            capture_output=True, check=False)

    def test_registered_source_change_reverts_and_keeps_restore_point(self):
        result = self.run_rollback()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.file.read_text(encoding="utf-8"), "safe baseline\n")
        self.assertEqual(git(self.root, "status", "--porcelain"), "")
        restore_branch = "restore-points/" + ID + "-" + self.pre_rollback_head[:12]
        self.assertEqual(git(self.root, "rev-parse", restore_branch), self.pre_rollback_head)
        self.assertNotEqual(git(self.root, "rev-parse", "HEAD"), self.pre_rollback_head)
        self.assertIn("NOT_RESTORED:", result.stdout)

    def test_unknown_change_fails_closed_without_mutation(self):
        result = self.run_rollback("CHG-20261120-8888")
        self.assertEqual(result.returncode, 2)
        self.assertIn("ROLLBACK_REFUSED", result.stderr)
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), self.pre_rollback_head)
        self.assertEqual(self.file.read_text(), "proposed update\n")

    def test_dirty_worktree_fails_closed_without_mutation(self):
        self.file.write_text("unsaved work\n", encoding="utf-8")
        result = self.run_rollback()
        self.assertEqual(result.returncode, 2)
        self.assertIn("Dirty worktree", result.stderr)
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), self.pre_rollback_head)
        self.assertEqual(self.file.read_text(), "unsaved work\n")

    def test_non_git_only_change_fails_closed(self):
        path = self.root / "ops" / "rollback_manifest.json"
        payload = json.loads(path.read_text())
        payload["changes"][ID]["kind"] = "database-migration"
        path.write_text(json.dumps(payload))
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "mark migration")
        result = self.run_rollback()
        self.assertEqual(result.returncode, 2)
        self.assertIn("not registered for source-only", result.stderr)

    def test_repeat_rollback_is_refused(self):
        self.assertEqual(self.run_rollback().returncode, 0)
        result = self.run_rollback()
        self.assertEqual(result.returncode, 2)
        self.assertIn("Restore point already exists", result.stderr)


if __name__ == "__main__":
    unittest.main()
