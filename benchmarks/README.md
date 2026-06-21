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
- Architrave gate pass/fail (`gates/checks.sh`, backend checks, Storybook build/test where configured);
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
- model identity;
- output tokens and tool-call counts from CLI JSON events when exposed;
- raw session JSONL/transcripts for later trace grading.

## Primary Arms

Start small and controlled:

1. `copilot-baseline`: Copilot CLI with custom instructions disabled. This approximates a general development agent.
2. `copilot-architrave`: Copilot CLI using the installed Architrave agent. This tests the current published plugin.
3. `copilot-architrave-local`: optional local plugin dir or checkout for unreleased variants.

Later arms can add `claude`, `opencode`, `kilo`, or other external-agent commands. The runner is intentionally command-pluggable; it does not require direct Anthropic/OpenAI credentials.

## Dataset Shape

Use existing repositories, but never mutate their real working trees. Each scenario declares:

- `repo`: local repository path;
- `baseRef`: commit/tag/branch to check out in a detached benchmark worktree;
- `lane`: `ui`, `ux`, `backend`, `full-stack`, `infra`, `ops`, `learning`, or `yagni`;
- `prompt`: the benchmark task;
- `validation`: shell commands run after the agent finishes;
- `expectedArtifacts`: files/directories that should exist after the run;
- `scoring`: rubric notes for human/LLM review.

The runner creates `.architrave/bench/runs/<run-id>/<scenario>/<arm>/worktree` using `git worktree add --detach`. This makes it cheap to go back to older changesets, replay old product work, and compare agent variants against the same starting point.

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

Human feedback should become new scenarios. Do not bury it in chat.

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

## Safety Rules

- Use detached worktrees or temp clones only.
- Keep secrets out of prompts, artifacts, transcripts, and result rows.
- Use `--execute` as an explicit switch; default mode lists/plans but does not run agents.
- Treat DNF/timeouts as results, not crashes.
- Validate with deterministic gates before trusting an LLM judge.
- Keep benchmark prompts and expected outcomes versioned.
