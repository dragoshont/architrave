# Architrave Benchmarks

This directory is the foundation for Architrave's autonomous evaluation loop: frozen tasks, isolated worktrees, repeatable agent arms, deterministic gates, trace artifacts, and reviewable scores.

The goal is not to create a toy leaderboard. The goal is to answer the enterprise question: does Architrave improve real work in real repositories without hiding cost, complexity, or regressions?

## Research Baseline

Current agent-evaluation practice converges on a few patterns:

- **SWE-bench / Terminal-Bench:** evaluate agents on real tasks in isolated environments; report task resolution, not just response quality.
- **OpenAI agent evals:** debug with traces first, then move to datasets and repeatable eval runs when comparing prompts or workflow versions.
- **LangSmith:** separate offline evals on curated datasets from online evals on production traces; use code evaluators, LLM-as-judge, and human/pairwise annotation.
- **Inspect AI:** model evals as datasets + solvers/agents + scorers, with sandbox support and transcript review.
- **Anthropic agent guidance:** code is especially evaluable because tests provide ground truth; multi-agent systems need end-state evaluation, small initial eval sets, observability, and human review for edge cases.
- **Promptfoo:** use test-driven prompt engineering: define representative cases and failure modes, run repeatable comparisons, then add failures back into the dataset.
- **ApprenticeOps local pattern:** use Copilot CLI/GitHub Models as the frontier judge path when direct Anthropic/OpenAI credentials are unavailable; record JSONL rows, model identities, deterministic checks, and judge metadata.

## What We Measure

Each benchmark run emits one JSONL row per `(scenario, arm, repeat)`.

**Correctness and safety**
- deterministic validation command return codes;
- Architrave gate pass/fail (`gates/gate_runner.py checks`, backend checks, Storybook build/test where configured);
- expected artifact checks (run artifacts, Storybook files, contract/docs updates);
- optional LLM/human judge verdicts.

**Implementation clarity and maintainability**
- changed files, additions, deletions, net LOC;
- dependency/config churn (`package.json`, `*.csproj`, `project.yml`, lockfiles);
- YAGNI findings: speculative abstraction, unused config, wrapper-only layers, reinvention of repo/native/stdlib capability;
- Storybook-first evidence for UI and contract-first evidence for backend.

**Agent process quality**
- visible intake present;
- Tournament of Options present;
- YAGNI ladder considered;
- recommended plan present;
- judge gate evidence present;
- learning artifacts created/updated.

**Efficiency**
- wall-clock time;
- requested semantic execution treatment and concrete local binding;
- producer-reported intent, kept separate from host-observed model identity and reasoning effort;
- output tokens and tool-call counts from CLI JSON events when exposed;
- raw session JSONL/transcripts for later trace grading.

Context tier is recorded as requested-only unless the host emits observable context telemetry. Do not claim that a context treatment was honored when it cannot be observed.

### Question metrics

`agent.question_mentions` is a lexical count of `ask_user`/`ask-user`/`ask user`,
`please confirm`, `could you clarify` and `should I proceed` in captured stdout.
It counts mentions inside prose and log payloads, not necessarily tool calls.
`agent.unnecessary_questions` retains exactly that legacy integer for existing
consumers; it is a deprecated lexical alias, not a necessity score.
`question_metric_basis` names this limitation, and `question_necessity: null`
means unassessed (not zero unnecessary questions). Necessity, successful delivery
and substantive answer require decision context and observed results. Benchmark
approval and `--no-ask-user` defaults are unchanged. No host answer handler is
changed or host result shape inferred here.

## Evidence-first analysis calibration (#31)

Use the existing `semantic-cases.json` and `score-semantic-cases.py` seam.
The map below distinguishes already-covered rules from uncovered behavioral
checks; it is not a new workflow or a claim that instructions guarantee behavior.
Policy detail lives in execution policy's **Evidence-first analysis**, loaded on
demand by the lead and research role and assessed by the existing judge rubric.

| Behavior | Existing rule / preserved coverage | Added action/artifact check |
|---|---|---|
| Consequential, discoverable and settled decisions | Lead: consequential questions, contradictions, owner corrections; worker: evidence first | A1 unresolved transport with safe work, A2 settled owner choice, A3 discoverable command (positive controls) |
| Source authority and passage entailment | Worker: primary sources/passages; evidence gate explicitly structural; C6 contradiction, C8 unsupported FIPS, C9 stale edition, H3 unverified provider behavior | A4 authoritative edition vs editorial summary, pagination owner, proposed vs demonstrated, exact restriction |
| Coverage confidence and historical evidence | Worker: facts/interpretations/unknowns; policy: historical vs current observations | A5 strong local finding with partial coverage and failed current access |
| Correction propagation | Lead: apply owner corrections; C9 detects stale decision | A6 final prose/table/diagram/REQ/estimate/decision values, not just acknowledgement |
| Forecast and numeric integrity | Lead: no silent scope reduction; strengthened policy supplies constraint detail | A7 constrained lanes, dependencies, work windows, shared overhead once, human acceptance, waits, unknown QA; A11 target/estimate/sensitivity/required vs measured improvement |
| Bounded handoff and truthful receipt | Policy: ownership, explicit guidance loading, recoverable assignments; worker: sent/started/observed/accepted | A8 usable inline input, decision, owner, acceptance, stop/return route, no assumed runtime grant; A12 admission vs delivery vs verification |
| Revision evidence and assets | Policy: evidence chain and preservation; strengthened asset rule | A9 retained revision with matching relative asset and named owner |
| Verification level | Policy/rubric: required checks cannot be replaced by semantic PASS | A10 structural/source success cannot replace failed rendering, unavailable runtime or owner acceptance |

Generate blind inputs (expected results are omitted), give the cases plus the
applicable contract to a supported agent, and retain its produced JSON array:

```bash
python3 scripts/score-semantic-cases.py --blind
python3 scripts/score-semantic-cases.py --hard --blind
python3 scripts/score-semantic-cases.py --analysis --blind
python3 scripts/score-semantic-cases.py --analysis /path/to/answers.json
```

Analysis answers are `{"case":"A1","result":{...},"rationale":"..."}`. Tasks
request final decision/artifact values, including preserved file contents, not
promises. The scorer compares complete typed JSON results and requires a
nonempty rationale; it does **not** grade that rationale. It rejects missing,
duplicate, unknown and mismatching cases; regular/hard modes now also fail
missed unverified responsibilities rather than merely printing the misses.
Positive mechanical fixtures test the scorer, not agent quality.

A separate semantic assessment must inspect the produced decisions, artifact
contents and rationale against the supplied source and owner context, including
whether a question is necessary and a passage entails the claim. An exact enum
or numeric match is not semantic PASS. Keep evaluation inputs, answers, scorer
output and review references as evidence. Synthetic A1 describes transport
without an answer; it is not a captured host result or a handler integration test.
No live question-result shape, rendering/runtime capability, general productivity
gain or intervention reduction is established by these small synthetic cases.
Use comparative repeated runs before making improvement claims.

Recorded trial: `results/evidence-first-analysis-2026-10-27.json` retains all
answers and scorer output, including failures: regular 9/10 verdicts; hard 4/4
verdicts but 5/7 lost responsibilities and 0/1 unverified; analysis initially
10/12 exact artifacts, then 12/12 after A1/A4 identifier-only clarification.
That follow-up is not an independent trial or reasoning improvement. A7's
rationale imports an unsupported sensitivity from another case, despite correct
numeric artifacts. These observations calibrate the evaluation; they are not a
blanket semantic PASS or evidence that the behavioral problem is eliminated.

## Primary Arms

Start small and controlled:

1. `copilot-baseline`: Copilot CLI with custom instructions disabled. This approximates a general development agent.
2. `copilot-architrave`: Copilot CLI using the installed Architrave agent. This tests the current published plugin.
3. `copilot-architrave-local`: optional local plugin dir or checkout for unreleased variants.

Later arms can add `claude`, `opencode`, `kilo`, or other external-agent commands. The runner is intentionally command-pluggable; it does not require direct Anthropic/OpenAI credentials.

Supported runner types today are `copilot` and `shell`. Add new runner types in both `benchmarks/scenarios.schema.json` and `scripts/bench-architrave.py` in the same change.

Model selection is outside Architrave policy. Optional benchmark arm fields are
user-local harness controls used only for explicit experiments; canonical
agents, published scenarios, WorkPackets, and Run state do not recommend or
persist them. Shell arms reject unsupported controls rather than pretending to
honor them.

## Dataset Shape

Use existing repositories, but never mutate their real working trees. Each scenario declares:

- `repo`: local repository path;
- `baseRef`: pinned commit SHA to check out in a detached benchmark worktree;
- `lane`: `ui`, `ux`, `backend`, `full-stack`, `infra`, `ops`, `learning`, `yagni`, or `knowledge`;
- `prompt`: the benchmark task;
- `validation`: shell commands run after the agent finishes;
- `expectedArtifacts`: files/directories that should exist after the run;
- `scoring`: rubric notes for human/LLM review.

The runner creates `.architrave/bench/runs/<run-id>/<scenario>/<arm>/worktree` using `git worktree add --detach`. This makes it cheap to go back to older changesets, replay old product work, and compare agent variants against the same starting point.

Validation commands may use `{python}` to invoke the exact interpreter running the benchmark, which avoids `python` versus `python3` portability drift.

`benchmarks/routing-scenarios.json` is the compact adaptive set. Its `expectedExecution` is a provisional classification hypothesis and never changes base pass/fail. Result rows keep four layers distinct: scenario expectation, arm request, producer-reported selection from a valid run summary, and observed host telemetry. `controlStatus` marks requested controls as `honored`, `mismatch`, `unobserved`, or `not-requested`; exclude mismatched and unobserved controls from concrete binding recommendations.

Use full commit SHAs, not moving branch names, for published scenarios. Branch names are acceptable for private exploratory smoke tests only.

Preflight scenario refs before spending model calls:

```bash
python3 scripts/bench-architrave.py --scenarios benchmarks/scenarios.json --validate
```

## Scenario Portfolio

For a credible enterprise benchmark, use 10-20 curated scenarios first:

- **UI / Storybook:** add or modify a visible UI state; must start in Storybook, not app code.
- **UX:** change navigation/empty/loading/error behavior; must capture interaction states.
- **Backend:** extend an existing service seam; must not invent parallel abstractions.
- **Full-stack:** contract-first API/UI change; UI and backend bind to the same contract.
- **YAGNI:** request tempting over-build; agent should reuse native/stdlib/existing repo feature.
- **Learning loop:** repeated gotcha should update repo profile/lessons without bloating config.
- **Tournament:** ambiguous implementation with multiple viable choices; agent must compare tradeoffs.

Do not jump straight to hundreds of cases. Industry practice is to start with 5-20 high-quality, manually curated examples, then add failures from real runs.

## Feedback Collection

Collect three layers:

1. **Automated:** JSONL metrics, validation logs, diffs, session JSONL.
2. **LLM judge:** rubric-based scoring using Copilot CLI/GitHub Models when available; blind the arm name and randomize order for pairwise comparisons.
3. **Human review:** small annotation queue for subjective dimensions: design quality, maintainability, over-build, and whether the produced plan would be accepted by a senior engineer.

Use `benchmarks/HUMAN_REVIEW.md` for single-run and pairwise annotations. Human feedback should become new scenarios. Do not bury it in chat.

## Autonomous Run Pattern

Recommended first pass:

```bash
python3 scripts/bench-architrave.py --scenarios benchmarks/scenarios.json --list
python3 scripts/bench-architrave.py --scenarios benchmarks/scenarios.json --scenario <id> --arm copilot-architrave --execute
```

Recommended comparison pass:

```bash
python3 scripts/bench-architrave.py --scenarios benchmarks/scenarios.json --all-enabled --arm copilot-baseline --arm copilot-architrave --repeats 3 --execute
```

The run output stays under `.architrave/bench/` by default and is not committed unless intentionally publishing a benchmark snapshot.

Summarize rows:

```bash
python3 scripts/summarize-bench.py .architrave/bench/runs/<run-id>/results.jsonl --out .architrave/bench/runs/<run-id>/summary.md
```

Optional LLM judging through Copilot CLI:

```bash
python3 scripts/judge-bench.py --results .architrave/bench/runs/<run-id>/results.jsonl --out .architrave/bench/runs/<run-id>/judged.jsonl
```

The benchmark judge is fail-closed and tool-free. It receives nonce-delimited
untrusted evidence, blinds producer identity and host-selected execution
metadata, verifies zero tool requests, and keys resumability by reviewer,
prompt, and rubric configuration. Independent reviewer identity must be
demonstrable; model choice remains user/host-owned.

Create concrete experiment arms only in an ignored local copy, for example `.architrave/bench/routing.local.json`. Vary one useful dimension at a time, use at least three repeats, and retain `controlsHonored=true` rows for model/effort conclusions. Long-context results remain inconclusive while context application is unobservable.

## Safety Rules

- Use detached worktrees or temp clones only.
- Keep secrets out of prompts, artifacts, transcripts, and result rows.
- Use `--execute` as an explicit switch; default mode lists/plans but does not run agents.
- Use `--scenario <id>` or `--all-enabled` when executing; the runner refuses implicit one-scenario execution.
- Treat DNF/timeouts as results, not crashes.
- Validate with deterministic gates before trusting an LLM judge.
- Keep benchmark prompts and expected outcomes versioned.

## Secrets And Data Safety

Benchmark runs include raw agent stdout/stderr, session transcripts, prompts, diffs, and validation logs. Treat `.architrave/bench/` as sensitive. It is ignored by git, but do not upload it to CI artifacts, share it externally, or publish snapshots without review.

Set `ARCHITRAVE_BENCH_SECRET_ENV_VARS` to a comma-separated list of environment variable names that should be redacted from captured artifacts, for example:

```bash
ARCHITRAVE_BENCH_SECRET_ENV_VARS='GITHUB_TOKEN,GH_TOKEN,ANTHROPIC_API_KEY,OPENAI_API_KEY' \
	python3 scripts/bench-architrave.py --scenario ... --arm ... --execute
```

The runner also redacts common bearer/API-key/token/password patterns from captured stdout/stderr/diffs, but explicit env-var redaction is still the strongest path. Never put real secrets in scenario prompts.

Timeouts are intentionally row-level data. If an agent exceeds `--agent-timeout`, the row records `agent.timed_out=true`, `agent.returncode=124`, any partial stdout/stderr, and then the runner continues to the next arm/scenario. That is how long-running autonomy failures become loop-engineering evidence instead of wedging the suite.

## Result Retention

- Keep raw `.architrave/bench/runs/<run-id>/` directories locally while debugging.
- Commit only curated aggregate snapshots under a deliberate docs/data path after redaction and human review.
- Delete stale raw runs after extracting `results.jsonl`, `summary.md`, selected patches, and human annotations.
- Treat timeouts, nonzero agent exits, validation failures, and artifact misses as distinct `failure_mode` values.

## Tooling Caveats

- Copilot CLI minimum for legacy scenarios remains `1.0.64-1`; adaptive arms additionally require native effort/context flags exposed by the installed host. The fail-closed judge verifies its required no-tools and structured-output options before invocation.
- `copilot-architrave` uses the fully qualified agent id `architrave:architrave`.
- On Windows, timeout cleanup uses normal process termination rather than POSIX process groups; prefer short smoke tests before long runs.
