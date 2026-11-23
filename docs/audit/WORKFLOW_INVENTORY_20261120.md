# Phase 0 — GitHub Actions workflow inventory (source inspected 2026-11-20 IST)

**Master Prompt v2 §3:** inventory/triage only; no workflow deleted, disabled or rescheduled. Primary repository `main` tree `c1377288910b080ca11cb66e4ed0fcc7d8f2c0cb`. All **23** `.github/workflows/*.yml` files had their contents read through the GitHub connector. The prior initial audit's claim of 20 files was an incomplete count, corrected here. For scheduled workflows, UTC cron is converted to IST with +05:30 **without assuming GitHub triggers on time**.

| Workflow (YAML basename) | Trigger evidence | Disposition | Risk / rationale |
|---|---|---|---|
| `backfill-firestore-paper-history` | Manual dispatch | Keep / restricted | Writes historical Firestore; restore point and idempotent dry-run needed |
| `cloud-ce-pe-paper` | Weekdays UTC 03:30/03:45, 04:00/04:15/04:30/04:45, 05:00/05:15/05:30 + manual | Migrate after gate | UTC 03:30 = IST 09:00; 405-min transient runner; scheduled skips and late starts; no durable lease proof |
| `ema9-ema15-angle-365-once` | Manual | Archive candidate | One-shot researcher; preserve artifacts and dependencies |
| `ema9-ema15-live-paper` | Manual | Refactor | Separate 359-min paper workflow, overlapping market owner risk |
| `ema9-ema15-nightly` | Weekdays 17:20 UTC = 22:50 IST + manual | Keep pending evidence | Historical/cost research; quota and calendar checks |
| `ema9-ema15-robustness-v2-once` | Manual | Archive candidate | One-shot output retention |
| `ema9-fib-one-year-backtest` | Manual | Keep research | Must keep index-only results marked proxy |
| `ema9-fib-v2-daily-tracks` | Weekdays 17:30 UTC = 23:00 IST + manual | Refactor | Parallel scheduled research; duplicate data pulls possible |
| `ema9-v2-stock-backtest-once` | Manual | Archive candidate | Equity research outside options execution v1; no deletion without runtime proof |
| `firebase-firestore-smoke-test` | Push to diagnostic files / manual | Keep + test | Tests credentials and write/read/cleanup: **must verify safety and restore behavior before invoking** |
| `forex-execute` | Manual | Archive candidate | Non-option execution outside primary Indian-index-options v1 scope; no disabling yet |
| `nifty-rollover-backtest-once` | Manual | Archive candidate | One-shot research, lineage to keep |
| `nightly-ce-pe-audit` | Weekdays 17:30 UTC = 23:00 IST + manual | Keep | Public-safe event diagnostics; false zero on missing journals must be prevented |
| `nightly-index-strategy-research` | Weekdays 17:30 UTC = 23:00 IST + manual | Fix under isolated PR | Run 44639810153 failed from invalid JSON suffix in downstream merged paper/research report. Code repair exists on unmerged PR #18 |
| `nightly-strategy-evaluation` | Weekdays 17:40 UTC = 23:10 IST + manual | Keep with contract test | Firestore write; `paper_evaluations` absent from inspected client read rules |
| `orb-30m-comparison` | Manual | Keep research | Qualification requires real option prices and OOS |
| `orb-timeframe-rr-sweep` | Manual | Keep research | Manual 300-min job, cost cap/experiments tracking |
| `test` | Push / pull request per workflow source | Keep / extend | Python 3.10/3.11/3.12 syntax+offline tests, no broker credentials |
| `three-candle-live-paper` | Manual | Refactor | Separate 359-min market runner; needs ownership contract |
| `three-candle-nightly` | Weekdays 17:45 UTC = 23:15 IST + manual | Keep pending evidence | Separate 3-candle diagnostics/write collection |
| `three-candle-top-down-once` | Manual | Archive candidate | Historical one-off; do not hard delete |
| `three-candle-top-down-v2-once` | Manual | Archive candidate | Historical one-off; do not hard delete |
| `two-agent-intraday-research-once` | Manual | Archive candidate | Two-agent one-shot experiment; archive not destroy |

**Nonduplicated source count:** 23 workflow files. **One-shot-name candidates:** 7 (`*-once`). Some parallel research uses shared external data; similarity is not proof of duplication. **No files archived in Phase 0.** All inspected workflow files use version-tagged GitHub actions (e.g. checkout@v4, setup-python@v5, upload-artifact@v4), **not immutable commit SHA pinning**; SHA-pin audit and actions permissions matrix remain required. Check action token permissions before changes.

## Scheduling and operational evidence

- `cloud-ce-pe-paper` source crons 03:30/03:45 UTC and multiple retries through 05:30 UTC; 09:00–11:00 IST nominal trigger window. Gate itself uses 08:45–15:25 IST startup window. **Actual firing may drift**; do not equate cron with verified uptime.
- GitHub logs from runs [44524841092](https://github.com/ambani5204/codex-india-day-trader/actions/runs/44524841092) and [44538910622](https://github.com/ambani5204/codex-india-day-trader/actions/runs/44538910622) show 18:02 and 19:29 IST out-of-window skips respectively. Those gates behaved as designed; workflow success was not session success.
- [44639810153](https://github.com/ambani5204/codex-india-day-trader/actions/runs/44639810153) nightly research failed downstream JSON parsing, source-confirmed literal backslash-n report suffix. Fix validated in [44660439921](https://github.com/ambani5204/codex-india-day-trader/actions/runs/44660439921) but unmerged.
- Several extra scheduled/nightly jobs run after market close and may use API/data/CI minutes. **Actual minutes, Firestore quota, API-rate and resource costs: UNKNOWN**, since no org billing/quota evidence was returned by source inventory. No invented totals.

## Exit blockers

1. Active-run ID ↔ session journal ↔ persisted Firebase snapshot correlation for a full normal day, and a holiday simulation.
2. Calendar/cron delay and cancellation recovery harness (including long-running transient-worker failure) with exact output.
3. Privilege reduction and immutable action pinning after supply-chain test.
4. Resource/cost baseline measured from actual GitHub/Firestore access.
5. Record which one-shot jobs have active references before archiving; no hard deletes.

Change: audit-only `CHG-20261120-0013`; **no workflow modifications or execution**.
