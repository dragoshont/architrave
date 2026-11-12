# Migrating Bespoke Agents To Architrave

Architrave is meant to replace most project-specific development agents with one front-door conductor plus a small specialist crew. Keep project knowledge in `architrave.config.json`, `AGENTS.md`, `.github/instructions/*.md`, docs, contracts, and Storybook; keep reusable workflow behavior in Architrave.

## Migration Pattern

1. **Inventory existing agents.** Capture each agent's mission, tools, trigger phrases, handoffs, and hard rules.
2. **Map reusable behavior to Architrave.** Move general behaviors into Architrave agents, knowledge packs, or `gates/rubric.md`; leave product/domain facts in the app repo.
3. **Archive, don't delete.** Move old agents into `docs/archive/<old-agent-set>/` with a README explaining the replacement mapping.
4. **Adopt the repo.** Add `architrave.config.json`, copy agents/gates/knowledge/harness with `python tools/install_update.py install <repo>`, and refresh copied `gates/` + `knowledge/` + `harness/` + the Architrave `AGENTS.md` stanza with `python tools/install_update.py update <repo>`. Plain update intentionally preserves copied agents; it is a partial update, not proof of a unified role migration.
5. **Validate.** Run `gates/gate_runner.py checks`, `gates/gate_runner.py backend-checks` when configured, and any app-specific test/screenshot gates.

## Unreleased domain-aware candidate adoption

The candidate retains version 1.1.1 and the existing Service Architect identity.
Its domain-first backend pack must not be qualified alongside an unreconciled
technical-first copied architect. Inventory copied/customized Architrave roles
and generated Codex roles, compare them with the exact candidate, and reconcile
local product rules into repository guidance or reviewed role changes first.
Preserve customizations; an update command is not permission to discard them.

After explicit authorization for the reconciled replacement, run the candidate
kit's `python tools/install_update.py update --agents <repo>`. Add `--codex`
when generated Codex project roles are used. Plain update remains a supported
preservation operation, but cannot complete this candidate's role migration.

Read back the installed Service Architect, Backend Planner, Backend Implementer,
Adversarial Judge, backend pack and applicable generated Codex Judge against the
candidate's paths and content identities, documenting any reviewed local delta.
Verify lead/worker/review skills from the effective plugin path as well. Reload
affected native-host sessions and verify the actual loaded identities before
claiming qualified adoption. Version stamps, updater success and temporary byte
parity do not establish native loading. Keep adoption held for unresolved local
rules or unavailable host evidence; do not silently select the old architect.

## Common Mappings

| Bespoke agent role | Architrave replacement | Keep in repo-specific docs |
|---|---|---|
| UI researcher / competitor researcher | **Product Research** | Product domain, competitors to prefer/avoid, paid-source caveats |
| UI designer / UX planner | **UX Architect** + **UI Visual** | Product vocabulary, screen list, Storybook conventions |
| Native/platform reviewer | **Platform Design** | Platform target and app-specific platform exceptions |
| UI implementer | **Architrave** UI lane | Component names, app folder layout, local commands |
| Adversarial UI/product reviewer | **Adversarial Judge** + `gates/rubric.md` | Domain-specific capability limits and policy red lines |
| Backend/API architect | **Service Architect** | ADRs, architecture docs, contract files |
| Backend implementation agent | **Backend Implementer** | Repo seams, data stores, migration commands |
| IaC/deploy agent | **Infra Engineer** | IaC kind/path, plan/policy commands, approval boundaries |

## What Not To Migrate Into Architrave

- App secrets, credentials, tokens, or environment-specific deployment values.
- Product facts that only apply to one repo.
- Academic, writing, or study agents that are not development workflow agents.
- Homelab operations agents and MCP servers; those are operational tools, not Architrave development lanes.

## Sideport Example

Sideport's old UI agents map cleanly:

- `sideport-ui-research.agent.md` -> **Product Research** plus Sideport docs for Apple-device operations patterns.
- `sideport-ui-designer.agent.md` -> **UX Architect** + **UI Visual**.
- `sideport-ui-reviewer.agent.md` -> **Adversarial Judge** and the product-truth / anti-slop rubric dimension.
- `sideport-ui-implementer.agent.md` -> **Architrave** UI/full-stack implementation lane.

Archive those files with a README rather than leaving them active in `.github/agents/`, otherwise the agent picker splits authority and the old agents drift from the shared gates.