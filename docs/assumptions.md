# ALGOBANI — Phase 0 assumptions register

Source of truth: Master Prompt v2 §§0,3,17,20. These are low-risk, reversible decisions, not confirmed broker/Firestore facts.

| ID | Assumption / decision | Evidence / status | How to undo |
|---|---|---|---|
| ASM-001 | Work stays **paper-only**, with no live orders or risk expansion. | Master Prompt v2 explicit; baseline paper config `allow_live_orders=False`. Verified intent, not broker enforcement audit. | No change to undo; live mode needs critical owner approval |
| ASM-002 | NIFTY is app primary; SENSEX remains a configurable data source, never merged into NIFTY totals. | Owner requests and spec §2/§12. Actual updated NIFTY-first Android source exists only on unmerged draft PR #5. | Abandon draft PR #5, preserve raw data |
| ASM-003 | A workflow green check is not proof of a completed, reconciled market session. | Nov19 18:02/19:29 IST gate logs show correctly skipped sessions. | Retain distinct status contract; no relaxation |
| ASM-004 | Missing journal/day data = **unknown**, not 0 trades / ₹0 profit. | Private Nov20 audit explicitly says no archived journals and no valid zero-trade conclusion. | Correct only with authenticated complete archive evidence |
| ASM-005 | Source Firestore rules are **not necessarily deployed**; verify separately as authenticated owner/non-owner. | Repo rules lack `paper_evaluations` read grant; server service-account GET successfully read actual collection, which bypasses client rules. | Update claim after emulator + effective deployed rules proof |
| ASM-006 | Nov14 `paper_evaluations` without a matching eligible history record is an **unexplained orphan**, not proven corruption or a valid trading session. | Actual read-only Firestore 14/15 probe, incident #20; Saturday date. | Reclassify only with provenance/event history |
| ASM-007 | Private GitHub journal CI HTTP404 is an **access-scope failure candidate**, not evidence that the private repository doesn't exist. | Connector read succeeds; CI private GET 404, incident #21. | Record verified fine-grained CI permission result |
| ASM-008 | Verified source Git rollback tests do **not** restore Firestore or signed APK; no merges until actual rollback drill. | Unmerged draft PR #19, five synthetic rollback tests, empty manifest. | Conduct evidence-backed real code/config/schema/app drills, then update gate |
| ASM-009 | UI visualization-first skill is required but cannot hide incomplete financial KPIs or operational warnings. | Master Prompt priorities and owner screenshots. Source UI draft PR #5 only, no deployment. | Feature flags/abandon draft if false information risk |
| ASM-010 | **An expired Firestore paper-session lease is not permission to restart the market session.** Automatic takeover stays disabled until immutable private journal events, open positions, after-cost P&L and every downstream publisher are fenced and reconciled. | CHG-20261123-2336 isolated Firestore CAS prototype; in-memory contention tests only, never integrated or production-verified. Runner clock/server-time skew remains an explicit future gate. | Discard PR #62; no production behavior changed |

**Current phase:** Phase 0 ACTIVE / stop for integrity; Phase 1 NOT STARTED. No capital, leverage, order, strategy-qualification or loss threshold changes. Assumptions are optional for owner review; no critical asks.

