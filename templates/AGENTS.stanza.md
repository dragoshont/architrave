<!-- This block is managed by Architrave (tools/install.sh / install.ps1). Edit the kit, not this copy. -->
## Delivery Workflow — Architrave

This repo uses **Architrave**, a config-grounded, judge-gated workflow for UI, backend, full-stack features, and plan-only infrastructure. The retargeting config is **`uikit.config.json`** at the repo root — read it first; it names this repo's `platform`, `stack`, UI source of truth (`designSource`, `designMap`, `tokens`), and optionally `backend` / `iac` lanes.

**Before any UI change:**
- **Ground first; reproduce, don't reinvent.** Open the design source of truth named in `uikit.config.json` (the `designSource` Storybook + the `designMap` glossary) and the matching platform knowledge pack. Reproduce the existing component by its glossary name and specify only the deltas. Net-new UI must be mocked in Storybook and confirmed first.
- **Tokens are the single source of truth.** Take values from `uikit.config.json` → `tokens`; if a value must change, change the **token first**, then regenerate. Never hard-code colors/space/type that a token already owns.

**Before any backend/full-stack change:**
- **Contract first.** If `backend` is configured, ground in its architecture docs and contracts before code. The Service Architect owns the API/data contract; the Backend Planner turns it into the human sign-off artifact; the Backend Implementer builds only after that plan is approved.
- **Infrastructure is plan-only.** If `iac` is configured, Architrave may propose diffs and run plan/what-if/policy checks, but a human applies. Never materialize secrets or run apply-shaped commands.

**Gates — must be green before a change is "done":**
- Deterministic: `gates/checks.sh` (POSIX) or `gates/checks.ps1` (Windows) → runs the configured generate/build/test + validates the designMap/tokens JSON. `gates/reconcile.sh` / `.ps1` → reports design↔code token drift. `gates/backend-checks.sh` / `.ps1` covers backend build/test plus plan-only IaC checks when configured.
- Semantic: for non-trivial features, use the **Architrave** agent (the judge-gated harness); the **Adversarial Judge** grades against `gates/rubric.md` and must return PASS.

**Never:** introduce platform-foreign UI, raw values where a token exists, parallel backend abstractions, secret materialization, apply-shaped IaC commands, or any UI/API claim the product cannot truthfully perform.
