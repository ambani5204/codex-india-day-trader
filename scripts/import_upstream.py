#!/usr/bin/env python3
"""Import unmodified upstream scripts under vendor/ from a separately cloned repo.

Does not modify installed Codex SKILL.md files, and never executes imported code.
"""
import argparse
import shutil
from pathlib import Path

SKILLS='scanner news entry exit timemachine risk budget broker alerts analyst pelosi'.split()

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',required=True,help='Directory where you cloned Jakeschincariol/day-trader-skill')
    a=p.parse_args()
    source=Path(a.source).resolve()
    root=Path(__file__).resolve().parents[1]
    if not (source/'README.md').exists():p.error('Source path does not contain README.md')
    for skill in SKILLS:
        folder='trader-'+skill
        src=source/folder
        if not (src/'SKILL.md').is_file():p.error('Missing '+str(src/'SKILL.md'))
        dst=root/'vendor'/'upstream'/folder
        shutil.copytree(src,dst,dirs_exist_ok=True)
        print('Imported original Claude skill and scripts:',folder)
    for name in ('LICENSE','LICENSE.md'):
        f=source/name
        if f.exists():
            d=root/'vendor'/'upstream';d.mkdir(parents=True,exist_ok=True)
            shutil.copy2(f,d/f.name)
    print('Original source retained under vendor/upstream/. Indian skills remain .agents/skills/.')
    print('Upstream US scripts require their original runtime/paths; see upstream README.')
if __name__=='__main__':main()
