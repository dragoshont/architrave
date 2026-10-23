# Program requirements

Owner-approved source of truth for a long program. It lives in a repository, never
in session scratch. Code and test output outrank this file; when they disagree,
fix the file or the code, then record a correction.

Statuses: `open`, `claimed`, `in-progress`, `blocked`, `accepted` (needs evidence),
`superseded`, `withdrawn` (both need a correction row).

## Requirements

| ID | Requirement | Acceptance | Owner | Status | Evidence |
|---|---|---|---|---|---|
| REQ-01 | Library lists owned titles | `make test-library` passes; owned count matches service | ui-lane | in-progress | |
| REQ-02 | Service reports ownership | `curl /owned` returns the owner's titles | service-lane | accepted | commit abc1234, test log ci/123 |
| REQ-03 | Grid shows 4 columns | screenshot at 1440px | | superseded | |
| REQ-04 | Grid adapts to window width | resize 900→1800px keeps cards ≥ 220px | | open | |

## Corrections

Every owner change mid-flight lands here first (`add`, `revise`, `retract`, `supersede`).

| ID | Type | Target | Change |
|---|---|---|---|
| C-01 | supersede | REQ-03 → REQ-04 | Owner, 2026-10-23: fixed columns replaced by adaptive grid |

## Handoff

Next: REQ-01 fix the empty-state loop, then rerun `make test-library`.
Failed approaches: forcing a refresh on appear re-triggered the loop (reverted in def5678).
Verify: `python gates/gate_runner.py requirements` then `make test-library`.
