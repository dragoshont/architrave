<!-- This block is managed by Architrave (tools/install.sh / install.ps1). Edit the kit, not this copy. -->
## Delivery Workflow — Architrave

This repo uses **Architrave**, a config-grounded, judge-gated workflow for UI, backend, full-stack features, plan-only infrastructure, and durable learning artifacts. The retargeting config is **`architrave.config.json`** at the repo root — read it first; it names this repo's `platform`, `stack`, UI source of truth (`designSource`, `designMap`, `tokens`), optional `backend` / `iac` / `ops` lanes, and optional `learning` paths.

**Before any UI change:**
- **Ground first; reproduce, don't reinvent.** Open the design source of truth named in `architrave.config.json` (the `designSource` Storybook + the `designMap` glossary) and the matching platform knowledge pack. **On a native platform, also load the repo-root constitution — `constitution-apple.md` (Apple) or `constitution-windows.md` (Windows)** — the deep, source-cited native rule base (verbatim type tables/ramp, materials layering, system icons, the native component catalog, and the shared-screenshot conformance-audit protocol). Reproduce the existing component by its glossary name and specify only the deltas. Net-new UI must be mocked in Storybook and confirmed first.
- **Tokens are the single source of truth.** Take values from `architrave.config.json` → `tokens`; if a value must change, change the **token first**, then regenerate. Never hard-code colors/space/type that a token already owns.

**Before any backend/full-stack change:**
- **Contract first.** If `backend` is configured, ground in its architecture docs and contracts before code. The Service Architect owns the API/data contract; the Backend Planner turns it into the human sign-off artifact; the Backend Implementer builds only after that plan is approved.
- **Infrastructure is plan-only.** If `iac` is configured, Architrave may propose diffs and run plan/what-if/policy checks, but a human applies. Never materialize secrets or run apply-shaped commands.

**Before any implementation:**
- **YAGNI ladder.** Do not build presumptive features. First try: delete/skip, reuse existing repo source of truth, native/platform feature, standard library, already-installed dependency, tiny local implementation. New abstractions, dependencies, flags, config, factories, or layers need current evidence, not a guessed future. Never cut validation, data-loss handling, security, accessibility, capability honesty, or the smallest useful test.
- **Phase ledger.** For non-trivial SDD/backend/full-stack/multi-slice work, keep a visible phase ledger before implementation. Mark exactly one phase `in-progress`, state each phase's scope/out-of-scope/gate, and explicitly separate completed phases from phases that are `not-started`. Do not silently begin the next phase.

**Gates — must be green before a change is "done":**
- Deterministic: `gates/checks.sh` (POSIX) or `gates/checks.ps1` (Windows) → runs the configured generate/build/test + validates the designMap/tokens JSON. `gates/reconcile.sh` / `.ps1` → reports design↔code token drift. `gates/backend-checks.sh` / `.ps1` covers backend build/test plus plan-only IaC checks when configured.
- Semantic: for non-trivial features, use the **Architrave** agent (the judge-gated harness); the **Adversarial Judge** grades against `gates/rubric.md` and must return PASS.

**Learning loop:** For non-trivial work, keep the run artifacts under `.architrave/runs/` (or `learning.runArtifactsPath`), maintain the concise repo profile at `.architrave/learning/repo-profile.md` (or `learning.repoProfilePath`), and record repeated lessons in `.architrave/learning/repo-lessons.md` (or `learning.lessonsPath`). Validate persisted facts against the current branch before using/promoting them, never store secrets, and promote stable lessons into config, `AGENTS.md`, `.github/instructions/`, or docs only after review.

**Never:** introduce platform-foreign UI, raw values where a token exists, parallel backend abstractions, secret materialization, apply-shaped IaC commands, or any UI/API claim the product cannot truthfully perform.
