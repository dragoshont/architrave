# Delivery authenticity

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
python <kit>/gates/gate_runner.py delivery-audit --prepare --repo <repo> --base <reviewed-commit> --session <host-session-uuid> --reqs <REQ-IDs> --request <original-owner-event-id> --document <design-or-demo-doc>
```

Repeat `--request`, `--document` and `--reference` as needed. A reference is an
original image/design file whose identity must survive the work. File
attachments on the referenced owner events are also bound automatically.
The host event must be an attributable original owner message, not an
agent-originated `user.message`, system notification or continuation reminder.
No private message contents are copied into source control.

One session-owned `files/architrave-delivery.json` holds this task's evidence.
It is not a second task ledger: REQs and their statuses stay in the repository
requirements file. The report stores the original requirement/acceptance/
correction scope; changing a status or adding evidence does not change it.
Silently shrinking acceptance invalidates the report. Preserve the old intake
and use `--amend --request <new-owner-event-id>` when a task's scope changes.
An amendment requires a newer distinct original owner instruction, retains the
previous requirement scope/digest and clears observations/review. It does not
judge whether that instruction actually authorizes every proposed scope change;
the independent reviewer must compare them. Dropping REQs additionally requires
`--drop <exact-removed-IDs>`; the command prints dropped/changed scope alongside
the delivery digest. Refresh the board scope when REQs change.
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

Sealing freezes the current source inventory. It does not declare completion.
The original resolved base commit and full nonignored source-file hashes bind
the evidence, including unchanged dependencies. Requirement status/evidence is
excluded from the source fingerprint; the selected semantic contract is bound
separately. Contract documents, references and effective configuration artifacts
have their own identities. Ignored runtime/credential stores are not scanned;
bind an explicitly selected redacted effective-config observation for integration
acceptance instead of exposing credentials.

The scanner inventories whole changed files and nonignored untracked source,
including effective dotenv/INI settings, launchers and tests. `--all` deliberately
selects full-repository scanning. No directory is silently exempted as "test only".
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

## Completion

```text
python <kit>/gates/gate_runner.py delivery-audit --check --repo <repo> --session <host-session-uuid>
python <kit>/gates/gate_runner.py requirements --done --repo <repo> --delivery-session <host-session-uuid>
```

The existing requirements gate checks the declared delivery when a session is
explicitly supplied, or its current host session has a declaration. Historical
ledgers without declarations retain their old validation scope; this is not
retroactive certification of prior accepted work.

The plugin's narrow completion hook checks `task_complete` for declared work.
It does not run full builds after every edit, block unrelated tools, answer
permission prompts or repeatedly force agentStop continuation. A missing/stale/
failed declared check denies that completion request. Report genuine blockers
without calling incomplete work accepted. Read-only/undeclared sessions are
untouched.

After a host completion, the old report does not authorize later changed work:
source, contract and ledger-scope freshness are checked again. A new task that
changes them needs a newer owner-bound declaration. Source-neutral undeclared
work cannot be classified reliably by this mechanism; default-session guidance
still owns that intake decision. Subdirectory hook working directories resolve
to the actual Git root rather than falsely becoming another repository.

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
