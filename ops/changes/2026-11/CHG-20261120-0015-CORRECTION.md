# CHG-20261120-0015 — Pre-test source correction

- 2026-11-20 IST, recorded before editing reconciliation source. Initial read-only implementation `50344c8e6dc51a22d1742d736b4579075681488b` invokes `gh_get(token, "")` for the repo metadata check, but its own defensive URL validator requires a slash prefix. This would fail before any Firestore request.
- Planned single-line change: invoke `gh_get(token, "/")` to retrieve exact approved repo metadata while keeping restrictions and all methods GET-only. No production data mutation.
- Validation: offline unit tests and GitHub Actions job must pass; not a proven live reconciliation until CI completes.
- Rollback: abandon unmerged audit PR.
