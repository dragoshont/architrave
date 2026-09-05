# Architrave LongBuild

LongBuild extends the existing benchmark harness; it does not replace it.

Categories are `short-mechanical`, `feature`, `multi-surface`, and `longbuild`.
The frozen local fixture under `benchmarks/fixtures/tessera-shaped/` approximates
a persistent backend, Web, Electron, iOS, provider boundary, sandbox deployment,
runtime health, restart recovery, and an external auth checkpoint without using
private Tessera code or data.

Enabled next-generation scenarios cover:

- overnight-equivalent multi-surface delivery;
- process kill/resume without repeated work;
- external checkpoint continuation with independent tasks;
- no-authorization plan-only vs explicit scoped deployment.

```bash
python3 scripts/bench-architrave.py --validate
python3 scripts/bench-architrave.py --list
python3 scripts/bench-architrave.py \
  --scenario longbuild-tessera-shaped-release \
  --arm copilot-architrave --repeats 3 --execute
python3 scripts/summarize-bench.py <results.jsonl>
```

Results include Outcome PASS, acceptance counts, false PASS, interventions,
unnecessary-question heuristic, false external blockers, repeated work, peak
parallel workers, deployment verification, E2E failures, tokens, wall time,
changes, and dependency churn. Summaries report success rate, median, p90,
variance, and time to verified outcome per intervention.

Raw benchmark runs remain ignored and sensitive. Repeats and human/semantic
mergeability review are required before broad comparative claims.