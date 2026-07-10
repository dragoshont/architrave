# Changelog

All notable changes to **Architrave** are documented here. This project follows
[Keep a Changelog](https://keepachangelog.com/) and [Semantic Versioning](https://semver.org/).
Releases at or before **v0.8.12** are on the
[GitHub Releases](https://github.com/dragoshont/architrave/releases) page.

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
