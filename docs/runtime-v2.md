# Runtime v2

Architrave Runtime v2 turns a goal into a durable Outcome, Acceptance Matrix,
TaskGraph, typed EventLog, policy, checkpoints, bounded WorkPackets, and gates.
The complete behavioral contract lives in
[`knowledge/runtime-v2.md`](../knowledge/runtime-v2.md).

## Canonical state

- `.architrave/runs/<id>/run.json` is authoritative.
- `events.jsonl` is append-only and HMAC-authenticated with the local ignored
  `.architrave/runtime.key`.
- Markdown and `summary.json` are projections.
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

## Safety

Policy defaults to deny. Workers cannot change policy, resolve challenge-bound
external waits,
or complete tasks. Unknown side effects require reconciliation. Event tampering,
repository drift, mutable-path escape, deterministic failure, and stale live
deployment evidence block completion.