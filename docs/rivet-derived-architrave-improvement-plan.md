# Rivet-Derived Architrave Improvement Plan

This plan captures the Architrave-core improvements suggested by the Rivet 3.0-preview discussion. The intent is to generalize only the reusable engineering patterns, not to import Rivet's full SDD harness or domain-specific workflows into Architrave core.

## Goal

Make Architrave more native to VS Code/Copilot, more resilient during deep audits, and less prone to ceremony for small tasks.

## Non-Goals

- Do not hard-code Rivet-specific SDD, NuGet, .NET, or scanner workflows into Architrave core.
- Do not replace Architrave's existing Storybook-first / contract-first / judge-gated model.
- Do not introduce a bespoke UI or long-running service.
- Do not remove existing deterministic gates or learning-loop artifacts.

## Findings To Implement

| Finding | Architrave-Core Implementation | Why It Belongs In Core |
|---|---|---|
| Tool / MCP readiness is a first-order failure mode. | Add a generic tool/MCP preflight artifact and harness command. | Applies to Storybook MCP, Mobbin, SearXNG, ops tools, backend tools, and corp MCPs. |
| Full ceremony is too expensive for tiny tasks. | Add an explicit task-risk router before full intake/tournament/phase-ledger work. | Protects Architrave from becoming the same kind of mandatory harness. |
| Long-running audits need durable state. | Formalize deep-audit artifacts: source ledger, evidence index, subagent outputs, checkpoints. | Helps context compaction, agent handoff, and multi-hour investigations. |
| Subagent findings should not be lossy. | Store subagent outputs as files and pass references back to the orchestrator. | Reduces token churn and avoids coordinator summary loss. |
| YAGNI needs visibility. | Add a visible YAGNI decision block when it materially affects a design; compact note for small work. | Users can accept, challenge, or override minimalism with roadmap evidence. |
| TDD should guide bug and feature work. | Add a TDD / characterization-test hook to task routing and implementation gates. | Keeps feature/bug work evidence-driven and prevents unverified edits. |

## Source Anchors

- Anthropic, "Building effective agents" — https://www.anthropic.com/engineering/building-effective-agents — simple composable workflows, routing, parallelization, orchestrator-workers, evaluator-optimizer, tool interface quality.
- Anthropic, "How we built our multi-agent research system" — https://www.anthropic.com/engineering/multi-agent-research-system — tool design, effort scaling, tracing, checkpointing, subagent artifacts, source quality, token cost.
- Google ADK — https://adk.dev/ — graph workflows, callbacks/plugins, artifacts, sessions/state/memory, evaluation, observability.
- Google Gemini Enterprise Agent Platform scale docs — https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale — sessions, memory bank, runtime, tracing/logging/monitoring, evaluation.
- Microsoft Foundry Agent Service — https://learn.microsoft.com/en-us/azure/ai-foundry/agents/overview — agent identity, MCP tool catalog, observability, managed lifecycle, prompt/hosted agent distinction.
- Microsoft Semantic Kernel Agent Framework — https://learn.microsoft.com/en-us/semantic-kernel/frameworks/agent/ — modular agents, multi-agent collaboration, process orchestration.
- Promptfoo / existing Architrave benchmark notes — local `knowledge/learning-loop.md` and `benchmarks/RESEARCH.md` — prompt and agent changes should be test-driven, not trial-and-error.

These anchors were refreshed on 2026-06-25 for planning. Phase 5 should create the durable source ledger entries if implementation proceeds.

## Proposed Phases

| Phase | Name | Scope | Gate |
|---|---|---|---|
| 0 | Design Review | Validate this plan and decide scope for Architrave core. | Existing Adversarial Judge PASS after REVISE findings are resolved; dual-model review optional for Rivet pilots. |
| 1 | Artifact Contracts + Validators | Define artifact lifecycle, schemas/headings, POSIX/PowerShell validators, fixture tests, and summary integration before agent behavior changes. | `scripts/check-manifests.sh`, new validator fixtures, and `git diff --check` pass. |
| 2 | Task-Risk Router | Add task classification guidance, risk matrix, and minimal agent/rubric changes. | Fixtures or benchmark prompts prove trivial/small/medium/deep-audit routing. |
| 3 | Tool/MCP Preflight | Add `harness/tool-preflight.*`, inferred config behavior, schema, and docs. | Fixture tests cover available/missing/unauthenticated/permission/empty-result states. |
| 4 | TDD Hook | Add bug/feature/refactor test-first template, validator checks, and examples. | Fixtures cover bug repro, feature acceptance, characterization, and substitute signal. |
| 5 | Deep-Audit Artifacts | Add source ledger, evidence index, subagent artifact handoff, and checkpoints as one lifecycle. | Validator accepts concise artifacts and rejects missing metadata/redaction failures. |
| 6 | Visible YAGNI | Add YAGNI decision/note templates and judge rubric checks. | Tests/examples show full block for non-trivial work and compact note for small work. |
| 7 | Agent/Rubric/Docs Rollout | Update Architrave agent instructions, README, AGENTS stanza, examples, and install/update copied kit behavior after validators exist. | Manifest checks pass; copied-kit sync paths include new files. |
| 8 | Benchmark + Smoke Scenarios | Add scenarios proving trivial, small, medium, and deep-audit paths. | Benchmark smoke passes and documents before/after ceremony reduction. |

## Artifact Lifecycle Contract

New artifacts must extend the existing Architrave run-artifact and learning-loop model rather than creating a parallel memory system.

| Artifact | Created By | Required For | Validation | Summary Integration |
|---|---|---|---|---|
| `task-classification.md` | Architrave lead | Medium, large, high-risk, deep-audit; inline note for small/trivial | Required headings for non-small classes | `summary.json.taskClass` |
| `tool-preflight.json` / `.md` | Harness helper + Architrave lead | Deep research, runtime/ops, MCP-dependent UI, backend/infra with external tools | JSON schema + markdown heading checks | `summary.json.toolPreflight` |
| `tdd-plan.md` | Architrave lead | Bug fixes, features, refactors/upgrades where tests are meaningful | Required fields by task kind | `summary.json.tdd` |
| `source-ledger.md` | Architrave lead | Deep research, external/org research, long-running audits | Source metadata and redaction checks | `summary.json.sources` |
| `evidence-index.json` | Architrave lead | Long-running audits and source-heavy work | JSON schema, path containment, no secrets | `summary.json.evidence` |
| `subagents/*.md` | Architrave lead from specialist returns | Advisory subagent outputs that would otherwise be lossy | Redaction/path/heading checks | `summary.json.subagents` |
| `checkpoints/*.md` | Architrave lead | Deep-audit mode only | Phase/resume heading checks | `summary.json.checkpoints` |

The existing learning-loop taxonomy remains the source of truth:
- run artifacts are episodic memory;
- `repo-profile.md` is concise semantic repo memory;
- `repo-lessons.md` stores candidate lessons;
- promoted instructions/config/docs remain reviewed durable policy.

`source-ledger.md`, `evidence-index.json`, `subagents/*.md`, and `checkpoints/*.md` belong under run artifacts. They do not replace `repo-profile.md` or `repo-lessons.md`; they provide evidence that can later be summarized into those files.

## Mandatory-By-Risk Matrix

| Task Class | Run Directory | Intake | Tournament | YAGNI | TDD | Tool Preflight | Source Ledger | Judge |
|---|---|---|---|---|---|---|---|---|
| `trivial` | No | Inline only | No | No or inline | No unless bug needs repro | No | No | No |
| `small` | Usually no | Short local evidence | No, or one alternative sentence | Compact note | Compact note when bug/feature | No unless tool-dependent | No | No |
| `medium` | Yes | Visible intake | Compact | Compact or full if material | Required when bug/feature/refactor | If external tools needed | If external sources used | Optional or existing gate |
| `large` | Yes | Full | Full | Full | Required where executable validation exists | Yes if tools/MCP needed | Yes | Existing Adversarial Judge |
| `high-risk` | Yes | Full | Full + rollback | Full | Required or substitute signal documented | Yes | Yes | Existing Adversarial Judge; optional dual-model pilot |
| `deep-audit` | Yes | Full | Research strategy tournament | Full if recommendations affect design | Not always; use eval/benchmark instead | Yes | Yes | Existing Adversarial Judge; optional dual-model pilot |

Dual-model review is valuable for Rivet validation and high-risk pilots, but it should not become Architrave core's default semantic gate until evidence shows enough benefit over the existing Adversarial Judge plus deterministic gates.

## Phase Details

### Phase 1 — Artifact Contracts + Validators

Define the artifact contract before any Architrave agent prompt starts requiring the new behavior.

Scope:
- add or extend schemas for `summary.json`, `tool-preflight.json`, `evidence-index.json`, and any required structured fields;
- define heading requirements for markdown artifacts where JSON schema is not appropriate;
- update `harness/init-run.sh` / `.ps1` to scaffold only the artifacts required by the task class;
- update `harness/validate-run.sh` / `.ps1` to validate required artifacts by task class;
- add positive and negative fixtures for the new validators;
- update `scripts/check-manifests.sh` so the fixtures run in CI/local validation;
- keep PowerShell parity, with documented skips when `pwsh` is unavailable.

Gate:
- `scripts/check-manifests.sh` passes;
- `git diff --check` passes;
- validator fixtures prove missing required fields fail and minimal valid artifacts pass.

### Phase 2 — Task-Risk Router

Implement only after Phase 1 artifact contracts and validators are in place.

Add a mandatory classification step before expensive ceremony. The router should choose the lightest safe path.

Task classes:
- `trivial`: direct answer or one-line local mechanical edit; no full intake/tournament.
- `small`: local evidence, edit, narrow validation, compact YAGNI/TDD note.
- `medium`: visible intake, compact tournament, focused plan, deterministic gate.
- `large`: full Architrave harness with phase ledger, learning artifacts, judge gate.
- `high-risk`: full harness plus stronger adversarial review and rollback evidence.
- `unknown`: one exploration pass, then classify.

Artifacts:
- `task-classification.md` for non-trivial work.
- Inline classification note for small/trivial work.

### Phase 3 — Tool/MCP Preflight

Configuration should be inferred first from existing `architrave.config.json` fields:
- `designSource.mcp` implies Storybook MCP readiness;
- `ops.mcpServer` implies runtime observer tool readiness;
- `backend.build`, `backend.test`, `iac.plan`, `iac.policy`, `generate`, `build`, `test`, and `screenshot` imply command/tool availability;
- optional external research guidance implies Mobbin/SearXNG when configured by the user's MCP client.

Add optional config only for tools that cannot be inferred. Do not make repos enumerate every obvious command manually.

Add a generic preflight that detects whether required and optional tools are ready before deep research or runtime-gated work starts.

Tool states:
- `available`
- `missing`
- `unauthenticated`
- `permission-denied`
- `empty-result`
- `not-applicable`

Candidate future states, only after current evidence requires them:
- `vpn-required`
- `timeout-prone`
- `rate-limited`

Outputs:
- `tool-preflight.json`
- concise human-readable `tool-preflight.md`

Rules:
- Required missing tools block the phase or produce an explicit degraded-mode decision.
- Optional missing tools are recorded as coverage gaps.
- Tool failures are not silently converted into weak evidence.

### Phase 4 — TDD / Characterization-Test Hook

TDD should be visible when investigating bugs or adding features.

Bug investigation:
- First try to reproduce the failure with a failing test, smoke, script, log assertion, or diagnostic check.
- If the bug cannot be reproduced cheaply, record the attempted repro and the next best observable signal.
- Fix only after the failing/observable case is identified, unless blocked by environment limits.

Feature work:
- Define at least one executable acceptance check before or alongside implementation.
- For UI work, the Storybook story or Playwright interaction can be the acceptance surface.
- For backend work, use contract tests, handler/service tests, or integration smoke.

Refactors and upgrades:
- Add characterization tests before changing behavior.
- If characterization is too expensive, record why and use the smallest deterministic gate that can catch regression.

Artifacts:
- `tdd-plan.md` for medium/large/high-risk tasks.
- Compact `TDD:` note for small tasks.

Template fields:
- current failing or characterization signal;
- expected failure before fix, when applicable;
- acceptance check;
- edge/adversarial case;
- post-fix proof;
- cannot-run reason and substitute signal, if blocked.

### Phase 5 — Deep-Audit Artifacts

Add durable source/evidence tracking and subagent handoff conventions for external research, organizational research, and deep audits.

#### Source Ledger + Evidence Index

`source-ledger.md` fields:
- source URL, file path, tool, or system name;
- vendor/source type;
- retrieval date;
- claim or pattern extracted;
- decision influenced;
- trust level;
- sensitive/private flag.

`evidence-index.json` fields:
- artifact path;
- source kind;
- phase;
- summary;
- validation status.

#### Subagent Artifact Handoff

Subagents should return structured findings. The Architrave lead writes or updates durable artifacts, keeps the final state, and owns gates. This preserves the conductor model while avoiding lossy summaries.

Suggested structure:

```text
.architrave/runs/<run-id>/subagents/
  product-research.md
  ux-architect.md
  service-architect.md
  adversarial-judge-pre.md
  adversarial-judge-post.md
```

Rules:
- The final answer should summarize and link/reference subagent artifacts.
- Large findings should not be copied repeatedly through the orchestrator prompt.
- Subagent artifacts must not contain secrets.

### Phase 6 — Visible YAGNI

Add two visibility levels.

Compact note:

```text
YAGNI: reused existing helper; no new dependency/config/abstraction.
```

Full block:

```text
YAGNI Decision
- Requirement:
- First satisfying rung:
- Existing reuse found:
- New complexity accepted:
- Deferred:
- Long-term override, if any:
- Evidence:
```

Judge rubric should check whether YAGNI is evidence-backed and whether it preserves security, data safety, accessibility, authorization, privacy, and meaningful tests.

### Phase 7 — Agent/Rubric/Docs Rollout

Roll out the validated artifact contracts into Architrave's user-facing behavior only after the prior phases have deterministic coverage.

Scope:
- update `agents/architrave.agent.md` with the task-risk router, tool preflight expectations, TDD hook, source ledger rules, subagent artifact handoff, visible YAGNI, and deep-audit mode;
- update `gates/rubric.md` so the Adversarial Judge can evaluate task classification, tool preflight quality, TDD evidence, source ledger quality, and YAGNI visibility;
- update README and AGENTS managed stanza content so installed repos understand the new behavior;
- update install/update copy paths so new harness files, schemas, templates, and knowledge packs are included;
- update examples/templates only after validators exist.

Gate:
- `scripts/check-manifests.sh` passes;
- install/update smoke confirms copied-kit files are present;
- example configs remain schema-valid;
- no new behavior is required by the agent before the corresponding validator exists.

### Phase 8 — Benchmark + Smoke Scenarios

Add focused benchmark and smoke scenarios that prove the new paths reduce ceremony without losing safety.

Scenario coverage:
- `trivial`: direct answer or tiny local edit does not create a run folder;
- `small`: compact classification plus narrow validation, no full SDD ceremony;
- `medium`: visible intake, compact tournament/YAGNI/TDD as needed;
- `large/high-risk`: full harness still works;
- `deep-audit`: tool preflight, source ledger, evidence index, subagent artifacts, checkpoints, and `recommended-plan.md` are present.

Gate:
- benchmark smoke passes;
- before/after comparison records LOC, token cost, elapsed time, artifact count, success/blocker rate, and developer-visible complexity;
- at least one Rivet-derived scenario exercises the deep-audit path.

### Deep-Audit Mode Details

Formalize a deep-audit mode for multi-hour investigations. This phase consumes the deep-audit artifact conventions from Phase 5.

Suggested artifacts:

```text
.architrave/runs/<run-id>/
  intake.md
  task-classification.md
  phase-ledger.md
  tool-preflight.json
  source-ledger.md
  evidence-index.json
  subagents/
  checkpoints/
  recommended-plan.md
```

Rules:
- Checkpoint after every phase.
- Record what has and has not started.
- Keep raw evidence in files and summarize references.
- Resume from artifacts after context loss rather than restarting.

## Implementation Notes

- Keep this as a branch until Phase 0 review is complete.
- Prefer docs/schemas/harness fixtures before agent-instruction rewrites.
- Add deterministic validator coverage before making these requirements mandatory in the Architrave agent prompt.
- Preserve Architrave's current lightweight path for simple local fixes.
- Treat Rivet as the demanding validation case, not the only target consumer.
- Maintain POSIX and PowerShell parity for new harness helpers, with skip behavior documented when `pwsh` is unavailable.
- Update `harness/init-run.*`, `harness/validate-run.*`, `harness/schemas/run-summary.schema.json`, README, AGENTS stanza, install/update copy paths, and manifest checks when new artifacts become part of the kit.

## Alternatives Considered

### Task-Risk Router

| Option | Pros | Cons | Decision |
|---|---|---|---|
| Prompt-only classification | Fast to ship; no schema work | Hard to validate; likely inconsistent | Reject as insufficient for core behavior |
| Config-driven thresholds only | Deterministic | Too rigid across repos and task types | Reject as sole mechanism |
| Hybrid: prompt-visible classification plus fixture-backed examples | Flexible and reviewable | Needs examples and rubric work | Recommended |

### Tool/MCP Preflight

| Option | Pros | Cons | Decision |
|---|---|---|---|
| Require explicit config for every tool | Deterministic and auditable | High setup burden; repeats existing config | Reject |
| Infer from existing config only | Low burden | Cannot cover organization-specific tools | Partial |
| Infer first, optional config for non-inferable tools | Low burden with escape hatch | Requires clear precedence rules | Recommended |

## Open Questions

These are implementation notes rather than blockers:

- Tool preflight should infer from existing lane configuration first. Add optional config only for non-inferable organization-specific tools.
- `task-classification.md` should be required for medium, large, high-risk, and deep-audit tasks. Trivial/small tasks use inline classification only unless they explicitly create a run directory.
- Subagent artifacts should start as a convention written by the Architrave lead from specialist returns. Add a harness helper only if repeated implementation work shows enough duplication.
- The TDD hook belongs in Architrave core as a generic behavior. Language/framework-specific examples belong in knowledge packs and repo instructions.
- Visible YAGNI should be added to the judge rubric when Phase 6 templates and fixtures exist, not before.