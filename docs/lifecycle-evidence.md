# Lifecycle acceptance evidence and limits

The supplied 11 November state/intent brief is the acceptance inventory. This
document records what the source checks exercise, not a production reliability
claim. Source baseline: `c50742b333d2b93c2582dfbdd67a009070ba64a3`.
The source is included in 1.1.0; package installation and loaded-context refresh
remain separate observations.

## Executable paths

`python scripts/test-lifecycle.py` executes the real `StateStore`, native locks,
atomic replacement, command transitions, CLI and existing program-board entrypoint.
It uses temporary local repositories/state. Concurrent writers are separate
spawned processes. Crash tests exit a process immediately before/after the real
replacement and reopen the snapshot. Simulated owner/host events and injected
crashes are explicitly evaluation-only.

| Brief cases | Exercised behavior |
| --- | --- |
| T05 | Two scoped decisions, one resolved; the other remains held across restart |
| T06–T08, T19, T31 | Stable entities, targeted correction/reorder, proposal/defer and dependency completion without activation |
| T09, T17 | Stop requested, acknowledgement and terminal observation differ; unknown ownership survives restart |
| T10–T14 | Late/duplicate results retained; relevant-input applicability; unchanged unrelated work; command dedup/conflicts; two writers, one stale rejection |
| T15 | Real process exit before/after atomic replace preserves old/new valid state with matching command receipt |
| T16 | Unknown external outcome blocks duplicate operation and needs explicit target-reconciliation observation |
| T18, T28, T34 | Restricted parser, duplicate/nonfinite/depth/schema rejection; escaped HTML; unsupported-edit digest detection |
| T24 | Persistent phase, scoped decisions, attempts, sources and next action recovered by new store instance and CLI context |
| T25–T27 | Fixed-input/time deterministic rendering; stale/stopped/error presentation and explicit unknowns |
| T29 | Deterministic tasks import, originals/mapping retained, no fabricated acceptance/ownership, dual-write rejection |
| T32 | Changing one criterion stales its proof while another criterion's proof remains current |
| T33 | Worker role cannot revise intent; unknown actor fields rejected; document source cannot support owner correction |
| T35 | Moved store remains readable; mutation requires location/owner reconciliation |
| T36 | Scoped context excludes unrelated goals/sources; source originals retrieved separately rather than replaying transcripts |

The integrated repair pass executes **48 lifecycle tests** and **15 operation-policy
tests**, plus **18 existing/extended board tests** (one opt-in browser-output skip).
The added adverse combinations freeze ownership across scope corrections, reject
unknown mutable scope, prevent old-candidate proof accepting a new candidate,
serialize different actions on one uncertain target, retain constraint/decision
history, and re-evaluate stale readiness. Older unbound records remain unavailable,
not silently qualified.

The policy tests use real migrated Runs, grants, checkpoints, receipts,
reconciliation and a local fixture operation through the existing runner.
They do not authorize or demonstrate a cloud deployment. A real generated
operation capsule is also validated against the shipped Run JSON Schema in the
full manifest suite; manual validation alone did not catch its initial schema
integration gap.

The equipped full suite on the integrated repair candidate returned the same
nine legibility errors as the original baseline, with no additional failing
suite; schema, capsule, installer, host/worker, legacy runtime and other manifest
checks completed. Final narrow read-only/readiness and legacy-scope admission
repairs were followed by the affected 48/15/18 suites above, guidance and quality
checks. That checkpoint's full suite was nonpassing; the release requalification
below is a separate, later result.

These are API regression cases, **not all behavioral criteria passed**. T01–T04,
T20–T23 and the semantic portions of T33 require evaluating an actual agent's
interpretation, research/clarification choices, test integrity and use of
retrieved material. A role restriction or source hash does not prove correct
understanding, human authenticity or prompt-injection immunity.

## Additional checks

Existing board, session-start/loop advisory, delivery-focus, installer and legacy
runtime suites remain relevant. Installer tests compare installed bytes,
including the new lifecycle API and guidance; they do not prove a running host
loaded them. The full manifest suite also requires `npx` for AJV and optional
Ruby frontmatter checks. Report missing tools as missing coverage, never as a
full-suite PASS or silently replace it with `--scan-only`.

The execution host initially exposed Python 3.9 but no `copilot`, `codex`, `node`
or `npx` on PATH. The first full run failed missing tooling/stdlib features.
An isolated Python 3.12 and checksum-verified official Node 22 distribution were
then provisioned in the session for qualification; no repository dependency or
global host configuration changed. The original source baseline was re-run in
a separate real git checkout with that same equipped environment. Its full
suite still failed **nine legibility trusted-executor observation cases**;
those failures and the unsuccessful initial runs are retained, not rewritten
as success. This is not a full-suite PASS.

Source tests and a real browser-canvas observation can
qualify their own paths only. T30 live plugin loading, native Windows execution,
live host interruption/resume, lost external replies and multi-machine handoff
still need separate supported-host observations.

Two independent final source reviews initially returned REVISE. Their supported
findings were routed to fresh bounded implementers, with parent integration and
affected-path rechecks. Initial review is not recorded as PASS by agreement or
by the implementer's passing tests.

## 1.1.0 release requalification

The complete manifest suite passes on macOS with Python 3.12 and Node 22,
including schema/role checks and the runtime/installer suites. The earlier nine
legibility errors were traced to fixture paths under macOS's symlinked `/var`
temporary directory. The fixture now creates its temporary directory using the
physical resolved parent; all 29 legibility cases pass. The production observer
still rejects linked/reparse ancestors. Earlier failures and baseline comparisons
were not rewritten as successes.

This full-suite result is not native Windows, live provider, loaded-session,
cross-host embedding, intervention-count or behavioral-benefit qualification.

## Corrective pass against 1.1.0

Reviewed baseline: `9ef899a87d51245bd09238e3700c3a548ee1fc70`. Three
temporary-store probes reproduced the owner-supplied counterexamples before
changes. This narrows F1 to missing consumed-output selection/binding, F2 to
qualification/presentation rather than refusing true integration, and F3 to
filesystem-dependent aliases rather than unconditional case folding.

The corrected lifecycle suite has **70 tests** (17 added); the affected existing
policy/dashboard/board suites have **15/29/18** cases respectively, with one
optional board skip. Commands:

```text
python scripts/test-lifecycle.py
python scripts/test-lifecycle-policy.py
python scripts/test-dashboard.py
python scripts/test-program-board.py
python gates/gate_runner.py quality-gate
python gates/gate_runner.py checks --quick
```

Added cases use actual transitions, restart/CLI/board and operation-capsule
admission. They cover selected replacement, equivalent and unselected output,
ordering-only work, transitive consumers, missing legacy bindings, comparable
conflict despite a selected pass, linked rerun history, separate environments,
idempotent reruns and observed integration without qualification. A real negative
process result is asserted as the expected outcome rather than copied as failure.

An independent source review found that integration recorded with no selected
checks had no late qualification-selection path. A fresh bounded repair added
optional `select_output.checks`: it selects current subject/environment proof
without recording another external integration or changing original
`integration_checks`. Three additional regressions exercise late linked reruns,
replay/conflicts, wrong/stale subjects and omitted failures. Prior failed reviews
and the stopped pre-repair full run remain distinct from final qualification.

The native temporary-store volume on this Mac is case-insensitive; simultaneous
case aliases and nonexistent case-alias targets are rejected there. Pure-policy
tests cover sensitive/insensitive/unknown comparisons; they are not native Linux
or Windows qualification. Empty/unavailable parent identity stays conservative.
Links are tested on this Mac; general hardlink/mount/race protection is not
claimed. The browser canvas timed out on scoped board navigation/read; generated
HTML and the real CLI/rendering tests are separate, not a claimed live panel view.

Synthetic identities/observations are explicitly evaluation data, not production
merges or permission evidence. No fewer-interventions, all-platform reliability
or live-provider qualification follows from these regressions.

## Required behavioral evaluation before benefit claims

Run matched baseline / revised-guidance / guidance-plus-state tasks using the
same host, model and budget, repeated with a held-out real-session-derived set.
Keep cases out of worker context. Preserve baseline failures and uncertainty.
Measure outcome correctness, preserved requirements, obsolete/unauthorized
actions, missed/repeated/unnecessary questions, response incorporation, valid
work retained, owner interventions, elapsed time and tokens.

Do not claim fewer interventions or improved understanding from passing these
fixtures. A convenient score cannot hide a critical scope violation. External
benchmark adaptations need release/license/judge verification and must not be
reported as official scores.
