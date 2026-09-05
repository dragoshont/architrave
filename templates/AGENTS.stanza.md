<!-- This block is managed by Architrave (tools/install.sh / install.ps1). Edit the kit, not this copy. -->
## Delivery Workflow — Architrave

This repo uses **Architrave**, a config-grounded durable build control plane for
knowledge/automation, UI, backend, full-stack, infrastructure, product/runtime
verification, and learning. Read root **`architrave.config.json`** first.

**When `kind` is `knowledge`:**
- Ground in repository docs, scripts, skills, schemas, tests, existing instructions, and learning artifacts.
- Run configured `build` and `test` commands.
- Do not infer or request a UI platform, Storybook, design map, tokens, backend, IaC, or runtime lane. UI reconciliation is not applicable.

When `kind` is absent, use the application fields and optional `backend`, `iac`,
`ops`, `autonomy`, `workers`, `runtime`, `invariants`, `evaluation`, and
`learning` blocks. Load `knowledge/runtime-v2.md` for non-trivial durable work.

**Before any UI change in an application-profile repo:**
- **Ground first; reproduce, don't reinvent.** Open the design source of truth named in `architrave.config.json` (the `designSource` Storybook + the `designMap` glossary) and the matching platform knowledge pack. **On a native platform, also load the repo-root constitution — `constitution-apple.md` (Apple) or `constitution-windows.md` (Windows)** — the deep, source-cited native rule base (verbatim type tables/ramp, materials layering, system icons, the native component catalog, and the shared-screenshot conformance-audit protocol). Reproduce the existing component by its glossary name and specify only the deltas. Net-new UI must be mocked in Storybook and confirmed first.
- **Tokens are the single source of truth.** Take values from `architrave.config.json` → `tokens`; if a value must change, change the **token first**, then regenerate. Never hard-code colors/space/type that a token already owns.

**Before any backend/full-stack change:**
- **Contract first.** If `backend` is configured, ground in its architecture docs and contracts before code. The Service Architect owns the API/data contract; the Backend Planner turns it into the human sign-off artifact; the Backend Implementer builds only after that plan is approved.
- **Infrastructure is plan-only by default.** Apply/rollback is allowed only
	when canonical Run policy explicitly grants the exact target/operation. Then
	checkpoint, record a mutation receipt, and verify health/version/digest.

**Before any implementation:**
- **YAGNI ladder.** Do not build presumptive features. First try: delete/skip, reuse existing repo source of truth, native/platform feature, standard library, already-installed dependency, tiny local implementation. New abstractions, dependencies, flags, config, factories, or layers need current evidence, not a guessed future. Never cut validation, data-loss handling, security, accessibility, capability honesty, or the smallest useful test.
- **Durable Run.** Use `harness/architrave_runtime.py` for canonical Run v2
	state. Outcome, Acceptance Matrix, TaskGraph, events, policy, and checkpoints
	are machine-readable. The phase ledger is a projection, not an autonomy gate.
	Under `approved-program`, continue dependency-ready in-scope tasks across
	internal phase boundaries without asking again.

**Gates — must be green before a change is "done":**
- Deterministic: `gates/checks.sh` (POSIX) or `gates/checks.ps1` (Windows) runs configured generate/build/test and profile-appropriate JSON checks. `gates/reconcile.*` reports UI token drift when configured and is not applicable to knowledge profiles. `gates/backend-checks.*` covers backend plus plan-only IaC when configured.
- Runtime: use `harness/invariant_engine.py` and configured
	`harness/legibility.py` Web/Electron/iOS/deployment checks. Compile is not a
	product reality gate.
- Semantic: scale by R0-R4. R3/R4 require independent GPT- and Claude-family
	passes; R4 also requires security and policy review.

**Learning loop:** Keep private Run evidence under `.architrave/runs/`, isolated
workers under `.architrave/worktrees/`, and the HMAC key at
`.architrave/runtime.key`; all stay ignored by default.
Maintain concise tracked repo profile/lessons, validate stale facts, and never
store secrets or hidden reasoning.

**Adaptive execution:** Load `knowledge/execution-policy.md`. Express bounded work with provider-neutral model/reasoning/context/verification intent, treating FAST/BALANCED/DEEP/CRITICAL as provisional convenience presets. Task characteristics override role hints. Use the current host's structured subagent invocation when useful and otherwise inherit; never shell out to another agent harness, depend on a provider SDK, or commit concrete model IDs as universal policy. A stronger model never replaces required gates.

Low-risk FAST/BALANCED knowledge or mechanical work may use deterministic-only `verification: default` when every criterion is mechanically checked. Semantic, UI, contract, architecture, migration, security/trust, IaC, and high-blast-radius work raises the floor to `independent` or `cross-family`; the full cross-family gate still requires verified GPT/Copilot and Claude passes.

**Never:** invent an unconfigured lane, introduce platform-foreign UI, use raw values where a token exists, create parallel backend abstractions, manually edit canonical Run state, let workers escalate policy or complete tasks, blindly retry uncertain side effects, mutate outside scoped policy, materialize secrets, run apply-shaped IaC commands, or claim compile/plan/simulation or an unsupported capability as a shipped reality.
