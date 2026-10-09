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
  recovery.json            rolling last-known-good recovery snapshot
  workers/                 one compact redacted result per worker
  workspaces/              one candidate patch per mutable task
  legibility/              app/runtime evidence
  mutations/               receipts
```

Status, phase, handoff, and audit reports are rendered on demand from canonical
state and events. Runs do not create empty Markdown placeholders or duplicate
per-agent plans and reports.

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

## Focus and correction controls

### 0.14 factual visibility and owner correction

`status` distinguishes executing module fingerprint, copied kit stamp and
session-loaded instructions (UNKNOWN without supported host provenance).
`activeWorkers` is canonical-only. The joined extension observes this session's
tasks; it does not certify every app/chat idle. Unknown visibility does not block
cheap direct work or imply zero budget. Source drift labels the stall projection
stale rather than declaring a current product failure.

`milestone-advance RUN TASK --criterion ID --milestone "observed slice"
--gate gate:ID` consumes an existing product legibility observation bound to the
exact current task/criterion/objective/source. Control tests, coordinator files,
chat claims, wrong producer, stale source and duplicate substantive observations
cannot advance it. It does not set criterion PASS. Path/commit activity stays a
separate proxy; milestone-free churn requests bounded feasibility review, not an
automatic time-based halt. An unexpired bound lease suppresses idle/stall advice
while real scoped work is in flight. Intermediate exploratory milestones must
describe verified observable behavior, not each compatibility patch.

For outdated primary paths, the owning coordinator uses
`focus-correction-request RUN TASK --path PATH --principal OWNER --actor
human:OWNER --id CHECKPOINT`, then `focus-correction-apply RUN CHECKPOINT
--challenge VALUE --actor human:OWNER`. The one-use owner challenge binds
revision/task/objective/source and existing repository paths. Only primary paths
change. Budgets, attempts, side effects, baseline, candidates, acceptance and
auth/consent/product holds are preserved. Source/revision drift rejects it.
Objective strategy changes still use `objective-replace`; explicit accepted
baseline reconciliation uses `resume --accept-commit`, never a silent status fix.
Closed-resource observation uses trusted `reconcile-attest`. No cross-repository
path correction certifies another application's outcome.

At a safe boundary run the published installer `adoption-status TARGET`, then
`update --agents TARGET` only for authorized consumers. It preserves product
code/config/custom agents and ignored Run state; verify matching hashes and load
the updated skill in a new supported turn/session. A file update alone is not a
loaded-context receipt. Do not interrupt gameplay, authentication prompts or
user-paused work for harness adoption; report inactive/deferred/UNCONFIRMED
honestly and give a concrete safe handoff.

The current objective is versioned and singular. An explicit correction or
priority change replaces it, emits `objective.replaced`, marks prior nonterminal
tasks `DEFERRED`, releases their leases, fails their active workers, resets
lanes/target identity, and records the next cheapest acceptance test.
Old objective evidence remains in authenticated events; it cannot remain active.

Correction phrases such as “stay focused”, “you lost my ask”, “do not drift”,
“wrong target”, and “use the existing working implementation” are objective
reset signals. Status messages and cross-session evidence updates cannot replace
the objective without explicit user direction.

When a working baseline is identified, `reuseBaseline` must record its path,
registered test/diff evidence, and the exact difference being evaluated before a
replacement architecture or compatibility constraint can enter the TaskGraph.
`reuse-verify` executes the declared baseline test and binds its path digest and
difference. A replacement or port task records that baseline as its
`reference`; the first gate is a parity test against the reference on the real
flow, before any hardening. `objective-replace` requires a `HUMAN_JUDGMENT_REQUIRED` challenge;
`target-resolve` requires a `SAFE_WRITE_TARGET_REQUIRED` challenge bound to the
provider/principal. Neither flow accepts a repository-authored self-attestation.

At most two execution lanes are active by default (lanes are not children). The product lane cannot be
displaced by communications, unrelated research, or infrastructure; those
become deferred lanes until explicitly promoted.

Except for immediate R4 safety/security work, extensive diagnostics,
infrastructure, large refactors, and review are deferred until a minimal
acceptance slice is proven. Two review reopens without new product evidence
force one coherent fix batch before another review.

A Run may declare its failing user-visible criterion as
`focus.primaryCriterion` with repository code paths (`run --primary-criterion
ID --primary-path PATH` or `primary-set`). Status merges commits since the
declaration with later Run events into one timeline. A commit touching a
primary path, or a gate/criterion/task result bound to the criterion, resets the
streak; other commits and worker/task results extend it. At the threshold
(default 3) while the criterion is not PASS, status reports
`STALLED_PRIMARY_CRITERION` and `task-start` refuses tasks not bound to it.
`objective-replace` clears the declaration. Runs without it are unchanged.
The primary criterion must use `reality`, `e2e`, or `external` verification. It
passes only on a runtime-bound reality/e2e receipt (legibility, mutation, or
external-proof producer, created after Run start) or a resolved
`PRODUCT_OUTCOME_CONFIRMED` checkpoint; anything else raises
`PRIMARY_EVIDENCE_NOT_OBSERVED`. The loop cap counts failed attempts on the
criterion (task failures, failed workers, failed gates, observed FAIL) since its
last observed PASS or objective replacement; commits do not reset it. At the
threshold (default 3) status reports `PRIMARY_STALLED` with the best attempt and
caveats, and task-start refuses new work on that criterion.

Current reality/e2e PASS credit from legibility requires an authenticated
receipt bound to the current Run, objective, task (when present), criteria and
source commit/hash at admission and consumption. Legacy unbound product
receipts and gates remain readable as history, but cannot admit a new PASS,
set a current criterion to PASS or satisfy verification, including after
`resume --accept-commit`. Obtain a fresh bound observation; do not upgrade history.
Binding/source validation also applies to current failed observations so
verification can report a failed Run. Failed receipts never provide PASS
admission or consumption credit.
Failed legibility admission rechecks those bindings inside the Run transaction;
an earlier observation check cannot authorize evidence after source drift.
Canonical verification and the ribbon use the same source-current failure
classification. Stale failed receipts/gates remain historical, and their
criteria need fresh observation rather than forcing a corrected Run to FAILED.
Malformed or tampered evidence remains an error, not ordinary staleness.
Current authenticated policy-engine and security-review failures remain
governing when source coverage is unknown. Only explicit stale Run/objective
or source bindings on all their evidence can move them to history; missing
bindings never imply safety clearance.
Visual artifacts are retained once before freshness/pixel validation, and the
receipt references those exact validated bytes. Retention preserves the observed
source modification time; copying an old screenshot does not refresh its proof.

New Runs set `focus.pushbackRequired`: `task-start` refuses tasks without a
push-back verdict (`PUSHBACK_MISSING`) and never dispatches CUT/DEFER; status
lists them in `missingPushback`. Legacy Runs are flagged but not blocked. When
`evaluation.budget` sets limits, status reports real counters (Run transitions
as turns, commits since baseline, task starts as dispatches, minutes since
creation) and `BUDGET_80`/`BUDGET_100`, or `BUDGET_UNKNOWN` when history
diverged from the baseline. At 100% task-start refuses (`BUDGET_100`); gates and
status still run. Status and checkpoint add `OWNER_MESSAGE_LINT_FAIL` when
owner-facing text carries three or more full SHAs, PIDs, run IDs, or UUIDs.

Launch/test/install tasks require a verified target identity: provider/store,
artifact or executable, version/build, SHA-256, environment, workspace/prefix,
and acceptance target. Any mismatch pauses the Run and blocks task start.

## TaskGraph and WorkPackets

### On-demand feasibility reset

The CTO skill is the canonical reasoning procedure; the conductor only links
to it. Use `feasibility-record` after settling the actual host owner of the
implicated lane. It never cancels a host, starts a worker, closes human holds,
resets attempts or grants policy. Active lane leases require supported host
pause/cancellation and truthful candidate/recovery handling first.

The agent, not a hard-coded estimator, selects a finite window from uncertainty,
risk, dependency depth, known evidence, the next discriminating test's cost and
remaining task/parent/global budgets. Explicit owner ceiling/deadline wins.
Record CONTINUE/BOUNDED_GO/PIVOT/PARK, reported delta, failed hypotheses, blocker,
next step, uncertainty and revisit condition in the existing task. Native/shell
dispatch consumes the selected WorkPacket bounds; no extra report files.

```bash
python harness/architrave_runtime.py feasibility-record <run> <task> \
  --trigger user --decision BOUNDED_GO --seconds 120 --turns 8 --output-bytes 2000 \
  --rationale "One cheap test can distinguish the current mechanism." \
  --product-delta "Outcome not yet observed." --blocker "Cause remains unproven." \
  --next-step "Run the focused real-flow test." --revisit "New discriminating evidence." \
  --uncertainty "External dependency may still block." --owner-seconds 60
```

Time spent since initial task start is deducted. Actual reported child turns
and retained result/diagnostic bytes are deducted cumulatively across the reset
lane; admission binds the reduced output limit, including late cancelled results.
The reset lane admits one discriminating owner at a time, so parallel owners
cannot each spend the entire shared ceiling. Other lanes remain independent.
If a finished owner does not report turns, another dispatch is blocked with
unknown-budget diagnostics rather than assuming zero spend. The global turn
limit remains a separate Run-transition proxy, not model turns. Unsupported
host credit/generated-output/turn telemetry stays unknown. Explicit parent constraints
should be passed through the same owner-ceiling flags. The original deadline,
clock and authorized ceiling cannot be extended by a repeat decision. Only
substantive source/acceptance/dependency/hold/failure evidence permits re-estimation
inside that original window. Expiry projects a partial/PARK result with retained
evidence and blocks further dispatch; no daemon or automatic paid reviewer runs.
PIVOT/PARK pause the lane. New tasks/objective corrections still require their
usual authorization, policy, loop and evidence checks. Direct host work follows
the skill's identical finite-window contract without inventing a durable Run.

Tested agent-chosen examples (not automatic duration presets): a small known-path
check at 120 seconds / 8 turns / 2,000 retained bytes; an uncertain independent
dependency at 900 seconds / 20 turns / 6,000 bytes inside a larger task grant;
and a request narrowed by its owner to 45 seconds / 3 turns / 1,000 bytes.
An absolute owner deadline or smaller global remainder further narrows any
example. Atomic admission captures the effective grant before dispatch, so an
intervening completed owner cannot leave a ticket with stale larger headroom.

Tasks have explicit dependencies, mutable paths, worker profile, workspace,
risk, criterion references, artifacts, gate, retry/checkpoint policy, attempts,
lease, bounded WorkPacket, and optional side-effect reconciliation state.

Tasks also bind to objective version, lane, work kind, change kind, target
operations, and whether they are the minimal acceptance test. A task from a
superseded objective or deferred lane cannot start.

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

Historical side effects that have already closed use `reconcile-attest`. The
trusted executor enrollment binds the exact Run/task/operation/target, immutable
historical evidence path and digest, original process id, and one outcome:
`applied-closed` or `closed-unknown`. The public command accepts no caller
outcome or observed JSON, verifies the pinned evidence and that the original
process is absent, then atomically records and consumes the reconciliation
receipt. `closed-unknown` clears the resource ambiguity without claiming that
the original action occurred; both outcomes preserve a failed worker task as
failed and never replay the side effect.

## Autonomy and policy

- `current-task`: conservative default; pauses before the next accepted unit.
- `approved-program`: the full Outcome/Acceptance Matrix is authorized; internal
  phase transitions do not require another prompt.
- `advisory-only`: no mutation.

Mutation policy always defaults to deny. Grants name exact scopes and operations.
An explicit user mandate may create a bounded deployment grant. Configuration,
tool access, worker output, or a phase label cannot escalate policy.

An existing Run may add an exact grant or confirmation-required operation only
through `policy-amend-request` followed by `policy-amend`. The dedicated
`HUMAN_JUDGMENT_REQUIRED` checkpoint binds Run id, objective version, revision,
principal, provider, exact additive delta, reason, and one-time challenge.
Authorization is checked inside the transaction commit boundary with a
store-private capability. Any intervening transition, replay, actor/provider/
delta mismatch, cross-Run use, running mutation, or pending/uncertain side
effect fails closed. A released task becomes `READY`; actions are not replayed.
Default deny, autonomy, objective/outcome, task paths, and unrelated state are
not amendable through this transition.

Operations in `confirmationRequired` still require a trusted resolution. Every
non-trivial mutation produces target/before/after/result/verification evidence.

## External checkpoints

Use typed checkpoints for `AUTH_REQUIRED`, `MFA_REQUIRED`, `CONSENT_REQUIRED`,
`SAFE_WRITE_TARGET_REQUIRED`, `SIGNING_REQUIRED`, and
`HUMAN_JUDGMENT_REQUIRED`. Record principal, provider, reason, task, and resume
task. Resolution requires the one-time challenge returned only to the trusted
caller; the Run persists only its hash. A worker cannot resolve one. Independent
READY tasks continue while one task waits.

`SAFE_WRITE_TARGET_REQUIRED` has a public trusted producer path:
`target-attest`. The runtime reads `~/.architrave/executors.json`, rejects a
registry or adapter inside the target repository, verifies absolute Python and
adapter paths plus their SHA-256 pins, and invokes the observer with an argv
vector, a minimal environment, a non-repository working directory, bounded
input/output, and a timeout. The request binds Run, objective version, revision,
task, checkpoint, provider, principal, challenge hash, and intended identity.
The caller cannot supply observed JSON. The runtime validates the exact result
schema and identity, then atomically registers and consumes the external proof.
The bundled exact-target observer only hashes a declared regular file and checks
an exact existing-or-absent workspace; it never launches or mutates the target.
If an unconsumed target challenge is lost before task start,
`checkpoint-renew <run-id> <checkpoint-id> --actor human:<principal>` rotates
the challenge and target binding atomically. Renewal is limited to the same
pending target checkpoint while its task is still `WAITING_EXTERNAL`, has zero
attempts, and has no lease; terminal, started, superseded, policy, and other
checkpoint types fail closed. The prior challenge becomes invalid immediately.
For a target on another trusted host, the same observer has one fixed SSH relay
mode: an absolute pinned SSH client uses strict pinned `known_hosts`, a
relay-specific pinned copied identity under the user trust root,
batch/identities-only operation, an explicit pinned host-key alias, and isolated
remote Python. The pinned local
adapter streams a fixed Python 3.9-compatible launcher over stdin. The launcher
independently hashes the installed remote observer before loading it; no
self-reported adapter digest or caller-provided command is trusted. The bounded
request and result remain end-to-end; Run state and runtime keys never move
hosts.

## Worker adapters

Agent WorkPackets use `native`; deterministic executable argv uses `shell`.
Legacy Copilot/Claude/Codex task records remain readable, but the worker CLI
returns `NATIVE_HOST_REQUIRED` instead of spawning those agent CLIs. Shell argv
and configured recipes reject agent-CLI launch recipes.
Old config adapter names remain compatibility aliases for native transport,
not host/model selection; updates preserve user config and allow the new native
route without silently rewriting it. New configs use only `native` and `shell`.

On a supported Copilot host, explicitly install the minimal user-scope extension
with `python tools/install_update.py native-host-install`, then reload host
extensions. Its joined SDK session uses the actual `session.rpc.tasks`
start/list/sendMessage/cancel transport, with no provider/model override.
`architrave_native_dispatch` admits the canonical task, creates its isolated
worktree, and returns only a bounded candidate. An optional `owner_handle` is
an existing idle agent task in the same joined host session, not an app root
session ID. Its context is retained; results must belong to the delivered
WorkPacket. Other hosts fail visibly before admission; there is no shell fallback
or fake human-judgment checkpoint.

**Trust boundary:** the user installs the extension and pinned Python bridge
outside target repositories. The extension, not repository JSON or a claimed
actor, observes results over its existing host-owned RPC connection. A private
per-invocation pipe and process-local ticket bind Run/objective/revision/task/
WorkPacket/lease/host owner; replay, stale revisions, mismatched owners, scope
escape and history changes fail closed. Installation hashes detect local drift;
they do not authenticate a remote provider. This is not a sandbox against
malicious same-OS-user code. The host owns permissions and execution context;
the tasks RPC has no per-task cwd/sandbox parameter, so absolute isolated paths
and post-execution scope checks are defense layers, not an invented host sandbox.
Native workers cannot execute registered side effects.

`architrave_native_gate` / `gate-execute` executes the installed quick gate or
configured build/test through the trusted Python executor, or observes an exact
GitHub workflow Run for the current source commit. It records actual
command/exit/source identities, and registers a task/objective/risk-bound gate.
It accepts no claimed result. Candidate completion never sets criteria PASS;
the coordinator sets a criterion only using its matching verified gate, then
completes the task and derives Run completion. Source drift invalidates this
evidence. Existing unrelated evidence stays historical.

`worker-recover` closes expired/orphaned workers without replaying side effects.
An explicitly named failed, side-effect-free task may be released for a new
attempt, retaining prior attempts, results, events and workspaces. The native
extension can additionally withdraw only the known obsolete
`native-adapter-required` tooling wait, with its exact provider/reason/task
guards; it cannot resolve human sign-in, policy amendment or target checkpoints.
Repository baseline changes still require explicit `resume --accept-commit`.
`status` reports revision, source, freshness and active/historical/stale workers
on demand instead of generating continually stale prose.

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
- R3 deterministic, E2E/reality, and one independent semantic review (two
  different families only with `review.crossFamily`);
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
python3 harness/architrave_runtime.py primary-set <run-id> --criterion LOGIN-001 \
  --path Sources/Auth --threshold 5
python3 harness/architrave_runtime.py resume <run-id>
python3 harness/architrave_runtime.py policy-amend-request <run-id> \
  --id <checkpoint-id> --task-id <task-id> --principal <principal> \
  --provider <provider> --actor human:<principal> \
  --reason "..." --add-allow repository:edit
python3 harness/architrave_runtime.py policy-amend <run-id> <checkpoint-id> \
  --challenge <challenge> --principal <principal> --provider <provider> \
  --actor human:<principal> --add-allow repository:edit
python3 harness/architrave_runtime.py target-attest <run-id> \
  --checkpoint-id <checkpoint-id> --challenge <challenge> \
  --actor human:<principal>
python3 harness/architrave_runtime.py checkpoint-renew <run-id> <checkpoint-id> \
  --actor human:<principal>
python3 harness/architrave_runtime.py reconcile-attest <run-id> <task-id>
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