<!-- This block is managed by Architrave UI (tools/install.sh / install.ps1). Edit the kit, not this copy. -->
## Design language — Architrave UI

This repo uses **Architrave UI**, a design-grounded, judge-gated UI workflow. The retargeting config is **`uikit.config.json`** at the repo root — read it first; it names this repo's `platform`, `stack`, `designSource` (Storybook), `designMap` (component glossary), and `tokens`.

**Before any UI change:**
- **Ground first; reproduce, don't reinvent.** Open the design source of truth named in `uikit.config.json` (the `designSource` Storybook + the `designMap` glossary) and the matching platform knowledge pack. Reproduce the existing component by its glossary name and specify only the deltas. Net-new UI must be mocked in Storybook and confirmed first.
- **Tokens are the single source of truth.** Take values from `uikit.config.json` → `tokens`; if a value must change, change the **token first**, then regenerate. Never hard-code colors/space/type that a token already owns.

**Gates — must be green before a change is "done":**
- Deterministic: `gates/checks.sh` (POSIX) or `gates/checks.ps1` (Windows) → runs the configured generate/build/test + validates the designMap/tokens JSON. `gates/reconcile.sh` / `.ps1` → reports design↔code token drift.
- Semantic: for non-trivial features, use the **Feature Builder** agent (the judge-gated harness); the **Adversarial Judge** grades against `gates/rubric.md` and must return PASS.

**Never:** introduce platform-foreign patterns, raw values where a token exists, parallel abstractions, or UI that claims a capability the app can't truthfully perform.
