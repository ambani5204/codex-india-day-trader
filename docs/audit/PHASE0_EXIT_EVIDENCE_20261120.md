# Phase 0 — Evidence ledger, risk register and exit decision

**Document basis:** directly inspected uploaded `Autonomous Algo Trading Platform: Agent Master Prompt (v2)`, §3, §17, §18, §20 and its Phase 0/1 table. **As of 2026-11-20 IST**. The phase table says Phase 0 deliverables: AUDIT.md, inventory, current test results, baseline metrics and risk register; exit evidence: test run output, list of failing tests, schema map. Phase 1 deliverable: PLAN.md with milestones/risks/rollback/assumptions; exit: reviewed against master prompt. Section 17 forbids advancing while predecessor exit evidence and corruption/ledger stop conditions are unresolved.

## Phase 0 evidence matrix

| Requirement | Evidence ID / exact outcome | Gate |
|---|---|---|
| Both repositories and actual code trees | Trading main `c1377288910b080ca11cb66e4ed0fcc7d8f2c0cb`; journals main `a610546612630605771a72b6269a5642d9821182`. Source tree fetched via authorized GitHub connector | **Verified** repository access |
| Python tests | [Run 44521553711](https://github.com/ambani5204/codex-india-day-trader/actions/runs/44521553711), SHA `3d33eecfecd8d9322887a03f6bbf6dac0dbda4e1`: Python 3.10/3.11/3.12 `Check syntax` and `Unit tests (offline, no broker keys)` steps success. More recent [run 44662172817](https://github.com/ambani5204/codex-india-day-trader/actions/runs/44662172817) tests source-rollback draft branch, not main. Local clone/test couldn't run because GitHub DNS unavailable in runtime. | **Verified CI steps**, local reproduction unverified |
| App build | [Run 44664178426](https://github.com/ambani5204/codex-trading-journals/actions/runs/44664178426), implementation head `2d7c907ab785493778522186f91a46b25d6defda`, debug build/upload success; ZIP artifact ID `14597925156`, 873,952 bytes. This is an *unmerged draft*, not signed release/device tested. | **Debug compile verified**; release unverified |
| Source rollback | [Run 44662024039](https://github.com/ambani5204/codex-india-day-trader/actions/runs/44662024039), head `1e7f493b73912735d515a6971f0c085ad25b6de0`; 3.10/3.11/3.12 tests passed; Python 3.11 183 tests, 5/5 isolated revert tests. Draft PR #19 unmerged, manifest empty. | **Local disposable-Git rollback verified**; actual code/app/DB rollback **unverified** |
| All workflow definitions | `WORKFLOW_INVENTORY_20261120.md`: 23 workflow files; triggers, dispositions, UTC→IST; 7 named `*-once` candidates; scheduling costs unavailable. | **Verified source inventory**, runtime coverage incomplete |
| Firestore field/collection schema | `FIRESTORE_SCHEMA_SOURCE_MAP_20261120.md`: producer/consumer/rules/typed fields for core/nightly; specialized sidecars partially mapped. Reviewed rules contain no `paper_evaluations` permission. | **Source-level partial**; real deployed DB/rules **unknown** |
| Archived event baseline | Private 12 JSONL archives Nov 13–19; 3 `SESSION_SUMMARY`, 9 no-summary, 4 start-only, 3 numeric closed paper trades totaling `−₹2,786.18`. Nov 20 private report explicitly says **no journals archived, no zero-trade conclusion valid**. | **Archive observed**, production reconciliation **blocked** |
| Late scheduler outcomes | Cloud runs 44524841092 and 44538910622 logs prove 18:02/19:29 IST out-of-window skips, not session success/failure. | **Verified**, holiday, startup coverage and cancellation **unverified** |
| KPI aggregation | Audit PR #16: 31-trade synthetic regression shows strategy_stats last-30 truncation while overall aggregates all. Test is `expectedFailure`, not repaired. | **Known defect**, release blocker |
| Nightly JSON error | Run 44639810153 failed `JSONDecodeError`; fix PR #18 tested [44660439921](https://github.com/ambani5204/codex-india-day-trader/actions/runs/44660439921), unmerged. | **Fix tested in PR**, deployed outcome **unknown** |
| Secrets, permissions, action pinning | Owner-only source rules; service credentials referenced in CI secrets; `YOUR_FIREBASE_AUTH_UID` source placeholder; GitHub actions version tags not immutable SHA, observed read-only. No secret values inspected. | **Partial**, deployed IAM/rotation scope unknown |
| Data coverage | No exact real historical contract-backed NIFTY/SENSEX CE/PE timestamps, strikes, expiries, sessions, completeness metric or gap report returned. Mean Reversion V4 index proxy had 0 OOS trades; **PROXY RESEARCH, NOT OPTIONS P&L**. | **Unknown**, no strategy qualification |
| Resources | 23 workflow definitions; *actual GitHub minutes, Firestore quotas and option API consumption* not retrieved from billing/runtime. | **Unknown**; no fabricated amount |
| Backup and restore | Git source rollback test isolated; no proven Firestore snapshot/restore or signed Android release rollback. | **Open** |

## Explicit failures / evidence incidents, with no synthetic repairs

- **INC-P0-001 / P0 DATA INTEGRITY**: The 9 private journals without `SESSION_SUMMARY` include more than four start-only sessions; one Nov 16 journal contains a closed paper trade but no closing summary. Whether Firestore and all open positions agree is unknown. Preserve files. **Stop phase advancement** until per-session reconciliation or explicit documented exceptions with proof.
- **INC-P0-002 / P0 DATA INTEGRITY**: `strategy_stats` counts a subset (30 recent trades) while overall totals include all. Corrected display may suppress unsafe sums; server data remains inconsistent at 31+ trades. **Do not reduce 200 OOS/150 sessions or 40 forward-paper thresholds to force profit**.
- **INC-P0-003 / P1 SECURITY/CONTRACT**: Android requests `paper_evaluations` but reviewed rules lack allow-read. Deployed rules unknown; no blanket rule relaxation. Validate emulator and actual deployment.
- **INC-P0-004 / P1 RELIABILITY**: Historical workflow `44538910622` green although session step skipped at 19:29 IST; operational outcome must distinguish SKIPPED vs COMPLETE_RECONCILED. The gate's skip itself was correct.
- **INC-P0-005 / P1 RELIABILITY**: Nightly run 44639810153 failed invalid JSON report serialization. Fixed only on draft PR #18; do not call production recovered.
- **INC-P0-006 / P1 RELEASE**: Production source/config/schema/app rollback, signed Android and live data restore drills not proven. Draft Git rollback utility refuses unregistered IDs.
- **INC-P0-007 / P1 DATA COVERAGE**: Missing actual CE/PE historical contract data coverage. Zero-trade proxy research cannot qualify any strategy.

## Phase readiness and stop decision

**Phase 0 = ACTIVE / NOT EXIT QUALIFIED.** Audit documentation and CI evidence advanced, but full schema/Firestore reconciliation, session-root cause and tested production rollback are unresolved. A source-only map is not an actual database schema. **Phase 1 = NOT STARTED (gate blocked by §17).** Do not claim Phase 1 complete, launch production changes, raise risk or merge draft PRs.

**Safe non-blocking next actions:** (1) read-only Firestore history/rules evidence from an approved connected environment, (2) immutable ledger ↔ archived journals reconciliation with mismatches/incident IDs, (3) independent emulator tests, (4) real rollback drill for code/config/Firestore/Android release, (5) verify market calendar/holiday and cost/resources. After all exit criteria, produce Phase 1 `docs/PLAN.md` using exact milestones and architecture review (not premature implementation).

## User digest and rollback

Changes associated with this evidence package: `CHG-20261120-0013` on isolated unmerged branch. Undo before merge: close/abandon the draft PR. No runtime behavior changed. Post-merge `scripts/rollback --to CHG-20261120-0013` not available/registered; exact merged revert not tested, so merge remains blocked. Critical owner asks: 0.


## Subsequent live-evidence addendum — 2026-11-20 03:17 IST (supersedes older UNKNOWN entries above)

**Authenticated Firestore GET-only inspection VERIFIED** in [run 44665611987](https://github.com/ambani5204/codex-india-day-trader/actions/runs/44665611987). Six collections exhaustively scanned within bounded page cap (no next-page token): `paper_dashboard` 3 records /25 observed top-level fields; `paper_history` 8/25; `paper_evaluations` 7/18; `three_candle_paper` 8/16; `ema9_ema15_paper` 8/19; `three_candle_nightly` 8/6. Only field names/types were logged; no financial values or IDs. This upgrades deployed **collection/type existence** from unknown to verified, but **effective Android client rules and private journal parity remain unknown**.

**Actual Firestore internal financial consistency:** [run 44666732450](https://github.com/ambani5204/codex-india-day-trader/actions/runs/44666732450), exact code/tests head `d63c2745bf748956311f433b204d1d4ad75295d2`, nine synthetic tests PASS and **14/15** live check outcomes MATCH (7 market-day history self-consistency; 2 latest/history; 5 evaluation/history). One `paper_evaluations/2026-11-14` has **no corresponding eligible paper_history**; Nov 14 was Saturday. **P0 incident [#20](https://github.com/ambani5204/codex-india-day-trader/issues/20)**. An initially reported Nov19 warning was a false positive caused by treating a zero-trade SENSEX null P&L as incomplete; fixed with preregistered test correction and rerun. The remaining orphan record is not automatically deleted or overwritten.

**Private archive ↔ Firestore comparison was NOT performed:** [run 44666175016](https://github.com/ambani5204/codex-india-day-trader/actions/runs/44666175016) passed six offline tests but obtained `HTTP 404` at GitHub private repository metadata GET from CI. Authenticated in-chat GitHub connector can access it, but CI permission is a separate scope. **P0 incident [#21](https://github.com/ambani5204/codex-india-day-trader/issues/21)**. No trade/fee/identity reconciliation assertion is justified.

**Offline matrix:** [run 44666732355](https://github.com/ambani5204/codex-india-day-trader/actions/runs/44666732355), head `d63c2745bf748956311f433b204d1d4ad75295d2`, Python 3.10, 3.11, 3.12 syntax/unit steps successful. Python 3.11 log: `Ran 196 tests in 4.632s`, `OK`. Read-only invariant CI intentionally returns exit code 4 for an open integrity finding; do not misclassify that as passing production integrity.

**Revised gate decision (authoritative):** Phase 0 remains **NOT EXIT QUALIFIED** because private archive↔Firestore comparison, unexplained orphan evaluation, Android client security-rules check, real option data coverage and production code/config/schema/APK rollback drills are outstanding. Phase 1 remains **NOT STARTED** under §17 despite drafting Phase 1 *inputs*. Existing feature PRs remain unmerged; paper-only mode. No owner critical asks. Continue phase-gated automation.
