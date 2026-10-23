# Architrave requirements

Source of truth for Architrave's own development (spec-driven, see
`agents/architrave.agent.md`). Code and test output outrank this file.

## Requirements

| ID | Requirement | Acceptance | Owner | Status | Evidence |
|---|---|---|---|---|---|
| REQ-01 | Spec-driven by default: non-trivial work starts from REQ rows with testable acceptance in the requirements file (config `requirements`, else `SPEC.md`) | `python3 scripts/test-delivery-focus.py` asserts the spec-first contract in agent, skills, stanza, rubric and policy | lead | accepted | test-delivery-focus.py PASS (0.20.0) |
| REQ-02 | Requirements gate validates table, acceptance, evidence, typed corrections and Handoff; `--claim` refuses duplicate lanes; `--done` decides completion; `SPEC.md` default; `checks`/`quality-gate` validate it | `python3 scripts/test-components.py` | lead | accepted | test-components.py 18 OK incl. gate hygiene (0.20.0) |
| REQ-03 | Runtime and native dispatch bind tasks to REQ ids, own claims, carry acceptance and corrections into kickoffs, and refuse Run completion until bound REQs are accepted | `python3 scripts/test-runtime-v2.py` and `python3 scripts/test-native-host.py` | req-runtime | accepted | test-runtime-v2 79 OK, test-native-host 55 OK, runtime SPEC.md fallback (0.20.0) |
| REQ-04 | Self-improving loop: executable-first lesson promotion, improvement proposals approved only with before/after evidence and a human, harness pruning review per model | `python3 scripts/test-improvement.py` | self-improve | accepted | test-improvement.py 20 OK (0.20.0) |
| REQ-05 | README documents the full capability set and leads with spec-driven development; manifests describe Architrave as spec-driven | `python3 scripts/test-delivery-focus.py` checks README and manifest wording; `python3 scripts/check_manifests.py` passes | lead | accepted | README Full capability set; test-delivery-focus manifest check PASS (0.20.0) |
| REQ-06 | Vendored third-party skills ship unchanged with licence files and README attribution | `python3 scripts/check_manifests.py` skill inventory; README "Third-party skills" table | lead | accepted | PR #19, check-manifests PASS 0.19.0 |
| REQ-07 | Requirement claims coordinate every worktree of one clone through the git common directory; conflicts name the holding checkout | `python3 scripts/test-runtime-v2.py` cross-worktree claim test | lead | accepted | test_requirements_claims_conflict_across_worktrees_of_one_clone PASS (0.20.1) |
| REQ-08 | REQ-bound native dispatch is exercised in a real Copilot session, not only fixtures | Live `architrave_native_dispatch` with `reqs` against `test-native-host.py --prepare-live` fixture returns a gated candidate | lead | accepted | 2026-10-23 live: dispatch reqs=[REQ-1] returned candidate (worker obeyed correction C-1, answered "42"); `architrave_native_gate test` PASS gate-test-77dfd7ba; second run on same REQ rejected REQ_CLAIM_CONFLICT |
| REQ-09 | Architrave is Python only: no shell entrypoints ship (vendored skill assets excepted); every gate, harness command, installer and test runs as `python <file>.py`; install/update have no legacy migrations | `python3 scripts/check_manifests.py` rejects tracked shell entrypoints; `python3 scripts/test_install_update.py` no-launcher and install/update safety tests | lead | accepted | 0.21.0 |
| REQ-10 | Reusable kickoff guidance closes only gaps in fresh multi-repo bootstrap, component ref/write identity, precursor evidence and scoped scheduled-automation retirement; reuse existing ownership, permission and E2E rules | `python3 scripts/test-delivery-focus.py` protects the new guidance; `python3 scripts/check_manifests.py`, quality-gate and requirements --done pass; one independent R2 rubric review PASS | kickoff-guidance | accepted | 2026-10-23: 20 new delivery-focus assertions fail before guidance and pass after; check_manifests.py PASS incl. 18 runtime suites; quality-gate PASS; independent host code-review R2 PASS, no findings |

## Corrections

| ID | Type | Target | Change |
|---|---|---|---|
| C-01 | revise | REQ-01 | Owner, 2026-10-23: spec-driven applies to every non-trivial task, not only long programs |
| C-02 | add | REQ-05 | Owner, 2026-10-23: README must list the entire functionality set |
| C-03 | add | REQ-10 | Owner, 2026-10-23: capture only missing generic lessons from an overlong kickoff in Architrave source, not installed caches or project-specific rules; preserve human grants, exclusive ownership, dirty work and host lifecycle; no versions, release or automatic merge |

## Handoff

Next: REQ-10 accepted on base 02c7218; open new REQ rows for the next owner request. No version change or release; hardening session confirmed no overlapping work.
Failed approaches: treating spec-driven work as a long-program exception (0.17–0.18) repeated the drift that removed it in 0.11.1.
Verify: `python3 gates/gate_runner.py requirements --done` then `python3 scripts/check_manifests.py`.
