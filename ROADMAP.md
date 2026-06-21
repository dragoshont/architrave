# Roadmap

## Milestone 1 — Foundation (this commit)
- [x] Architecture + adoption model (`README.md`)
- [x] Per‑repo config schema (`kit/uikit.config.schema.json`) + example configs for PhonoDeck / Sideport / Tessera
- [x] Platform knowledge packs (researched + cited): Apple HIG, Microsoft Fluent 2 / WinUI, Web + React + component‑driven dev
- [x] Design‑token + design↔code reconciliation backbone (`knowledge/design-tokens.md`)

## Milestone 2 — Agents (port + generalize from PhonoDeck)
- [x] `agents/ux-architect.agent.md` — platform‑agnostic IA/flow/state, grounded per‑repo by config + Storybook.
- [x] `agents/ui-visual.agent.md` — platform‑agnostic visual hierarchy/tokens; loads the platform pack for specifics.
- [x] `agents/platform-design.agent.md` — **pluggable**: reads `config.platform` and the matching `knowledge/*.md` (Apple HIG / Fluent / Web).
- [x] `agents/architrave.agent.md` — the config‑driven, judge‑gated harness (understand → propose → judge → implement → reconcile → tests → judge → verify).
- [x] `agents/adversarial-judge.agent.md` — LLM‑as‑judge against `gates/rubric.md` (cross‑platform).

## Milestone 3 — Gates (DONE)
- [x] `gates/rubric.md` — cross‑platform evaluation rubric (spec / design‑language / platform / adversarial / security / a11y / reconcile / tests / verification).
- [x] `gates/reconcile.sh` + `gates/reconcile.ps1` — design↔code drift checker (regenerate from tokens via `config.tokenBuild`, diff against committed code).
- [x] `gates/checks.sh` + `gates/checks.ps1` — deterministic gate runner driven by `uikit.config.json` (generate/build/test + designMap/tokens JSON valid; `--quick` / `-Quick` for hooks).
- [x] `gates/quality-gate.sh` + `gates/quality-gate.ps1` — lightweight quick gate (fast JSON guard + reconcile/judge reminder).
- [x] `gates/hooks/design-guard.json` (POSIX) + `design-guard.windows.json` (pwsh) — PostToolUse JSON‑validity guard.

> **Cross‑platform:** every gate ships a POSIX `.sh` (jq) **and** a PowerShell `.ps1` (native `ConvertFrom-Json`, no jq needed on Windows) variant. Both verified to produce identical PASS / FAIL / BLOCK / DRIFT exit codes (0 / 1 / 2 / 1).

## Milestone 4 — Distribution
- [x] **Plugin packaging** — `plugin.json` + `.github/plugin/marketplace.json`. Verified end‑to‑end with the real Copilot CLI (v1.0.64): both `copilot plugin install <path>` and the future‑proof `copilot plugin marketplace add dragoshont/architrave` + `copilot plugin install architrave@architrave` load the agent crew. The shared `~/.copilot` runtime ⇒ also reaches the Copilot app + VS Code.
- [x] `tools/install.sh` (+ `install.ps1`) — per‑repo grounding: copies agents → `.github/agents/`, gates → `gates/`, scaffolds `uikit.config.json`, injects the `AGENTS.md` stanza (idempotent), wires the per‑OS PostToolUse hook, drops `copilot-setup-steps.yml`. Both variants tested on throwaway repos.
- [x] `AGENTS.md` (kit) + a per‑repo `AGENTS.md` stanza template (`templates/AGENTS.stanza.md`) — the cloud‑agent reach.
- [x] Prove on Sideport (web) — adopted on an isolated worktree (branch `architrave-ui-adoption`, based on the UI branch's committed HEAD). The installer wired the gates to Sideport's real `tsc -b && vite build` + `eslint`; baseline gate green; ran the Feature‑Builder harness for a grounded a11y change (`aria-current` on the primary nav + the onboarding step‑tabs — WCAG 2.2 / web pack), with a consistency sweep; post‑change gate green. The config was corrected to the repo's real scripts (`test`→`lint`, `screenshot`→`test:screens`).

---

**Status: M1–M4 complete.** The kit is built, cross‑platform tested, packaged as a Copilot/Claude plugin, installable per‑repo, and proven on a non‑PhonoDeck repo. The public repo is `dragoshont/architrave`.
