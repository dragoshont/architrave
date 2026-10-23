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
| REQ-05 | README documents the full capability set and leads with spec-driven development; manifests describe Architrave as spec-driven | `python3 scripts/test-delivery-focus.py` checks README and manifest wording; `bash scripts/check-manifests.sh` passes | lead | accepted | README Full capability set; test-delivery-focus manifest check PASS (0.20.0) |
| REQ-06 | Vendored third-party skills ship unchanged with licence files and README attribution | `bash scripts/check-manifests.sh` skill inventory; README "Third-party skills" table | lead | accepted | PR #19, check-manifests PASS 0.19.0 |

## Corrections

| ID | Type | Target | Change |
|---|---|---|---|
| C-01 | revise | REQ-01 | Owner, 2026-10-23: spec-driven applies to every non-trivial task, not only long programs |
| C-02 | add | REQ-05 | Owner, 2026-10-23: README must list the entire functionality set |

## Handoff

Next: released 0.20.0; open new REQ rows for the next owner request before work.
Failed approaches: treating spec-driven work as a long-program exception (0.17–0.18) repeated the drift that removed it in 0.11.1.
Verify: `python3 gates/gate_runner.py requirements` then `bash scripts/check-manifests.sh`.
