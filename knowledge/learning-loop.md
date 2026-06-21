# Learning loop pack

The cited rule base for Architrave's durable learning loop: how an agent keeps useful repo knowledge across context loss without turning config into a transcript, stale-memory cache, or unsafe source of truth.

Grounded in current practice:
- **Anthropic — Building effective agents:** start simple, add agentic complexity only when it improves outcomes, show planning steps, use ground truth from the environment, pause for human checkpoints, define stopping conditions, and test tool interfaces.
- **Anthropic — Multi-agent research system:** save plans to memory before context loss, use filesystem artifacts instead of relaying everything through the lead agent, evaluate end state at checkpoints, start with small eval sets, add observability/tracing, and scale effort to task complexity.
- **Claude Code memory:** separate project instructions from auto memory; add durable instructions when the same correction repeats; keep always-loaded instructions concise and specific; use scoped rules for path-specific guidance; hooks enforce behavior while instructions only guide it.
- **GitHub Copilot instructions and Memory:** repo facts should include build commands, architecture, conventions, and validation steps; instructions should be short and broadly applicable; stored repo facts need citations and validation against the current branch to avoid stale behavior.
- **LangGraph memory model:** distinguish short-term thread memory from long-term memory; separate semantic facts, episodic experiences, and procedural instructions; prefer smaller scoped memory documents when a single profile becomes hard to update; evaluate memory behavior.
- **OpenAI / Promptfoo eval guidance:** describe desired behavior, run representative test inputs, analyze results, and iterate; treat prompt and agent changes as test-driven, not trial-and-error.
- **MCP tool spec:** model-controlled tools need user-visible invocation, human approval for sensitive operations, structured schemas, result validation, audit logs, and no trust in untrusted tool annotations.

## Memory taxonomy for Architrave

Architrave uses four different stores because each has a different job:

1. **Run artifacts (episodic memory):** `.architrave/runs/<run-id>/` records what happened in one task: intake, tournament, plan, gates, judge verdicts, runtime evidence, final status. It is auditable and can resume after context loss, but it is not automatically treated as future instruction.
2. **Repo profile (semantic memory):** `.architrave/learning/repo-profile.md` is the concise, validated description of the repository: purpose, surfaces, architecture lanes, source-of-truth paths, build/test commands, recurring gotchas, and last-reviewed evidence.
3. **Candidate lessons (semantic/episodic bridge):** `.architrave/learning/repo-lessons.md` tracks repeated observations with evidence and occurrence counts. It is a review queue, not a command file.
4. **Promoted rules (procedural memory):** stable lessons move into `architrave.config.json`, `AGENTS.md`, `.github/instructions/*.instructions.md`, docs, or contracts after review. These are the places future agents are allowed to treat as standing guidance.

## Promotion rules

- Do not write one-off discoveries directly into `architrave.config.json`. Config is for stable pointers, policy knobs, source-of-truth paths, and verified commands.
- Add a candidate lesson when a fact would save a future agent time or prevent a repeated mistake. Include evidence: run id, file/command, current branch/source, and whether it was validated.
- Promote after the configured threshold, usually two occurrences, or immediately for a high-severity validated safety/build fact with human approval.
- Before promotion, validate against the current branch. Stale facts from closed/unmerged branches must not affect behavior unless the codebase still substantiates them.
- Keep always-loaded instruction files short and scoped. Use path-specific `.github/instructions/*.instructions.md` or docs for local rules instead of stuffing every detail into `AGENTS.md`.
- Redact secrets. Learning artifacts may say a secret reference exists or a config file is required; they must not contain secret values, tokens, private keys, cookies, or credentials.

## Repo profile shape

The repo profile should be compact enough to load/read quickly:

```markdown
# Architrave Repo Profile

## Purpose

## Surfaces And Lanes

## Source Of Truth

## Build And Test

## Architecture Map

## Recurring Gotchas

## Validated Facts

## Last Reviewed
```

Each durable fact should either cite a file/command/run artifact or be marked as unvalidated. When a fact becomes a standing instruction, move it to the appropriate promoted target and leave a short pointer in the profile.

## What the judge checks

The Adversarial Judge should treat missing learning artifacts on non-trivial work as a process gap, not as implementation failure by itself. It becomes a Blocker when the missing artifact hides an unsafe change, skipped sign-off, unverified runtime claim, stale lesson promotion, or secret leakage.

## Citations

- Anthropic — *Building effective agents* (simplicity, transparency, ground truth, evaluator-optimizer, tool design, human checkpoints, stopping conditions).
- Anthropic — *How we built our multi-agent research system* (plans saved to memory, artifacts over telephone, context management, end-state evaluation, tracing, small evals, human evaluation, token/coordination costs).
- Anthropic — *How Claude remembers your project* (CLAUDE.md vs auto memory, concise instructions, repeated-correction promotion, scoped rules, compaction survival, hooks for enforcement).
- GitHub — *About customizing GitHub Copilot responses* and *About GitHub Copilot Memory* (repo instructions, precedence, short self-contained instructions, repo facts with citations, validation against current branch, retention/staleness).
- LangChain/LangGraph — *Memory overview* (short-term vs long-term memory; semantic, episodic, procedural memory; profile vs collection tradeoffs; hot-path vs background memory writes).
- OpenAI — *Working with evals* (task description, test data, testing criteria, analyze/iterate; BDD-like behavior specification).
- Promptfoo — *Workflow and philosophy* (test-driven prompt engineering, representative failure modes, feedback loop).
- Model Context Protocol — *Tools* (human-in-the-loop for sensitive operations, structured schemas, result validation, tool usage audit, untrusted annotations).