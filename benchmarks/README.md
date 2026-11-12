# Architrave Benchmarks

## Real host domain matrix

`domain-host-cases.json` extends the existing Copilot runner, not the semantic
answer-key calibration. Its seven cases cover a small authorized change without
a Planner, a genuinely missing business decision, conflicting status-labelled
sources, a .NET invariant repair, functional Python/TypeScript audit controls,
live owner correction, and read-only audit with writable tools and source bait.
The same small parcel application includes accepted, superseded and proposed
decisions and a documented express-shipping exception. Two integration variations
are selected by repetition index for the conflict and injection cases; the task
prompt does not disclose their expected outcomes.

Only `fixtures/domain-host/source` plus the selected variation is copied into the
agent's target. `fixtures/domain-host/oracle.py` stays outside, as do the scenario,
review topics and hidden behavioral assertions. The agent receives its task and
the application sources, not expected findings or validator text. Protected
authority documents cannot be rewritten to make a wrong implementation pass.
The oracle exercises composed Python API calls, actual TypeScript functions and
an authentic package-free `net10.0` console project. Missing Node/.NET is
unavailable, never a successful language check.

### Matched runs

Supply independently pinned plugin directories; do not install/uninstall global
plugins. The baseline must be the owner's verified 1.1.1 source, not a moving
branch. The candidate must be frozen before the comparison. Configuration allows
environment substitution only in `pluginDir`; no model/provider is selected here.
Use the same native executable, host defaults, tool profile and budgets for both
arms. Actual default models can change; compare recorded observations and reject
unmatched or unobserved cells rather than assuming equal models.

```bash
export ARCHITRAVE_BENCH_BASELINE_PLUGIN=/absolute/pinned-1.1.1
export ARCHITRAVE_BENCH_CANDIDATE_PLUGIN=/absolute/candidate
# Put the owner's chosen native Copilot, Python, Node and .NET 10 on PATH.
python scripts/bench-architrave.py --scenarios benchmarks/domain-host-cases.json --validate
python scripts/bench-architrave.py --scenarios benchmarks/domain-host-cases.json --list
python scripts/bench-architrave.py --scenarios benchmarks/domain-host-cases.json \
  --all-enabled --repeats 2 --execute --out /absolute/private-evidence \
  --agent-timeout 600 --validation-timeout 180 --run-timeout 18000 \
  --heartbeat-interval 60
```

Default invocation still lists/plans; only `--execute` launches agents. A run
directory must be new: existing targets are never deleted or silently reused.
`--cleanup-worktrees` removes only targets created by that invocation. Preserve
private evidence until independent review has consumed it.

Domain runs set `COPILOT_PLUGIN_DIR_ONLY=true` and use the explicit plugin path.
They retain the actual invocation, executable/version, fixture/scenario/oracle
hashes and role/pack hashes before and after each cell. Configured agent/path
and content hashes are not proof that the host loaded those bytes. Host-reported
role fields and instruction-event hashes are separate; an instruction hash alone
does not attest a selected role. No concrete model, provider or reasoning level
is pinned. `--usage-output-file` supplements JSONL observations, retaining only
reported values (unknown remains null, not zero).

### Tools, read-only observations and interruption

The domain profile exposes `view,glob,rg,apply_patch,ask_user,skill`, disables
built-in MCPs, omits shell/network/delegation tools, denies shell/URL/memory
operations, and scopes write approval to the disposable target. It does not use
legacy `--allow-all`, disable questions, or grant all filesystem paths. Native
option availability is checked before launch; unsupported controls fail closed.
Tool names accepted by an option are not necessarily exposed by a host.
`tool_catalogue` is null when the host does not publish names (native 1.0.108
`session.tools_updated` may report only the model). Successful `apply_patch`
calls are positive observations; audit abstention alone does not prove a writable
capability. Retain a same-profile positive capability control with real host
evidence before interpreting the audit cells.

The agent cannot execute application tests under this deliberately restricted
profile. The evaluator runs those tests afterward, outside the agent fixture.
Worktree isolation is not a security sandbox. Before/after snapshots cover
tracked, untracked, ignored files and symlink identities without following links;
only root `.git` metadata is excluded, with HEAD/status recorded separately.
Snapshots precede **all** post-agent Git access and validation. Domain fixtures
also freeze the owned `.git` directory's HEAD, config, refs, index and trust-related
files. A changed Git pointer, trust metadata, oracle/config/source identity,
target symlink or read-only target write blocks post-agent Git and validation.
No domain diff runs `git add -N`; read-only Git observations disable global/system
configuration, fsmonitor, external diff and text conversion. Rejected Git metadata
is reported without following its pointer to another repository.

Audit/read-only cases never execute target code or their configured validation
commands, even when a benchmark configuration lists one. Implementation validators
receive an environment stripped of credential variables, provider settings,
provider headers and injected Git configuration. They still execute modified
application code with the host's available OS permissions: environment filtering
is not filesystem/network isolation or protection from malicious implementations.
Use a separately authorized host sandbox when that boundary is needed.
Evaluator-generated files are not attributed to the agent. Snapshots cannot
detect a transient write restored before the snapshot, or
prove that no external effect occurred. Observed tool calls supplement snapshots;
global read-only compliance remains advisory, not universally enforced.

The correction case supplies a first safe step and a marker, without a sleep
barrier. The runner requires the **same generated session UUID** in the persisted
host event log plus actual prior tool events and the marker while its child is
still running. It signals only that owned process group, records prior event
count/hash, PID, signal, observed termination and return code, writes the
source-bound newer owner decision, then invokes `--resume=<same UUID>`. The
resumed session identity must be observed again. A process that finishes before
interruption, a missing persisted event, timeout or unverifiable resume is an
explicit nonpass, never relabelled as interruption. A two-turn completed handoff
is not this experiment. Native sidebar interruption may be evaluated separately
when the CLI cannot expose the required observation.

### Evidence and adjudication

`results.jsonl` remains the detailed private receipt; `public-summary.jsonl`
contains sanitized machine-readable metrics and identities, not raw session
content. Public fields are allowlisted: usage counts/model, file and input hashes,
observed tool names, completion and checks. Personal absolute paths become
placeholders; account metadata and hidden reasoning/encrypted reasoning fields
are excluded. Full exact local invocations stay in private evidence; public
invocations use relocatable path placeholders. CLI exports, usage,
command/validation logs and source evidence are
redacted for detected secret environment names and credential patterns.
`ARCHITRAVE_BENCH_SECRET_ENV_VARS` adds nonstandard secret names to both CLI shell
filtering and redaction. These are best-effort protections: review the summary
before publication and never publish raw host histories, credentials or private
traces. Host-owned persisted session files are not rewritten by the runner.

Completion, executable behavior and semantic judgment are separate. A successful
implementation oracle establishes only its tested behavior. Audit exit zero or
an answer matching JSON shape cannot pass an audit: semantic adjudication,
identified defects, false positives and correct unknowns remain **null** until a
real independent review. The ambiguous case likewise remains unadjudicated;
stopping for necessary input is not implemented completion. An overall nonzero
exit can therefore mean pending semantic review rather than a failed behavior
test; retain all rows, including failures.

Behavior completion requires both successful execution and the evaluator's
completed JSON result matching the selected check, target, variation and fresh
invocation ID. Missing, malformed, mismatched and premature-exit reports fail.
The Python oracle catches target `SystemExit`, including exit zero, before
reporting assertion completion. This is a validation-process contract, not
authentication or a sandbox against arbitrary malicious target code. Native
dispatch checks include satisfied, unsatisfied and mixed nonempty express
obligations; express waives only the empty-list restriction.

The existing scorer can validate finding references without judging semantics:

```bash
python scripts/score-semantic-cases.py --host-findings /private/findings.json \
  --target /private/run/scenario/arm/rep-0/worktree
```

Each record requires code and source paths/line ranges, source status/authority,
scenario, alternative/unknown, remedy, falsifier and confidence. Mechanical
validation checks existing references and declared statuses, not whether the
passage supports the conclusion. The existing independent `judge-bench.py`
receives source snapshots, findings, changes, observed question/tool requests
and behavior results. For domain rows it must separately adjudicate each finding;
counts must bind to those records. Producer receipts bind sanitized source
artifact bytes and each captured file to the original target snapshot and
redacted-text hashes. The judge verifies that binding before using source text;
missing bindings (including older receipts), missing files and digest mismatches
cannot qualify. A new review digest does not retroactively bind old evidence.

Deterministic boundary, frozen-input, authority, finding-reference, required
validation and interruption failures or missing mandatory observations override
optimistic reviewer JSON. Failed rows remain available for diagnostic judgment,
but cannot produce gate-eligible PASS or semantic completion. An audit whose
only pending outcome is `semantic_adjudication_unset` remains eligible when its
mechanical evidence is positive. Valid structured output alone is not a claim
that the reviewer is correct. Its evidence digest binds the review, and unknown
reviewer-family telemetry or failed reviewer execution cannot qualify a semantic
result. Producer rows remain immutable; retain the independently judged JSONL
alongside the summary. Domain judgments also emit `<judge-output>.public.jsonl`
(replacing its original suffix) with evidence-bound independently adjudicated
counts, or null when the reviewer result cannot qualify.

`question_request_count` counts observed `ask_user` tool requests, deduplicated
by call ID. The old lexical mention metric remains for compatibility and does
not measure genuine questions or necessity; answers and necessity stay unknown
unless independently inspected. Review complete outcome evidence for unnecessary
questions, missing defects, invented behavior and false positives.

Focused source checks (not agent-under-test qualification):

```bash
python scripts/test-benchmark-tools.py
python scripts/test-benchmark-runtime.py
python benchmarks/fixtures/domain-host/oracle.py functional benchmarks/fixtures/domain-host/source
```

These include real Python/TypeScript/C# counterexamples and repairs when their
toolchains are available, plus owned-process control tests. No scripted process
test is evidence of a live Copilot interruption or of agent defect recognition.

## Domain fidelity (1.2.0 prerelease)

Use the existing scorer with `--domain --blind` to obtain D01-D13 without
expected answers, then `python scripts/score-semantic-cases.py --domain answers.json`.
Answers use the same `{"case", "result", "rationale"}` objects as analysis
calibration. Typed correctness and nonempty rationale are mechanical checks,
not independent assessment of reasoning, tool actions or business correctness.

`python scripts/test-domain-fidelity.py` executes the intentionally defective
Python and functional TypeScript application under `fixtures/domain-audit`.
It reproduces positive/negative rules, distinct actor boundaries, incorrect
translations and a coordinated two-thread revocation race; it also exercises
valid guards and unknown-preserving translations. The synthetic accepted rules
are in `domain.md`, not inferred from code. TypeScript needs Node 22.7+ with
default module detection and `--experimental-strip-types` (22.23.5 exercised);
a skip is not a qualified language run.
This tests the audit substrate, not agent behavior, actual host loading or an
owner application. See [release evidence](../docs/domain-release-evidence.md)
for source qualification and unresolved empirical/release holds.

The existing analysis suite also includes D1-D6 delivery-authenticity decisions:
original mandate versus a narrowed SPEC, fake/flag-off fresh-demo rejection,
approved local emulators and environment selection, explicitly requested
isolated test doubles, visual-reference preservation, stale source/config
evidence, and reuse of an already valid owner grant. These are evaluation inputs,
not substitute product integrations. `score-semantic-cases.py --analysis --blind`
withholds expected answers. Mechanical expected-answer matches alone do not
establish semantic quality, live enforcement or improved model performance.

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
- task-required artifact checks (Storybook files, contract/docs updates; Run or learning paths only for explicitly selected experiments);
- optional LLM/human judge verdicts.

**Implementation clarity and maintainability**
- changed files, additions, deletions, net LOC;
- dependency/config churn (`package.json`, `*.csproj`, `project.yml`, lockfiles);
- YAGNI findings: speculative abstraction, unused config, wrapper-only layers, reinvention of repo/native/stdlib capability;
- Storybook-first evidence for UI and source-backed domain meaning before derived backend contracts.

**Agent process quality**
- requested observable behavior delivered against original sources and applicable checks;
- settled domain decisions reused, consequential unknowns kept explicit;
- existing seams reused and unnecessary abstractions/ceremony avoided;
- option comparison only where materially different alternatives warrant it;
- applicable independent review evidence, not document or agent counts;
- Run/recovery/learning artifacts only when the experiment explicitly requires them.

Routine tasks do not require a tournament, plan document, `.architrave/runs`
or learning files. Their absence must not reject an otherwise successful row.
The explicit LongBuild, recovery, checkpoint, deployment-policy and learning
experiments retain their declared artifacts and checks; keep those legacy Run
experiments separate when interpreting current-workflow qualification. Removing
irrelevant artifact requirements does not waive failed behavior, validation,
agent execution or requested-control checks. Mechanical row success still needs
source-grounded review of actual outcomes; an existing file is not proof of them.

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
| Actor provenance and review scope (#32) | Evidence-first policy: transport type is not owner authority; retained/unverified sources differ from semantic sampling | A13 agent-originated `user.message`, unknown actor, preserved genuine owner appendix direction; A14 faithful forwarding positive control, partial semantic review vs whole-document structural check. Fixtures, not a claim of evaluated model performance |
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
- `expectedArtifacts`: task-required files/directories; every missing entry fails the row, so never require optional process artifacts for routine work;
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
- **Full-stack:** source/domain-grounded API/UI change; derive the contract before implementation and bind UI and backend to it.
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
untrusted evidence, recursively blinds producer identity and absolute target,
cell and source paths across the entire evidence object before hashing or
enveloping it (including tool/question arguments, validation commands and
interruption metadata), preserves file-relative source locations, verifies zero
tool requests, and keys resumability by reviewer,
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
