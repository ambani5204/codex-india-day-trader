"""Loader for config/strategies.json (strategy-spec-dhansetu-v1).

Every strategy is individually switchable. `enabled` defaults to False and a
strategy stays OFF in a live paper session until it has been validated — this
module never flips a strategy on by itself. An env override
ALGOBANI_ENABLE_STRATEGIES="S2_supertrend_sma,S4_buffer_breakout" can enable
specific validated strategies for a session without editing the file; it can
only ENABLE, never silently change parameters. The resolved config (with the
values actually used) should be written into each session journal.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List

_DEFAULT_PATH = Path(__file__).resolve().parents[1] / "config" / "strategies.json"


class StrategyConfigError(ValueError):
    pass


def load(path: str = None) -> dict:
    p = Path(path) if path else _DEFAULT_PATH
    try:
        cfg = json.loads(p.read_text())
    except FileNotFoundError:
        raise StrategyConfigError(f"strategy config not found: {p}")
    except json.JSONDecodeError as exc:
        raise StrategyConfigError(f"invalid strategy config JSON: {exc}")
    _validate(cfg)
    _apply_env_enables(cfg)
    return cfg


def _validate(cfg: dict) -> None:
    if "strategies" not in cfg or not isinstance(cfg["strategies"], dict):
        raise StrategyConfigError("config needs a 'strategies' object")
    common = cfg.get("common", {})
    for key in ("square_off_ist", "no_new_entries_after_ist"):
        v = common.get(key, "")
        if not (isinstance(v, str) and len(v) == 4 and v.isdigit()):
            raise StrategyConfigError(f"common.{key} must be HHMM")
    for name, s in cfg["strategies"].items():
        if "enabled" not in s or not isinstance(s["enabled"], bool):
            raise StrategyConfigError(f"{name}: 'enabled' bool required")
        for mkt, r in s.get("risk", {}).items():
            for field in ("sl", "tp"):
                if field in r and not (isinstance(r[field], (int, float)) and r[field] > 0):
                    raise StrategyConfigError(f"{name}.risk.{mkt}.{field} must be > 0")


def _apply_env_enables(cfg: dict) -> None:
    raw = os.environ.get("ALGOBANI_ENABLE_STRATEGIES", "").strip()
    if not raw:
        return
    wanted = {x.strip() for x in raw.split(",") if x.strip()}
    unknown = wanted - set(cfg["strategies"])
    if unknown:
        raise StrategyConfigError(f"ALGOBANI_ENABLE_STRATEGIES names unknown strategies: {sorted(unknown)}")
    for name, s in cfg["strategies"].items():
        if name in wanted:
            s["enabled"] = True


def enabled_strategies(cfg: dict) -> List[str]:
    return [name for name, s in cfg["strategies"].items() if s.get("enabled")]


def strategy(cfg: dict, name: str) -> dict:
    try:
        return cfg["strategies"][name]
    except KeyError:
        raise StrategyConfigError(f"unknown strategy: {name}")
