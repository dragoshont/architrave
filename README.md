# Architrave UI

**Build native‑quality UI with AI agents that respect the design you already have — on Apple, Windows, and the Web.**

Architrave UI is a small kit you drop into a UI repo. It gives GitHub Copilot a team of specialist **agents** and a set of **quality gates** that always start from *your* design (your Storybook + design tokens), reproduce the components you already have instead of inventing new ones, and refuse to call a change "done" until it builds, passes its tests, and clears an automated reviewer.

One small config file (`uikit.config.json`) retargets the whole kit from SwiftUI to WinUI to React, so the **same method works in every UI repo you own**. It deliberately covers **UI only** — backend services and infrastructure are a separate lane.

> **Status:** complete (M1–M4). Packaged as a Copilot plugin (verified in the real `copilot` CLI), installable per‑repo, and dogfooded on **PhonoDeck** (SwiftUI/macOS) and **Sideport** (React/web).

![Architrave UI — ground in your design, let specialist agents propose, gate with a judge + your real build, then ship native UI](assets/overview.png)

## What it does

- 🎯 **Grounds first, never reinvents.** Every change starts from your existing Storybook + component map; agents reproduce a component by its real name and touch only the deltas.
- 👥 **Five specialist agents.** *UX Architect* (how it works), *UI Visual* (how it looks), *Platform Design* (is it idiomatic for this OS?), *Adversarial Judge* (an LLM‑as‑judge quality gate), and the *Feature Builder* that orchestrates them.
- ✅ **Two layers of gates.** Deterministic checks (your real build + tests + JSON/token lint) **and** a semantic judge graded against a rubric — nothing ships until both are green.
- 🔁 **Design ↔ code stays reconciled.** Design tokens are the single source of truth; a reconcile gate catches drift between the tokens and the committed code.
- 🧩 **One method, every surface.** The same kit runs in the Copilot CLI, the Copilot desktop app, VS Code, **Claude Code**, and the cloud coding agent.

## What it looks like

Install the plugin once — then the agents are available everywhere, and the deterministic gate runs your repo's real build + tests:

![Installing the Architrave UI plugin in the Copilot CLI, then a green gate run](assets/cli.png)

---

## Why this exists

Three of your repos independently arrived at the **same** workflow:

| Repo | Stack | Design source of truth | Tests |
|---|---|---|---|
| **PhonoDeck** | SwiftUI / macOS | Storybook (`ui-lab/`) + `phonodeck-ui-map.json` | XCTest |
| **Sideport** (admin) | Vite + TS / web | Storybook (`.storybook`) + `docs/ui/*-design-spec.md` | Playwright |
| **Tessera** (web) | .NET + `web/` | Storybook / design docs | — |

That convergence is the signal: a single **design‑first, reproduce‑don't‑reinvent, judge‑gated** method is worth extracting. Architrave UI is that method, made stack‑agnostic by a small per‑repo config.

## Architecture — four layers

```
1. DESIGN SOURCE OF TRUTH      Storybook (component workbench) + design tokens (.tokens.json, W3C DTCG)
        │  validate / tweak the design here FIRST
        ▼
2. KNOWLEDGE PACKS             knowledge/apple.md · microsoft.md · web.md · design-tokens.md
        │  the Platform Design agent loads the pack named by config.platform
        ▼
3. AGENTS                      UX Architect · UI Visual · Platform Design (pluggable) ·
        │                      Feature Builder (harness) · Adversarial Judge (LLM-as-judge)
        ▼
4. GATES                       deterministic (build/test/token-lint) + semantic (judge) + design↔code reconcile
```

Everything in layers 2–4 is **retargeted per repo by one config file** (`uikit.config.json`). The agents never hard‑code a stack; they read the config and the matching knowledge pack.

## The design↔code reconciliation model (the hard part)

"Any variation in design or code must be reconciled" is solved by making **design tokens the single source of truth** (see `knowledge/design-tokens.md`). Three token tiers:

- **Reference** (`ref.*`) — raw values (palette, type scale). Context‑free.
- **System / semantic** (`sys.*`) — roles ("label/primary", "surface"). Theming + context (light/dark/RTL/density) lives here.
- **Component** (`comp.*`) — per‑component element decisions, pointing at system tokens.

Both the design (Storybook/Figma) and the code (SwiftUI `Color`/`Font`, WinUI `ResourceDictionary`, CSS vars) **reference the same token names**. A translation step (Style Dictionary / Terrazzo) generates platform code from the tokens. **Drift = when generated platform values diverge from committed code.** The reconcile gate diffs the two and the Feature Builder fixes by regenerating from the tokens (or, if the design legitimately changed, updates the tokens first, then the code).

```
design tweak ──▶ tokens (.tokens.json, SSOT) ──▶ Style Dictionary ──▶ swift / xaml / css
                       ▲                                                    │
                       └──────────── reconcile gate (diff) ◀───────────────┘
```

## Requirements

The kit is just Markdown + small scripts; the only hard dependencies are for the **gates**.

| Tool | Why it's needed | Install |
|---|---|---|
| **GitHub Copilot** (CLI, desktop app, or VS Code) **or Claude Code** | runs the agents | [github.com/features/copilot](https://github.com/features/copilot) |
| **`jq`** | the POSIX (`.sh`) gates read `uikit.config.json` | macOS: `brew install jq` · Ubuntu/Debian: `sudo apt-get install -y jq` · Windows: `winget install jqlang.jq` |
| **PowerShell 7+** | only for the Windows (`.ps1`) gates — built in on Windows | macOS: `brew install --cask powershell` · [releases](https://github.com/PowerShell/PowerShell/releases) |
| **git** | the reconcile gate diffs generated vs committed code | already installed on most systems |

> On **Windows you don't need `jq`** — the `.ps1` gates use PowerShell's built‑in `ConvertFrom-Json`. On **macOS/Linux you don't need PowerShell** — the `.sh` gates use `jq`.

Your repo's own build/test toolchain (Node for web, Xcode for Apple, .NET for WinUI, …) is whatever your `uikit.config.json` `build`/`test` commands invoke — the gates just run those.

## Install

**1 — Install the agents once** (shared across the Copilot CLI, the desktop app, VS Code, and Claude Code):

```bash
copilot plugin marketplace add dragoshont/architrave-ui
copilot plugin install architrave-ui@architrave
```

> VS Code alternative: **Chat: Install Plugin From Source** → the repo URL.
> Repo not on GitHub yet? Install from a local path: `copilot plugin install /abs/path/to/architrave-ui`.

**2 — Ground a repo** (this is also what reaches the Copilot **cloud** agent):

```bash
/path/to/architrave-ui/tools/install.sh .                          # macOS / Linux
pwsh -NoProfile -File /path/to/architrave-ui/tools/install.ps1 .    # Windows
```

This copies the agents → `.github/agents/`, the gates → `gates/`, the knowledge packs → `knowledge/`, scaffolds `uikit.config.json`, injects a grounding stanza into `AGENTS.md` (idempotent), wires the PostToolUse hook, and drops `.github/workflows/copilot-setup-steps.yml`.

**3 — Point it at your repo:** edit `uikit.config.json` — set `platform`, `stack`, `designSource` (your Storybook), `tokens`, and the `build`/`test` commands. Then ask the **Feature Builder** agent to make a UI change; it grounds, proposes, judges, implements, reconciles, and verifies.

## Layout

```
README.md                     ← you are here
ROADMAP.md                    ← what's built vs. ported next
plugin.json                   ← agent-plugin manifest (Copilot CLI / app / VS Code)
.github/plugin/marketplace.json ← self-hosting plugin marketplace
kit/
  uikit.config.schema.json    ← per-repo config schema (the keystone)
  examples/                   ← phonodeck / sideport / tessera example configs
knowledge/
  apple.md                    ← Apple HIG pack (SwiftUI) — cited
  microsoft.md                ← Microsoft Fluent 2 / WinUI pack — cited
  web.md                      ← Web + React + component-driven dev pack — cited
  design-tokens.md            ← 3-tier tokens + design↔code reconciliation — cited
agents/                       ← UX Architect · UI Visual · Platform Design · Feature Builder · Adversarial Judge
gates/                        ← rubric.md · checks.{sh,ps1} · reconcile.{sh,ps1} · quality-gate.{sh,ps1} · hooks/
templates/                    ← AGENTS.stanza.md · copilot-setup-steps.yml (injected by the installer)
tools/                        ← install.sh · install.ps1 (per-repo grounding)
assets/                       ← README screenshots (drop PNGs here)
AGENTS.md                     ← kit-level agent instructions
```
