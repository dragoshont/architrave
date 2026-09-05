# Run v1 to v2 Migration

Run v1 remains supported during transition. `harness/validate-run.sh` and
`.ps1` detect v1 artifacts and use the original phase/summary validator. When a
directory contains `run.json`, both wrappers delegate to the shared Python v2
validator.

Create a separate advisory v2 projection from a legacy summary:

```bash
python3 harness/architrave_runtime.py migrate-v1 \
  .architrave/runs/<legacy-id>/summary.json \
  --run-id <legacy-id>-v2
```

Migration does not claim old work was newly verified. It creates an
`advisory-only` Run, maps legacy phases to tasks, and leaves acceptance
`UNTESTED`. Review the TaskGraph, Outcome, policy, and evidence before resuming.

Existing `architrave.config.json` files remain valid. The new `autonomy`,
`workers`, `runtime`, `invariants`, and `evaluation` blocks are optional. Adopt
them incrementally; no repository must add an unused lane.