#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m unittest discover -s tests -v
printf '\nSkills installed locally in .agents/skills/; open this folder in Codex.\n'
printf 'Optional user-global install: cp -R .agents/skills/trader-* "$HOME/.agents/skills/"\n'
