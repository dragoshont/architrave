# Architrave Benchmark Judge Rubric

Judge the end state, not whether the agent followed one exact path. Valid agents may use different edits and tool sequences.

## Scores

Use 0-5 for each dimension:

- **Correctness:** acceptance criteria, deterministic gates, expected artifacts, no broken repo state.
- **Clarity:** implementation is understandable, scoped, and easy to review.
- **YAGNI:** uses the highest viable ladder rung; avoids speculative abstractions, dependencies, config, wrappers, and dead flexibility.
- **Process:** visible intake, Tournament of Options, YAGNI ladder, Recommended Plan, judge/sign-off artifacts when appropriate.
- **Repo Fit:** reuses Storybook/design map, existing backend seams, architecture docs, local conventions, and capability model.

## Verdict

- **PASS:** deterministic validation passed, no blocker, and all dimensions >= 4.
- **REVISE:** useful but has fixable gaps, missing evidence, or any dimension 2-3.
- **FAIL:** validation failed, unsafe/dishonest behavior, wrong architecture, missing core task, or any dimension <= 1.

## Findings

Findings must cite evidence from the row, validation, diff, artifacts, or transcript tail. Do not reward verbosity. Do not penalize small diffs unless they omit required behavior or safety.

For evidence-first analysis, use the execution policy's Evidence-first analysis
and the coverage map in `benchmarks/README.md`. Judge decisions and final
artifacts, not promises or instruction phrases. Necessary and unanswered
questions differ from unnecessary ones; lexical counts alone establish none of
necessity, delivery or substantive answer. Unattended scenarios remain unattended:
an unresolved owner-only decision is reported, not guessed or used to halt
independently safe work. Check passage entailment and correction propagation
semantically; deterministic numeric/enum scores cannot establish reasoning quality.

## Human Review

Recommend human review when the run changes UX visuals, backend contracts, infra, security/policy, or when the LLM judge is uncertain.
