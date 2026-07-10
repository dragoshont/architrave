# Intake

## Understanding

Fix Architrave issue #3 at the config contract so a knowledge repository can
adopt the kit without synthetic UI fields, then migrate `social-ops` and prove a
fresh VS Code editor chat loads the repo-local knowledge-aware agent.

## Acceptance Criteria

1. `kind: knowledge` validates without UI, backend, IaC, or ops fields.
2. Legacy application configs remain valid when `kind` is absent.
3. Both installers scaffold the canonical knowledge example explicitly.
4. Paired gates, agents, docs, and tests describe knowledge mode honestly.
5. Linux and Windows release gates pass.
6. `social-ops` migrates, passes gates, and works in a fresh VS Code chat.

## Grounding Sources

- GitHub issue `dragoshont/architrave#3`.
- `kit/architrave.config.schema.json`.
- `tools/install.*`, `gates/*`, `agents/*`, and existing CI fixtures.
- `/Users/dragoshont/Repo/social-ops` as the first consumer.

## Assumptions

- The only proven non-application profile is `knowledge`.
- Configured build and test commands remain intentionally executable by gates.

## Blocking Questions

None. The user authorized autonomous continuation after the third judge loop.