# AGENTS.md — Architrave

Architrave is a **cross-platform, judge-gated durable software-build control plane** for
knowledge/automation, UI, backend, full-stack, plan-only infrastructure, optional
runtime observation/verification, adaptive execution intent, and durable
learning/audit artifacts. It is distributed as a Copilot / Claude / Codex /
ChatGPT plugin plus a per-repo installer. Knowledge profiles ground in repository
sources without inventing UI; UI grounds in Storybook + design tokens; backend
grounds in architecture docs + contracts; IaC is proposal/plan-only. Mutation
defaults to deny; explicit Run policy may authorize a bounded target and operation.

## What's here
- `agents/` — fourteen optional roles: **Architrave**, **CTO**, **Product Research**, **Operations UX**, **UX Architect**, **UI Visual**, **Platform Design**, **Service Architect**, **Backend Planner**, **Backend Implementer**, **Infra Engineer**, **Runtime Observer**, **Tournament Analyst**, and **Adversarial Judge**. Shared `.agent.md` format across VS Code / Copilot CLI / the Copilot app / Claude Code; role availability is not a reason to spawn.
- `gates/` — deterministic gates as **`.sh` + `.ps1` pairs** (`checks`, `reconcile`, `quality-gate`, `backend-checks`) + `rubric.md` (the judge's rubric). No automatic hook definitions are packaged.
- `harness/` — durable run-artifact helpers (`init-run`, `validate-run`, `semantic-review`, semantic learning review/recovery) as `.sh` + `.ps1` pairs plus schemas, and the Python Run v2 state machine, worker/workspace adapters, invariants, product legibility, and v1/v2 validation.
- `knowledge/` — platform packs (`apple.md`, `microsoft.md`, `web.md`) + `backend.md` + `operations-ux.md` + `design-tokens.md` + `execution-policy.md` + `learning-loop.md` + `yagni.md` + `runtime-v2.md` for durable control-plane semantics.
- `kit/` — `architrave.config.schema.json` (the per-repo config keystone) + `examples/`.
- `plugin.json` + `.github/plugin/marketplace.json` — Copilot agent-plugin + self-hosting marketplace.
- `.codex-plugin/plugin.json` + `skills/` + `.codex/` — Codex/ChatGPT plugin skills and generated project roles. Skills stay plugin-only; adoption copies roles only with `--codex` / `-Codex`.
- `templates/` + `tools/install.{sh,ps1}` — the per-repo installer and what it injects.

## Conventions when changing the kit
- Keep Python as the sole substantive cross-platform implementation. `.sh` and
  `.ps1` compatibility entrypoints may only discover Python and forward argv,
  stdout/stderr, and exit codes to the same Python CLI. Gate exits remain
  PASS=0 / FAIL=1 / BLOCK=2 / DRIFT=1 where applicable.
- **Keep install/update logic canonical in `tools/install_update.py`** — the four public `.sh` / `.ps1` entrypoints are Python-discovery/exec shims only; managed-path safety and adversarial fixtures live in Python.
- **Agents and gates are config-driven** — resolve everything through `architrave.config.json`; never hard-code a stack or a path.
- **Thin supervision** — direct work first; the host owns sessions, context,
  routing and lifecycle. At most three active children, depth one, exclusive
  mutable ownership, compact returns, and deterministic repeated-failure stops.
- **Model selection is host-owned** — user pins/mappings live in host settings,
  not repository config, WorkPackets or Run state. Record only reported effective
  selection in worker evidence. Never shell out to another harness as a worker.
- **Run state is API-owned** — never manually edit `run.json`, `events.jsonl`,
	policy, checkpoints, or task statuses. The Phase Ledger is a projection.
- **Default deny** — unconfigured infrastructure/runtime is plan/read-only.
	Scoped authorized mutation needs checkpoint, receipt, and live verification.
- **YAGNI is a gate, not a vibe** — use `knowledge/yagni.md`; do not add future-proof abstractions/dependencies/config unless the current task proves they are needed.
- **Reproduce, don't reinvent** — extend the existing agent / gate / knowledge structure; don't add a parallel abstraction (the kit practices what it preaches).
- Keep the README + ROADMAP in sync when structure changes.

## Build / verify
- Validate JSON manifests: `jq empty plugin.json .github/plugin/marketplace.json kit/architrave.config.schema.json`.
- Validate harness schemas: `jq empty harness/schemas/*.json`.
- Validate agent YAML frontmatter with `ruby -ryaml` (PyYAML is not installed on the dev Mac).
- Validate Codex skills/roles and all adapter fixtures through `scripts/check-manifests.sh`; use `python3 scripts/test-codex-runtime.py --live` only for provider-backed release evidence.
- Run focused runtime suites with `python3 scripts/test-runtime-v2.py`,
  `test-worker-adapters.py`, `test-invariant-engine.py`, `test-legibility.py`,
  `test-workspaces.py`, and `test-longbuild-runtime.py`.
- Smoke-test the gates against a config with `gates/checks.sh --quick`.
- Test repository profiles with `scripts/test-config-profiles.sh` and installers with `python3 scripts/test_install_update.py`.
- Test plugin load: `copilot plugin install "$PWD"` → `copilot plugin list` → `copilot plugin uninstall architrave`.
