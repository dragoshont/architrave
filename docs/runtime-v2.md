# Runtime v2

Architrave Runtime v2 turns a goal into a durable Outcome, Acceptance Matrix,
TaskGraph, typed EventLog, policy, checkpoints, bounded WorkPackets, and gates.
The complete behavioral contract lives in
[`knowledge/runtime-v2.md`](../knowledge/runtime-v2.md).

## Canonical state

- `.architrave/runs/<id>/run.json` is authoritative.
- `events.jsonl` is append-only and HMAC-authenticated with the local ignored
  `.architrave/runtime.key`.
- `recovery.json` is the single rolling last-known-good snapshot.
- Status, phase, handoff, and audit views are rendered on demand.
- `harness/architrave_runtime.py` is the only state transition API.
- v1 `summary.json` remains readable and migratable.

## Common flow

```bash
python3 harness/architrave_runtime.py run \
  --goal "Ship and verify the release" \
  --outcome "The intended release is healthy on the scoped target" \
  --autonomy approved-program \
  --allow repository:edit,build,test \
  --allow sandbox:app:deploy,rollback \
  --criterion 'DEPLOY-001|Live version and digest match|deployment|R3|reality'

python3 harness/architrave_runtime.py task-add <run-id> \
  --id build --title Build --objective "Build the release" \
  --criteria DEPLOY-001 --risk R2

python3 harness/architrave_runtime.py status <run-id>
python3 harness/architrave_runtime.py resume <run-id>
python3 harness/architrave_runtime.py verify <run-id>
```

An `approved-program` Run crosses internal phase/task boundaries automatically.
It still stops for policy denial, failure, exhausted retry, unavailable worker or
resource, cancellation, and typed external checkpoints.

## Native workers and observed gates

Install the explicit user-scope Copilot integration from the kit:

```bash
python3 tools/install_update.py native-host-install
```

Reload extensions through the supported host tool. `architrave_native_dispatch`
takes `repo`, `run_id`, `task_id` and optionally an existing idle native
`owner_handle` in this same host session. It admits one bounded canonical
WorkPacket, creates the isolated workspace before task start, observes the
actual host result and binds a compact candidate to the Run. No model settings
or caller-authored result JSON are accepted. Unsupported hosts return an early
capability error without inventing a human authorization checkpoint.

Then invoke `architrave_native_gate` (same repo/Run/task, `recipe` =
`test`, `build`, `quick` or `ci`) or the public CLI:

```bash
python3 harness/architrave_runtime.py gate-execute <run-id> <task-id> --recipe test
python3 harness/architrave_runtime.py criterion-set <run-id> <criterion-id> \
  --status PASS --evidence gate:<observed-gate-id>
python3 harness/architrave_runtime.py task-complete <run-id> <task-id> \
  --evidence gate:<observed-gate-id>
python3 harness/architrave_runtime.py verify <run-id>
```

For CI milestones, `gate-execute ... --recipe ci --ci-run-id <workflow-run-id>`
queries the origin's GitHub workflow through the installed CLI and requires the
exact current commit, workflow id, completed status and successful conclusion.
Unrelated/historical CI or caller-provided CI JSON cannot prove this Run.
For a side-effect-free deterministic `shell` task, `--recipe task` independently
executes its already stored structured argv; it never accepts a new command or
imports a claimed result.

The executor runs a real configured command and binds source/exit/objective/task/
risk identities. Criteria, risk gates and completion remain independently
checked; a candidate or an arbitrary registered file is insufficient.

For an existing stalled Run, the owner updates the copied kit (preserving config
and Run data), explicitly reconciles baseline drift with `resume --accept-commit`,
and uses `worker-recover <run-id> --task-id <failed-side-effect-free-task>`.
The installed `architrave_native_recover` tool additionally supports the one
obsolete `native-adapter-required` integration wait. It cancels that tooling
wait, never resolves human product/sign-in/target/policy authority, and leaves
unverified criteria open. Neither recovery path executes a command or replays a
side effect; uncertain side effects still need their existing reconciliation.

The trust/capability boundary and same-user limitations are explicit in
[`knowledge/runtime-v2.md`](../knowledge/runtime-v2.md#worker-adapters).

## Authenticated worktree reconciliation

`resume --accept-commit` still accepts only the current checkout's HEAD. It
cannot name a different baseline or transfer authentication to another path.
When the verified source is a **pristine linked Git worktree**, use the two-step
owner-confirmed reconciliation instead. Run these commands using the updated
runtime code, not an older installed copy:

```bash
# ORIGINAL and VERIFIED are absolute repository roots, not Run directories.
# All three commits must be full object IDs independently checked by the owner.
python3 /path/to/updated/harness/architrave_runtime.py --repo "$ORIGINAL" \
  reconcile-worktree-request "$RUN" \
  --destination "$VERIFIED" \
  --source-commit "$ORIGINAL_HEAD" --baseline-commit "$RUN_BASELINE" \
  --destination-commit "$VERIFIED_HEAD" --revision "$CURRENT_REVISION" \
  --principal "$OWNER" --provider user-direction --actor "human:$OWNER" \
  --reason "Bind this existing Run to the exact verified clean worktree"

# Review result.reconciliation. Only the actual owner may confirm that binding.
# Use the returned revision and resolutionChallenge, not CURRENT_REVISION.
python3 /path/to/updated/harness/architrave_runtime.py --repo "$ORIGINAL" \
  reconcile-worktree "$RUN" \
  --destination "$VERIFIED" \
  --source-commit "$ORIGINAL_HEAD" --baseline-commit "$RUN_BASELINE" \
  --destination-commit "$VERIFIED_HEAD" --revision "$REQUEST_REVISION" \
  --principal "$OWNER" --provider user-direction --actor "human:$OWNER" \
  --challenge "$RESOLUTION_CHALLENGE"

python3 /path/to/updated/harness/architrave_runtime.py --repo "$VERIFIED" inspect "$RUN"
python3 /path/to/updated/harness/architrave_runtime.py --repo "$VERIFIED" resume "$RUN"
```

All subsequent coordinator entrypoints must also use the updated runtime;
older installations do not understand the authenticated context reference.
This source repair does not install or reload a native extension.

This is the **same Run**, not an import into a new Run. Its directory moves by
same-filesystem rename; old signed events and artifact attestations remain
unchanged. The original key stays at its original private path: it is never
printed, copied, linked or moved. A non-secret
`.architrave/runtime-context.json` at the destination refers back to that
authority and must match the signed `run.reconciled` event. Keep the original
checkout/key available. No authentication-context chains or new Runs in that
referenced context are supported.

Source HEAD, branch, index, dirty/staged/untracked/ignored product bytes are
untouched. The only source writes are canonical control-plane transitions,
locks and relocation metadata under ignored `.architrave/`; the Run directory
itself moves to the destination. This does not promise a byte-identical
control-plane directory while recording a transition.

The request binds both real paths, Git common-directory/worktree identities,
branches, full commits, source-byte fingerprints, original baseline, Run
revision, objective version, principal/provider and a one-time challenge.
Any intervening transition or identity/byte drift invalidates confirmation.
The destination must have no existing `.architrave`, no dirty/untracked or
ignored product files, and exact committed blob bytes/executable modes (even
when Git's index flags hide dirt). Submodules and checkout transforms such as
CRLF conversion are not supported by this strict transfer. Clones, unrelated
histories, cross-filesystem moves, active/leased workers, unresolved side
effects and unfinished assigned workspaces are rejected. Pending task packets
are rebound only from the old repository scope to the new one; custom scopes
or execution argv tied to the old checkout are rejected, not rewritten.
Completed/cancelled Runs cannot be rebound to a new unverified outcome.

Policy, objective, autonomy, acceptance, gates, task statuses, minimal-slice
requirements, side effects and all existing checkpoints remain unchanged.
No action is started or retried and no human/product approval is fabricated.
As with any transition, revision-bound pending policy amendments become stale;
their unchanged delta still needs supported owner reauthorization.
Historical evidence outside the Run directory must already match at the
destination; no product files are copied. Old source-bound evidence remains
historical and must pass the ordinary current-source checks before reuse.

If interrupted after the signed transition, the source rejects normal writes.
Keep both worktrees unchanged and retry the **identical** confirmation command;
the signed transition and empty destination reservation are recoverable without
another approval or another transition. Inspect the destination first if the
move may already have finished. Unexpected reservation data, changed source
bytes or unavailable original authority fail closed; do not delete canonical
state or copy a key to bypass these failures.

The owner label/challenge uses the existing same-user CLI trust boundary; it
does not authenticate a remote person or isolate a malicious process running
as the same OS user. Operators must obtain actual owner direction before
issuing the human confirmation.

## Policy amendment

Run policy remains immutable except for an additive, challenge-bound amendment.
Request the exact delta against the task blocked by policy, then apply the same
delta as the authorized principal:

```bash
python3 harness/architrave_runtime.py policy-amend-request <run-id> \
  --id policy-scope-correction --task-id publish \
  --principal release-owner --provider user-direction \
  --actor human:release-owner \
  --reason "Correct public-candidate:edit to repository:edit." \
  --add-allow repository:edit

python3 harness/architrave_runtime.py policy-amend <run-id> policy-scope-correction \
  --challenge <one-time-challenge> \
  --principal release-owner --provider user-direction \
  --actor human:release-owner --add-allow repository:edit
```

The request binds the Run, current objective version and revision, principal,
provider, exact additive delta, reason, and one-time challenge. Any intervening
transition makes it stale. Apply fails while a mutating task is running or a
side effect is pending/uncertain. Success returns the blocked task to `READY`;
it never starts or replays the action automatically. The command cannot change
default deny, autonomy, objective/outcome, task paths, or other Run state.

## Safety

Policy defaults to deny. Workers cannot change policy, resolve challenge-bound
external waits,
or complete tasks. Unknown side effects require reconciliation. Event tampering,
repository drift, mutable-path escape, deterministic failure, and stale live
deployment evidence block completion.