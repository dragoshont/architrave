# Benchmark Research Notes

This benchmark harness follows current practice for agent evaluation:

## What The Field Does

- **SWE-bench / Mini-SWE-agent / SWE-ReX:** use real repositories or sandboxed shell environments, isolate each run, and grade by whether the task is resolved. This is the right model for coding agents because tests and final state are more reliable than transcript-path matching.
- **Terminal-Bench:** focuses on long-running terminal tasks and reports task-resolution success. It reinforces that workspaces need timeouts, isolated sandboxes, and first-class DNF outcomes.
- **OpenAI agent evals:** start with traces while debugging, then promote good/bad examples into datasets and repeatable eval runs. This maps directly to Architrave's run artifacts and benchmark scenarios.
- **LangSmith:** distinguishes offline datasets from online traces, and recommends human, code, LLM-as-judge, and pairwise evaluators. It also recommends starting with 10-20 curated examples and adding failures back into the dataset.
- **Inspect AI:** formalizes evals as dataset + solver/agent + scorer, with sandbox support and transcript review. Architrave's runner mirrors that shape without taking a framework dependency yet.
- **Anthropic agent research:** says coding agents are promising because code has objective tests, but multi-agent systems need end-state evaluation, observability, small initial eval sets, and human review for edge cases.
- **Promptfoo:** frames prompt/agent improvement as test-driven, not trial-and-error: define representative cases, run repeatable comparisons, analyze, then expand from failures.
- **ApprenticeOps:** already uses Copilot CLI/GitHub Models as a frontier judge path when direct API keys are not available. This benchmark keeps that path optional and Copilot-first.

## Design Decisions

1. **Use existing repos, never their working trees.** Every run gets a detached git worktree from a declared `baseRef`.
2. **Benchmark workflow features, not just code answers.** Architrave's value includes Storybook-first, contract-first, YAGNI, tournament, durable artifacts, and judge gates.
3. **Compare arms.** Start with `copilot-baseline` versus `copilot-architrave`; add local-plugin and other-agent arms later.
4. **Keep deterministic checks first.** Quick gates and backend checks run before any LLM judge is trusted.
5. **Capture raw traces.** Copilot JSONL, session markdown, validation logs, diff stats, and prompts are kept under `.architrave/bench/runs/<run-id>/`.
6. **Use LLM/human judges for fuzzy dimensions.** UI quality, implementation clarity, and over-engineering require review. Use blind/pairwise human review for key comparisons.
7. **Measure cost and speed when exposed.** Copilot JSON events expose model id and output tokens; full input/cost may need CLI footer/session logs or provider-specific adapters later.
8. **DNF is data.** Timeout, tool failure, and validation failure are result rows, not reasons to discard a run.

## Planned Loop Engineering

The next feature should convert benchmark failures into loop-engineering inputs:

1. Run benchmark suite.
2. Summarize failures by rubric dimension.
3. Promote recurring failures into `knowledge/*.md`, agent prompts, gates, or scenario additions.
4. Re-run the same frozen scenarios plus new failure-derived scenarios.
5. Require no regression on baseline metrics before release.
