# Roadmap

## Unreleased follow-up - Passive session companion

- [x] Ordinary-session display in the same portable renderer, without a Run,
  repository or named agent; lightweight discovery does not disclose Run schemas.
- [x] Passive host events for bounded activity and usage, selected vs observed
  model/effort, truthful unknowns, no routine transcript/model traffic.
- [x] Owned SDK-subagent names, roles, lifecycle, explicit assigned slice and
  model details; app-native child-session visibility explicitly unavailable.
- [x] One-shot opening, session dismissal, durable user preference and explicit
  standalone one-file adoption, with no permissions or orchestration changes.
- [ ] Fresh-session lifecycle and same-host context-delta qualification;
  fixture success alone does not close native-host or footprint claims.
- [x] Preserve committed v0.14.1 corrections through `6b15d16`; later release
  fixes must still be preserved before eventual landing.
- [ ] Reviewed published-source adoption only, not candidate global installation.

## Milestone 10.1 - Optional Route Ribbon (v0.14.1 candidate)

- [x] One portable, optional Copilot canvas with a segmented route and evidence
  inspector, responsive keyboard navigation and explicit snapshot freshness.
- [x] Bounded Python projection of authenticated Run state/events; scoped done,
  source-bound product observations, superseded history, stops and retry
  fingerprints remain separate. No orchestration or canonical state writes.
- [x] Domain-keyed durable display snapshots, extension-reload rehydration,
  loopback-only serving and opt-in managed project installation/refresh.
- [x] Stacked workstream views grounded in Run/task lanes and work kinds, with
  independent slices/source/owner and explicit BLOCKS vs display-only INFORMS.
- [x] Fresh joined native semantic producer with source/policy/holds/owner/
  challenge binding, actual host family and one-use evidence.
- [x] Retired automatic quality registrations; exact recognized transactional
  retirement, custom-hook preservation and explicit executable check cadence.
- [ ] Approved publication after final requested reviews and CI; consumer
  installation/adoption remains separate owner authorization.

## Milestone 10 - Truthful adaptive supervision (v0.14.0)

- [x] Agent-estimated finite on-demand feasibility reset, cumulative observed
  budgets, atomic admission and expiry/unknown-signal regressions.
- [x] Provenance-separated executing/adopted/installed/loaded identities and
  session-scoped native worker visibility; missing observations stay UNKNOWN.
- [x] Exact source/task/criterion product milestones distinct from path-touch
  activity, and one-use owner primary-path correction preserving human holds,
  acceptance, policy, side effects, baseline and budget clocks.
- [x] Product gate registration/completion reject frozen evidence from a
  superseded objective or changed source; path correction rejects junctions.
- [x] Hypothesis/reproduction/verified advice contract and bounded actionable
  handoffs. No generic process manager, daemon or new dependency.
- [ ] Final published-source installation and per-owner active adoption receipts
  (inactive/deferred and unavailable loaded-context proof must remain explicit).

## Milestone 1 — Foundation (this commit)
- [x] Architecture + adoption model (`README.md`)
- [x] Per‑repo config schema (`kit/architrave.config.schema.json`) + example configs for PhonoDeck / Sideport / Tessera
- [x] Platform knowledge packs (researched + cited): Apple HIG, Microsoft Fluent 2 / WinUI, Web + React + component‑driven dev
- [x] Design‑token + design↔code reconciliation backbone (`knowledge/design-tokens.md`)
- [x] Operations/admin UX knowledge pack (`knowledge/operations-ux.md`): onboarding, offboarding, inventories, app catalogs/uploads, RBAC, health, diagnostics, queues/jobs/schedules, and operational state truth.

## Milestone 2 — Agents (port + generalize from PhonoDeck)
- [x] `agents/ux-architect.agent.md` — platform‑agnostic IA/flow/state, grounded per‑repo by config + Storybook.
- [x] `agents/operations-ux.agent.md` — source-backed operational/admin product UX patterns and contract requirements.
- [x] `agents/ui-visual.agent.md` — platform‑agnostic visual hierarchy/tokens; loads the platform pack for specifics.
- [x] `agents/platform-design.agent.md` — **pluggable**: reads `config.platform` and the matching `knowledge/*.md` (Apple HIG / Fluent / Web).
- [x] `agents/architrave.agent.md` — the config‑driven, judge‑gated harness (understand → propose → judge → implement → reconcile → tests → judge → verify).
- [x] `agents/adversarial-judge.agent.md` — LLM‑as‑judge against `gates/rubric.md` (cross‑platform).
- [x] `agents/tournament-analyst.agent.md` — isolated, read-only option comparison for materially risky decisions.
- [x] `agents/cto.agent.md` + `skills/architrave-cto` — consulted at Run start and on stall; keeps the Run outcome-driven and lean.

## Milestone 3 — Gates (DONE)
- [x] `gates/rubric.md` — cross‑platform evaluation rubric (spec / design‑language / platform / adversarial / security / a11y / reconcile / tests / verification).
- [x] `gates/reconcile.sh` + `gates/reconcile.ps1` — design↔code drift checker (regenerate from tokens via `config.tokenBuild`, diff against committed code).
- [x] `gates/checks.sh` + `gates/checks.ps1` — deterministic gate runner driven by `architrave.config.json` (generate/build/test + designMap/tokens JSON valid; `--quick` / `-Quick` for hooks).
- [x] `gates/quality-gate.sh` + `gates/quality-gate.ps1` — lightweight quick gate (fast JSON guard + reconcile/judge reminder).
- [x] `gates/hooks/design-guard.json` (POSIX) + `design-guard.windows.json` (pwsh) — legacy recognition definitions only in 0.14.1; automatic registration retired.
- [x] `harness/init-run.*` + `validate-run.*` + `semantic-review.*` — durable run artifacts, learning notes, and optional judge prompt helper.

> **Cross-platform:** every gate ships thin POSIX `.sh` and PowerShell `.ps1`
> launchers for the same canonical Python CLI. Both preserve PASS / FAIL / BLOCK /
> DRIFT exit codes (0 / 1 / 2 / 1); macOS needs no PowerShell. Copied core paths
> support Python 3.9+, while optional Codex role adoption requires Python 3.11+.

## Milestone 4 — Distribution
- [x] **Plugin packaging** — `plugin.json` + `.github/plugin/marketplace.json`. Verified end‑to‑end with the real Copilot CLI (v1.0.64): both `copilot plugin install <path>` and the future‑proof `copilot plugin marketplace add dragoshont/architrave` + `copilot plugin install architrave@architrave` load the agent crew. The shared `~/.copilot` runtime ⇒ also reaches the Copilot app + VS Code.
- [x] **Codex / ChatGPT packaging** — `.codex-plugin/plugin.json`, three plugin-only Agent Skills, two generated project roles, opt-in role installation/update, bounded dual-family launchers, and disposable plugin/role/MCP runtime smokes. Normal roles inherit parent MCP/skills/permissions and are documented as advisory contexts, not mandatory security gates.
- [x] `tools/install.sh` (+ `install.ps1`) — per‑repo grounding: copies agents → `.github/agents/`, gates → `gates/`, scaffolds `architrave.config.json`, injects the `AGENTS.md` stanza (idempotent), wires the per‑OS PostToolUse hook, drops `copilot-setup-steps.yml`. Both variants tested on throwaway repos.
- [x] `AGENTS.md` (kit) + a per‑repo `AGENTS.md` stanza template (`templates/AGENTS.stanza.md`) — the cloud‑agent reach.
- [x] Prove on Sideport (web) — adopted on an isolated worktree (branch `architrave-adoption`, based on the UI branch's committed HEAD). The installer wired the gates to Sideport's real `tsc -b && vite build` + `eslint`; baseline gate green; ran the Feature‑Builder harness for a grounded a11y change (`aria-current` on the primary nav + the onboarding step‑tabs — WCAG 2.2 / web pack), with a consistency sweep; post‑change gate green. The config was corrected to the repo's real scripts (`test`→`lint`, `screenshot`→`test:screens`).

---

**Status: M1–M4 complete.** The kit is built, cross‑platform tested, packaged as a Copilot/Claude plugin, installable per‑repo, and proven on a non‑PhonoDeck repo. The public repo is `dragoshont/architrave`.

## Milestone 5 — SDD + Learning Hardening
- [x] Mandatory visible intake for non-trivial work, with direct plans for routine bounded changes and a Tournament of Options only for materially ambiguous or high-risk choices.
- [x] Compact canonical Run state plus authenticated events and one rolling recovery snapshot; phase/status/audit views are rendered on demand.
- [x] Run v1 migration support retained without requiring legacy projection files for Run v2.
- [x] Validator hardening for canonical state, event integrity, recovery state, and compact artifact receipts.
- [x] Direct validator fixture tests (`scripts/test-validate-run.sh`) covering valid and malformed run artifacts.
- [x] Learning artifact validator (`harness/validate-learning.*`) for required learning files, local markdown links, and obvious secret patterns.
- [x] Approval-first lesson promotion helper (`harness/promote-lesson.*`), dry-run by default and Markdown-only in the first slice.
- [x] Candidate-row lesson promotion picker (`harness/promote-lesson-picker.*`) for `.architrave/learning/repo-lessons.md`.

## Next SDD Phases
- [x] PowerShell execution validation in CI for run-artifact, learning, and promotion harness parity.
- [x] PowerShell execution validation in CI for all gate scripts.
- [x] Expanded benchmark scenario suite: representative scenarios across UI, backend, full-stack, plan-only infra, operations UX/read-only runtime, YAGNI, and learning promotion.
- [x] Interactive lesson promotion picker for `.architrave/learning/repo-lessons.md` candidate rows.
- [x] Deterministic stale-learning guard that validates repo-profile and lessons against current repo files before promotion.
- [x] Deterministic stale-fact recovery that marks unsupported local-link facts as `UNVALIDATED` before promotion.
- [x] Semantic stale-fact recovery that checks prose claims beyond local file references via provider-backed JSONL findings plus deterministic exact-line `UNVALIDATED:` recovery.

## Milestone 6 - Repository Profiles
- [x] First-class `kind: knowledge` schema contract with no synthetic UI fields.
- [x] Explicit POSIX and PowerShell knowledge installer profiles.
- [x] Profile-aware gates, agent routing, examples, and cross-platform fixtures.
- [x] First-class Codex CLI packaging and role routing (issue #4; release/rollout follows the gated phase ledger).

## Milestone 7 - Durable Outcome Runtime

- [x] `architrave.run.v2` schema with Outcome, Acceptance Matrix, TaskGraph,
	WorkPackets, policy, checkpoints, external checkpoints, artifacts, workers,
	gate results, and explicit Run/task states.
- [x] Atomic Python runtime with hash-chained typed events, interrupted-append
	recovery, repository drift checks, leases, resume, and v1 migration.
- [x] `current-task`, `approved-program`, and `advisory-only` autonomy separated
	from the Phase Ledger projection.
- [x] Default-deny scoped mutation policy, trusted external-checkpoint resolution,
	uncertain-side-effect reconciliation, and deployment receipts.
- [x] Challenge-bound additive mutation-policy amendments for an existing Run,
  enforced by a store-private transaction capability.
- [x] Copilot/Claude/Codex/shell worker adapters with bounded/redacted output and
	coordinator-only task completion.
- [x] Isolated git worktrees, mutable-path validation, candidate patch artifacts,
	and coordinator integration.
- [x] Mechanical invariant/dead-control engine and risk-based R0-R4 evaluation.
- [x] Web/Electron/iOS/deployment legibility and compile-only false-PASS tests.
- [x] LongBuild fixture/scenarios, recovery/external/parallel/deployment-policy
	dogfood, repeat metrics, false-PASS and intervention reporting.
- [x] Existing config/plugin/install paths remain compatible; v1 and v2 validators
	run through paired POSIX/PowerShell entrypoints.

### Release-readiness evidence still external

- [ ] Provider-backed live Codex/Copilot/Claude LongBuild repeats and independent
	human mergeability review.
- [ ] Real iOS simulator/product repository legibility dogfood beyond the
	deterministic fixture.
- [ ] Safe-target live deployment dogfood beyond the sandbox fixture.

## Milestone 8 - Host-owned Execution Policy
- [x] Canonical agents, Run state, WorkPackets, docs, and templates contain no model class, tier, provider, reasoning, or context recommendations.
- [x] Host-native custom-agent/subagent delegation is used only for bounded isolation, parallelism, permissions, expertise, or independent review.
- [x] Durable Copilot WorkPackets use a minimal joined-session tasks RPC extension,
  with independent observed gates, source-bound evidence, orphan cleanup and
  side-effect-free recovery. No nested agent CLIs or provider/model overrides.
- [x] Risk-based verification requires deterministic evidence and independent reviewer identities without constraining host model choice.
- [x] Compact Run v2 artifacts replace eager per-agent plans, reports, status files, and per-transition snapshots.

## Prioritized v0.11.3 follow-ups
- [ ] Add a public Run cancel/supersede transition and terminalize invalid
  unstarted task intake instead of returning retryable tasks to `READY`.
- [ ] Add a public trusted external-attestation registration path so factual
  cross-session resource-release receipts can resolve checkpoints without
  private executor hooks.

## Milestone 9 - Thin mission supervisor (v0.13.0)

- [x] Small canonical startup contract and on-demand lane/recovery/review packs;
  existing CTO checklist applies inline.
- [x] Direct-work default; bounded native parallel children, exclusive mutable
  ownership, compact returns and no recursive spawning.
- [x] Event-driven Copilot transport; task-scoped sibling lifecycle commutation
  without weakening policy, human holds, source or ownership checks.
- [x] Three-active limit, finite native turn/time/output bounds, new-evidence/
  hypothesis retries and deterministic two-identical-failure stop.
- [x] Frozen one-run direct A / two-child B baseline and candidate evaluation,
  with unavailable context/cost telemetry separated from byte proxies.
- [x] Current official Copilot/Codex capability investigation and supported
  Codex local marketplace packaging. Desktop execution is not inferred from CLI
  discovery; the audit records the observed boundary and one owner smoke prompt.
