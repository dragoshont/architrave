# AGENTS.md — Architrave

Architrave is a **cross-platform, judge-gated agent kit** for UI, backend, full-stack features, and plan-only infrastructure, distributed as a Copilot / Claude **agent plugin** plus a per-repo **installer**. UI grounds in Storybook + design tokens; backend grounds in architecture docs + contracts; IaC is proposal/plan-only.

## What's here
- `agents/` — the ten agents: **Architrave**, **Product Research**, **UX Architect**, **UI Visual**, **Platform Design**, **Service Architect**, **Backend Planner**, **Backend Implementer**, **Infra Engineer**, and **Adversarial Judge**. Shared `.agent.md` format across VS Code / Copilot CLI / the Copilot app / Claude Code.
- `gates/` — deterministic gates as **`.sh` + `.ps1` pairs** (`checks`, `reconcile`, `quality-gate`, `backend-checks`) + `rubric.md` (the judge's rubric) + `hooks/` (PostToolUse guards).
- `knowledge/` — platform packs (`apple.md`, `microsoft.md`, `web.md`) + `backend.md` + `design-tokens.md`.
- `kit/` — `uikit.config.schema.json` (the per-repo config keystone) + `examples/`.
- `plugin.json` + `.github/plugin/marketplace.json` — agent-plugin + self-hosting marketplace.
- `templates/` + `tools/install.{sh,ps1}` — the per-repo installer and what it injects.

## Conventions when changing the kit
- **Keep every gate's `.sh` and `.ps1` in lockstep** — identical behavior and exit codes (PASS=0 / FAIL=1 / BLOCK=2 / DRIFT=1). POSIX uses `jq`; PowerShell uses native `ConvertFrom-Json` (no jq on Windows).
- **Agents and gates are config-driven** — resolve everything through `uikit.config.json`; never hard-code a stack or a path.
- **Reproduce, don't reinvent** — extend the existing agent / gate / knowledge structure; don't add a parallel abstraction (the kit practices what it preaches).
- Keep the README + ROADMAP in sync when structure changes.

## Build / verify
- Validate JSON manifests: `jq empty plugin.json .github/plugin/marketplace.json kit/uikit.config.schema.json`.
- Validate agent YAML frontmatter with `ruby -ryaml` (PyYAML is not installed on the dev Mac).
- Smoke-test the gates against a config with `gates/checks.sh --quick`.
- Test plugin load: `copilot plugin install "$PWD"` → `copilot plugin list` → `copilot plugin uninstall architrave`.
