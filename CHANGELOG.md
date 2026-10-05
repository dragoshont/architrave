# Changelog

All notable changes to **Architrave** are documented here. This project follows
[Keep a Changelog](https://keepachangelog.com/) and [Semantic Versioning](https://semver.org/).
Releases at or before **v0.8.12** are on the
[GitHub Releases](https://github.com/dragoshont/architrave/releases) page.

## Unreleased

### Planned
- Add a public Run cancel/supersede transition and make invalid unstarted-task
  intake terminal instead of retry-ready.

## [0.12.3] - 2026-10-05

Deterministic only: no new agents, workflows, dependencies, or model calls.
Feature freeze after this release.

### Added
- Push-back verdicts: `task-add --pushback KEEP|CUT|DEFER:reason`. New Runs
  refuse to start a task without one (`PUSHBACK_MISSING`), and CUT/DEFER never
  dispatch. Structure is enforced; reason quality is not. Tournament results
  must include typed `DO_NOTHING` and `SMALLEST_VIABLE` options and
  `winnerBeatsDoNothing` (`tournament-review --result`).
- Run budget from real signals: optional `evaluation.budget` limits for turns
  (Run transitions), commits, dispatches, and minutes. Status reports
  `BUDGET_80`/`BUDGET_100`/`BUDGET_UNKNOWN` (diverged history). At 100%, new
  dispatches stop.
- Owner-summary lint in status and checkpoint (`OWNER_MESSAGE_LINT_FAIL` for
  three or more full SHAs, PIDs, run IDs, or UUIDs), also available as
  `gates/gate_runner.py message-lint`.
- Semantic reviews record `reviewer: host-native|architrave-judge` and their
  family. The review skill prefers the host-native reviewer over
  `adversarial-judge` (never both), and a duplicate same-family R3/R4 PASS is
  rejected (`DUPLICATE_REVIEW_FAMILY`).
- `PRODUCT_OUTCOME_CONFIRMED` external checkpoint type for typed user
  confirmation of a product outcome.

### Changed
- The primary criterion passes only on a runtime-bound reality/e2e receipt or
  `PRODUCT_OUTCOME_CONFIRMED`; CI/test results, auth/MFA/policy checkpoints, and
  self-authored evidence are rejected (`PRIMARY_EVIDENCE_NOT_OBSERVED`).
- Loop cap: three failed attempts on the primary criterion (commits don't
  reset) raise `PRIMARY_STALLED` with the best attempt and caveats, and block
  new work on it. The default stall threshold is now 3.

## [0.12.2] - 2026-10-05

### Added
- **CTO** agent (`architrave:cto`) and `architrave-cto` skill checklist. The
  conductor consults it at Run start and on stall.
- Primary-criterion stall detector: `run --primary-criterion/--primary-path` or
  `primary-set`. After 5 consecutive commits/worker results that miss the
  criterion's code path, status reports `STALLED_PRIMARY_CRITERION` and
  `task-start` refuses unrelated tasks.
- Replacement/port tasks record their tested `reference`; parity on the real
  flow is the first gate.
- Opt-in `productCopy` check in `gates/checks` (and the quality-gate hook) for
  internal evidence/spec/status language in UI strings.

### Changed
- Policy text: default-deny covers mutation and side effects only; parse
  third-party protocol input leniently; failures carry a specific step and
  reason; R0/R1 fixes need only the focused test plus CI; approved operations
  may escalate a graceful quit to SIGTERM without a new hold.

## [0.11.3] - 2026-10-05

### Added
- Public `target-attest` Run v2 command for exact
  `SAFE_WRITE_TARGET_REQUIRED` observation through a user-level trusted
  executor registry.
- Stdlib-only exact filesystem observer and `executor-install` enrollment path
  with absolute Python/adapter paths, SHA-256 pins, exact provider/checkpoint
  allowlists, and exact target identities outside the target repository.
- Fixed SSH relay mode for canonical Runs whose exact read-only target is on a
  different trusted host, without copying Run state or runtime keys.
- Public trusted historical side-effect reconciliation for exact
  `applied-closed` and `closed-unknown` outcomes without replay or
  repository-local self-attestation.
- Public one-use challenge renewal for unchanged, unstarted pending exact-target
  checkpoints when the original returned nonce is lost.
- End-to-end regressions for repository-local and modified adapters, provider,
  principal, task/challenge and observed-identity mismatches, replay, timeout,
  malformed output, oversize output, and successful atomic proof consumption.

### Security
- Target attestation rechecks Run, objective version, state revision, task,
  checkpoint, provider, principal, challenge hash, target binding, and intended
  identity at commit time.
- Adapter execution uses argv without a shell, a minimal environment,
  non-repository working directory, bounded request/stdout/stderr, and a
  configured timeout. Caller-supplied observed JSON is not accepted.

## [0.11.2] - 2026-10-04

### Added
- Public `policy-amend-request` and `policy-amend` Run v2 commands for additive,
  exact-scope mutation grants and confirmation-required operations.
- Replay-protected amendment checkpoints bound to Run, objective version,
  revision, principal, provider, exact delta, reason, and one-time challenge.
- Public CLI regressions for the `public-candidate:edit` to `repository:edit`
  correction and authorization, replay, stale-state, cross-Run, transaction,
  worker/coordinator spoof, and active-mutation rejection paths.

### Changed
- Policy mutation authorization is enforced inside the transaction commit
  boundary with a store-private capability.
- A successful amendment releases its policy-blocked task to `READY` without
  replaying the action; active or uncertain mutation state fails closed.

- Model selection is entirely user/host-owned; canonical agents, Run state,
  WorkPackets, schemas, templates, and docs no longer specify model classes,
  tiers, providers, reasoning levels, context tiers, or concrete models.
- Run v2 now persists canonical state, authenticated events, one rolling
  recovery snapshot, and compact evidence only. Human views are on demand.
- Python stdlib is now canonical for install/update, gates, Run/learning
  validation, review launchers, and orchestration; OS scripts are launch shims.
- Versioned objective replacement, reuse-first redesign gating, target identity
  preflight, two-lane isolation, bounded checkpoints, and review batching guard
  long-running work against correction loss and objective drift.

## [0.11.1] - 2026-09-09

### Added
- Delivery-first scheduling with an explicit support-work budget, targeted-first
  gate cadence, bounded semantic reopen rules, and stalled-command thresholds.
- Focused policy validation covering canonical agent, execution, rubric,
  learning, and installed AGENTS-stanza behavior.
- Figma MCP tool patterns in the canonical lead agent.

### Changed
- Full tournaments are reserved for risky or materially ambiguous decisions;
  routine bounded work records a direct plan and YAGNI rung.
- Small safe two-file mechanical changes stay with the coordinator when an
  existing targeted check fully decides acceptance.
- Status reporting leads with usable product behavior and accepted product
  criteria; infrastructure and audit evidence are reported separately.
- Learning artifacts are emitted at useful boundaries rather than after every
  micro-action.

### Fixed
- Supporting tasks no longer independently trigger full configured gates.
- Repeated micro-review loops now consolidate after two reopens and stop after
  a third non-PASS.

[0.11.3]: https://github.com/dragoshont/architrave/compare/v0.11.2...v0.11.3
[0.11.2]: https://github.com/dragoshont/architrave/compare/v0.11.1...v0.11.2
[0.11.1]: https://github.com/dragoshont/architrave/compare/v0.11.0...v0.11.1

## [0.11.0] - 2026-09-05

### Added
- Host-native bounded delegation and risk-based verification policy.
- Benchmark treatments for delegation, verification, and observable execution telemetry.
- Optional run-summary execution evidence with paired POSIX/PowerShell validation.
- Durable `architrave.run.v2` control plane with Outcome, Acceptance Matrix,
  TaskGraph, typed HMAC-authenticated EventLog, checkpoints, resume,
  challenge-bound external waits,
  default-deny mutation policy, and v1 migration.
- Bounded Copilot/Claude/Codex/shell workers, isolated worktree management,
  mechanical invariants, product/deployment legibility, risk-based evaluation,
  registered evidence binding, PNG blank-screen analysis, and mutation receipts.
- Architrave LongBuild benchmark categories, frozen Tessera-shaped fixture,
  recovery/external-checkpoint/parallel/deployment-policy scenarios, and durable
  outcome/intervention metrics.
- First-class Codex/ChatGPT plugin manifest with three plugin-only Agent Skills.
- Project-scoped Tournament Analyst and Adversarial Judge roles generated from
  canonical agents, with opt-in POSIX/PowerShell install and update support.
- Bounded, nonce-verified independent semantic review launchers.
- Disposable Codex runtime fixtures for plugin skill discovery, role routing,
  exactly-one MCP invocation, and hostile-output resistance.
- Installers and updaters ignore `.architrave/runs/` and
  `.architrave/worktrees/` by default while learning remains tracked.

### Changed
- Execution benchmarks now emit periodic progress heartbeats, cap each
  agent cell at 10 minutes and each invocation at 20 minutes by default, and
  stop launching cells when the configurable run budget is exhausted.
- The lead agent is materially smaller and delegates lane detail to retrievable
  knowledge. Phase Ledger is now a Run projection rather than an autonomy wall.
- Infrastructure/runtime remains plan/read-only by default but explicit bounded
  Run policy can authorize a target/operation with receipt and verification.
- Manifest validation and version bumping now synchronize seven version fields
  and enforce Codex JSON/YAML/TOML, generator, transaction, launcher, and
  structural runtime checks.
- Codex role documentation explicitly distinguishes the read-only command
  sandbox override from inherited parent permission, skill, and MCP authority.
- The `knowledge` profile now installs only its five-agent crew (`architrave`,
  `adversarial-judge`, `tournament-analyst`, `product-research`, and
  `runtime-observer`) without native-app constitutions. Explicit agent refresh
  migrates existing knowledge repos by removing only non-crew agent basenames
  packaged by the kit, preserving target-only custom agents and Codex roles.

### Fixed
- Benchmark validation now accepts the already-supported Claude and Codex
  runners, and frozen fixture paths resolve consistently relative to their
  scenario file.
- POSIX updates now require `jq` and fail before writes on malformed,
  non-object, or unsupported-profile configuration instead of falling back to
  application behavior. PowerShell enforces the same `kind` contract.
- Tournament review verification now supports nonce generation without
  `uuidgen`, accepts exact CRLF evidence lines, and rejects missing or duplicate
  completion markers consistently across POSIX and PowerShell.

### Security
- Benchmark judging is now fail-closed and tool-free, nonce-delimits untrusted evidence, blinds producer identity, verifies observed judge family, and prevents stale verdict reuse across judge configurations.
- Installers and updaters now validate every managed destination, reject
  symbolic links, junctions, reparse points, and unsupported path types, and
  revalidate immediately before each write or deletion. Per-file staged
  replacement also prevents target hard links from mutating external content.
- Cross-platform adversarial fixtures verify external directory/file sentinels
  and target snapshots remain unchanged when managed paths or configuration are
  unsafe.
- Focused managed-path tests now run on Windows plus Linux x64 and arm64 during
  validation and release, covering Unicode paths, FIFOs, links, device nodes,
  hard links, and containment behavior.

[0.11.0]: https://github.com/dragoshont/architrave/releases/tag/v0.11.0

## [0.10.3] - 2026-07-10

### Fixed
- PostToolUse design guards now invoke the paired quality gates in structured
  hook mode, emitting `{"continue":true}` on success and exit 2 with stderr
  diagnostics on invalid configuration.
- POSIX and PowerShell fixtures parse the successful hook JSON and verify the
  blocking failure contract, eliminating VS Code's non-JSON hook warnings.

[0.10.3]: https://github.com/dragoshont/architrave/releases/tag/v0.10.3

## [0.10.2] - 2026-07-10

### Fixed
- PowerShell install and update paths no longer append a second newline to the
  managed `AGENTS.md` block, so freshly adopted repositories pass
  `git diff --check` on Windows.
- The PowerShell installer fixture now validates the full generated repo and an
  `update.ps1 -Agents` refresh with actionable captured output.

[0.10.2]: https://github.com/dragoshont/architrave/releases/tag/v0.10.2

## [0.10.1] - 2026-07-10

### Fixed
- PowerShell profile-aware gate fixtures now capture the information stream
  emitted by `Write-Host`, so Linux and Windows CI can assert the messages that
  were already visible in job output.

[0.10.1]: https://github.com/dragoshont/architrave/releases/tag/v0.10.1

## [0.10.0] - 2026-07-10

### Added
- First-class `kind: knowledge` configuration for repositories with docs, skills, schemas, and automation but no UI or service lane.
- Explicit `--profile knowledge` / `-Profile knowledge` installer support backed by a canonical example.
- Paired POSIX and PowerShell regression fixtures for schema profiles, installers, and profile-aware gates.

### Changed
- The lead agent, Adversarial Judge, managed `AGENTS.md` stanza, checks, reconciliation, and quick quality gate now classify the repository profile before applying UI rules.
- Linux and Windows validation/release workflows exercise knowledge-profile installation end to end.

[0.10.0]: https://github.com/dragoshont/architrave/releases/tag/v0.10.0

## [0.9.1] — 2026-07-02

Dual-judge semantic gates are now packaged as their own release so installed clients refetch the
updated Architrave instructions instead of staying on the existing v0.9.0 package.

### Changed
- Full semantic gates now require two independent judge-family passes by default: one Copilot/GPT
  family judge and one Claude family judge.
- Semantic review helpers default to running both configured providers, with explicit Copilot and
  Claude command guidance.
- Copilot and Claude marketplace manifests describe the dual-judge gate posture consistently.

[0.9.1]: https://github.com/dragoshont/architrave/releases/tag/v0.9.1

## [0.8.13] — 2026-06-28

Native‑app **constitutions**: deep, source‑cited rule bases that ground Architrave when it builds or
reverse‑engineers native desktop/mobile apps, so it **reuses system components instead of guessing or
reinventing them** — including when you hand it a task or a screenshot.

### Added
- **`constitution-apple.md`** — Apple **HIG / SwiftUI** (macOS · iOS). Verbatim macOS/iOS type tables
  (macOS Body 13 pt ≠ iOS Body 17 pt), Liquid Glass functional‑layer + material rules, SF Symbols
  rendering modes/variants/weights, the native component catalog (toolbar regions · sidebar ≤ 2 levels ·
  `Table` vs `List` · button roles · menu‑bar parity), the window active‑state model, a SwiftUI
  reverse‑engineering protocol, and a **shared‑screenshot HIG‑audit** pass. Grounded in the live HIG,
  WWDC sessions, and SF Symbols.
- **`constitution-windows.md`** — Microsoft **Fluent 2 / WinUI 3 / Windows App SDK / WPF (.NET)**. The
  Segoe UI Variable type ramp, Mica/Acrylic/Smoke materials + the two‑layer elevation model, the 4‑epx
  grid, Segoe Fluent Icons, the native component catalog (`NavigationView` · `CommandBar` · `DataGrid` ·
  inspector), WinUI 3 vs WPF/.NET deltas, a XAML reverse‑engineering protocol, and a **shared‑screenshot
  Fluent‑audit** pass. Grounded in Microsoft Learn, Fluent 2, and Build sessions (elevation values and
  DWM/backdrop APIs verified against the live docs).

### Changed
- The UI crew now grounds in the matching constitution per `config.platform`: **UX Architect**,
  **UI Visual**, **Platform Design**, **Adversarial Judge**, and **Architrave** load
  `constitution-apple.md` (Apple) or `constitution-windows.md` (Windows) and run its screenshot
  conformance‑audit before reproducing a shared task/screenshot. The `web` / no‑constitution paths are
  unchanged (the constitution is an additive layer on the platform knowledge pack).
- `gates/rubric.md` grades platform conformance against the matching constitution — reinventing a catalog
  component, copying a cross‑platform screenshot's chrome, or shipping the wrong platform's type sizes is
  a **Fail**.
- `knowledge/apple.md` and `knowledge/microsoft.md` each point to their deep constitution.
- The installer/updater (`tools/install.*`, `tools/update.*`) copy `constitution-*.md` into each adopted
  repo's root, and the injected `AGENTS.md` stanza references them (so the Copilot **cloud** agent picks
  them up too).

### Upgrade notes
- In an **already‑adopted repo**, run `tools/update.sh` (or `tools/update.ps1` on Windows) after updating
  the plugin — this copies the constitutions in and refreshes the `AGENTS.md` stanza. A plain
  `copilot plugin update architrave` refreshes the plugin's agents but **not** the per‑repo copied assets,
  so the root‑level constitutions won't appear until you run the updater.

[0.8.13]: https://github.com/dragoshont/architrave/releases/tag/v0.8.13
