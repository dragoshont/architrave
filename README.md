# Architrave

Architrave helps Copilot, Claude Code, and Codex work from the system you already
have: your code, design components, architecture docs, and tests. Describe the
change you want. It works directly on small tasks, splits independent work into
scoped child sessions when useful, and brings the results back for checks and
review.

Use it for a UI change, a backend feature, a full-stack project, or work on docs,
skills, and automation. The plugin supplies the instructions and specialist
roles; the optional repository kit adds configured checks, resumable task
records, and reviewable learning.

![Workflow diagram: a request and repository context lead to direct work or up to three scoped child sessions, then integration, checks, and a result; a dashed deployment-only branch adds scoped approval and live verification](assets/workflow.svg)

## What you can use it for

- **Build UI from your own design system.** Use Storybook or the configured
  design source, real component names, and design tokens instead of a new
  one-off design. The UI roles cover navigation, keyboard interaction,
  empty/loading/error states, and visual details. Platform guidance covers
  Apple HIG, Microsoft Fluent, and web accessibility. With a token generator
  configured, the reconcile gate checks generated values against committed code.
- **Keep UI and backend in agreement.** Start with architecture docs and API/data
  contracts. Backend roles help with service boundaries, migrations, rollback
  plans, implementation, and tests. Full-stack work uses the same contract
  across the UI and service rather than planning each in isolation.
- **Design operational workflows.** The operations guidance covers setup and
  offboarding, inventories, uploads, roles and permissions, health, diagnostics,
  queues, and scheduled or long-running jobs. It connects what the UI displays
  to the data and action states the backend must provide.
- **Work on non-app repositories.** The knowledge profile grounds work in docs,
  scripts, skills, schemas, and tests without requiring Storybook or inventing
  a UI or backend.
- **Check the result, not just the build.** Run the repository's configured
  checks. Add independent review for semantic or higher-risk changes, and
  configured runtime evidence for app or deployment work: exercised workflows,
  screenshots, health, logs, and the deployed artifact's digest.
- **Keep the change small.** Reuse existing code, platform features, and installed
  dependencies before adding another abstraction. Compare alternatives when
  an architecture choice, migration, security concern, or recurring failure
  makes the decision worth examining.

## Child sessions and resumable work

Architrave keeps one lead responsible for the request and final integration.
Independent slices can run in coordinated child sessions with separate
worktrees and non-overlapping ownership. Each child gets its own objective,
relevant source paths, allowed edits, acceptance criteria, and a bounded budget;
it returns a compact result rather than handing the lead its entire transcript.
The default is at most three active children, one level deep.

On hosts with app-native session controls, those children can appear as separate
sidebar sessions. In a CLI, Architrave uses native subagents when available.
Work that follows one continuous trace or touches the same files stays direct.
Model and reasoning choices remain in your host settings.

For longer work, an adopted repository can keep a **Run** under
`.architrave/runs/`. It records the requested outcome, acceptance criteria,
dependent tasks, permissions, checkpoints, checks, and evidence. A rolling
recovery snapshot and authenticated event history support resuming after an
interruption without treating the chat transcript as the task database.

Independent tasks can continue while another waits for sign-in, signing,
consent, or another human decision. Scoped permissions and recorded deployment
results keep external actions separate from ordinary code edits. Uncertain
actions are checked before retrying; repeated identical failures stop that path.
An on-demand feasibility check helps choose whether to continue, narrow the
change, try another approach, or park it.

The lead integrates candidate changes and verifies the acceptance criteria.
Recorded checks are tied to the task and source being reviewed, so an old green
build or a worker's completion message cannot stand in for the current result.
See the [runtime guide](docs/runtime-v2.md) and
[execution policy](knowledge/execution-policy.md).

## See what is happening

The Copilot package includes two companion panels for hosts that support
extensions and canvases:

| Panel | What it shows |
|---|---|
| **Session companion** | Session activity, host-reported model and effort, context usage, and expandable SDK subagent rows with names, roles, assigned work, and lifecycle status. App-native child-session rows are not yet exposed by the host integration. |
| **Route Ribbon** | Run snapshots showing the route, workstreams, blockers, stops, retries, and evidence, with completed work kept separate from verified product results. |

The session companion observes host events without recurring model calls.
It follows the host theme, supports keyboard navigation and reduced motion,
and can be dismissed or opted out of.

See [panel setup and supported hosts](docs/route-ribbon.md).

## Keep useful knowledge between tasks

With learning configured, Architrave keeps a concise repository profile and
candidate lessons with supporting evidence. Repeated build gotchas, operational
facts, and conventions can become standing guidance after validation and review.
The learning helpers check local evidence and stale facts; semantic review can
flag unsupported prose and mark exact matching claims as unvalidated.

Task history stays in Run records, useful repository facts stay in the profile,
and promoted rules belong in the relevant instructions, docs, or config.
See the [learning guide](knowledge/learning-loop.md).

## Agents and skills

You can use the specialist roles directly or let Architrave select the relevant
ones. They are optional contexts, not a required procession for every task.

| Work | Roles |
|---|---|
| Coordination and decisions | **Architrave** leads the work; **CTO** supplies a short start/stall checklist; **Tournament Analyst** compares consequential alternatives. |
| Research and UI | **Product Research** finds source-backed patterns; **Operations UX** covers admin workflows; **UX Architect** handles flows and interaction; **UI Visual** handles appearance; **Platform Design** checks platform conventions. |
| Backend | **Service Architect** works through boundaries and contracts; **Backend Planner** sequences implementation and migration; **Backend Implementer** builds the approved slice and tests it. |
| Infrastructure and runtime | **Infra Engineer** plans scoped infrastructure work; **Runtime Observer** checks deployed or running behavior. |
| Review | **Adversarial Judge** reviews proposals and implementations against the repository and rubric, returning PASS, REVISE, or FAIL. |

The plugin also packages these focused skills:

| Skill | When to use it |
|---|---|
| `architrave` | Coordinate a non-trivial repository change. |
| `architrave-work` | Carry out one assigned development, research, or writing task in a child. Writing can use author-provided voice samples. |
| `architrave-cto` | Apply the start/stall checklist inline, without spawning another supervisor. |
| `architrave-tournament` | Compare material implementation alternatives. |
| `architrave-review` | Request a read-only rubric review of a proposal or implementation. |
| `architrave-agent-authoring` | Create, revise, or review a focused agent role. |
| `architrave-skill-authoring` | Create, revise, or package a skill with a clear trigger and supporting sources. |
| `architrave-mcp-integration` | Design or review an MCP tool contract, permissions, data flow, and failure behavior. |

Authoring skills are used when you ask for authoring work, not during routine
tool use.

## Install the plugin

Install Architrave in an agent client you already use.

With **GitHub Copilot** (CLI, desktop app, or VS Code):

```bash
copilot plugin marketplace add dragoshont/architrave
copilot plugin install architrave@architrave
```

With **Claude Code**:

```bash
claude plugin marketplace add dragoshont/architrave
claude plugin install architrave@architrave
```

With **Codex CLI** or **Codex in the ChatGPT desktop app**, from a local clone
of this repository:

```bash
codex plugin marketplace add /path/to/architrave
codex plugin add architrave@architrave
```

Start a conversation in the host, select or invoke Architrave, and describe
the change you want. Plugin-only use does not require modifying the target
repository. The plugin adds Architrave's host-specific instructions and
roles; it uses tools already available to the host.

For example:

> Add an empty state to the library list using our existing components. Include
> the loading and error states, and run the relevant tests.

## Optional repository setup

Install the kit into a repository when you want repo-local roles, configured
checks, or durable task records. Run the installer from an Architrave checkout
or installed kit, with the target repository as the final argument:

```bash
python3 /path/to/architrave/tools/install_update.py install /path/to/your/repo
```

For documentation, automation, or other repositories without a product UI,
use the knowledge profile:

```bash
python3 /path/to/architrave/tools/install_update.py install --profile knowledge /path/to/your/repo
```

Review the generated `architrave.config.json` and set real repository sources
and build/test commands before relying on its checks:

| Work in the repository | Configure |
|---|---|
| UI | Design source, component map, platform, tokens, and generation/build/test commands. Early projects can start with specs and Storybook before adding token generation. |
| Backend | Architecture docs, contracts, source paths, and backend build/test commands. |
| Infrastructure and runtime | Optional `iac`, `runtime`, and `ops` commands and scoped execution policy. |
| Learning | Profile, lesson, and artifact paths, plus validation and promotion rules. |

Repository adoption also installs managed grounding instructions and Copilot
cloud-agent setup. The knowledge profile installs only the roles appropriate to
that repository.

To generate the optional Codex project roles during setup, add `--codex` to
either install command. Plugin skills stay in the plugin rather than being
copied into the repository.

For durable Copilot workers and source-bound native review, install the
additional host bridge from the kit:

```bash
python3 /path/to/architrave/tools/install_update.py native-host-install
```

Then reload extensions through the supported host controls. The bridge provides
`architrave_native_dispatch`, `architrave_native_gate`, and
`architrave_native_review`, with status, cancellation, and recovery tools.
See [native review](docs/native-semantic-review.md) for the evidence contract.

The kit uses Python; the shell and PowerShell entrypoints forward to the same
implementation. Your project's build and test toolchain stays unchanged.

## Updates

Update the plugin through its host. For the Copilot and Claude command-line
clients:

```bash
copilot plugin update architrave
claude plugin marketplace update architrave
claude plugin update architrave@architrave
```

Plugin updates do not refresh kit files copied into adopted repositories. Run
the updater from the updated kit to refresh those files:

```bash
python3 /path/to/architrave/tools/install_update.py update /path/to/your/repo
```

The updater leaves the repository's config and local agents alone by default.
Use `--agents` only when you also want to refresh copied Architrave roles; use
`--codex` to refresh generated Codex project roles.

## Checks and experiments

The repository includes fixture tests and a benchmark harness for mechanical
changes, features, multi-surface work, recovery, deployment policy, and authoring
tasks. It records validation results, changes, time, tokens, interventions, and
optional review scores. List scenarios without starting an agent run:

```bash
python3 scripts/bench-architrave.py --list
```

See the [benchmark guide](docs/longbuild.md) and
[orchestration audit](docs/orchestration-audit.md) for how experiments are run
and interpreted.

## Host boundaries

Plugin installation adds instructions, roles, and skills, not missing tools or
MCP servers. Checks must be configured and invoked; Architrave does not intercept
every host tool call. Worktrees and scope checks separate changes but are not an
OS security sandbox. Infrastructure starts as plan-only work; applying changes
requires permission for the target and operation.

## Further reading

- [Repository adoption and migration](kit/MIGRATION.md)
- [Configuration examples](kit/examples/)
- [Execution policy and host limits](knowledge/execution-policy.md)
- [Runtime and durable task records](docs/runtime-v2.md)
- [App and deployment verification](docs/application-legibility.md)
- [Design tokens and reconciliation](knowledge/design-tokens.md)
- [Apple](knowledge/apple.md), [Microsoft](knowledge/microsoft.md), and [web](knowledge/web.md) guidance
- [Explicit quality-check cadence](docs/quality-check-cadence.md)
- [YAGNI guidance](knowledge/yagni.md)
- [Changelog](CHANGELOG.md) · [GitHub releases](https://github.com/dragoshont/architrave/releases)
