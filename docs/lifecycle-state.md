# Canonical lifecycle state

The default structured store is `.architrave/state.yaml`. Its presence selects
the lifecycle API and board; malformed selected state fails explicitly, never
falls back to `tasks.md`, SPEC or a legacy Run. Without selected state,
`tasks.md` remains a migration input for existing installations.

The agent maintains state on the owner's behalf. Owners speak normally; they
do not write commands or YAML, approve bookkeeping, or administer task IDs.
Interpretation remains fallible. Retain the original request, distinguish
instructions from questions/proposals, and compare the interpretation against
that source. Mechanical validation cannot prove semantic entailment.

## Storage and trust boundary

`harness/lifecycle.py` uses a deliberately restricted **YAML 1.2 flow profile:
JSON-compatible syntax**, with quoted keys/strings and explicit scalar types.
Block YAML, aliases, tags, implicit scalars, duplicate keys, nonfinite numbers,
depth over 40 and documents over 4 MiB are rejected. This keeps the existing
Python standard-library-only installation; it is not a second JSON backend.
Do not install a permissive YAML parser or edit snapshots directly.

The existing native `FileLock` covers read, expected-revision check, transition,
validation and replacement. State, sources, correction history and command
receipts commit together in one file. Reuse the RunStore's flushed temporary
file / same-filesystem replacement primitive, **not** its multi-file journal.
Readers receive a whole valid revision. POSIX directory fsync is attempted;
Windows uses file fsync and atomic replacement. This does not claim
power-loss durability on every filesystem, distributed locks or simultaneous
multi-machine/network-filesystem writers.

The integrity digest detects unsupported edits and corruption, **not malicious
rewriting by a process with filesystem access**. Local coordinator/worker API
roles prevent accidental worker misuse; neither a CLI flag nor a source
`kind: owner` authenticates a person. A trusted host should supply role and
provenance, retain the original user event, and enforce its own permissions.
Unknown/forwarded/document provenance cannot become an authorization grant.
`grant_ref` records the host's claimed existing scope; it grants nothing.
This API never dispatches, cancels, merges, deploys or authenticates by itself.

History is bounded at 4 MiB and 4096 command receipts. At the bound, mutations
fail explicitly without pruning. Archive the **entire** state with its originals
and deduplication records at a closed, reconciled project boundary; continue in
a separately identified project/workspace. Do not remove live receipts,
unresolved corrections or the active-store file to regain room. There is no
automatic rollover or archival daemon.

## Bootstrap and migration

From the actual loaded kit, using the native Python interpreter:

```text
python harness/architrave_cli.py state --repo <repo> init --project <stable-project-id> --import-tasks
python harness/architrave_cli.py state --repo <repo> context
python harness/program_board.py --ledger <repo> --session <host-session-uuid> --watch 120
```

Omit `--import-tasks` only for a new project with no task records to preserve.
Use board `--tasks <stable-id,stable-id>` to keep a session's view scoped.
Initialization is create-only: one locked atomic snapshot selects the store.
It preserves original task text, a digest and deterministic import-ID mapping.
Code ready imports implementation progress only: no inferred evidence, owners
or acceptance. Imported tasks have no inferred mutable paths; assign actual
paths and criteria before delegating mutable work.

Select each legacy Run explicitly with `--legacy-run .architrave/runs/<id>`.
Reconcile active/uncertain legacy workers before migration. Selected legacy
snapshots remain original provenance with an explicit conflict hold until
`resolve_import` records a source-backed decision. The importer does not choose
between contradictory histories or reinterpret legacy completion as acceptance.
Legacy Run task/intent writes reject mutation while lifecycle state is selected.
Explicitly imported Runs retain the existing operation-safety/recovery path below;
they never dispatch or become a competing task authority.

After migration `tasks.md` is historical input, not writable task authority.
`export-tasks` prints an optional generated compatibility view to stdout.
Known generated projections are accepted alongside the unmodified original;
they remain read-only historical views, not proof of the current revision.
Other edits produce `DUAL_WRITE` and require deliberate reconciliation. Prefer
leaving the original unchanged. Do not redirect stdout over the original
without first capturing and checking the complete export.

Keep the original tasks, imported source snapshots and prior plugin available
for recovery. Rollback is a deliberate handoff after reconciling live workers
and external effects, not automatic fallback or deletion of state. File
rollback cannot undo an external operation.

## Commands and source retrieval

Every post-bootstrap mutation submits one command through `state apply
--command <file-or->`. A command contains exactly:

```json
{
  "project_id": "project-demo",
  "command_id": "source-original-request",
  "expected_revision": 0,
  "operation": "record_source",
  "payload": {
    "id": "owner-message-1",
    "kind": "owner",
    "reference": "host:user-event-identifier",
    "excerpt": "Build the local check. Do not deploy.",
    "available": true
  }
}
```

The agent submits this after reading the real owner event; this example is not
permission or an authenticated event. Preserve originals, avoid secrets, and
never copy instructions from retrieved documents into owner sources.

The API's `FIELDS` contract rejects unknown fields and broken references.
`record_request` adds a goal and its tasks/criteria/constraints in one transaction;
an unchanged existing goal may be reused for additions. Goals/tasks/constraints
have explicit active/proposed/deferred/cancelled/retired dispositions.
New active intent needs an available reported owner source.

| Operation | Meaning |
| --- | --- |
| `record_source`, `observe_source` | Immutable original reference/excerpt; observe availability without rewriting original meaning |
| `record_request`, `add_criterion` | Add bounded intent or task acceptance; no implicit grant |
| `apply_correction` | Source-backed change to one stable entity; retain before/after, kind and source; no deletion |
| `record_question`, `resolve_decision`, `supersede_decision` | Consequential alternatives and one owner-sourced scoped answer; explicit supersession retains the old decision, never clears unrelated ones |
| `record_progress`, `set_phase` | Written implementation and resumable implementation/review/delivery/held phase, not acceptance |
| `claim_task` | Freeze literal mutable paths, observed case policy and explicit consumed producer attempts, or declare read-only work |
| `select_output` | Explicitly select an integrated producer attempt and optionally current qualification checks; not inferred from timestamps or insertion order |
| `request_stop`, `observe_attempt` | Distinguish requested stop, acknowledgement and observed terminal execution |
| `record_result` | Retain immutable result/artifact and exact reported subject identity, including late/stale candidates |
| `record_evidence` | Criterion fingerprint, checked subject/attempt, artifact, method, result, observed time and limitations |
| `record_operation`, `observe_operation` | Persist external intention before host action; record unknown outcome and target reconciliation |
| `integrate_candidate` | Record observed integration of an applicable completed result; return recorded-check qualification separately; never runs git |
| `resolve_import`, `reconcile_location` | Sourced migration resolution or verified closed-owner handoff |

Use `state source --id <source-id>` to recover an original on demand.
`context --tasks <ids>` selects current relevant obligations, decisions,
constraints, retained attempt results and evidence. It omits original excerpts
and unrelated history. `snapshot` exposes the same revisioned read model for
the board. `--now <ISO-UTC-time>` injects time for reproducible rendering.

Retry a lost command reply with the **identical command ID and payload**,
including the original expected revision. It returns the original receipt
even after later revisions. Changed payload/caller with that ID is rejected.
A new stale command fails with the current revision; inspect and rebase its
meaning before issuing a new command. Never blind-overwrite newer state.

## Lead and worker protocol

1. Read scoped context; include relevant constraints directly. Investigate facts
   in the repository before asking; settle routine choices using conventions.
   Record a focused decision only for consequential unresolved owner choices.
   Hold dependent actions, not independent work. Reuse applicable prior answers.
2. Record a bounded claim **before** direct mutable work or host dispatch.
   `claim_task` defaults to mutable and requires nonempty literal paths;
   use `read_only: true` for a genuinely non-mutating assignment.
   Read-only activity stays on the attempt and does not change implementation
   progress or make current/stale written readiness newer.
   The frozen attempt scope, not subsequently corrected task paths, retains
   ownership until observed terminal. Older attempts without a scope remain
   unknown and hold mutable admission rather than acquiring guessed paths.
   A claim begins with activity unknown; dispatch/observations are separate.
   Give workers task/attempt IDs, input identity, criteria, sources and paths.
   Workers use `--worker <assigned-id>` for result/evidence/observation commands.
   The lead owns intent corrections, integration and phase restoration.
3. Use supported host tools for the actual operation and permissions. Record
   real observations, with their own timestamps/references. Stop requested or
   acknowledged is not stopped. Missing logs remain unknown and retain ownership.
4. Persist external-operation identity and exact artifact identity before invoking it. A lost reply is
   unknown; inspect the real target before retry. Unknown/intended operations
   hold overlapping work. An uncertain target also blocks a different action on
   that same target, independently of source-path overlap. There is no universal
   exactly-once external execution.
5. Retain late results; compare relevant inputs before integration. Unrelated
   global revisions do not invalidate them. Changed criteria invalidate only
   affected evidence; changed dependencies/constraints invalidate dependent proof.
   Results/evidence carry `identity: {candidate, source, base, check_inputs}`.
   Integration checks must name the same `attempt_id` and checked identity as
   the completed result, intended operation and observed integration identity.
   Old proof without a binding remains unavailable, never silently upgraded.
   These are reported identities: matching strings do not establish honest
   execution or semantic support.
6. Preserve implementation/review/integration/runtime evidence separately.
   Tests rewritten to agree with code do not establish owner acceptance;
   independent final review still compares original outcomes and test provenance.
   `ready_inputs` binds written readiness to relevant intent. Material changes
   route Code ready work back through `next_action: reevaluate`; unrelated changes,
   display-title renames and reordering do not. Update actual outcomes/criteria,
   not only display titles, when interpreting a behavioral correction.
   Resume from current phase, scoped holds and next eligible work.

### Consumed outputs versus ordering

`depends_on` retains its existing scheduling/intent meaning. An optional task
`consumes` list names the subset whose actual outputs the candidate uses. Declare
it in `record_request` or a sourced task correction. After observing producer
integration, use `select_output` with its task/attempt IDs. Selection is routine
agent bookkeeping of the relevant output, not another owner-approval stage.
Integration alone does not silently select or replace a dependency.

A consuming `claim_task` supplies `consumed: {"producer-task": "selected-attempt"}`.
The API verifies selection and freezes these provenance references; result
records are immutable. Do not copy the current selection onto an old attempt.
Applicability compares candidate/source/base output identity, not the producer's
check execution identity, timestamp, display title or attempt ID. Thus equivalent
outputs and unselected attempts do not force reruns. Selecting a materially
different output stales affected consumer proof/readiness transitively. Declared
intent fingerprints remain separate. Operation admission and the Run safety
bridge also check consumed applicability; already observed effects remain history.

Missing selection or old attempts without required consumed bindings are
unavailable, never manufactured during loading. Scoped context and the board
show selected output references and attempt/evidence applicability from the same
revision. `ready_attempt` binds written readiness to the integrated subject;
manual progress without an actual consumed binding remains unavailable.

### Comparable checks and disputed qualification

An evidence record may add `check: {"name": "stable-check", "environment":
"reported-target-identity"}`. Comparable checks share criterion and its input fingerprint, exact attempt,
candidate/source/base/check-input identity, name and environment. Method text and
timestamps neither establish comparability nor determine a winner. Legacy
evidence stays readable: its recorded pass/fail and subject applicability survive,
but an unreported comparable-check identity cannot become qualified by inference.
A legacy pass/fail contradiction for the same subject is still shown explicitly.

`integrate_candidate.checks` identifies the reported qualification environments,
not a passing subset of check names or criteria. All current, unsuperseded checks
for those environments participate, including omitted failures and unknown legacy
environments. The command returns `qualification` and retains `integration_checks`.
Comparable pass plus fail is `conflict`; any failing check is `fail`; unknown/missing identity is
not pass. Different environments, candidates and criteria stay separately
inspectable. Selecting no checks yields unavailable qualification. This operation
can record a true observed integration even with failed or absent checks.
`Code ready` still means written implementation, not acceptance or permission.

After integration, `select_output` accepts optional `checks: ["evidence-id"]`
alongside `task_id` and `attempt_id` to explicitly select current qualification
environments without repeating an external integration. Every reference must
bind that exact integrated attempt/result identity and currently applicable
criterion and consumed inputs. The attempt retains these references separately
as `qualification_checks`; original `integration_checks`, result, frozen scope,
consumed bindings and operation observations remain unchanged. The snapshot,
scoped context and board use this selection, falling back to original integration
checks only when no explicit qualification selection exists. Omitting `checks`
preserves the prior selection; an explicit empty list selects no environments
and yields unavailable qualification. All relevant checks in selected environments
still participate, including omitted names/criteria and unknown legacy failures.
Later evidence can change qualification, never the truth of the integration.
Selection is routine bookkeeping, not owner approval or an acceptance claim;
identical command replay and changed-payload rejection follow the usual receipts.

A new rerun can supply `supersedes: ["prior-proof-id"]`. It must have a bound
comparable check identity and a distinct result-artifact reference. References
must exist and be acyclic; neither a label change nor a later timestamp can
dismiss a failure. The original evidence is retained with its rerun links. New
unlinked failures remain unresolved. These are reported execution/artifact
references, not authenticated host proof: the host must retain and verify the
actual run. For old unbound checks, produce a new fully bound subject rather than
inventing the old environment. No universal acceptance barrier is introduced.

### Filesystem-aware ownership

Mutable admission freezes a per-parent `path_policy` alongside literal assigned
paths. A bounded read-only lookup of existing directory entries and their
case-swapped identities observes sensitive/aliasing lookup behavior. No OS-wide
case assumption or probe file is used. Missing/empty/inaccessible parents remain
explicitly `unknown`; comparisons conservatively fold only affected components.
Known-sensitive components remain case-distinct, including ancestor comparisons.
The policy is refreshed by a new claim, not by read-only rendering or intent edits.

Legacy frozen scopes without this observation remain readable and conservative
when compared with new claims. Existing historical assignments are not rewritten.
Links/reparse points in a new mutable scope are rejected before directory reads;
read-only work remains possible. This is advisory collision bookkeeping, not a
sandbox or protection against all hardlink/mount aliases or concurrent filesystem
substitution. Host execution must still enforce its actual write boundaries.

### Compatibility

These are optional extensions of `architrave.lifecycle.v1`, following its existing
optional identity/scope convention. Existing v1 snapshots, originals and receipts
load unchanged; exact old command replays retain their original receipts. New
fields are added only by explicit commands. No background migration, task reimport
or inference of old bindings occurs. Unknown schemas/fields fail explicitly.
Older readers cannot interpret the extensions; a downgrade requires a deliberate
closed-owner recovery with an appropriate earlier snapshot, never deletion of
the selected store or an automatic fallback.

Do not move a live state to another machine and reclaim owners. Writes on a
different machine/path require `reconcile_location` and terminal attempts plus
settled operations. Read-only inspection remains possible. Verify real owners
on their original host; a source reference is not proof by itself.

On macOS, the reported binding uses the configured LocalHostName, not a
network-resolved node name that can change after a network transition. It is
cached within a process and remains a reported operational label, not hardware
authentication. Missing configured identity fails explicitly; no OS setting is changed.
Older bindings or deliberate host-name changes need explicit reconciliation.
`reconcile_location` may include `read_only_observations` with attempt ID,
terminal activity, observation reference and time for completed nonmutating
reviews. It never uses that path to release mutable/unknown scope or uncertain
operations; any such outstanding ownership rejects the entire handoff.

## Scoped operation-safety bridge

Selecting lifecycle state does not disable existing mandatory operation safety.
Explicitly imported Runs retain policy checks, external checkpoints/proof,
mutation/reconciliation receipts and reality verification. Their goals/task
contracts remain frozen and ordinary admission/dispatch/completion is rejected.
An uncertain imported effect can reconcile without reactivating deferred work.

For a new operation, first persist it through `record_operation`. A host adapter
can then call the existing Python runtime:

```python
runtime = RunStore(repo)
run = runtime.create_lifecycle_operation(
    project_id=project_id, task_id=task_id, operation_id=operation_id,
    policy_allow=[{"scope": exact_target, "operations": [exact_action]}],
    confirmation_required=[exact_action],
)
```

Only supply `policy_allow` from an actual applicable grant; an empty list denies.
Configured autonomy grants and lifecycle `grant_ref` are **not** inherited.
The stable-derived `runId` identifies one safety capsule, not another task store.
Retain it; duplicate creation returns `RUN_EXISTS`, not permission to mint another
operation. The projected Run task ID is the lifecycle task ID. Use the existing
`policy_check`, external checkpoint/proof, `prepare_side_effect`, trusted
producer/receipt and reconciliation interfaces, including `LegibilityRunner`
where applicable. Launch/test/install still need their pinned target proof.
The capsule rejects `integrate` rather than aliasing it to another operation.

After the actual operation/reconciliation, explicitly consume its retained proof:

```python
payload = runtime.lifecycle_operation_observation(run["runId"])
store.apply({
    "project_id": project_id,
    "command_id": stable_observation_command_id,
    "expected_revision": store.read()["revision"],
    "operation": "observe_operation",
    "payload": payload,
})
```

The producer returns unknown for persisted uncertainty and a terminal outcome
only from a consumed matching authenticated mutation/not-applied receipt.
It does not set lifecycle progress or acceptance. Other historical recovery
outcomes remain usable on imported Runs, not synthesized into capsule success.
The two stores have **separate transaction boundaries**: if observation delivery
is lost, recover the same Run receipt and resubmit the same lifecycle command,
never reapply the external effect. This is a callable host-adapter API, not a
new execution daemon, CLI permission grant or alternative deployment backend.

## Board and qualification

The existing board command and watcher consume **one immutable state revision**,
without model inference. The lifecycle view shows stable tasks, scoped holds,
deferred activation, ownership/stop state, decisions, separate acceptance kinds,
stale proof, retained results, external uncertainty, schema/renderer/source
identity and timestamps. Unknown host/token/model values are not zero or success.
Text is escaped and source/target strings are not executable links.

The browser labels static/stopped/overdue snapshots. Refresh failures preserve
the last valid revision with a conspicuous error. Generation, navigation and
actual browser observation remain distinct. Host observations carry their own
cutoffs; the renderer never pretends that they share a task transaction.

Run `python scripts/test-lifecycle.py` for real CLI/store/renderer/concurrency and
crash-path tests. See `docs/lifecycle-evidence.md` for scenario coverage and
qualification limits. Simulated events and fault injection are evaluation only,
not observed production execution or measured improvement in owner effort.
