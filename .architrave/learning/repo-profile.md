# Architrave Repo Profile

## Purpose

Architrave is a cross-platform, judge-gated agent kit distributed as a Copilot/Claude plugin plus per-repo installer. It supports application lanes and an explicit knowledge/automation repository profile. Evidence: `AGENTS.md`, `plugin.json`, `README.md`, `kit/architrave.config.schema.json`.

## Surfaces And Lanes

- Agents live under `agents/` and are distributed by plugin manifests.
- Knowledge packs live under `knowledge/` and are copied into adopted repos by `tools/install.*` and `tools/update.*`.
- Deterministic gates live under `gates/`; audit helpers live under `harness/`.
- Config schema and examples live under `kit/`.
- Knowledge repositories use `kind: knowledge`; first-class Codex packaging is tracked separately in issue #4.

## Source Of Truth

- Plugin manifests: `plugin.json`, `.github/plugin/marketplace.json`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`.
- Agent roster and repo conventions: `AGENTS.md`, `README.md`, `ROADMAP.md`.
- Validation gate: `scripts/check-manifests.sh`.

## Build And Test

- Validate plugin/manifests/frontmatter/schema: `scripts/check-manifests.sh`.
- Validate run artifacts: `bash harness/validate-run.sh <run-dir>` when executable bit is unavailable.

## Architecture Map

- `agents/architrave.agent.md` is the conductor.
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
| There are 12 packaged agents. | `find agents -maxdepth 1 -name '*.agent.md' | wc -l`; `scripts/check-manifests.sh` frontmatter pass. | 2026-07-10 |
| Knowledge packs include operations UX, YAGNI, and the learning loop. | `scripts/check-manifests.sh` knowledge-pack pass. | 2026-07-10 |
| Current released plugin version is 0.9.1; issue #3 changes remain unreleased until Phase 2. | `plugin.json`; manifest version-sync gate; issue #3 phase ledger. | 2026-07-10 |
| The working tree has a schema-valid `kind: knowledge` profile and explicit installer support. | `kit/examples/knowledge.architrave.json`; `scripts/test-config-profiles.sh`; `scripts/test-installers.sh`. | 2026-07-10 |

## Last Reviewed

2026-07-10 during run `20260710T-issue-3-knowledge-profile`.