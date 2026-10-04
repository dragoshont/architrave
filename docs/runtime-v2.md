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