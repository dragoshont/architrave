# Changelog

All notable changes to **Architrave** are documented here. This project follows
[Keep a Changelog](https://keepachangelog.com/) and [Semantic Versioning](https://semver.org/).
Releases at or before **v0.8.12** are on the
[GitHub Releases](https://github.com/dragoshont/architrave/releases) page.

## [0.11.0] - 2026-09-05

### Added
- Provider-neutral adaptive execution intent across model class, reasoning, context, and verification dimensions, with provisional FAST/BALANCED/DEEP/CRITICAL presets and host-native subagent delegation.
- Backward-compatible routing benchmark treatments, model/effort/context requests, observed execution telemetry, control-honor status, and four model-neutral routing scenarios.
- Optional run-summary execution evidence with paired POSIX/PowerShell validation of preset consistency, evidence-bearing escalation/fallback, and verified independent/cross-family acceptance.
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
- Claude Opus 4.8 MAX Tournament launcher and bounded, nonce-verified dual-family
  semantic launchers using GPT-5.6 Sol MAX and Opus 4.8 MAX.
- Disposable Codex runtime fixtures for plugin skill discovery, role routing,
  exactly-one MCP invocation, and hostile-output resistance.
- Installers and updaters ignore `.architrave/runs/` and
  `.architrave/worktrees/` by default while learning remains tracked.

### Changed
- Adaptive-routing benchmarks now emit periodic progress heartbeats, cap each
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
