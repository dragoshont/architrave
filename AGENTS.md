# AGENTS.md — Architrave

Architrave is a **spec-driven, cross-platform, judge-gated durable software-build control plane**.
The canonical lifecycle source is `.architrave/state.yaml`, maintained through
`python harness/architrave_cli.py state`; see `docs/lifecycle-state.md`.
Existing `tasks.md` is a migration input or generated read-only view, never a
competing authority once state is selected. Progress stays blank, In progress
or Code ready, separate from disposition and acceptance. Preserve owner corrections and verify actual behavior; do not create
SPEC/REQ declarations or use the retired completion barrier. Legacy Run and
requirements commands remain explicit opt-in operations. It covers
knowledge/automation, UI, backend, full-stack, plan-only infrastructure, optional
runtime observation/verification, adaptive execution intent, and durable
learning/audit artifacts. It is distributed as a Copilot / Claude / Codex /
ChatGPT plugin plus a per-repo installer. Knowledge profiles ground in repository
sources without inventing UI; UI grounds in Storybook + design tokens; backend
grounds in architecture docs + contracts; IaC is proposal/plan-only. Mutation
defaults to deny; explicit Run policy may authorize a bounded target and operation.

## What's here
- `agents/` — fourteen optional roles: **Architrave**, **CTO**, **Product Research**, **Operations UX**, **UX Architect**, **UI Visual**, **Platform Design**, **Service Architect**, **Backend Planner**, **Backend Implementer**, **Infra Engineer**, **Runtime Observer**, **Tournament Analyst**, and **Adversarial Judge**. Shared `.agent.md` format across VS Code / Copilot CLI / the Copilot app / Claude Code; role availability is not a reason to spawn.
- `.architrave/state.yaml` — API-owned lifecycle state; `tasks.md` is historical/import input. `SPEC.md` retains historical requirements.
- `gates/` — deterministic optional gates in `gate_runner.py` + `rubric.md`. `hooks.json` supplies a compact Copilot session-start pointer and advisory repeated-read loop detection; the SPEC-based completion barrier is retired. No automatic post-edit quality or stop-loop hooks.
- `harness/` — durable run-artifact helpers (`init-run`, `validate-run`, `semantic-review`, semantic learning review/recovery) as `architrave_cli.py` subcommands plus schemas, and the Python Run v2 state machine, worker/workspace adapters, invariants, product legibility, and v1/v2 validation.
- `harness/board_data.py`, `board_view.py` + `board.css`/`board.js` — bundled YAML-backed work board, bounded observations and advisory insights; see `docs/dashboard.md`.
- `knowledge/` — platform packs (`apple.md`, `microsoft.md`, `web.md`) + `backend.md` + `operations-ux.md` + `design-tokens.md` + `execution-policy.md` + `learning-loop.md` + `yagni.md` + `runtime-v2.md` for durable control-plane semantics.
- `kit/` — `architrave.config.schema.json` (the per-repo config keystone) + `examples/`.
- `plugin.json` + `.github/plugin/marketplace.json` — Copilot agent-plugin + self-hosting marketplace.
- `.codex-plugin/plugin.json` + `skills/` + `.codex/` — eight Architrave plugin-only Codex/ChatGPT skills (including explicit-only agent, skill, and MCP authoring) plus six vendored MIT/Apache-2.0 skills (sources and licences in README) plus generated project roles. Adoption copies roles only with `--codex`.
- `templates/` + `tools/install_update.py` — the per-repo installer and what it injects.

## Conventions when changing the kit
- **Python only.** Every gate, harness command, installer and test is a Python
  CLI invoked as `python <file>.py`; do not add shell entrypoints
  (the validator rejects them; vendored skill assets are the only exception).
  Gate exits remain PASS=0 / FAIL=1 / BLOCK=2 / DRIFT=1 where applicable.
- **Keep install/update logic canonical in `tools/install_update.py`** — managed-path safety and adversarial fixtures live there.
- **Agents and gates are config-driven** — resolve everything through `architrave.config.json`; never hard-code a stack or a path.
- **Thin supervision** — direct work first; the host owns sessions, context,
  routing and lifecycle. `workers.maxParallel` active children (default three, max twenty), depth one, exclusive
  mutable ownership, compact returns, and deterministic repeated-failure stops.
- **Model selection is host-owned** — user pins/mappings live in host settings,
  not repository config, WorkPackets or Run state. Record only reported effective
  selection in worker evidence. Never shell out to another harness as a worker.
- **Run state is API-owned** — never manually edit `run.json`, `events.jsonl`,
	policy, checkpoints, or task statuses. The Phase Ledger is a projection.
- **Lifecycle state is API-owned** — one locked restricted-YAML snapshot holds
  state, corrections and idempotent receipts. The board and scoped agent context
  read that same revision; human labels and hashes do not authenticate authority.
- **Default deny** — unconfigured infrastructure/runtime is plan/read-only.
	Scoped authorized mutation needs checkpoint, receipt, and live verification.
- **YAGNI is a gate, not a vibe** — use `knowledge/yagni.md`; do not add future-proof abstractions/dependencies/config unless the current task proves they are needed.
- **Reproduce, don't reinvent** — extend the existing agent / gate / knowledge structure; don't add a parallel abstraction (the kit practices what it preaches).
- Keep the README + ROADMAP in sync when structure changes.

## Build / verify
Interpreter: `python3` on macOS/Linux, `python` on native Windows, where `python3` is
usually the Microsoft Store stub and exits 49. Examples use `python`; every entrypoint is a
Python or Node CLI.
- Full manifest suite (manifests, seven-field version sync, Codex roles, installer, profile
  and runtime fixtures): `python scripts/check_manifests.py`. It is long-running, must run
  inside a git checkout, needs `npx` for its AJV schema checks, and skips agent/skill YAML
  frontmatter when `ruby` is not on PATH.
  Release validation uses Python 3.11+ (`tomllib` and `unittest.enterContext` are
  required by the complete fixture suite), rather than macOS's older system Python.
- `python scripts/check_manifests.py --scan-only` runs only the repository scans and the
  Python-only entrypoint check. It skips JSON well-formedness, version sync, YAML and
  fixture coverage, so report it as scan-only, never as the full suite.
- Optional JSON spot check where `jq` is installed:
  `jq empty plugin.json .github/plugin/marketplace.json kit/architrave.config.schema.json harness/schemas/*.json`.
- Provider-backed Codex evidence, for releases only: `python scripts/test-codex-runtime.py --live`.
- Focused runtime suites: `python scripts/test-runtime-v2.py`, `test-worker-adapters.py`,
  `test-invariant-engine.py`, `test-legibility.py`, `test-workspaces.py` and
  `test-longbuild-runtime.py`, plus `node --experimental-vm-modules scripts/test-native-review.mjs`.
- Canonical lifecycle: `python scripts/test-lifecycle.py` (real store/CLI/board,
  concurrent writers, crash replacement and scoped correction/recovery paths).
- Dashboard data/CLI/rendering: `python scripts/test-dashboard.py`; optional real
  Chromium controls/layout: `python scripts/test-dashboard-browser.py --board <html> --output <session-dir>`.
- Gates: `python gates/gate_runner.py checks --quick` is the smoke test. `python gates/gate_runner.py checks`
  runs the configured build and test recipes through the host shell (Git Bash when present,
  else `cmd`); on native Windows cite that run, not WSL or a direct test invocation.
- Repository profiles: `python scripts/test-config-profiles.py` (needs `npx`). Installers:
  `python scripts/test_install_update.py`.
- Test plugin load: `copilot plugin install "$PWD"` → `copilot plugin list` → `copilot plugin uninstall architrave`.
