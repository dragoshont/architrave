# Migrating Bespoke Agents To Architrave

Architrave is meant to replace most project-specific development agents with one front-door conductor plus a small specialist crew. Keep project knowledge in `uikit.config.json`, `AGENTS.md`, `.github/instructions/*.md`, docs, contracts, and Storybook; keep reusable workflow behavior in Architrave.

## Migration Pattern

1. **Inventory existing agents.** Capture each agent's mission, tools, trigger phrases, handoffs, and hard rules.
2. **Map reusable behavior to Architrave.** Move general behaviors into Architrave agents, knowledge packs, or `gates/rubric.md`; leave product/domain facts in the app repo.
3. **Archive, don't delete.** Move old agents into `docs/archive/<old-agent-set>/` with a README explaining the replacement mapping.
4. **Adopt the repo.** Add `uikit.config.json`, refresh copied `gates/` + `knowledge/`, and inject the Architrave `AGENTS.md` stanza with `tools/install.*` or `tools/update.*`.
5. **Validate.** Run `gates/checks.*`, `gates/backend-checks.*` when configured, and any app-specific test/screenshot gates.

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