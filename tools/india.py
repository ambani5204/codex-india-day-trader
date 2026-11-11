#!/usr/bin/env python3
"""Thin Python entrypoint; invoked from the repository root."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from india_trader.cli import main
if __name__ == '__main__':raise SystemExit(main())
