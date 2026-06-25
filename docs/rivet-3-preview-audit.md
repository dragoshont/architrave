# Rivet Agent Operating Brief

Rivet is an agent orchestrator for engineering work that should stay grounded in specs, organizational evidence, and explicit trade-off review. One important capability is dual-model adversarial review: Rivet runs independent reviewers and then reconciles the results into one decision. The default review path should use native model-pinned subagents. The fallback path should use the existing CLI review runner when subagents fail, cannot be model-pinned, time out, or return malformed output.

## Collaboration Context

Rivet cannot be brought into this personal workspace directly, but Architrave can be brought into the corporate environment where Rivet runs. Future Rivet improvement work should assume access to the actual corporate codebase, Rivet's local harness artifacts, and organizational research sources rather than relying only on abstract prompts.

When the corporate environment is available, the improvement loop should be:

1. Read Rivet's current prompts, agents, harness files, output artifacts, and excluded local run folders.
2. Inspect representative feature runs, especially the 70+ local harness instances that show repeated workflows, failures, and design intent.
3. Ground proposed changes in code, commit history, Azure DevOps, Microsoft Learn, Eng Hub / organizational wiki, and current SDLC guidance.
4. Search current public material when relevant, including recent discussion of AI-assisted SDLC and vibe-coding workflows.
5. Convert findings into concrete Rivet operating rules, tests, fallback behavior, and visible gates.
6. Validate changes against real Rivet scenarios before generalizing them into the agent contract.

The local harness footprint is important evidence, not clutter: it can reveal how Rivet actually thinks, where it repeats itself, what features were attempted, and which patterns should become first-class workflows.

## Corporate Laptop Investigation Prompt

Use this section as the opening prompt when Architrave is available in the corporate environment where Rivet and its run artifacts exist.

```text
You are Architrave helping improve Rivet, an internal engineering agent. Start with a read-only investigation. Do not redesign from generic assumptions. Derive your conclusions from Rivet's code, prompts, local harness artifacts, generated files, commit history, organizational context, and representative feature runs.

Primary goal:
Understand whether Rivet's SDD harness has become too rigid, too slow, and too token-expensive, then propose a 3.0-preview redesign grounded in evidence.

Run mode:
- Assume this may run from a high-context model session such as GPT-5.5 extra-high with a large context window, but do not rely on context memory alone.
- Treat this as a long-running audit, not a single-turn answer.
- Create or update durable audit artifacts as you work so the run can resume after context loss, editor reload, network failure, or model handoff.
- Work in phases with explicit checkpoints; do not stop after shallow analysis if repo evidence remains available.
- Prefer making measurable progress autonomously. Ask the user only for blockers that cannot be resolved from code, harness artifacts, documentation, commits, tools, or online sources.

Online research requirement:
- Before proposing Rivet 3.0-preview, search current public sources for modern agent and AI-assisted SDLC practices.
- At minimum, check current Anthropic, Google, and Microsoft guidance relevant to agent architecture, subagents, hooks/callbacks, MCP/tools, evaluation, observability, long-running sessions, and app modernization.
- Treat online sources as research inputs, not as authority over the local Rivet evidence.
- Keep a source ledger with URL, title, vendor, retrieval date, and the concrete pattern extracted.

Evidence to inspect:
- Rivet source code and prompt templates.
- SDD-specific harness code.
- Generated harness files: contracts, design docs, adversarial analyses, organizational context files, run ledgers, and local excluded artifacts.
- At least 10-15 representative harness instances from the 70+ local feature runs.
- Commits associated with those runs.
- Azure DevOps work items / PRs / build or release evidence when available.
- MCP configuration and intended MCP usage, including Azure DevOps MCP and any other MCP servers referenced in configs, docs, scripts, prompts, harness artifacts, or commit history.
- Eng Hub / organizational wiki guidance when available.
- Microsoft Learn and relevant library/service documentation for workflows Rivet touches.
- Current public best-practice sources from Anthropic, Google, Microsoft, and other relevant agent/SDLC references discovered during research.

First pass outputs:
1. LOC and footprint report:
  - total Rivet LOC;
  - SDD-specific LOC;
  - prompt/template LOC;
  - generated harness artifact count and size;
  - excluded local run folder count and total size.
2. Harness sample table:
  - run/feature id;
  - user request shape;
  - task size: tiny, small, medium, large, high-risk, unknown;
  - artifacts produced;
  - estimated token cost if available;
  - elapsed time if available;
  - outcome: success, blocker, abandoned, reverted, unknown;
  - whether full SDD was justified.
3. Ceremony duplication report:
  - repeated prompt sections;
  - repeated context dumps;
  - repeated docs/code searches that did not affect design;
  - artifacts generated for low-risk tasks where a lightweight path would have been enough.
4. Failure-mode report:
  - common blockers from recent versions;
  - user complaints;
  - places where SDD prevented or delayed simple work;
  - places where SDD missed important evidence despite high cost.
5. Online best-practice source ledger:
  - source URL;
  - vendor/source type;
  - retrieval date;
  - relevant pattern;
  - how it applies or does not apply to Rivet.
6. 3.0-preview recommendation:
  - a task-risk router;
  - which tasks bypass full SDD;
  - which tasks require full SDD;
  - which artifacts are mandatory by risk level;
  - how YAGNI becomes visible;
  - how tournament and dual adversarial review fit without becoming mandatory ceremony.

Hard rules:
- Do not ask the user to summarize information that is present in the repo, harness artifacts, or commits.
- Do not treat the 70+ harness folders as junk. Mine them as the behavioral dataset.
- Do not propose a 3.0-preview design until you have measured the current 2.9.x footprint.
- Do not propose a 3.0-preview design until you have also refreshed current public guidance from Anthropic, Google, and Microsoft.
- Do not optimize only prompts if the issue is architecture, routing, or artifact lifecycle.
- Do not preserve full SDD for tiny/unit-test-only/one-class tasks unless evidence shows risk.
```

### Suggested Long-Running Audit Artifacts

Create the equivalent of these files in the Rivet repo or local audit workspace. Use the repo's existing harness conventions if they already exist.

```text
.rivet-audit/<timestamp-or-run-id>/
  00-intake.md
  01-source-ledger.md
  02-footprint-report.md
  03-harness-sample-table.md
  04-failure-mode-report.md
  05-native-replacement-map.md
  06-3.0-preview-plan.md
  phase-ledger.md
  evidence-index.json
  tool-preflight.json
```

Artifact rules:
- Keep artifacts concise; they are evidence, not a transcript dump.
- Store large raw outputs as files and link to them from the evidence index.
- Record tool failures and missing MCP/VPN/auth state explicitly.
- Checkpoint after each phase so a later agent can continue without rereading everything.
- If the repo already has ignored harness folders, mine them first and use their structure instead of inventing a parallel convention.

Recommended audit phases:

| Phase | Goal | Exit Criteria |
|---|---|---|
| 0. Preflight | Confirm repo state, tool/MCP/VPN readiness, and audit artifact path. | Tool preflight written; missing tools escalated. |
| 1. Footprint | Measure Rivet code, prompts, SDD/research/tournament/YAGNI/scanner modules, generated artifacts. | Footprint report written. |
| 2. Harness Mining | Sample representative runs from the 70+ harness instances. | Harness sample table written. |
| 3. External Research | Refresh Anthropic/Google/Microsoft/SDLC best practices. | Source ledger written. |
| 4. Architecture Diagnosis | Map current architecture and identify native replacement opportunities. | Current architecture + replacement map written. |
| 5. Refactor Plan | Propose phased 3.0-preview migration with metrics, gates, and rollback. | 3.0-preview plan ready for review. |

## Deep Audit and 3.0-Preview Refactor Launch Contract

Use this section when the goal is not just to inspect Rivet, but to start a major refactor toward a more native, lower-ceremony, Copilot/VS Code-centered architecture.

```text
You are Architrave helping launch Rivet 3.0-preview.

Goal:
Perform a deep audit of Rivet 2.9.x and produce an evidence-backed refactor plan that moves Rivet toward native Copilot/VS Code workflows: model-pinned subagents, MCP/tool preflight, lightweight hooks/gates, VS Code-friendly tasks, and Copilot CLI fallback only where native subagents/tools are unavailable or deterministic replay is required.

Long-running execution:
- Assume this audit may need a long GPT-5.5 extra-high session or equivalent.
- Use durable files and phase checkpoints so the work can survive context compaction or handoff.
- Do not collapse the investigation into a short recommendation before measuring code, harness artifacts, and modern public practice.
- Continue autonomously through the audit phases while evidence remains accessible.

Current-practice research:
- Search online during the audit for current Anthropic, Google, and Microsoft guidance on agents, multi-agent systems, MCP/tools, hooks/callbacks, state, artifacts, tracing, evaluation, and app modernization.
- Start with these source families, then add more if the Rivet repo points elsewhere:
  - Anthropic: effective agents, multi-agent research, MCP/tool design, Claude Code/Agent SDK patterns.
  - Google: Agent Development Kit, ADK graph workflows, callbacks/plugins/hooks, sessions/state/memory, artifacts, evaluation, observability, Agent Engine / Gemini Enterprise Agent Platform.
  - Microsoft: GitHub Copilot/VS Code agent features, Foundry Agent Service, Semantic Kernel Agent Framework, Azure DevOps MCP, .NET app modernization, NuGet/.NET upgrade guidance.
- Record each source in the source ledger with the concrete pattern it supports.

Initial source anchors:
- https://www.anthropic.com/engineering/building-effective-agents
- https://www.anthropic.com/engineering/multi-agent-research-system
- https://adk.dev/
- https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale
- https://learn.microsoft.com/en-us/azure/ai-foundry/agents/overview
- https://learn.microsoft.com/en-us/semantic-kernel/frameworks/agent/
- https://learn.microsoft.com/en-us/dotnet/core/porting/
- https://learn.microsoft.com/en-us/nuget/concepts/auditing-packages

Native-first constraints:
- Developers primarily use VS Code and Copilot CLI.
- Prefer VS Code/Copilot-native mechanisms when available: agent/subagent orchestration, model pinning, MCP configuration, workspace instructions, agent/prompt files, VS Code tasks, and terminal-friendly commands.
- Keep custom CLI harness code only where it provides deterministic reproducibility, offline auditability, fallback behavior, or integration with existing corporate systems.
- Do not preserve custom process spawning if native subagents can do the same job with equivalent reliability.
- Do not require developers to operate a separate bespoke UI for common flows.
- Keep artifacts readable from the repo and VS Code; avoid creating large opaque local footprints unless they are summarized and indexed.

Hooks/gates target model:
- Preflight hook: classify task size/risk, repo state, required tools, VPN/auth/MCP readiness, and whether full SDD is justified.
- Research hook: record sources queried, source failures, retries, contradictions, and confidence.
- YAGNI hook: record reuse search, selected ladder rung, deferred work, and any long-term override.
- Tournament hook: run only when useful; store options, scores, rejected alternatives, and the winning plan.
- Dual-review hook: run model-pinned Claude/GPT subagents when available; fall back to CLI reviewers if subagents fail.
- Implementation gate: run deterministic build/test/static checks for the touched slice.
- Post-run hook: summarize artifacts, token/time cost, blocked tools, and lessons into a compact ledger.

Required audit outputs before refactoring:
1. Current architecture map:
  - CLI entry points;
  - prompt/template files;
  - SDD/research/tournament/YAGNI/upgrade scanner modules;
  - hook/gate points;
  - MCP/tool adapters;
  - generated artifact lifecycle;
  - Copilot CLI / VS Code integration points.
2. Native replacement map:
  - what can move to native subagents;
  - what can become VS Code tasks or simple scripts;
  - what should remain a deterministic CLI fallback;
  - what should be deleted;
  - what needs new MCP/tool preflight.
3. Complexity report:
  - total LOC and module churn;
  - SDD/research/tournament/YAGNI/scanner LOC;
  - duplicated prompts/templates;
  - generated artifact size and count;
  - token/time cost per representative run.
4. Scenario replay report:
  - replay or inspect representative harnesses from SDD, research, tournament, YAGNI, NuGet, .NET, and scanner flows;
  - classify each old run by task risk and whether the new router would choose tiny/small/medium/full.
5. 3.0-preview refactor plan:
  - phases;
  - deletion targets;
  - migration adapters;
  - compatibility/fallback plan;
  - deterministic gates;
  - rollback plan;
  - success metrics.

Refactor strategy:
- Use a strangler approach: add the task-risk router and native subagent path first, then migrate one workflow at a time.
- Do not rewrite all 25k+ lines at once.
- Keep old CLI behavior behind a fallback path until the native path is proven on real harness scenarios.
- Prefer deleting duplicated prompt/harness code over wrapping it in another abstraction.
- Require before/after metrics for every refactor slice: LOC, token cost, elapsed time, artifact count, success/blocker rate, and developer-visible complexity.

Success criteria for 3.0-preview:
- Tiny and one-class tasks no longer trigger full SDD.
- Missing MCP/VPN/auth/tool problems are raised before deep research hangs.
- Tournament and YAGNI are visible only at the right depth.
- Dual-model adversarial review uses native subagents by default and CLI fallback only on failure.
- NuGet/.NET/scanner workflows produce actionable, deduplicated, source-attributed findings.
- Developers can run and inspect the workflow naturally from VS Code and Copilot CLI.
- The harness footprint shrinks or becomes indexed/summarized enough that 70+ runs are useful evidence rather than local clutter.
```

Suggested local measurement commands, to adapt after inspecting the actual repo layout:

```bash
# Broad footprint
git ls-files | wc -l
git ls-files | xargs wc -l | sort -n | tail -40

# SDD/harness surfaces
rg -n "SDD|spec-driven|contract|adversarial|tournament|YAGNI|judge|evaluator|eval|TDD|test-driven|characterization|harness" .
find . -iname '*sdd*' -o -iname '*harness*' -o -iname '*contract*' -o -iname '*adversarial*'

# MCP/tooling surfaces
rg -n "MCP|mcp|Azure DevOps|ado|Eng Hub|wiki|incident|tool" .
find . -iname '*mcp*' -o -iname '*tool*' -o -iname '*server*'

# Local excluded run artifacts, if present
find . -type d \( -iname '*harness*' -o -iname '*run*' -o -iname '*artifact*' \) | sed -n '1,200p'

# History and churn around SDD
git log --oneline --decorate --all --grep='SDD\|harness\|contract\|YAGNI\|tournament'
git log --name-only --pretty=format: -- . | sort | uniq -c | sort -nr | sed -n '1,80p'
```

## Main Functionalities

These are the current top-level Rivet capabilities to refine into concrete workflows.

| Capability | Intent | Needs More Detail |
|---|---|---|
| Spec-driven development | Turn requirements into SDD/ADR-style design artifacts, implementation slices, gates, and traceable acceptance criteria before coding. | Yes |
| Deep organizational research | Research across Azure DevOps, codebase, commit history, Microsoft Learn, Eng Hub / organizational wiki, and related internal sources before design decisions. | Yes |
| Tournament of options | Compare viable design/implementation options during the design phase, especially for SDD and research-backed architecture choices. | Yes; current implementation may be incomplete |
| Visible YAGNI | Make minimalism and anti-overengineering visible as a first-class decision gate, not only an implicit prompt rule. | Yes |
| NuGet upgrade workflow | Plan, execute, test, and review dependency upgrades with package-specific risk, compatibility, and rollback handling. | Yes |
| .NET upgrade workflow | Plan, execute, test, and review SDK/runtime/framework upgrades with solution-wide compatibility checks and migration evidence. | Yes |
| Repository vulnerability and upgrade scanner | Scan for vulnerable packages, package upgrades, deprecated packages, SDK/runtime upgrades, and cross-ecosystem component inventory. | Yes |
| Judge and evaluator | Evaluate SDD, research, tournament options, implementation plans, and final outputs with explicit rubrics, deterministic evidence, and model-backed review where useful. | Yes |
| TDD / characterization testing | Make bug investigation and feature work test-driven where possible: reproduce, characterize, implement, and prove with narrow gates. | Yes |

## Capability Detail Backlog

Use this section to capture scenarios as they are provided.

### 1. Spec-Driven Development

Rivet's SDD capability is a CLI-driven harness that tries to understand a feature before implementation. It produces harness files such as contracts, adversarial analysis, organizational context, and a design document. It should enforce YAGNI, but it also needs to perform deep repository and documentation research before proposing a design.

Expected SDD behavior:
- Gather requirements from the user, work item, repository state, and relevant organizational context.
- Search deeply through the target codebase, including neighboring implementations, tests, API surfaces, and commit history.
- Search repository documentation and service documentation for the client, platform, or service being changed or troubleshot.
- Investigate relevant library APIs, compatibility constraints, migration notes, and service contracts before choosing a design.
- Produce a concrete contract and design document that trace back to requirements and research evidence.
- Run adversarial analysis against the proposed design before implementation.
- Make YAGNI explicit: choose the smallest current solution that satisfies the requirement while preserving security, correctness, data safety, and meaningful tests.

Observed failure modes:
- The harness has become rigid: even very small tasks, including one-class changes or unit-test-only work, still pay the full SDD overhead.
- Small regular maintenance tasks can become dramatically slower than the implementation itself.
- SDD consumes about 80k tokens in some runs, which crowds out useful code context and makes the agent slower.
- Recent iterations have not improved perceived performance; versions have reached `2.9.35`, and the desired next step is a serious `3.0-preview` revamp rather than another incremental prompt tweak.
- The SDD implementation may have grown to roughly 10k lines by itself and the broader Rivet codebase may be over 25k lines. This needs actual measurement.
- Users are raising blocker issues in recent launches, suggesting the harness is not only slow but also failing productively at the wrong layer.

Revamp hypothesis:
- SDD should be a routing system, not a mandatory ceremony.
- Task size and risk should determine the harness depth.
- Tiny tasks should use a lightweight path: understand local code, make the change, run the narrow gate, and optionally write a short note.
- Medium and high-risk tasks should use the full SDD path with research, contract, tournament, adversarial analysis, and implementation gates.
- The harness should spend tokens on discriminating evidence, not repeated scaffolding or broad ritual.

Measurement plan for the Rivet repo:
- Measure total Rivet line count and SDD-specific line count.
- Count SDD harness files, templates, generated artifacts, and excluded local run folders.
- Sample several of the 70+ feature harness instances and classify them by task size, artifacts produced, token usage, elapsed time, outcome, and blocker reason.
- Identify repeated prompt/template sections that consume tokens without changing the decision.
- Identify places where SDD required documents even though the task should have used a lightweight path.
- Compare `2.9.x` iterations to see whether added logic improved outcomes or only increased ceremony.

3.0-preview direction:
- Introduce an explicit routing gate before SDD starts: tiny, small, medium, large, high-risk, or unknown.
- Let tiny/small tasks bypass full SDD while preserving local evidence and tests.
- Make full SDD opt-in by risk and uncertainty, not unconditional.
- Split research into targeted passes: codebase, organizational docs, service docs, library/API compatibility, and history.
- Make the tournament and YAGNI decisions visible in the design artifact.
- Use dual-review/adversarial analysis for the design only when the task risk justifies it.
- Treat token budget as a first-class resource: summarize or index stable context instead of re-emitting it every run.
- Preserve CLI reproducibility, but reduce generated file footprint for low-risk work.

Questions to answer later:
- What is Rivet's source of truth: SDD, ADR, work item, PRD, issue, or a generated spec?
- What gates must pass before implementation starts?
- How should requirements trace into tests and final review?
- What is the exact threshold for bypassing full SDD?
- Which artifacts are mandatory only for high-risk work?
- How much of the 80k-token cost is useful evidence versus repeated harness scaffolding?

### 2. Deep Organizational Research

Rivet's deep-research capability has several flavors, but the common goal is to search deeply in the code and in the operational context of the task. It should investigate production incidents, interrogate available organizational systems, identify contradictions, and use judge-style review for confidence. The ambition is correct, but the current implementation appears fragile and hard to reason about.

Expected deep-research behavior:
- Search the codebase around the task, not just by keyword but by ownership, call graph, API surface, tests, and history.
- Search production or operational incident context when the task is about troubleshooting, reliability, migrations, or regressions.
- Query organizational systems through MCP/tools where available: Azure DevOps, source control, build/release systems, Eng Hub / wiki, service catalogs, incident systems, and documentation stores.
- Cross-check public documentation such as Microsoft Learn and package/library docs when APIs, SDKs, service behavior, or compatibility are involved.
- Interrogate contradictions instead of flattening them: old docs versus current code, incident notes versus telemetry, work item intent versus implementation history.
- Use a judge or adversarial review to evaluate whether the research is complete enough to support a design or implementation.
- Produce a research ledger that records sources queried, tools used, missing tools, retries, evidence quality, contradictions, and unresolved gaps.

Observed failure modes:
- Research hangs or runs too long without a useful progress model.
- MCP-backed sources often return too little data or fail to return the expected data.
- There is no clear mechanism to raise missing, disabled, unauthenticated, or inactive tools to the developer.
- Developers are expected to have the required MCP tools, VPN, and permissions, but the harness does not reliably preflight those assumptions.
- Some tools may need retry/backoff, but the current behavior does not make retry policy visible or robust.
- When tools are unavailable, Rivet can continue with partial evidence without making the loss of evidence explicit enough.
- The deep-research driver is large, possibly around 8k lines, and the implemented patterns are no longer easy to remember or audit.
- The repository wiki and GitHub history likely contain the design intent, but the current harness does not make that history easy to recover.

Required tool-readiness behavior:
- Run a research preflight before deep research starts.
- Enumerate required and optional tools for the task: code search, git history, Azure DevOps, MCP servers, wiki/docs, incidents, package docs, service docs, web search.
- Treat Azure DevOps MCP as a known intended source, but do not assume it is the only one; discover the intended MCP inventory from config files, prompt text, harness artifacts, scripts, docs, and commit history.
- Classify each tool as available, unavailable, unauthenticated, VPN-required, permission-denied, timeout-prone, or not applicable.
- If a required tool is missing or inactive, raise a clear developer action item instead of silently continuing.
- Where possible, offer an enablement path: MCP config to add, VPN/auth prerequisite, Rivet-agent capability to activate, or documented manual fallback.
- Retry transient tool failures with bounded backoff and record every retry in the research ledger.
- Treat missing evidence as a first-class risk in the final design, not as a hidden implementation detail.

Revamp hypothesis:
- Deep research needs a capability-negotiation layer before it starts collecting evidence.
- Research should be staged and bounded: preflight, source plan, collection, contradiction pass, synthesis, judge, and escalation.
- The harness should produce useful partial results without pretending the investigation is complete.
- Rivet should distinguish between "not enough evidence to proceed" and "enough evidence for a small safe local change."
- The research engine should optimize for evidence quality and coverage, not just volume of collected text.

Measurement plan for the Rivet repo:
- Measure the deep-research driver size and identify its main modules, strategies, prompts, and tool adapters.
- Sample research-heavy harness runs and record which tools were requested, which succeeded, which failed, and whether failures were visible to the user.
- Compare research outputs against available wiki and GitHub history to see what evidence was missed.
- Identify hangs: where time is spent, whether it is tool latency, retries, unbounded loops, model synthesis, or oversized context.
- Build a matrix of MCP tools and their failure modes: missing config, disabled server, VPN/auth, permission, timeout, empty result, malformed result.
- Identify patterns from modern deep-research agents that should be adopted only after grounding in Rivet's actual code.

3.0-preview direction:
- Add a tool/capability preflight with explicit developer-facing remediation.
- Add a research plan before collection: what sources are needed, why, and which are mandatory.
- Add bounded retries and timeout budgets by source type.
- Add a research ledger with source coverage, missing tools, contradictions, confidence, and unresolved gaps.
- Add a contradiction pass before synthesis.
- Add a judge gate that evaluates research sufficiency, not just the final design.
- Make "blocked by missing tool" a valid outcome with precise enablement instructions.
- Mine Rivet's wiki and GitHub history to recover existing patterns before replacing the research engine.

Expected sources:
- Azure DevOps work items, PRs, builds, releases, and comments.
- Azure DevOps MCP and any other intended MCP servers discovered from the Rivet repository, local config, harness artifacts, wiki, or commit history.
- Current codebase and tests.
- Commit history and prior design decisions.
- Microsoft Learn.
- Eng Hub / organizational wiki.
- Any project-specific runbooks, templates, or internal standards.

Questions to answer later:
- Which sources are authoritative when they disagree?
- What should Rivet cite in the SDD versus keep as background evidence?
- How should Rivet handle private or sensitive organizational context in artifacts?
- Which tools are mandatory for each research flavor?
- Which MCP servers did Rivet intend to use originally, and which are still active, missing, disabled, or obsolete?
- Can Rivet enable or configure missing MCP tools directly, or should it only raise remediation instructions?
- What is the right fallback when VPN or organizational auth is missing?
- How should the harness distinguish empty-but-valid results from broken tools?
- What timeout, retry, and partial-result policy should each source type use?

### 3. Tournament of Options

Rivet's tournament capability is the idea that, for an idea or task, the agent should explore multiple viable options before choosing one. This should apply broadly: feature analysis, implementation strategy, documentation structure, migration plan, troubleshooting approach, or other engineering tasks. The important part is not ceremony; it is controlled diversity plus scoring.

Expected behavior:
- Run during design and research, before implementation, when the task has meaningful uncertainty or trade-offs.
- Generate multiple candidates that are actually different, not three rewrites of the same plan.
- Compare at least a minimal viable option, a proper architectural option, and a defer/ask/research-more option when uncertainty is material.
- Score options on correctness, organizational fit, risk, test burden, blast radius, YAGNI, reversibility, user value, and evidence quality.
- Let candidates compete through a judge, rubric, pairwise comparison, or debate loop when the risk justifies the added cost.
- Select a recommended plan with explicit rejected alternatives and the evidence that changed the decision.

Important source-backed patterns to verify against Rivet's code and wiki:
- Anthropic, "Building effective agents" (2024): tournament belongs in the family of routing, parallelization/voting, orchestrator-workers, and evaluator-optimizer workflows. The caution is to add complexity only when simpler workflows fall short.
- Anthropic, "How we built our multi-agent research system" (2025): multi-agent systems help with breadth-first research and parallel independent directions, but can use roughly 15x chat token cost and need explicit effort scaling, delegation rules, observability, and tool design.
- Self-Consistency (Wang et al., 2022): sample diverse reasoning paths and choose the most consistent answer. Useful for cheap candidate generation and aggregation.
- Tree of Thoughts (Yao et al., 2023): explore multiple reasoning paths, self-evaluate, look ahead, and backtrack. Useful when design choices have branching consequences.
- Multiagent Debate (Du et al., 2023): multiple model instances propose and debate answers over rounds, improving reasoning/factuality in some tasks. Useful for high-risk decisions, but too costly for tiny work.
- ChatEval (Chan et al., 2023): multi-agent debate can be used for evaluation; relevant for Rivet's judge/tournament scoring design.
- MT-Bench / Chatbot Arena LLM-as-judge (Zheng et al., 2023): LLM judges are scalable but have position, verbosity, self-enhancement, and reasoning biases. Rivet should mitigate these when scoring options.
- Reflexion (Shinn et al., 2023): feedback signals can be stored as verbal memory for later attempts. Rivet can use tournament results and judge findings as reusable learning, not just one-off output.
- Mixture-of-Agents (Wang et al., 2024): multiple model outputs can improve later-layer synthesis. Relevant as inspiration, but likely too expensive unless the task value warrants it.

Research seed references for the corp-laptop audit:
- Anthropic, "Building effective agents": https://www.anthropic.com/engineering/building-effective-agents
- Anthropic, "How we built our multi-agent research system": https://www.anthropic.com/engineering/multi-agent-research-system
- Wang et al., "Self-Consistency Improves Chain of Thought Reasoning in Language Models": https://arxiv.org/abs/2203.11171
- Yao et al., "Tree of Thoughts": https://arxiv.org/abs/2305.10601
- Du et al., "Improving Factuality and Reasoning in Language Models through Multiagent Debate": https://arxiv.org/abs/2305.14325
- Chan et al., "ChatEval": https://arxiv.org/abs/2308.07201
- Zheng et al., "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena": https://arxiv.org/abs/2306.05685
- Shinn et al., "Reflexion": https://arxiv.org/abs/2303.11366
- Wang et al., "Mixture-of-Agents Enhances Large Language Model Capabilities": https://arxiv.org/abs/2406.04692

Observed risk:
- Tournament may not be properly implemented today; it may be prompt-only, inconsistently invoked, or mixed into SDD without a clean artifact.
- If every task runs a heavy tournament, it repeats the SDD failure mode: too much ceremony for tiny tasks.
- If candidates are not forced to differ, the tournament produces fake diversity.
- If the same model writes and judges all options in one context, the tournament can collapse into self-confirmation.
- If scoring lacks evidence, the winner is just the most fluent option.

Revamp hypothesis:
- Tournament should be a risk-based design-phase tool, not mandatory for every task.
- Tiny tasks should skip tournament or use a one-paragraph alternative check.
- Medium tasks should use a compact tournament: 2-3 options, one rubric, one winner.
- High-risk or ambiguous tasks should use a stronger tournament: independent candidate generation, dual-model judging, explicit disagreement handling, and a durable decision artifact.
- Research-heavy tasks should use tournament to compare research strategies before spending large tool/token budgets.

Measurement plan for the Rivet repo:
- Find every tournament prompt, class, template, artifact, and generated output.
- Measure how often tournament is invoked across the 70+ harness runs.
- Classify tournament outputs: real alternatives, near-duplicates, or generic filler.
- Check whether scores are tied to evidence or only prose preference.
- Check whether the winning option maps to the implemented code or disappears after design.
- Check whether judge output was independent from candidate generation.
- Compare tournament cost to outcome: did it prevent rework, catch risk, improve design, or just add tokens?

3.0-preview direction:
- Add a tournament router: none, lightweight alternative check, compact tournament, or full adversarial tournament.
- Require option diversity: each candidate must differ in boundary, mechanism, risk, cost, or reversibility.
- Require evidence-backed scores and explicit rejected alternatives.
- Add bias mitigation for judges: shuffle option order, hide author/model identity where possible, penalize verbosity, and require concrete evidence.
- Preserve tournament artifacts only when they matter; summarize or discard low-risk alternative checks.
- Feed high-quality tournament findings into Rivet's memory/wiki so repeated design trade-offs become reusable.

Questions to answer later:
- What exact tournament papers or posts did Rivet originally rely on?
- Is tournament implemented as code, prompt text, generated artifact, or all three?
- Does Rivet currently run candidates independently, or in one shared context?
- Who scores: the same model, a separate judge, dual judges, or deterministic rubric?
- What tasks should never pay tournament overhead?
- How should tournament interact with SDD, YAGNI, and dual-review?

### 4. Visible YAGNI

YAGNI should be more than a prompt preference. In Rivet it should be a visible engineering decision gate that asks whether the current task really needs new capability, abstraction, dependency, configuration, harness ceremony, or long-term architecture. It must be grounded in codebase research, existing reusable logic, libraries, APIs, and user roadmap context.

Expected behavior:
- Make the YAGNI ladder visible in the design artifact.
- Record the first rung that satisfies the requirement.
- Treat new dependencies, abstractions, flags, factories, caches, and config knobs as things that need current evidence.
- Never simplify away security, data-loss prevention, accessibility, authorization, privacy, or meaningful tests.
- Search the existing codebase before declaring that new code, abstractions, libraries, or services are needed.
- Prefer existing repo patterns, already-installed libraries, platform/native capabilities, and standard library features when they satisfy the current requirement.
- Allow users to choose a longer-term solution when they know credible future features are coming, but require that choice to be explicit and evidence-backed.
- Show what was deferred and why, so YAGNI does not look like the agent forgot future needs.
- Revisit YAGNI after deep research and tournament outputs; a YAGNI decision made before understanding the codebase is not trustworthy.

Source-backed interpretation:
- Ward's Wiki / XP YAGNI: implement things when actually needed, not merely because they are foreseen; avoid polluting the codebase with guesses that turn out wrong.
- Martin Fowler, "Yagni": presumptive features impose build cost, cost of delay, cost of carry, and technical debt when the right future feature is built wrong. YAGNI applies to extra complexity for future capability, not to refactoring, tests, or practices that keep code malleable.
- Martin Fowler, "Design Stamina Hypothesis": design effort can improve long-term delivery when the project is above the design payoff line. YAGNI must not be misused as an excuse for no design.
- Anthropic, "Building effective agents": start with the simplest solution and add agent/workflow complexity only when it demonstrably improves outcomes.
- Anthropic, "How we built our multi-agent research system": scale effort to query complexity; multi-agent systems can cost about 15x chat interactions and should be reserved for tasks whose value warrants the extra cost.

Research seed references for the corp-laptop audit:
- Ward's Wiki, "You Arent Gonna Need It": https://wiki.c2.com/?YouArentGonnaNeedIt
- Martin Fowler, "Yagni": https://martinfowler.com/bliki/Yagni.html
- Martin Fowler, "Design Stamina Hypothesis": https://martinfowler.com/bliki/DesignStaminaHypothesis.html
- Anthropic, "Building effective agents": https://www.anthropic.com/engineering/building-effective-agents
- Anthropic, "How we built our multi-agent research system": https://www.anthropic.com/engineering/multi-agent-research-system

Visible YAGNI ladder:
1. Delete, skip, or do nothing if the current requirement does not need a change.
2. Reuse existing product behavior, repo pattern, helper, service, workflow, or generated artifact.
3. Use native platform capability, standard library, framework feature, or already-approved infrastructure.
4. Use an already-installed dependency or existing service integration.
5. Write tiny local code with tests.
6. Add a new abstraction, dependency, configuration knob, cache, factory, service, or harness phase only with current evidence.

Long-term-solution override:
- A user may choose a more complicated long-term solution when they know upcoming roadmap features or organizational constraints.
- Rivet should allow this, but require a visible override record:
  - future feature or roadmap item;
  - evidence source: Azure DevOps, design doc, wiki, user statement, production constraint, compliance/security requirement, or committed architecture direction;
  - incremental cost now;
  - cost of delaying;
  - risk that the future need changes;
  - rollback or simplification path if the future need disappears.
- The override should be reviewed in tournament and adversarial review when risk is material.

Observed risk:
- YAGNI may currently be mostly prompt text, not a visible artifact or gate.
- If YAGNI runs before SDD/research has found existing code and library affordances, it can recommend the wrong "simple" solution.
- If YAGNI is buried inside full SDD, tiny tasks still pay SDD overhead just to decide they do not need SDD.
- If YAGNI is too dogmatic, it can block valid long-term design choices that the user knows are coming.
- If YAGNI is too vague, it becomes a rubber stamp for whichever option the agent already prefers.

Revamp hypothesis:
- YAGNI should be cross-cutting but lightweight: task router, SDD, research, tournament, and implementation review should all expose the same decision ladder.
- The full YAGNI artifact should appear only for non-trivial tasks. Tiny tasks can use a short inline note.
- YAGNI should depend on research quality: if codebase/library search is incomplete, the YAGNI decision should say so.
- YAGNI should measure cost of carry and cost of delay, not only implementation effort.

Measurement plan for the Rivet repo:
- Find every YAGNI prompt, code path, generated artifact, checklist, and judge criterion.
- Determine whether YAGNI is implemented in the right harness layer: router, SDD, deep research, tournament, implementation, review, or all of them.
- Sample harness runs and classify whether YAGNI was visible to the user.
- Check whether YAGNI decisions cite existing reusable code, libraries, platform capabilities, or service APIs.
- Check whether user long-term intent can override YAGNI and whether that override is recorded.
- Identify false positives: YAGNI blocked or discouraged a necessary design investment.
- Identify false negatives: YAGNI failed to stop unnecessary abstractions, dependencies, config, or generated artifacts.
- Compare YAGNI outcomes against later commits: did deferred complexity actually become needed, or did speculative complexity become dead weight?

3.0-preview direction:
- Add a visible `YAGNI Decision` block to design artifacts for non-trivial tasks.
- Add a compact `YAGNI note` for tiny/small tasks that bypass full SDD.
- Require evidence of reuse search before approving new abstraction/dependency/config.
- Add an explicit long-term override path with cost-of-delay and cost-of-carry analysis.
- Make the YAGNI gate consume outputs from deep research and tournament rather than duplicating their work.
- Add judge criteria for YAGNI quality: evidence, visibility, appropriate complexity, and preservation of safety/testing.
- Track YAGNI decisions in harness artifacts so future audits can learn whether the decision was right.

Questions to answer later:
- Is YAGNI currently in the SDD harness, research harness, tournament, implementation prompt, judge rubric, or only global instructions?
- Does Rivet search deeply enough for existing reusable code before applying YAGNI?
- Does Rivet distinguish "future speculation" from "known roadmap constraint"?
- Which tasks require a full YAGNI artifact versus a one-line note?
- How often did past YAGNI decisions prove correct in the 70+ harness runs?

### 5. NuGet Upgrade Workflow

Rivet has a specialized NuGet upgrade flow that is already complicated and tuned for this kind of work. There is no recent strong feedback on it, so the first step should be an audit rather than a rewrite. The audit should look for low-hanging improvements in vulnerability detection, package-update planning, transitive dependency handling, output clarity, and verification gates.

Expected behavior:
- Inventory packages and transitive risk.
- Read release notes / advisories where relevant.
- Upgrade in reviewable slices.
- Run restore, build, tests, and package-specific smoke checks.
- Produce rollback notes.
- Distinguish vulnerability remediation from routine package freshness updates.
- Prefer minimal safe remediation for vulnerabilities, especially patch/minor updates when compatible.
- Trace vulnerable transitive packages back to the closest direct dependency before pinning a transitive package directly.
- Detect deprecated packages and suggested alternatives, not only vulnerable packages.
- Respect repository package-management style: `PackageReference`, `packages.config`, Central Package Management, `Directory.Packages.props`, private feeds, lock files, and pinned SDK behavior.
- Output machine-readable evidence where possible so later judge/review stages can reason over it.

Source-backed operational anchors:
- NuGet Audit runs during restore and reports warnings `NU1900`-`NU1905` for vulnerability/audit-source issues.
- `NuGetAuditMode` can audit direct or all dependencies; .NET 10 changes defaults toward transitive/all mode for `net10.0` targets.
- `auditSources` can separate vulnerability-data sources from package sources; `https://data.nuget.org/v3/index.json` is a vulnerability-data-only endpoint.
- `dotnet package list --vulnerable --include-transitive --format json` can produce machine-readable vulnerable package reports. On .NET 9 or earlier the command is `dotnet list package`; .NET 10 introduces the noun-first `dotnet package list` form.
- `dotnet package list --outdated` and `--deprecated` cover package freshness and deprecation signals.
- `dotnet nuget why` helps explain why a transitive package appears in the graph.
- Microsoft Component Detection can produce a graph-based component inventory across NuGet and many other ecosystems.

Research seed references for the corp-laptop audit:
- NuGet package auditing: https://learn.microsoft.com/en-us/nuget/concepts/auditing-packages
- NuGet VulnerabilityInfo API: https://learn.microsoft.com/en-us/nuget/api/vulnerability-info
- `dotnet package list`: https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-package-list
- Microsoft Component Detection: https://github.com/microsoft/component-detection

Measurement plan for the Rivet repo:
- Find NuGet upgrade prompts, code paths, scripts, generated artifacts, and scanner outputs.
- Identify which data sources are used: NuGet Audit, NuGet vulnerability API, Component Governance / Component Detection, GitHub advisories, Azure DevOps policy, private feeds, or custom corp systems.
- Check whether the flow handles direct, transitive, deprecated, outdated, abandoned, and no-fixed-version cases separately.
- Check whether the flow knows the repo package-management style before editing package files.
- Check whether updates are sliced by risk: vulnerability patch, minor safe update, major breaking update, broad modernization.
- Check whether rollback is practical: package diff, lock-file diff, restore/build/test results, and feature smoke tests.
- Review recent NuGet upgrade harness runs for false positives, hanging scans, over-broad upgrades, or missed vulnerabilities.

Low-hanging fruit to look for:
- Add or fix a dedicated audit pipeline that treats high/critical `NU1903`/`NU1904` as errors without breaking all local builds.
- Ensure `--include-transitive` is used when vulnerability scanning expects transitive coverage.
- Emit JSON reports for vulnerable/outdated/deprecated packages.
- Preflight command syntax based on installed SDK version: `dotnet list package` versus `dotnet package list`.
- Configure `auditSources` explicitly when package sources are private or nuget.org is blocked.
- Surface `NU1900` and `NU1905` as tool/source failures, not package vulnerabilities.
- Use `dotnet nuget why` or equivalent graph evidence before adding direct pins for transitive fixes.
- Keep vulnerability remediation separate from opportunistic major-version cleanup.

Questions to answer later:
- Is the existing tuned flow actually effective, or just complex?
- Which scanners does Rivet trust when they disagree?
- Does Rivet know when a package update is security-driven versus hygiene-driven?
- Does Rivet over-upgrade packages when a smaller vulnerability fix would do?
- Does Rivet create durable evidence that reviewers can validate?

### 6. .NET Upgrade Workflow

Rivet also has a specialized .NET upgrade flow. Like the NuGet flow, it appears complicated and tuned, but it has not recently received enough feedback. It needs an audit for correctness, upgrade slicing, compatibility checks, SDK/runtime inventory, and obvious low-hanging improvements.

Expected behavior:
- Inventory SDK, target frameworks, runtime images, CI agents, deployment hosts, analyzers, and package compatibility.
- Plan the migration in slices.
- Run solution-wide build/test and targeted runtime verification.
- Record breaking changes and rollback constraints.
- Distinguish SDK update, target framework update, runtime hosting update, container base image update, language-version update, analyzer update, and package compatibility update.
- Respect .NET support lifecycle: LTS versus STS, end-of-support dates, runtime patching, and hosting constraints.
- Read compatibility and breaking-change docs for every target version crossed.
- Identify unsupported technologies when moving from .NET Framework to modern .NET.
- Prefer pilot migrations on low-risk projects before broad solution-wide migrations.
- Keep build/test/runtime validation tied to the slice being upgraded.

Source-backed operational anchors:
- Microsoft .NET upgrade guidance says to upgrade when dependencies reach end of support, vulnerabilities appear, compliance requires it, or newer versions address performance/scalability limits.
- .NET releases yearly, alternating STS and LTS; LTS is usually the production-stability choice.
- The .NET SDK can target older frameworks, but developer tools should stay current for security and compatibility.
- Microsoft docs now recommend GitHub Copilot app modernization for AI-assisted .NET upgrades; .NET Upgrade Assistant is deprecated and should be used only when the modernization agent is unavailable.
- .NET compatibility docs categorize changes as allowed, disallowed, or requiring judgment, especially for public API and behavioral changes.

Research seed references for the corp-laptop audit:
- .NET upgrade overview: https://learn.microsoft.com/en-us/dotnet/core/porting/
- .NET compatibility rules: https://learn.microsoft.com/en-us/dotnet/core/compatibility/

Measurement plan for the Rivet repo:
- Find .NET upgrade prompts, code paths, scripts, generated artifacts, and test plans.
- Identify how Rivet inventories `global.json`, installed SDKs, target frameworks, Dockerfiles, CI images, deployment hosts, analyzers, and package compatibility.
- Check whether the flow handles .NET Framework-to-modern .NET differently from modern-.NET-to-newer-.NET upgrades.
- Check whether the flow reads version-specific breaking changes and support lifecycle information.
- Check whether upgrade plans are sliced or try to upgrade SDK, TFM, packages, analyzers, containers, and app modernization in one large move.
- Review harness runs for rollback quality and whether runtime validation matched the actual deployment model.

Low-hanging fruit to look for:
- Add a preflight inventory report: current SDK, `global.json`, target frameworks, runtime identifiers, container base images, CI agent images, and deployment runtime versions.
- Add support-lifecycle flags for out-of-support TFMs and runtimes.
- Add a compatibility-docs checklist for every version crossed.
- Split package upgrades from framework upgrades unless evidence says they must be combined.
- Add a pilot-project mode for large solutions.
- Add explicit rollback notes for `global.json`, TFM changes, package centralization, container images, and CI agent updates.

Questions to answer later:
- Does Rivet currently conflate NuGet updates with .NET runtime/framework upgrades?
- Does Rivet know the deployed runtime, or only the repo target framework?
- Does it account for CI/build agent and container image compatibility?
- Does it use deprecated Upgrade Assistant assumptions where modern Copilot app modernization guidance should replace them?
- What is the smallest safe upgrade slice for common corporate repos?

### 7. Repository Vulnerability and Upgrade Scanner

This scenario is broader than NuGet or .NET upgrade alone. Rivet should scan everything that looks like vulnerable dependencies, packages needing upgrade, deprecated components, unsupported SDKs, out-of-support target frameworks, stale runtime images, and upgrade-relevant tooling. This should become an inventory-and-prioritization layer that feeds the NuGet and .NET upgrade workflows.

Expected behavior:
- Discover package ecosystems present in the repo, not only NuGet.
- Scan for vulnerable packages, deprecated packages, outdated packages, stale SDKs, stale target frameworks, stale container images, stale CI agent images, and unsupported runtimes.
- Correlate findings across multiple data sources: NuGet Audit, Component Governance / Component Detection, package-manager outputs, GitHub/organizational advisories, Azure DevOps policy, and repository configuration.
- Separate findings into security, support-lifecycle, hygiene, modernization, and unknown-risk buckets.
- Prioritize by severity, exploitability/applicability, exposure, transitive path, deployment reach, and upgrade blast radius.
- Produce an actionable backlog rather than one giant upgrade PR.

Measurement plan for the Rivet repo:
- Find existing scanner code, scheduled scan outputs, vulnerability reports, Component Governance integrations, and package/source adapters.
- Identify all package ecosystems Rivet can detect today and compare against Component Detection's supported ecosystem list.
- Check whether scanner results are deduplicated across sources or reported multiple times.
- Check whether scanner failures are explicit: source unavailable, auth missing, VPN missing, empty result, unsupported ecosystem, malformed output.
- Check whether scan output feeds real upgrade workflows or stops at report generation.
- Review past scanner-driven harness runs for missed packages, noisy findings, or unactionable recommendations.

3.0-preview direction:
- Add a scanner preflight that inventories repo ecosystems and available scanner sources.
- Emit a normalized finding schema across NuGet, Component Detection, SDK/runtime, containers, and CI agents.
- Add source-confidence and source-failure metadata to every finding.
- Add deduplication across scanner sources.
- Route findings into specific workflows: NuGet vulnerability fix, NuGet hygiene update, .NET runtime upgrade, container base image update, CI agent update, or manual/security review.
- Add low-risk auto-plan mode for obvious patch-level security updates, but keep major upgrades and runtime changes gated.

Questions to answer later:
- Which scanner sources exist today, and which were intended but never enabled?
- Does Component Governance mean Microsoft Component Detection, an internal governance system, Azure DevOps Advanced Security, or several sources?
- What scanner findings should block builds versus create backlog items?
- How should Rivet prevent broad scanner output from becoming a massive risky upgrade PR?

### 8. Judge and Evaluator

Rivet is supposed to evaluate its own research, SDD, tournament options, implementation plans, and final outputs. This is distinct from merely asking another model for an opinion. The evaluator should have an explicit rubric, know which evidence it is judging, distinguish deterministic failures from semantic concerns, and produce actionable findings. The current suspicion is that Rivet claims to have a judge/evaluator but either does not actually run it consistently, runs it too late, or produces output that does not change decisions.

Expected evaluator behavior:
- Evaluate research sufficiency before design: source coverage, missing tools, contradictions, source quality, and unresolved gaps.
- Evaluate SDD/design quality before implementation: requirement traceability, contract clarity, YAGNI, risks, rollback, and test plan quality.
- Evaluate tournament outputs: real option diversity, evidence-backed scoring, bias risks, and whether the chosen option actually follows from the scores.
- Evaluate implementation readiness: deterministic gates available, TDD/characterization plan present where needed, and blast radius understood.
- Evaluate final output: acceptance criteria met, tests/builds run, known gaps disclosed, and claims remain capability-honest.
- Separate deterministic evidence from model judgment. A failed build, missing test, missing artifact, or schema violation should outrank a PASS from a model judge.
- Emit structured findings with severity, evidence, required fix, and what would change the verdict.

Observed failure modes to look for:
- Judge/evaluator is only prompt text and is not reliably invoked.
- Judge runs but does not block or revise anything.
- Judge sees only a summary, not the actual artifacts/evidence.
- Same model/context writes the plan and judges the plan, causing self-confirmation.
- Judge output is generic, unactionable, or not tied to files/artifacts/gates.
- Judge does not distinguish tool failure, missing evidence, and genuine design correctness.
- Judge cost is paid for tiny tasks where deterministic validation would be enough.

Measurement plan for the Rivet repo:
- Find all judge/evaluator prompts, code paths, generated reports, schemas, and CLI invocations.
- Count how often the evaluator ran across the 70+ harness instances and whether it changed the outcome.
- Compare evaluator verdicts with deterministic failures: build/test failures, missing artifacts, invalid schemas, missing tools, or incomplete source coverage.
- Sample PASS results and check whether they were justified by evidence.
- Sample blockers and check whether the evaluator caught them early enough.
- Identify whether evaluator outputs are consumed programmatically or only written as decorative artifacts.

3.0-preview direction:
- Define evaluator stages: research sufficiency, design/SDD readiness, implementation readiness, final review, and optional retrospective learning.
- Use deterministic validators first; use model judges for semantic quality and ambiguity.
- Use model-pinned subagents for higher-risk semantic review when available, with CLI fallback only on failure.
- Require structured evaluator output: verdict, severity findings, evidence references, required fixes, and what would change the verdict.
- Make `TOOLING_FAILURE` and `INSUFFICIENT_EVIDENCE` valid evaluator outcomes.
- Add a small evaluator benchmark from historical Rivet harness failures.

Questions to answer later:
- Where is the evaluator implemented today: prompt, CLI, code module, subagent, or harness artifact?
- Does it run before decisions, after decisions, or only at the end?
- Does it have a schema and deterministic consumers?
- Which evaluator outputs actually changed Rivet behavior in past runs?
- Should dual-model judging be default, risk-based, or reserved for Rivet 3.0 pilots?

### 9. TDD / Characterization Testing

Rivet should support test-driven work when investigating bugs, adding features, refactoring, upgrading packages, or modernizing .NET projects. This should not mean forcing a full SDD harness for every small task. It means that bug and feature work should start from the narrowest meaningful executable signal whenever possible.

Expected TDD behavior:
- For a bug, first try to reproduce the failure with a failing test, smoke script, log assertion, diagnostic check, or minimal scenario.
- For a feature, define at least one executable acceptance check before or alongside implementation.
- For refactors/upgrades, add characterization tests before changing behavior when feasible.
- If no test can be written cheaply, record the attempted reproduction and the substitute signal.
- Use the smallest meaningful gate: unit test, integration test, contract test, Storybook interaction, Playwright flow, CLI smoke, build, analyzer, or log/assertion check.
- Keep TDD visible but scaled: compact note for small work; full `tdd-plan.md` for medium/high-risk work.
- Treat tests as evidence for YAGNI and evaluator decisions.

Observed failure modes to look for:
- Rivet edits first and only tests after the fact.
- Rivet creates test plans but no executable checks.
- Full SDD is invoked just to add a small unit test.
- Bug investigations lack a failing reproduction or a substitute observable signal.
- Refactors/upgrades proceed without characterization tests or rollback confidence.
- Generated tests are too broad, brittle, or unrelated to the reported defect.

Measurement plan for the Rivet repo:
- Search for TDD, test-first, reproduction, characterization, acceptance, and smoke-test prompts or modules.
- Sample bug-fix harness runs and check whether a failing signal existed before the fix.
- Sample feature harness runs and check whether acceptance criteria mapped to executable tests.
- Sample NuGet/.NET upgrade runs and check whether characterization/regression tests were used.
- Compare tasks where tests were created versus tasks where full SDD was used without meaningful tests.
- Identify whether TDD artifacts are consumed by evaluator/judge outputs.

3.0-preview direction:
- Add a TDD router: bug repro, feature acceptance, refactor characterization, upgrade regression, or no-test-with-substitute-signal.
- Add `tdd-plan.md` only for medium/high-risk work; use inline TDD notes for small work.
- Make TDD part of the evaluator rubric: no executable or substitute signal means lower confidence.
- Ensure the task-risk router can choose a lightweight path for unit-test-only and one-class test tasks.
- Keep deterministic validation cheap and local before model-heavy review.

Questions to answer later:
- Is TDD implemented today or only implied in prompts?
- Does Rivet know the repo's test framework and quickest targeted test command?
- How often did historical bug fixes include a failing reproduction before the fix?
- How should TDD interact with SDD, YAGNI, evaluator, NuGet upgrades, and .NET upgrades?

## Dual-Review Operating Model

## Operating Model

1. Rivet receives one artifact, one acceptance-criteria set, and one review rubric.
2. Rivet launches two isolated reviewers with identical inputs:
   - Reviewer A: Claude-backed subagent.
   - Reviewer B: GPT-backed subagent.
3. Reviewers must not see each other's output until both reviews complete.
4. Rivet validates both review outputs against the same schema.
5. Rivet merges duplicate findings, highlights disagreements, and returns one final verdict.
6. If a subagent path fails, Rivet falls back to the CLI path for that reviewer and records the backend used.
7. Rivet must never silently downgrade to a single-review gate.

## Prompt Skeleton

```text
You are Rivet, the orchestrator for a dual-model adversarial review.

Artifact:
[PASTE ARTIFACT / DIFF / SPEC / PLAN HERE]

Acceptance criteria:
[PASTE TESTABLE REQUIREMENTS HERE]

Review rubric:
- Correctness against acceptance criteria
- Safety and security risks
- Operational failure states
- Data loss, rollback, and recovery
- Test coverage and missing adversarial cases
- YAGNI / unnecessary complexity
- Capability honesty

Run two independent reviews:
1. Reviewer A: use a Claude-backed subagent.
2. Reviewer B: use a GPT-backed subagent.

Both reviewers must receive the exact same artifact, acceptance criteria, and rubric.
Do not let either reviewer see the other reviewer's output before both have completed.

Each reviewer must return this schema:

MODEL: claude | gpt
BACKEND: subagent | cli-fallback
VERDICT: PASS | REVISE | FAIL | TOOLING_FAILURE
FINDINGS:
- severity: blocking | high | medium | low
  title: <short title>
  evidence: <concrete file/function/behavior or requirement>
  recommendation: <specific change>
MISSING_TESTS:
- <test or verification gap>
WHAT_WOULD_CHANGE_MY_VERDICT:
- <specific evidence or fix>

After both reviews complete:
- Validate both outputs against the schema.
- Merge duplicate findings.
- Preserve model disagreements explicitly.
- Pick the stricter verdict unless there is concrete evidence to downgrade it.
- Return one final orchestrator verdict and one implementation/revision checklist.

If either subagent fails to launch, cannot use the requested model, times out, or returns malformed output:
- Run that reviewer through the CLI fallback.
- Set BACKEND=cli-fallback.
- Preserve the original subagent error in metadata.

If both subagent and CLI fallback fail for a reviewer:
- Return TOOLING_FAILURE.
- Do not claim the dual-review gate passed.
```

## Failure Conditions That Trigger CLI Fallback

- `SUBAGENT_SPAWN_FAILED`, including errors like `spawn EBADF`.
- `MODEL_PIN_UNAVAILABLE`.
- `TIMEOUT`.
- `MALFORMED_REVIEW`.
- `EMPTY_REVIEW`.
- `TOOLING_RATE_LIMITED`.
- `CONTEXT_TOO_LARGE`.

## Shared Result Contract

```ts
type ReviewResult = {
  reviewer: "claude" | "gpt";
  backend: "subagent" | "cli-fallback";
  verdict: "PASS" | "REVISE" | "FAIL" | "TOOLING_FAILURE";
  findings: Array<{
    severity: "blocking" | "high" | "medium" | "low";
    title: string;
    evidence: string;
    recommendation: string;
  }>;
  missingTests: string[];
  whatWouldChangeMyVerdict: string[];
  rawOutputPath?: string;
  error?: string;
};
```

## Orchestrator Policy

```ts
async function runDualReview(input: ReviewInput): Promise<FinalReview> {
  const [claude, gpt] = await Promise.all([
    reviewWithFallback("claude", input),
    reviewWithFallback("gpt", input),
  ]);

  return reconcileReviews([claude, gpt]);
}

async function reviewWithFallback(model: "claude" | "gpt", input: ReviewInput): Promise<ReviewResult> {
  const subagent = await trySubagentReview(model, input);

  if (subagent.ok && isValidReview(subagent.result)) {
    return { ...subagent.result, backend: "subagent" };
  }

  const cli = await runCliReview(model, input);

  if (cli.ok && isValidReview(cli.result)) {
    return {
      ...cli.result,
      backend: "cli-fallback",
      error: subagent.error,
    };
  }

  return {
    reviewer: model,
    backend: "cli-fallback",
    verdict: "TOOLING_FAILURE",
    findings: [{
      severity: "blocking",
      title: "Review backend failed",
      evidence: `Subagent failed: ${subagent.error}; CLI failed: ${cli.error}`,
      recommendation: "Repair review tooling and rerun the dual-review gate.",
    }],
    missingTests: [],
    whatWouldChangeMyVerdict: ["At least one valid review result from this reviewer."],
    error: cli.error,
  };
}
```

## Scenario Backlog

Add new Rivet improvement scenarios here as they come up.

| Scenario | Expected Rivet Behavior | Notes |
|---|---|---|
| Subagent spawn fails | Fall back to CLI for that reviewer; mark backend metadata. | Example: `spawn EBADF`. |
| Claude and GPT disagree | Preserve disagreement, then choose stricter verdict unless downgrade is justified. | Do not average away blocking findings. |
| One reviewer passes, one fails | Final verdict is usually REVISE or FAIL, not PASS. | Explain why. |
| Reviewer output is malformed | Retry once if cheap; otherwise CLI fallback. | Schema validation is mandatory. |
| Context too large for one backend | Use the same chunking strategy for both reviewers or mark comparison invalid. | Avoid unequal evidence. |

## Tested Locally

On 2026-06-25, the same pattern was smoke-tested in VS Code Copilot:

- Claude-pinned subagent launched successfully.
- GPT-pinned subagent launched successfully.
- Both reviewed the same deliberately flawed phase-gating artifact and found the same core issue.
- Isolation smoke test confirmed reviewers did not see each other's output.