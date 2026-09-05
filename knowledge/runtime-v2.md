# Durable Runtime v2

Load this pack for non-trivial, multi-task, resumable, deployment-aware, or
runtime-verified work. The runtime is a local control plane, not a deployment
platform and not a workflow language for shell commands.

## Architecture decision

### Runtime language tournament

| Option | Strength | Cost | Decision |
|---|---|---|---|
| Python | Existing benchmark language, standard-library JSON/process/file locking, cross-platform, directly testable | Python 3 required for Run v2 | **Chosen** |
| TypeScript/Node | Strong JSON/tooling ecosystem | Adds package/runtime dependency and duplicates existing Python benchmark infrastructure | Rejected |
| Go | Excellent static binary/concurrency | New toolchain and substantially more code for the current local runtime | Rejected |
| Shell + PowerShell | Already used for small gates | Unsafe duplication for structured transitions, recovery, process control, and event integrity | Rejected |

Python contains all orchestration logic. Shell and PowerShell remain thin entry
surfaces for small deterministic gates and v1 compatibility.

### Storage tournament

| Option | Strength | Cost | Decision |
|---|---|---|---|
| JSON | Simple atomic snapshot | Weak append/audit semantics alone | Part of hybrid |
| JSONL | Append-only event history | Expensive canonical reconstruction and atomic multi-field transitions alone | Part of hybrid |
| SQLite | Transactions/query/concurrency | Adds migration/inspection complexity not justified by one-engineer local runs | Deferred |
| Hybrid JSON + JSONL | Atomic canonical state plus append-only audit | Two-phase reconciliation required | **Chosen** |

`run.json` is canonical state. `events.jsonl` is typed, HMAC-authenticated
hash-chained audit using local ignored `.architrave/runtime.key`. The Run anchors
the event cursor. A pending event in canonical state makes process
death between state write and event append recoverable and detects deletion,
reordering, or mutation.

## Files

```text
.architrave/runs/<run-id>/
  run.json                 canonical architrave.run.v2
  events.jsonl             typed HMAC-authenticated events
  summary.json             concise projection
  phase-ledger.md          TaskGraph projection, never an autonomy gate
  intake.md
  tournament.md
  recommended-plan.md
  deterministic-gates.md
  judge-pre.md
  judge-post.md
  runtime-observer.md
  workers/                 bounded redacted worker artifacts
  workspaces/              candidate status and patches
  legibility/              app/runtime evidence
  mutations/               receipts
```

Runs, isolated worktrees, and the authentication key are ignored by default.
Never put secrets, cookies, provider sessions, private keys, or hidden model
reasoning in these files.

## Run and Outcome

Top-level states are `CREATED`, `PLANNING`, `RUNNING`, `WAITING_EXTERNAL`,
`WAITING_RESOURCE`, `WAITING_WORKER`, `PAUSED`, `RECOVERING`, `VERIFYING`,
`COMPLETED`, `FAILED`, and `CANCELLED`.

The Outcome defines what product result must occur. The Acceptance Matrix owns
criterion scope, risk, verification type, evidence, blocking status, and one of
`UNTESTED`, `PASS`, `FAIL`, `BLOCKED_EXTERNAL`, or `NOT_APPLICABLE`. Completion
is derived from all blocking criteria, all tasks, policy, gates, external waits,
and real product/deployment evidence.

Evidence is registered by trusted executors, HMAC-attested with producer/kind/
path/digest metadata, and re-verified on every load. Deterministic, invariant,
legibility, mutation, semantic, security, and policy gates accept only their
matching producer classes. An arbitrary file or caller-selected gate name cannot
manufacture PASS.

## TaskGraph and WorkPackets

Tasks have explicit dependencies, mutable paths, worker profile, workspace,
risk, criterion references, artifacts, gate, retry/checkpoint policy, attempts,
lease, bounded WorkPacket, and optional side-effect reconciliation state.

Only dependency-ready tasks become `READY`. Under `approved-program`, a passing
task automatically releases in-scope dependants. Under `current-task`, the Run
pauses at the next task boundary until resumed. Independent tasks may run in
parallel. Failed siblings do not destroy completed work.

Read-only tasks may share source. Concurrent mutating WorkPackets use detached
worktrees through `harness/workspaces.py`. Workers return candidates. The
coordinator validates scope, records the candidate patch, integrates it, runs
cross-slice gates, and completes the task.

A repository-wide resource lock checks active tasks across every Run before a
mutating task starts. Overlapping mutable scopes are serialized even when they
belong to different Runs.

## EventLog and checkpoints

Events include id, Run/task id, timestamp, type, actor, redacted payload,
evidence references, sequence, previous hash, and hash. Common types include
Run/task/worker/workspace/gate/artifact/external-wait/mutation/deployment events.

Canonical transitions use a local file lock, atomic `run.json` replacement, a
recoverable pending event, fsynced JSONL append, and cursor finalization. Events
do not store hidden reasoning.

Checkpoint around task/worker/gate completion, external waits, deployment
mutation, and side-effect ambiguity. Resume never replays an uncertain side
effect. Inspect the remote ref, live deployment version/digest, registry, or
other external truth first, then record reconciliation evidence.

Mutation receipts bind task, operation, target, intended and observed release
identity, apply/health result, and one reconciliation outcome. They are consumed
and re-attested exactly once. An applied receipt cannot prove `not-applied`; that
outcome needs its own observation-backed reconciliation receipt.

## Autonomy and policy

- `current-task`: conservative default; pauses before the next accepted unit.
- `approved-program`: the full Outcome/Acceptance Matrix is authorized; internal
  phase transitions do not require another prompt.
- `advisory-only`: no mutation.

Mutation policy always defaults to deny. Grants name exact scopes and operations.
An explicit user mandate may create a bounded deployment grant. Configuration,
tool access, worker output, or a phase label cannot escalate policy.

Operations in `confirmationRequired` still require a trusted resolution. Every
non-trivial mutation produces target/before/after/result/verification evidence.

## External checkpoints

Use typed checkpoints for `AUTH_REQUIRED`, `MFA_REQUIRED`, `CONSENT_REQUIRED`,
`SAFE_WRITE_TARGET_REQUIRED`, `SIGNING_REQUIRED`, and
`HUMAN_JUDGMENT_REQUIRED`. Record principal, provider, reason, task, and resume
task. Resolution requires the one-time challenge returned only to the trusted
caller; the Run persists only its hash. A worker cannot resolve one. Independent
READY tasks continue while one task waits.

## Worker adapters

`harness/worker_adapters.py` supports Copilot, Claude Code, Codex, and structured
shell argv. It bounds timeout/output, redacts artifacts, validates mutable paths,
protects canonical Run state, and normalizes candidate results. Native agent
sandboxes and tool permissioning remain defense layers; custom roles are not
security boundaries.

## Application and deployment legibility

`harness/legibility.py` wraps configured repo tooling for Web, Electron, iOS,
runtime, and deployment. Web needs health plus E2E/screenshot evidence. Electron
is verified distinctly. iOS needs build, install, launch, screenshot, and a
nonblank check. Deployment apply requires Run policy and verifies current state,
health, version, and digest while writing a mutation receipt.

## Evaluation

Risk controls cost:

- R0 deterministic;
- R1 deterministic, optional one judge;
- R2 deterministic plus one semantic judge;
- R3 deterministic, E2E/reality, GPT-family and Claude-family judges;
- R4 R3 plus security and policy review.

Repository `evaluation.riskPolicy` may tune this. Deterministic, invariant, E2E,
reality, security, and policy failures always override semantic PASS.

## CLI

```bash
python3 harness/architrave_runtime.py run --goal "..." --outcome "..." \
  --autonomy approved-program --criterion 'ID|description|scope|R3|reality'
python3 harness/architrave_runtime.py task-add <run-id> --id task-1 \
  --title "..." --objective "..." --criteria ID
python3 harness/architrave_runtime.py ready <run-id>
python3 harness/architrave_runtime.py resume <run-id>
python3 harness/architrave_runtime.py events <run-id>
python3 harness/architrave_runtime.py verify <run-id>
python3 harness/validate_run_v2.py .architrave/runs/<run-id>
```

Use `harness/workspaces.py`, `worker_adapters.py`, `invariant_engine.py`, and
`legibility.py --help` for their bounded interfaces.

## Future headless boundary

Keep the local runtime capable of a future transport adapter exposing
`startRun`, `getRun`, `streamEvents`, `resolveExternalCheckpoint`, and
`cancelRun`. Do not add a Tessera dependency, remote control plane, broker,
database service, or distributed consensus until benchmark evidence requires it.