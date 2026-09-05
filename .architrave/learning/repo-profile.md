# Architrave Repo Profile

## Purpose

Architrave is a cross-platform, judge-gated agent kit distributed as Copilot, Claude, and Codex/ChatGPT plugins plus a per-repo installer. It supports application lanes and an explicit knowledge/automation repository profile. Evidence: `AGENTS.md`, `plugin.json`, `.codex-plugin/plugin.json`, `README.md`, `kit/architrave.config.schema.json`.

## Surfaces And Lanes

- Agents live under `agents/` and are distributed by plugin manifests.
- Codex plugin skills live only under `skills/`; project role registrations and generated role files live under `.codex/` and are opt-in during adoption.
- Knowledge packs live under `knowledge/` and are copied into adopted repos by `tools/install.*` and `tools/update.*`.
- Paired managed-path helpers live at `tools/managed-paths.sh` and `tools/ManagedPaths.ps1`; install/update must route every managed target mutation through them.
- Deterministic gates live under `gates/`; audit helpers live under `harness/`.
- Config schema and examples live under `kit/`.
- Knowledge repositories use `kind: knowledge`; Codex custom roles are advisory contexts that inherit parent permission/MCP/skill state, while mandatory semantic gates use bounded external launchers.

## Source Of Truth

- Plugin manifests: `plugin.json`, `.github/plugin/marketplace.json`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.codex-plugin/plugin.json`.
- Agent roster and repo conventions: `AGENTS.md`, `README.md`, `ROADMAP.md`.
- Validation gate: `scripts/check-manifests.sh`.

## Build And Test

- Validate plugin/manifests/frontmatter/schema: `scripts/check-manifests.sh`.
- Validate run artifacts: `bash harness/validate-run.sh <run-dir>` when executable bit is unavailable.

## Architecture Map

- `agents/architrave.agent.md` is the conductor.
- `agents/tournament-analyst.agent.md` is the read-only high-risk option analyst.
- `agents/product-research.agent.md` and `agents/operations-ux.agent.md` are read-only research/pattern specialists.
- UI specialists: `ux-architect`, `ui-visual`, `platform-design`.
- Backend/infra/runtime specialists: `service-architect`, `backend-planner`, `backend-implementer`, `infra-engineer`, `runtime-observer`.
- `gates/rubric.md` is the judge rubric.

## Recurring Gotchas

- The plugin source repo intentionally has no `architrave.config.json`; `harness/init-run.sh` will not auto-initialize here. Create run artifacts manually or add a repo-local config only with explicit approval.
- Harness scripts may not have executable bits in the checkout; run with `bash harness/validate-run.sh ...` if direct execution is denied.

## Validated Facts

| Fact | Evidence | Last Checked |
|---|---|---|
| There are 13 packaged agents. | `find agents -maxdepth 1 -name '*.agent.md' | wc -l`; `scripts/check-manifests.sh` frontmatter pass. | 2026-07-11 |
| Knowledge packs include operations UX, YAGNI, and the learning loop. | `scripts/check-manifests.sh` knowledge-pack pass. | 2026-07-10 |
| Current released plugin version is 0.10.3 with structured workspace-hook output and updater propagation. | `plugin.json`; v0.10.3 release; issues #3 and #6 run artifacts. | 2026-07-10 |
| The released kit has a schema-valid `kind: knowledge` profile and explicit installer support. | `kit/examples/knowledge.architrave.json`; `scripts/test-config-profiles.sh`; `scripts/test-installers.sh`; v0.10.2 release. | 2026-07-10 |
| Codex/ChatGPT package three plugin-only skills and two generated project roles; disposable live smokes validate skill invocation, role routing, and isolated MCP hostile-output handling. | `.codex-plugin/plugin.json`; `.codex/`; `skills/`; `scripts/test-codex-runtime.py --live`. | 2026-07-11 |
| Knowledge adoption uses a five-agent crew (`architrave`, `adversarial-judge`, `tournament-analyst`, `product-research`, `runtime-observer`); explicit refresh safely migrates legacy full installs while preserving custom agents and Codex roles. | `tools/install.*`; `tools/update.*`; `scripts/test-installers.*`; run `20260721T-lean-install-hardening`. | 2026-07-21 |
| Installer/updater managed destinations fail closed on links/reparse points, escaping paths, unsupported file types, and ambiguous profile controls; staged replacement preserves external hard-linked content. | `tools/managed-paths.sh`; `tools/ManagedPaths.ps1`; `scripts/test-installers.*`; run `20260721T-lean-install-hardening`. | 2026-07-21 |

## Last Reviewed

2026-07-21 during run `20260721T-lean-install-hardening`.