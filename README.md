# Architrave UI

**A crew of UI/UX agents that design *and* build native‑looking apps — for Apple, Microsoft, and the web.**

Architrave UI is a **plugin for GitHub Copilot and Claude Code** that designs UI in [Storybook](https://storybook.js.org) first, then builds it natively in **SwiftUI, WinUI, or React** — and won't call it done until it builds, passes your tests, and clears an automated design review.

![Architrave UI — ground in your design, let specialist agents propose, gate with a judge + your real build, then ship native UI](assets/overview.png)

## Install

With **GitHub Copilot** (CLI, desktop app, or VS Code):

```bash
copilot plugin marketplace add dragoshont/architrave-ui
copilot plugin install architrave-ui@architrave
```

Or with **Claude Code**:

```bash
claude plugin marketplace add dragoshont/architrave-ui
claude plugin install architrave-ui@architrave
```

That installs the agents everywhere your assistant runs. Then [set up a repo](#set-up-a-repo) to point them at your Storybook + build.

## Use it

Open your assistant, pick the **Architrave** agent, and describe the change in plain language:

> Add an empty state to the library list — an icon, a short message, and a primary action.

It grounds in your Storybook, proposes a design, gets it graded by the **Adversarial Judge**, **shows you the result as a Storybook page for your sign-off**, then implements it, reconciles tokens, and runs your real build + tests before calling it done.

### The team behind it

**Architrave** runs the whole crew for you. You can also call **UX Architect** or **UI Visual** directly for focused design help; **Platform Design** and the **Adversarial Judge** work under the hood. Here's what each does on that single request:

| Agent | Invoke | Its job | On *“Add an empty state to the library list”* |
|---|---|---|---|
| **Architrave** | directly | the lead | Runs the whole pipeline — design → your Storybook sign-off → code → gates. |
| **UX Architect** | directly | how it works | Writes the message + primary action; defines the loading / populated / error variants. |
| **UI Visual** | directly | how it looks | Applies your design tokens: spacing, type scale, the icon, the button style. |
| **Platform Design** | under the hood | native correctness | Checks against Apple HIG / Fluent / WCAG (contrast, hit-target size). |
| **Adversarial Judge** | under the hood | the quality gate | Grades the design, then the built code — **PASS / REVISE / FAIL**. |

## A real app, built this way

**PhonoDeck** — a native macOS music app (SwiftUI) — is the most mature app built this way. Its design lives in **Storybook**; the agents ground in it, reproduce components by their real names, and build the native app to match — the sidebar, the Home recommendations, the now‑playing panel, and the `NowPlayingBar`, all held to Apple's Human Interface Guidelines.

![PhonoDeck — a native macOS music app (SwiftUI): sidebar, Home with recommendations, and the now-playing panel — designed in Storybook, built native](assets/phonodeck.png)

## Design in Storybook first, then build it native

Every change starts in **Storybook** — the fastest, most visual place to design and iterate, and the source of truth the build then matches.

1. **Design the flow in Storybook.** The **UX Architect** lays out the screens and *every* state (empty, loading, populated, error); **UI Visual** styles them with your design tokens. You see it live, tweak it, and confirm — before any app code is written.
2. **Build it for real.** **Architrave** turns the approved design into shipping code. On the **web**, Storybook *is* the build — it develops the real **React** components in isolation, then composes them into pages. On **native** (**SwiftUI**, **WinUI**), Storybook is the spec the native code reproduces, kept in sync by the same design tokens. Either way, the **Adversarial Judge** plus your real build and tests gate it before it's done.

![Designing a flow: information architecture, screens, and every state — sketched in Storybook and grounded in the platform's guidelines, before any native code](assets/flows.png)

## What it does

- 🧭 **Designs the UX, not just the pixels.** The *UX Architect* works out information architecture, navigation, and every state (empty / loading / error) — validated in **Storybook** before anything is built.
- 🎨 **Makes it look native.** *UI Visual* + *Platform Design* hold the UI to the platform's own language — Apple HIG, Microsoft Fluent, web / WCAG — so it feels at home on each OS.
- 🏗️ **Builds the real thing.** *Architrave* turns the approved design into native code — SwiftUI, WinUI, or React — driven by your repo's actual build + tests.
- 🎯 **Follows your design, never reinvents.** Every change starts from your existing Storybook + component map; agents reproduce a component by its real name and touch only the deltas.
- ✅ **Won't ship slop.** An *Adversarial Judge* (LLM‑as‑judge) plus deterministic gates (your real build + tests + token lint) must *both* be green — and design tokens stay reconciled with code.
- 🧩 **One method, every surface.** The same kit runs in the Copilot CLI, the Copilot desktop app, VS Code, **Claude Code**, and the cloud coding agent.

## What it looks like

Install the plugin once — then the agents are available everywhere, and the deterministic gate runs your repo's real build + tests:

![Installing the Architrave UI plugin in the Copilot CLI, then a green gate run](assets/cli.png)

---

## Why this exists

Hand an AI agent a UI task and it tends to **reinvent**: a brand‑new button, slightly different spacing, a component that ignores the design system you already maintain. You end up cleaning up inconsistent "AI slop" by hand.

Architrave UI takes the opposite stance — **ground in the design you already have, reproduce it, and prove it.** Your Storybook + design tokens are the source of truth; agents reproduce existing components by name and change only what's needed; and nothing is "done" until it passes your real build and tests **and** an automated design review.

The method isn't theoretical — it emerged independently across real apps, **PhonoDeck** (native macOS, SwiftUI) and **Sideport** (web, React), which had each settled on the same design‑first, Storybook‑as‑source‑of‑truth, judge‑gated workflow. Architrave UI extracts that shared method into a stack‑agnostic kit, retargeted per repo by one small config file.

## Architecture — four layers

```
1. DESIGN SOURCE OF TRUTH      Storybook (component workbench) + design tokens (.tokens.json, W3C DTCG)
        │  validate / tweak the design here FIRST
        ▼
2. KNOWLEDGE PACKS             knowledge/apple.md · microsoft.md · web.md · design-tokens.md
        │  the Platform Design agent loads the pack named by config.platform
        ▼
3. AGENTS                      UX Architect · UI Visual · Platform Design (pluggable) ·
        │                      Architrave (harness) · Adversarial Judge (LLM-as-judge)
        ▼
4. GATES                       deterministic (build/test/token-lint) + semantic (judge) + design↔code reconcile
```

Everything in layers 2–4 is **retargeted per repo by one config file** (`uikit.config.json`). The agents never hard‑code a stack; they read the config and the matching knowledge pack.

## The design↔code reconciliation model (the hard part)

"Any variation in design or code must be reconciled" is solved by making **design tokens the single source of truth** (see `knowledge/design-tokens.md`). Three token tiers:

- **Reference** (`ref.*`) — raw values (palette, type scale). Context‑free.
- **System / semantic** (`sys.*`) — roles ("label/primary", "surface"). Theming + context (light/dark/RTL/density) lives here.
- **Component** (`comp.*`) — per‑component element decisions, pointing at system tokens.

Both the design (Storybook/Figma) and the code (SwiftUI `Color`/`Font`, WinUI `ResourceDictionary`, CSS vars) **reference the same token names**. A translation step (Style Dictionary / Terrazzo) generates platform code from the tokens. **Drift = when generated platform values diverge from committed code.** The reconcile gate diffs the two and the Architrave fixes by regenerating from the tokens (or, if the design legitimately changed, updates the tokens first, then the code).

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

## Set up a repo

After installing the plugin (above), ground a repo — this is also what reaches the Copilot **cloud** agent:

```bash
/path/to/architrave-ui/tools/install.sh .                          # macOS / Linux
pwsh -NoProfile -File /path/to/architrave-ui/tools/install.ps1 .    # Windows
```

This copies the agents → `.github/agents/`, the gates → `gates/`, the knowledge packs → `knowledge/`, scaffolds `uikit.config.json`, injects a grounding stanza into `AGENTS.md` (idempotent), wires the PostToolUse hook, and drops `.github/workflows/copilot-setup-steps.yml`.

Then point it at your repo — edit `uikit.config.json` — set `platform`, `stack`, `designSource` (your Storybook), `tokens`, and the `build`/`test` commands. Then ask the **Architrave** agent to make a UI change; it grounds, proposes, judges, implements, reconciles, and verifies.

## Layout

```
README.md                     ← you are here
ROADMAP.md                    ← what's built vs. ported next
plugin.json                   ← agent-plugin manifest (Copilot CLI / app / VS Code)
.github/plugin/marketplace.json ← Copilot plugin marketplace (self-hosted)
.claude-plugin/               ← Claude Code plugin + marketplace manifests
kit/
  uikit.config.schema.json    ← per-repo config schema (the keystone)
  examples/                   ← phonodeck / sideport / tessera example configs
knowledge/
  apple.md                    ← Apple HIG pack (SwiftUI) — cited
  microsoft.md                ← Microsoft Fluent 2 / WinUI pack — cited
  web.md                      ← Web + React + component-driven dev pack — cited
  design-tokens.md            ← 3-tier tokens + design↔code reconciliation — cited
agents/                       ← UX Architect · UI Visual · Platform Design · Architrave · Adversarial Judge
gates/                        ← rubric.md · checks.{sh,ps1} · reconcile.{sh,ps1} · quality-gate.{sh,ps1} · hooks/
templates/                    ← AGENTS.stanza.md · copilot-setup-steps.yml (injected by the installer)
tools/                        ← install.sh · install.ps1 (per-repo grounding)
assets/                       ← README screenshots (drop PNGs here)
AGENTS.md                     ← kit-level agent instructions
```
