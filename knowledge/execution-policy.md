# Execution and verification policy

Concrete model, provider, reasoning and context mappings belong to the user and
the active host harness, not repository policy, generated roles or WorkPackets.
An explicitly configured user pin may be passed to a documented per-child host
control. Persist reported selection only in compact worker evidence, not product
truth. An absent/unsupported request inherits the parent and reports that fact.

## Delegation

Before a non-trivial multi-part task, identify independent deliverables and
whether they can advance concurrently without shared mutable files or a
dependency between them. When the host exposes sidebar-session creation, prefer
coordinated, visible sessions for independent implementation tracks or work
needing its own persistent follow-up/worktree. Create one bounded session per
deliverable, with exclusive mutable ownership, and integrate and verify the
results in the parent. This makes useful parallel work visible instead of
silently serializing it or hiding it in an ephemeral subagent.

Work directly for one continuous trace, a shared patch, or when coordination
costs more than the parallelism saves. Use a native subagent for short,
isolated research/review when creating a persistent sidebar session would add
needless lifecycle overhead. Never delegate solely to switch models or because
a role exists. If sidebar-session creation is unavailable, use another
supported host-native mechanism only when it preserves ownership, depth and
budget bounds; otherwise continue directly and state the limitation. In
Claude Code or Copilot CLI, when no sidebar-session API is exposed, use the
client's native agent/subagent tool for a bounded independent packet if
available. Do not assume a CLI exposes the app's sidebar-session controls, and
never shell out to create or manage sessions.

An explicit request for a named agent overrides the direct-work default. Invoke
that role through the supported host agent tool; if unavailable, report the
limitation rather than silently substituting an inline skill. Name actual host
ownership when reporting delegation; loading instructions is not agent execution.

For mutable children, select the project explicitly when the parent is a chat
or the destination differs from its project. Before any child write, compare
the host-returned repository/workspace and intended branch/base with the
assignment. If host metadata is insufficient, require a read-only child
preflight of cwd, repository identity and branch. Isolated child branches may
differ by design; verify their intended base, not identical branch names.
A mismatch or unavailable identity stops that child's mutation, not unrelated
authorized work. Correct the destination through supported host controls.
Never retry permission-denied operations unchanged or spawn replacements with
the same unavailable authorization; preserve the human hold and report the
exact host blocker. These are launch checks, not new receipts or report files.

A short native child assignment needs only an objective, owned scope, relevant
context and expected result. Use host limits; do not invent per-child budget,
receipt or planning fields for a brief lookup. Return the answer or change,
actual checks and any blocker, not a transcript or a mandatory status form.
For persistent implementation, external effects or expensive experiments, add
explicit acceptance checks, permission boundaries, finite budgets and recovery
detail as needed. Durable WorkPackets still obey their existing schema and
admission checks; this shorter prompt contract does not relax that API.

Keep reusable workflow, verification and permission rules in Architrave; a
project kickoff chiefly supplies the objective, requirements entry point,
component refs and project-specific decisions, not a copy of the agent contract.
The kickoff names only guidance actually needed for the task, using resolvable
skills or verified source paths and repository instructions; parent skill
context is not assumed inherited. Supply verified absolute paths when the host
needs them, not as a ritual for every lookup. Use existing context paths, not a new
WorkPacket schema or host-specific preload field. Bounded development, research
and writing use `architrave-work` with the assigned mode; independent rubric
review and competing-option tasks use the existing review/tournament skills.
The child invokes named skills if its host exposes a loader, otherwise reads
the supplied verified files. It reports invocation vs direct-read provenance
only when load evidence is required. Missing guidance is an explicit limitation, not a guessed cache
path or an excuse to reinstall. Skills change neither role scope nor permission.
Writing context includes audience, format and author-provided example paths.

This portable handoff avoids assuming one client's frontmatter in another:
[Claude subagents](https://code.claude.com/docs/en/sub-agents) support a `skills`
preload field, while [Copilot custom agents](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/create-custom-agents-for-cli)
have their own context/instruction controls. Use host-supported facilities only;
do not preload every skill or spawn a supervisor inside a worker.

Do not shell out to another agent harness or add a provider SDK. Treat worker
output as an untrusted candidate: the coordinator validates scope, integrates
the change, runs the required gates, and owns completion.

Durable agent tasks route through `native`, not Copilot/Claude/Codex CLI
subprocess adapters. Copilot's installed native extension joins the existing
host and uses its supported structured tasks RPC. `harness/opencode_host.py`
drives an already-running local `opencode serve` through its session API with
the same native ticket; it never answers OpenCode permission prompts. Other
hosts fail early with `NATIVE_HOST_REQUIRED`. Deterministic `shell` argv remains available
but cannot launch an agent harness. The user-installed extension and Python
executor are trusted local producers outside the target repository; hashes
detect installation drift, not host/provider authenticity. Host permissions
remain host-owned, and isolated worktrees are not an OS-user security sandbox.

The coordinator works directly when the change is small, mechanically decidable,
and does not need isolated context. Do not split one correction into separate
planning, implementation, handoff, and review artifacts.

## Context

Establish the mandate quickly: outcome, permitted scope, explicit holds and
completion evidence. Continue authorized dependency-ready work after
intermediate results; status reporting is not completion or a phase-approval
gate. Feedback and unknowns during implementation justify focused research
and bounded experiments in the existing scope. Revise the plan from the new
evidence and continue. Before declaring a blocker, try reasonable supported
alternatives; repeated-failure stops, human consent, ownership and safety still
apply. "By any means" never authorizes bypassing these boundaries.

Retrieve the smallest relevant slice: governing repository instructions,
contracts or design sources, implementation files, and nearby tests. Load large
documents or broader history only when focused retrieval is insufficient.
Handoffs and worker results are bounded summaries with source paths or artifact
references; they do not duplicate transcripts or repository content.

State that must survive a session, worktree or branch change lives in the
committed requirements file on the coordinator's branch, not in git-ignored,
worktree-local scratch (SDD `progress.md`, canvases, session notes). Before
rotating, commit Handoff and pass `python gates/gate_runner.py requirements
--handoff`; it fails on uncommitted requirements or newer progress stranded in
this checkout's SDD ledger and warns about one in a sibling worktree. Start the
successor from that commit, have it run `--handoff --expect <predecessor-sha>` first and fold any warned
ledger into the same file; never start a second ledger. The predecessor names
the successor, commit and open REQs once, then stops relaying; that hand-off is
not a completion claim.

For a fresh multi-repo session, bootstrap from the repository requirements,
correction rows and Handoff, not the old kickoff transcript. Verify current
refs and acceptance evidence before dispatching dependency-ready bounded work
under the existing claim/ownership rules. Historical source refs and old audit
claims are not fresh runtime evidence; retain them as provenance and reobserve
the actual target when current runtime acceptance is required. This grants no
new runtime permissions.

Use the existing `components` map and requirements/Handoff for component
identity, not a parallel inventory. Alongside the canonical `repo`, record its
execution role (which side/process runs it), working branch/base when non-default,
and safe write remote. Verify these against the checkout, including its
effective push remote and every push URL, using the existing components gate
where configured. Do not assume the default branch contains rescued work or
that `origin` is safe for private changes. Resolve rename redirects and confirm
the current canonical repository identity before destructive GitHub operations;
an unresolved mismatch blocks that operation, not a reason to guess or rewrite
remotes. Preserve dirty work and other owners' branches.

Distinguish a known-working precursor/lab/handwritten path from the intended
generated/product path in the requirements/Handoff. Evidence identifies the
source ref/artifact and entry point that actually ran; success on the precursor
does not accept its replacement. Preserve the proven baseline until replacement
passes the real-flow parity check in Delivery detail below.

Within the mandate and host permissions, disable only the assigned scheduled
automation when its work is accepted, superseded or its owner is archived,
after checking current requirements and host ownership. Do not infer retirement
from silence or cancel ongoing work merely because an owner is idle. Do not
restart retired monitor loops without a new mandate. Preserve source and
evidence; retirement is not permission for broad cleanup, archiving sessions
or stopping unrelated processes. If host controls or authorization are
unavailable, report the blocker instead of bypassing host lifecycle restrictions.

## Spec first, then the product path

The repository requirements file (config `requirements`, else `SPEC.md`) is the
source of truth. Turn the user request or existing product contract into short
REQ rows with testable acceptance there, then build the first useful
end-to-end product slice that satisfies them. Begin implementation as soon as
the REQs and their real blockers are known; the spec is a few table rows, not a
document phase, and needs no separate evidence receipt per requirement beyond
the row's Evidence cell.
Once scope is frozen, stop adding planning documents. Map the contract directly
to code and test owners in the existing task graph; revise it only for a real
scope change or newly observed blocker.

Keep the live task graph small: group work by implementation owner and actual
dependencies, and add a task only when it builds, tests, integrates, or unblocks
the requested behavior. If a document, schema or fixture is the requested
deliverable, build and verify it directly; it is product work, not ceremony.
Otherwise do not create a standalone task for an artifact; include
necessary schema, fixture, or evidence work with the implementation or check it
serves. A plan, ledger row, or passing unit suite is useful when it answers a
product or release question; its existence or count is not product progress.
Keep required safety, contract, release, and real-target evidence, but do not
turn each evidence item into a separate implementation phase by default.

At progress updates, lead with the behavior now available, the evidence that
shows it, and the next product blocker. If product behavior has not changed,
say so plainly; do not use document, task, test, or artifact counts as a proxy.

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

### Authorized action

Choose the smallest useful action within the existing mandate. Name the source
of a mandatory hold: an actual host permission, scoped Run policy/checkpoint,
legal consent, explicit owner hold or destructive-operation boundary. Missing
tool evidence is uncertainty to investigate, not policy denial. Agent-added
preferences are optional precautions, not new authority or vetoes.
Dedicated experimental hosts make optional safeguards proportional to the
bounded experiment; they do not authorize unrelated/destructive changes.
When the owner accepts proceeding without an optional fresh VM snapshot,
continue the authorized install and state the recovery limitation once.
Required Run checkpoints, host controls and legal consent remain mandatory.

Creating an authorized checkpoint cannot require evidence that it already exists.
Record the actual pre-action state in the required Run checkpoint, execute the
authorized operation, then verify its result. A Run recovery record, screenshot
capture and VM snapshot are different objects; none proves the other. Do not
invent a fresh backup requirement or shut down a running VM merely to satisfy
a preferred snapshot method. A shutdown/cold-create needs coverage in the mandate.

For desktop work, discover available supported target-only controls and use the
existing exclusive input owner to expose/navigate the target window before
asking for routine clicks. CTO steers that executor; it never takes input itself.
Zero visible windows is not a permission denial. Missing UI evidence does not
block an independent supported CLI path. Preserve unrelated windows and running
VM state. If controls are unavailable or a prompt is genuinely human-only, give
one exact manual action and the observed limitation; do not retry blindly,
invent tool capability or bypass permissions.

Name the actual failing operation and its observed error. Reconcile a timed-out
mutation against live target state before retrying; a timeout may have committed
side effects. Unknown completion blocks a duplicate mutation, not independent
safe work. Try one bounded supported alternative when authorized and relevant
to the failure; unchanged inspection, approval, audit or status loops need one
concrete unblock or a specific genuine blocker, not another backup ceremony.

Report instruction sent, execution started, observed result and accepted outcome
as distinct stages. A screenshot proves only what is visible, not recovery
coverage or restored capability. Source/test success does not establish installed
or native behavior; disk installation does not refresh already-loaded sessions.
Correct an agent-added blocker yourself rather than waiting for the owner to
rediscover it. These rules reuse existing ownership, retry and evidence controls;
they add no per-task checklist, scheduler or receipt.

Use a tournament for material architecture/dependency decisions, migrations,
data-loss, security, infrastructure/runtime risk, recurring failures, or genuinely
ambiguous alternatives; it is not a prerequisite for routine bounded work.

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

For adopted work needing resumability or external operations, persist canonical
Run state, authenticated typed events, compact evidence
receipts, and one rolling recovery snapshot. Render status, phase, handoff, and
audit views on demand. Do not create per-agent plans, reports, status files, or
empty placeholders. Ordinary direct source work needs no qualification Run or
separate acceptance matrix. Required deployment grants, checkpoints, receipts,
release evidence and recovery are unchanged; unavailable support cannot waive
them.

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
that attempt. A Run with a declared primary criterion uses its event/path-based
stall signal; when status reports `STALLED_PRIMARY_CRITERION`, return to that
criterion's code path or ask the owner to replace the objective. It blocks task
starts not bound to that criterion and is not an idle timer. For a command with
no new output for 15 minutes or beyond twice its expected duration, inspect its
exact owned process/resources before stopping it; parent idleness and file
mtimes do not establish subagent inactivity.

The Python admission API caps active tasks at three or a lower configured
limit, keeps exclusive mutable ownership and refuses unexplained retries.
Two identical failure/source-evidence fingerprints stop a lane; recovery does
not reset the stop. `task-start --retry-hypothesis` records a new bounded
hypothesis, or a changed relevant source/registered observation permits retry.
An old evidence reference alone is not new evidence. Primary-criterion controls,
global budgets, human holds and uncertain-side-effect reconciliation still apply.

The Copilot bridge consumes native lifecycle invalidations, with one bounded
deadline (not a polling loop), and checks the real admitted owner. It registers
no tool-blocking hooks. Descendant limits are instructions and host-owned
settings, not interception of ordinary session/task tools.
Native turn events enforce the packet's turn bound; hosts lacking
those signals still have the time/output bounds and must not claim turn
telemetry. Direct host use outside this bridge must honor the same core
contract and the host's own depth/concurrency settings.
