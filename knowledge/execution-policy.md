# Execution and verification policy

Concrete model, provider, reasoning and context mappings belong to the user and
the active host harness, not repository policy, generated roles or WorkPackets.
An explicitly configured user pin may be passed to a documented per-child host
control. Persist reported selection only in compact worker evidence, not product
truth. An absent/unsupported request inherits the parent and reports that fact.

## Delegation

Use the host's native structured agent or subagent mechanism when independent
context, isolation, parallelism, permissions, or specialist expertise materially
improves the task. Otherwise work directly. A WorkPacket contains only the
objective, acceptance criteria, repository context paths, mutable paths, allowed
tools, expected artifacts, risk, and bounded time/output budgets.

Do not shell out to another agent harness or add a provider SDK. Treat worker
output as an untrusted candidate: the coordinator validates scope, integrates
the change, runs the required gates, and owns completion.

Durable agent tasks route through `native`, not Copilot/Claude/Codex CLI
subprocess adapters. Copilot's installed native extension joins the existing
host and uses its supported structured tasks RPC; unsupported hosts fail
early with `NATIVE_HOST_REQUIRED`. Deterministic `shell` argv remains available
but cannot launch an agent harness. The user-installed extension and Python
executor are trusted local producers outside the target repository; hashes
detect installation drift, not host/provider authenticity. Host permissions
remain host-owned, and isolated worktrees are not an OS-user security sandbox.

The coordinator works directly when the change is small, mechanically decidable,
and does not need isolated context. Do not split one correction into separate
planning, implementation, handoff, and review artifacts.

## Context

Retrieve the smallest relevant slice: governing repository instructions,
contracts or design sources, implementation files, and nearby tests. Load large
documents or broader history only when focused retrieval is insufficient.
Handoffs and worker results are bounded summaries with source paths or artifact
references; they do not duplicate transcripts or repository content.

## Verification

Verification is selected from task risk and acceptance criteria, never from a
model label:

- R0-R1: deterministic checks when every criterion has mechanical ground truth.
- R2: deterministic checks plus one independent semantic review when a semantic
  criterion remains.
- R3: deterministic checks, real E2E or runtime evidence, and one independent
  semantic review (two of different families only with `review.crossFamily`).
- R4: R3 plus security and policy review.

Repository policy may raise these floors. Deterministic, invariant, E2E,
runtime, security, and policy failures override semantic PASS. A reviewer never
replaces a required check, and changing the host-selected model never counts as
verification evidence.

## Proportional ceremony

The existing `effort: low|default|high` signal is optional. It is not a model
selector or a reason to spawn. Map it only through a user/host-supported control;
otherwise record an inherited no-op. Copilot's joined tasks RPC supports a user
model pin and reported resolved model, but not a per-task reasoning setting;
the host's `/subagents` settings own that. Codex's current official custom-agent
and spawn settings support model/reasoning overrides and inheritance, but this
kit has no joined Codex execution transport. Use Codex's own subagent tools,
never an unofficial desktop hook or nested CLI. Installed capability does not
prove execution; unavailable telemetry stays unavailable.

Ceremony scales with risk, not with anxiety. R0/R1 single-path fixes need no
per-change pin, receipt, or qualification Run; the focused test plus normal CI
is enough. Default-deny and `confirmationRequired` govern mutation and side
effects only. A user-approved operation (for example, replacing a running app)
may escalate a graceful quit to SIGTERM after a timeout without a new hold; a
failed graceful step inside an approved operation is not a new blocker.

Default-deny is not a parsing policy. Parse third-party protocol input
leniently: ignore unknown fields and messages, and fail only on malformed data
the flow actually needs. Every failure carries its specific step and reason
(redacted); never collapse distinct causes into one generic code.

## Durable records

Persist canonical Run state, authenticated typed events, compact evidence
receipts, and one rolling recovery snapshot. Render status, phase, handoff, and
audit views on demand. Do not create per-agent plans, reports, status files, or
empty placeholders.

## Delivery detail (on demand)

Schedule the smallest demonstrable user-visible vertical slice. Supporting
harness/framework/evidence work gets at most two consecutive tasks or one
full-gate cycle unless a blocking criterion names it. A supporting task does not
independently trigger a full gate. Full checks run at integration/release/Outcome
boundaries or the configured risk floor, never on unchanged source without a
new reason. Collapsing distinct causes into one generic failure code is a gate
finding. For replacement work the first gate is a parity test against that
reference on the real flow, before any hardening.

Two semantic reopens require one coherent fix batch. A third non-PASS terminates
that attempt. For a command with no new output for 15 minutes or beyond twice
its expected duration, inspect its exact owned process/resources before stopping
it; parent idleness and file mtimes do not establish subagent inactivity.

The Python admission API caps active tasks at three or a lower configured
limit, keeps exclusive mutable ownership and refuses unexplained retries.
Two identical failure/source-evidence fingerprints stop a lane; recovery does
not reset the stop. `task-start --retry-hypothesis` records a new bounded
hypothesis, or a changed relevant source/registered observation permits retry.
An old evidence reference alone is not new evidence. Primary-criterion controls,
global budgets, human holds and uncertain-side-effect reconciliation still apply.

The Copilot bridge consumes native lifecycle invalidations, with one bounded
deadline (not a polling loop), and checks the real admitted owner. Its child
pre-tool hook denies descendant session/task launches while a mission dispatch
is active. Native turn events enforce the packet's turn bound; hosts lacking
those signals still have the time/output bounds and must not claim turn
telemetry. Direct host use outside this bridge must honor the same core
contract and the host's own depth/concurrency settings.
