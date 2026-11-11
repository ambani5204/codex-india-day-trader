import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'tools'/'india.py'

class CliTests(unittest.TestCase):
    def test_cli_readonly_paper_block(self):
        with tempfile.TemporaryDirectory() as temp:
            work=Path(temp);(work/'trader').mkdir()
            (work/'trader'/'config.example.json').write_text((ROOT/'trader'/'config.example.json').read_text())
            (work/'trader'/'orders.json').write_text(json.dumps({'id':'PAPER-X1','symbol':'NSE:RELIANCE','side':'BUY','quantity':1,
                       'estimated_risk':10,'estimated_notional':100}))
            run=subprocess.run([sys.executable,str(SCRIPT),'broker','live'],cwd=work,capture_output=True,text=True)
            self.assertEqual(run.returncode,4)
            self.assertIn('NO live order',run.stdout)
            risk=subprocess.run([sys.executable,str(SCRIPT),'risk'],cwd=work,capture_output=True,text=True)
            self.assertEqual(risk.returncode,0,risk.stderr)
            paper=subprocess.run([sys.executable,str(SCRIPT),'broker','paper'],cwd=work,capture_output=True,text=True)
            self.assertEqual(paper.returncode,0,paper.stderr)
            paper2=subprocess.run([sys.executable,str(SCRIPT),'broker','paper'],cwd=work,capture_output=True,text=True)
            self.assertNotEqual(paper2.returncode,0)

if __name__=='__main__':unittest.main()
