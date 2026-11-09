# Delivery authenticity

The current task workflow uses `tasks.md`. The SPEC/REQ completion barrier is
retired; startup guidance and advisory loop detection remain. The commands below
are legacy explicit opt-in checks, not prerequisites to close an ordinary turn.
Retained pre-tool-use handlers leave old declarations untouched and return `{}`.

The owner's requested outcome is the acceptance target. Working UI, storage or
orchestration is not evidence that an unexecuted provider worked. A test-only
label, an earlier result or a narrower agent-written requirement cannot replace
that outcome.

## Small default, on-demand detail

The plugin's small session bootstrap points to the lead skill; it does not
inject every role or policy. Non-trivial work declares its REQs and original
owner references, starts one scoped program board and opens/reads the browser
canvas before implementation. Read-only questions and trivial edits do not
need this lifecycle. Assigned children follow their parent scope, not a second
supervisor.

The detailed rules live in `knowledge/execution-policy.md` and the review rubric.
New fixtures, fakes, mocks, stubs, canned/replayed provider results and
feature/integration flags require a specific owner request for their purpose
and scope, including new test-only substitutes. Existing regression tests and
safety controls stay intact. An explicitly requested official local emulator
and development-to-cloud endpoint/adapter selection are valid targets, not
permission to substitute application behavior. A fixture that arranges a real
test environment is different from a fabricated service result; uncertain
authorization stays unresolved.

## Declare the original task

From the repository root, using the installed kit's Python entrypoint:

```text
python <kit>/gates/gate_runner.py delivery-audit --prepare --repo <repo> --base <reviewed-commit> --session <host-session-uuid> --reqs <REQ-IDs> --request <original-owner-event-id> --source <source-or-dependency-path> --document <design-or-demo-doc>
```

Repeat `--request`, `--source`, `--document` and `--reference` as needed. A reference is an
original image/design file whose identity must survive the work. File
attachments on the referenced owner events are also bound automatically.
The host event must be an attributable original owner message, not an
agent-originated `user.message`, system notification or continuation reminder.
The host's standard image-attachment reminder is allowed only with an attached
image; the original owner message and attached file identities remain bound.
No private message contents are copied into source control.

New declarations require explicit repository-relative source/dependency paths.
Files and bounded directories are supported; directory contents include
nonignored tracked/untracked files and detect additions/deletions. Missing named
files have a bound absent identity, so their later creation changes the evidence.
Traversal, absolute paths, Git metadata and symlink/junction traversal are
rejected. Include all relevant implementation, dependency, build/lock/config and
contract paths; the checker does not infer a dependency graph. The selected
requirement contract, `architrave.config.json` (including absence), and contract
documents are always bound. The default contract document is README when present.
Do not select credential stores; use redacted effective-config evidence.

The report's `source_paths` is one shared boundary for all selected REQs, not a
per-REQ dependency map. A change anywhere in that boundary conservatively affects
every outcome. Only a newer-owner `--amend --source ...` can change the declared
boundary; repeated sources replace the list, so repeat every retained path.
The history preserves previous source/document scope, and final review must
check additions **and removals** against owner intent. A legacy report without
`source_paths` retains full-repository source/full-ledger-contract freshness;
it is never silently upgraded or narrowed. Unscoped audit scans remain repository-wide.

One session-owned `files/architrave-delivery.json` holds this task's evidence.
It is not a second task ledger: REQs and their statuses stay in the repository
requirements file. The report stores the original requirement/acceptance/
correction scope; changing a status or adding evidence does not change it.
Silently shrinking acceptance invalidates the report. Preserve the old intake
and use `--amend --request <new-owner-event-id>` when a task's scope changes.
An amendment requires a newer distinct original owner instruction and retains the
previous requirement scope/digest. It preserves expectations and observations
only for unchanged requirement/acceptance/correction contracts whose previously
captured shared source/document evidence is unchanged. Changed/new outcomes are
unclassified and need proof invoked after amendment capture (`proof_after`), not
merely after a possibly earlier owner message. `owner_anchors` retains each unchanged REQ's
original event cutoff rather than using the latest event for every outcome.
Adding reference assets also invalidates retained outcomes. Aggregate review
always clears; a retained observation is not renewed delivery acceptance. It does not
judge whether that instruction actually authorizes every proposed scope change;
the independent reviewer must compare them. Dropping REQs additionally requires
`--drop <exact-removed-IDs>`; the command prints dropped/changed scope alongside
the delivery digest. Refresh the board scope when REQs change; unchanged scope
retains its original board-owner timing anchor.
A verified, host-completed declaration is archived when `--prepare`
starts the next task; an unfinished declaration cannot be silently overwritten.

An owner can stop or withdraw a mis-scoped declaration with
`--withdraw --request <new-owner-event-id> --reason <verbatim-owner-quotation>`.
This preserves the old report and records a still-declared `withdrawn` state.
The quotation/reference must resolve; semantic interpretation remains an
owner/reviewer responsibility. This retires the session's declaration, not
someone else's repository requirements. A valid withdrawal permits an honest
task-ending response but never integration/delivery acceptance:
`requirements --done --delivery-session` and canonical Run completion reject it.
Do not delete the declaration to bypass a blocker.

For a genuine blocker, wait or bounded handoff that is **not delivery**, use:

```text
python <kit>/gates/gate_runner.py delivery-audit --pause blocked --repo <repo> --session <host-session-uuid> --reason "<one-line explanation>" --evidence <actual-local-file>
```

`--pause` accepts `blocked`, `waiting` or `handoff`; repeat `--evidence` as needed.
It preserves requirements and prior evidence, records `state: paused` and a
`terminal` object with reason, file identities, current source digest and timestamp,
and clears aggregate review. It grants no permissions and accepts no requirements.
Its exact printed summary is the only `task_complete` summary allowed for this
state. The hook checks source/owner/reference/evidence identities and summary
agreement, not the semantic truth of an arbitrary reason. Extra success claims,
missing summaries or stale evidence fail closed. Automated continuation does not
resume the declaration or create new owner authority. `--check` and
`requirements --done --delivery-session` still reject paused delivery.

Pause evidence binds each file's SHA256 when it is recorded, so pass an immutable saved
copy (for example under the session's `files/`), never a live kit or repository file that
later work may change. If any bound evidence file changes before the first host completion,
the exact summary is denied (`non-delivery inspection blocked: evidence identity changed`).
`--completion-summary`,
`--resume` and a second `--pause` cannot clear it, because `--pause` accepts only active
work and `--resume` needs the identities unchanged. The supported recovery is a newer
distinct owner message that addresses the paused scope, then `--amend --request <that
owner event id>`, a fresh `--pause` with a saved evidence copy, and the newly printed
summary. Do not edit the managed report, restore old bytes or withdraw from another
repository.

`--resume` explicitly resumes an unchanged paused scope as `prepared`, preserving
the terminal history. It is not new authorization or acceptance. Changed scope
requires newer-owner `--amend` (or a new `--prepare` when the prior terminal
identity remains valid); source drift while paused fails closed rather than
silently resuming. `--seal` cannot resume paused/withdrawn work.

Retrieve the currently eligible completion summary without re-pausing,
resuming or editing the report:

```text
python <kit>/gates/gate_runner.py delivery-audit --completion-summary --repo <declared-repository> --session <host-session-uuid>
```

Before the first host completion, the command validates the existing pause and
prints its exact non-delivery summary. Use its complete output as the
`task_complete` summary once. A coordinator's
host cwd can differ from the explicitly declared repository: for this exact
non-delivery termination only, the hook validates the declared repository and
its source/owner/evidence bindings rather than comparing it to the caller cwd.
Active declarations, wrong-session records, stale pauses and success summaries
remain blocked; explicit delivery checks still require the matching repository
and never accept a pause. Do not retry an unchanged denial, delete the report,
or resume stopped work in response to an automated completion reminder.

After an actual host completion event with that exact non-delivery summary,
ordinary nonempty read-only follow-up summaries are permitted. No magic
prefix is required. This closes the later turn, not the prior requirements:
the paused scope remains NOT DELIVERED.
Unrelated follow-ups may optionally use the legacy label
`Unrelated follow-up (prior scope remains NOT DELIVERED): `, and
`--completion-summary` returns a summary with that label, not
the consumed one-time termination summary. For a reviewed delivered scope
with actual host completion, it instead returns the eligible
`Read-only follow-up (no new delivery acceptance): ` summary.
These legacy labels remain available for compatibility, but are optional after
retirement. Both command outputs are checked against the completion-hook policy,
including recorded edits in the command's current and declared repositories.
The command does not print an admissible summary when those checks fail.
This hook-only retirement checks recorded edits in both the current and declared
repositories and rejects new repository edits. Follow-up summary text is not
delivery acceptance and cannot change the prior requirement status.
It does not revalidate mutable historical source merely to end an unrelated
turn, grant permissions for that turn, or resume the paused work. New repository
work requires a newer original owner event and `--prepare`; the prior report is
archived unchanged, not accepted or silently overwritten. No matching host event
means no retirement. Retirement still validates the immutable declaration's
repository, nonempty requirement/owner scope and terminal evidence identities;
it does not rehash mutable historical files. As with delivered read-only follow-ups, shell mutations and
the meaning of arbitrary prose cannot be inferred by this hook.

Previously reviewed delivered scopes likewise permit ordinary nonempty
follow-up summaries after a real host completion, even if the caller repository
changes. Retirement is checked before
caller-repository equality; active delivery and explicit delivery checks still
require that equality. Recorded post-completion edits in either repository
require a new owner-bound scope.

Set each `expected` entry to its actual outcome kind before implementation:

- `source`: a source/tooling behavior proved by the named check, not an installed
  service claim.
- `integration`: explicitly identify the requested entrypoint, provider and
  target. Local emulator and deployed cloud are distinct targets.
- `visual`: intended consumer/width, reference fidelity and component/content
  coverage; prose correctness remains separately reviewed.

The default is `unclassified`, which cannot pass. Record the successful browser
open/read tool-call IDs in `board`. Generation alone does not establish a shown
canvas. A host without the required local log/canvas capability must report that
limitation; it cannot invent a displayed panel. An unavailable board is explicit:
`unavailable: true`, `displayed: false`, a reason and a real failed canvas
`tool_error_call_id`. If the host exposes no canvas tool to call, use
`basis: host-tool-absent` and a precise `capability_observation` instead. That
absence is reviewer-judged through the report digest, not a machine-verified
capability claim. It does not satisfy any requested rendered/visual outcome.
Local event-log evidence is still required for this verifier.

The board read must follow the owner scope and precede the first recorded
repository edit (other than the REQ ledger), and in all cases precede sealing.
The timing check recognizes explicit file-edit tool events; arbitrary shell
mutations and undisclosed work are not inferred.

## Capture, inspect and review

```text
python <kit>/gates/gate_runner.py delivery-audit --seal --repo <repo> --session <host-session-uuid>
```

Preparation captures the intake source identity. After implementation changes,
seal the final source before invoking the fresh checks/provider observations
that will support delivery. Sealing freezes the current source inventory; it
does not declare completion.
The original resolved base commit and declared source-file hashes bind
the evidence, including unchanged dependencies. Unrelated shared-checkout work
does not invalidate a scoped declaration. Requirement status/evidence is
excluded from the source fingerprint; the selected semantic contract is bound
separately. Contract documents, references and effective configuration artifacts
have their own identities. Ignored runtime/credential stores are not scanned;
bind an explicitly selected redacted effective-config observation for integration
acceptance instead of exposing credentials.

Within explicit scope the scanner inspects all declared source/dependency files,
including unchanged files. Without explicit scope it inventories whole changed
files and nonignored untracked source,
including effective dotenv/INI settings, launchers and tests. `--all` deliberately
selects full-repository scanning for unscoped/legacy audits; it never broadens
an explicit source boundary. No selected directory is silently exempted as "test only".
Source candidates have stable digest-based IDs, fixed categories and locations,
not potentially sensitive matched values.

For each candidate, add a disposition in the same report: `purpose`,
`reachability`, `effective_state`, `reason`, and one of `existing`,
`not-substitute` or `owner-requested`. The latter also names a bound
`owner_event_id`. A source/doc word match is only a review lead; it cannot prove
permission or actual runtime wiring. Unknown, changed or undisposed candidates
block acceptance. Do not clear them by changing names or deleting tests.

Each requirement needs an `observations` entry with its kind, `outcome: passed`,
bounded `meaning`, a successful host `tool_call_id` and a `proof` file
identity (`path`, `sha256`). Integration observations additionally bind:

- matching expected entrypoint, provider and target;
- `enabled` and `provider_invoked` true;
- `result_mode: fresh`;
- the same nonempty `run_id`, `provider_run_id` and `result_run_id`;
- a selected effective-configuration file identity.

The cited successful tool result must contain that proof digest, and
come from this session or a child actually created in its host log. This is
artifact/observation linkage, not proof that arbitrary output is semantically
true; the reviewer must inspect what the tool did and what the result entails.

Visual observations require an actual consumer/positive width, rendered output,
reference comparison and coverage inspection. Source/XML validity and image
counts cannot fill those fields honestly.

The checks validate relationships and identities, not arbitrary provider
semantics. An independent reviewer must inspect the original owner messages,
references, actual tool/source/config/adapter observations and useful result.
Put the reviewer's session ID and the report digest in `review`; that reviewer's
actual PASS report must contain `Delivery digest: <sha256>` on its own line.
The digest covers every report field except `review`. Changed observations,
requirements or source require renewed review, not copying a prior PASS.
Sealing changed source, including the first seal after intake, clears old observations and records a `proof_after`
cutoff: copying a proof produced before that capture cannot accept the new
source. Re-observe the outcomes after capture. This deliberately favors a fresh
run over guessing which prior integration result covered changed implementation.
For legacy declarations without an intake snapshot, the first seal establishes
that binding and also clears earlier observations. A later unchanged seal does
not manufacture a new proof identity or renew stale observations.

## Completion

```text
python <kit>/gates/gate_runner.py delivery-audit --check --repo <repo> --session <host-session-uuid>
python <kit>/gates/gate_runner.py requirements --done --repo <repo> --delivery-session <host-session-uuid>
```

With explicit `--delivery-session`, the requirements gate checks the selected
REQs, their linked decisions/evidence, relevant findings and lanes rather than
requiring unrelated program work to finish. Ambiguous/global findings and
unscoped lanes remain conservative blockers; repository-wide structural checks
(including malformed ledgers and conflicting mutable owners) still apply.
Without that explicit selector, `requirements --done` retains program-wide
meaning, while checking the current host declaration when present. Historical
ledgers without declarations retain their old validation scope; this is not
retroactive certification of prior accepted work.

The plugin's narrow completion hook checks `task_complete` for declared work.
It does not run full builds after every edit, block unrelated tools, answer
permission prompts or repeatedly force agentStop continuation. A missing/stale/
failed declared check denies that completion request. Report genuine blockers
without calling incomplete work accepted. Read-only/undeclared sessions are
untouched.

After verified host completion, the hook permits an ordinary nonempty read-only
follow-up summary with no recorded repository edits after the original
completion. Legacy follow-up labels remain valid but are not required.
It does not demand
repair of historical evidence merely because another writer changed the checkout.
This hook-only retirement is not delivery revalidation: explicit `--check` and
`requirements --done --delivery-session` still check current evidence. New work
needs a newer owner-bound declaration. Source-neutral undeclared
work cannot be classified reliably by this mechanism; default-session guidance
still owns that intake decision. Recorded edit detection is limited to explicit
edit/create/apply_patch events, not arbitrary shell mutations. Patch move
destinations count, and relative patch targets fail closed because tool events
do not record the originating cwd. Summary wording
is neither a sandbox nor proof of inactivity or delivery.
Subdirectory hook working directories resolve
to the actual Git root rather than falsely becoming another repository. A
confirmed non-Git hook cwd can still close a retired or first paused scope
against its declared repository; active declarations still require that repository.

## Limits

This is not a security sandbox or an assurance that every agent will declare
every non-trivial task. Host hooks can be unavailable/disabled, and documented
host timeouts can fail open. Startup instructions plus the source-bound
completion check reduce ordinary mistakes within the supported declared
workflow; they cannot prevent deliberate forging of writable local logs,
reports or provider observations. Unsupported hosts must disclose which checks
were not run.

A clean lexical scan is never proof of a real integration. Same-category
document references are not semantic entailment; source control identity is
not external-provider authenticity. No universal model-performance improvement
is claimed. Tests must cover false acceptance and false blocking, including
authorized emulator/environment selection, not just suspicious-word counts.
