# Architrave

**An AI agent that runs a full-stack specialist crew inside GitHub Copilot, Claude Code, Codex, or ChatGPT.**

Architrave helps you build a full-stack application, or any slice of one, without turning your codebase into an agent experiment. You ask for the feature; Architrave reads the repo, grounds in its Storybook/design map and backend architecture docs, runs the right specialist agents, and ships only the smallest proven change.

It has Apple and Microsoft design language built in, plus web/WCAG guidance,
Storybook-first UI, contract-first backend work, default-deny scoped deployment,
YAGNI, durable Run v2 state, product reality gates, and risk-based independent
judges. The point is simple: build the useful thing, survive interruptions, and
prove the requested product outcome actually occurred.

![Architrave — ground in the repo, route to specialists, gate with a judge plus real checks, then ship](assets/overview.png)

## Latest news: v0.11.2

Released **October 4, 2026**. This update closes the immutable-policy usability
gap without weakening Run v2's default-deny boundary.

- **Challenge-bound policy amendments:** an existing Run can add exact mutation
  grants and confirmation-required operations without replacing its objective.
- **Transaction-bound authorization:** direct `_transaction`, event-name,
  worker, coordinator, actor-string, replay, stale-revision, and cross-Run
  attempts cannot modify policy.
- **Safe resumption:** amendments apply only with no active or uncertain
  mutation; policy-blocked tasks become ready but never replay automatically.

Read the [full changelog](CHANGELOG.md#0112---2026-10-04).
After updating the plugin, refresh each adopted repository's copied kit assets
using the [update instructions](#install).

## Built With Architrave

<table>
        <tr>
                <th width="33%">PhonoDeck</th>
                <th width="33%">Sideport</th>
                <th width="33%">Tessera</th>
        </tr>
        <tr>
                <td><img src="assets/gallery-phonodeck.png" alt="PhonoDeck native macOS music app designed in Storybook and built in SwiftUI" width="100%"></td>
                <td><img src="assets/gallery-sideport.png" alt="Sideport admin console for devices, app signing, renewals, diagnostics, and live API health" width="100%"></td>
                <td><img src="assets/gallery-tessera.png" alt="Tessera homelab account and connection console with health and re-seed states" width="100%"></td>
        </tr>
        <tr>
                <td>Native macOS music app. Storybook design source, SwiftUI implementation.</td>
                <td>Web admin console. React UI, .NET backend, Kubernetes runtime.</td>
                <td>Homelab access console. React UI, .NET backend, connection health workflows.</td>
        </tr>
</table>

## The Crew

**Architrave** is the front door. It stays in control of the plan, routes focused work to specialists, and refuses to call the job done until real checks pass.

| Agent | Invoke | What it owns |
|---|---|---|
| **Architrave** | directly | Leads the durable Run: Outcome, Acceptance Matrix, TaskGraph, policy, bounded workers, resume, gates, and final status. |
| **Product Research** | under the hood | Finds shipped product/workflow patterns, competitor references, and domain-specific traps before planning. |
| **Operations UX** | under the hood | Turns admin/operations research into setup, offboarding, inventory, catalog/upload, RBAC, health, diagnostics, queue/job, and audit patterns with contract requirements. |
| **UX Architect** | directly | Information architecture, navigation, flows, interaction model, keyboard/input behavior, and empty/loading/error states. |
| **UI Visual** | directly | Visual hierarchy, layout, tokens, typography, color/materials, iconography, and polish. |
| **Platform Design** | under the hood | Native platform correctness: Apple HIG, Microsoft Fluent, or web/WCAG, depending on `architrave.config.json`. |
| **Service Architect** | under the hood | Backend boundaries, API/data contracts, ADR fit, auth surfaces, and source-of-truth architecture decisions. |
| **Backend Planner** | under the hood | Turns the backend contract into ordered slices, migration/rollback notes, risk, and human sign-off checklist. |
| **Backend Implementer** | under the hood | Implements approved backend/service slices and tests against the contract. |
| **Infra Engineer** | under the hood | Plans by default; applies only through an explicit scoped Run grant, then records a receipt and verifies live state. |
| **Runtime Observer** | under the hood | Establishes deployed/product truth. Read-only by default; scoped mutation follows Run policy. |
| **Tournament Analyst** | under the hood | Independently compares materially risky or ambiguous implementation options; advisory and read-only. |
| **Adversarial Judge** | under the hood | Grades proposals and implementations against the rubric: PASS / REVISE / FAIL. Cross-family review is reserved for its configured risk floor. |

## Install

Install the plugin once in your agent client:

With **GitHub Copilot** (CLI, desktop app, or VS Code):

```bash
copilot plugin marketplace add dragoshont/architrave
copilot plugin install architrave@architrave
```

Or with **Claude Code**:

```bash
claude plugin marketplace add dragoshont/architrave
claude plugin install architrave@architrave
```

Or with **Codex CLI / ChatGPT Codex mode**:

```bash
codex plugin marketplace add /path/to/architrave
codex plugin add architrave@architrave
```

The Codex plugin owns three skills: `architrave` (implicit lead workflow), plus
explicit-only `architrave-tournament` and `architrave-review`. Do not copy those
same names into `.agents/skills`; Codex does not merge duplicate skill names.

Then **adopt/ground each repository** so local agents, cloud agents, and
deterministic gates all see the same source of truth. Python is the canonical
cross-platform implementation; the small `.sh`/`.ps1` files are compatibility
launchers only.

```bash
python /path/to/architrave/tools/install_update.py install .
```

To add the two project-scoped Codex roles as well, opt in explicitly:

```bash
python /path/to/architrave/tools/install_update.py install --codex .
```

This writes only generated Tournament Analyst / Adversarial Judge role files
under `.codex/agents/` and one managed registration block in
`.codex/config.toml`. It never writes provider, auth, trust, MCP, plugin, skill,
or credential settings. Python 3.11+ is the kit runtime on every platform.

Codex roles are specialized contexts, not mandatory security gates: their
`sandbox_mode = "read-only"` constrains command filesystem/network access, while
the parent permission mode, skills, and MCP servers still apply. Mandatory high-risk review uses two independent reviewer identities while model
selection remains entirely host- or user-owned.

Edit `architrave.config.json` to point at the repo's Storybook/design source, build/test commands, optional backend, optional IaC, optional runtime observation, and optional learning paths. Then ask the **Architrave** agent to build a feature.

For a repository that contains knowledge, skills, schemas, and automation but no product UI or service lane, use the explicit knowledge profile:

```bash
python /path/to/architrave/tools/install_update.py install --profile knowledge .
```

The generated config is the canonical [`kit/examples/knowledge.architrave.json`](kit/examples/knowledge.architrave.json). It requires real build/test commands while deliberately omitting platform, Storybook, tokens, backend, IaC, and runtime fields. The default installer profile remains the existing application scaffold.

The knowledge profile installs only `architrave`, `adversarial-judge`,
`tournament-analyst`, `product-research`, and `runtime-observer`; it omits the
UI/backend crew and native-app constitutions. All profiles ignore
`.architrave/runs/`, `.architrave/worktrees/`, and `.architrave/runtime.key`
while leaving `.architrave/learning/` trackable.

**Updating.** Releases bump the plugin version, so a plain update pulls them:

```bash
copilot plugin update architrave
claude plugin marketplace update architrave
claude plugin update architrave@architrave
```

After updating the plugin, users **must also refresh each adopted repo's copied kit assets**. A plugin update refreshes the locally installed agent package only; it does not change copied gates, the active `.github/hooks/design-guard.json`, harness, knowledge, profile-appropriate constitutions, or the managed `AGENTS.md` stanza. Run the matching repo script in every adopted repo. This leaves `architrave.config.json` and copied `.github/agents` untouched by default:

```bash
python /path/to/architrave/tools/install_update.py update .
```

When the Architrave crew itself changes and you want to refresh the copied repo agents too, opt in explicitly. Application repos receive the full packaged crew. Knowledge repos converge to the five-agent crew above: only non-crew basenames packaged by Architrave are removed, so target-only custom agents remain untouched.

```bash
python /path/to/architrave/tools/install_update.py update --agents .
```

Refresh generated Codex roles separately (plugin skills update through the
native plugin command):

```bash
python /path/to/architrave/tools/install_update.py update --codex .
```

## How It Works

Open your assistant, pick the **Architrave** agent, and describe the change in plain language:

> Add an empty state to the library list — an icon, a short message, and a primary action.

Architrave starts with visible intake scaled to the task: understanding,
acceptance criteria, grounding sources, assumptions, and blocking questions.
Routine bounded work records a direct plan and the selected **YAGNI ladder**
rung: skip/delete, reuse existing repository source, platform/native feature,
standard library, installed dependency, tiny local implementation, and only
then new abstraction/dependency/config when the current task proves it. A full
**Tournament of Options** is reserved for architecture/dependency choices,
systemic failures, migrations, data loss, security, deployment, or materially
ambiguous alternatives.

For UI, Architrave starts in **Storybook** or the configured design source. For
backend/full-stack, it starts with the **contract**. Infrastructure is plan-only
unless the user mandate produces an exact target/operation grant; authorized
apply is checkpointed, receipted, and verified. Non-trivial work uses canonical
Run state under `.architrave/runs/` so interruption resumes from state, not chat.

## Durable Run v2

The next-generation harness is a dependency-free Python control plane:

```text
Goal → Outcome → Acceptance Matrix → TaskGraph → WorkPackets
                 → policy/checkpoints/events → deterministic/E2E/semantic gates
                 → verified product outcome
```

- `run.json` is atomic canonical state; `events.jsonl` is typed and
        HMAC-authenticated with an ignored local runtime key.
- `current-task`, `approved-program`, and `advisory-only` separate autonomy from
        phase observability. The Phase Ledger is generated from TaskGraph state.
- Copilot, Claude, Codex, and deterministic shell adapters return bounded
        candidate results. Mutating parallel work uses isolated git worktrees.
- Repository-wide leases serialize overlapping mutable scopes across Runs;
        mutation receipts are task-bound, outcome-bound, and single-use.
- Typed external checkpoints pause OAuth/MFA/consent/signing/human judgment
        without failing or restarting the program; independent work continues.
- Unknown side effects reconcile against remote/live truth before retry.
- Web, Electron, iOS, runtime, and deployment evidence prevent compile-only or
        stale-deployment false success.
- Evidence is executor-produced, HMAC-attested, digest-checked, and bound to the
        exact criterion/gate; arbitrary registered files cannot manufacture PASS.
- Risk class scales evaluation cost from deterministic-only R0 to R4 security,
        policy, E2E/reality, and two independent semantic reviewers.

See [`docs/runtime-v2.md`](docs/runtime-v2.md),
[`docs/application-legibility.md`](docs/application-legibility.md), and
[`docs/migration-run-v1-v2.md`](docs/migration-run-v1-v2.md). The measured
Pi/OpenCode comparison and basic-sh before/after footprint are in
[`docs/orchestration-audit.md`](docs/orchestration-audit.md).

**Full-stack is built in.** Set a `backend` and/or `iac` block in `architrave.config.json` and the same conductor extends past UI. Repos without a service, infra, or runtime lane simply omit those blocks.

**Knowledge repositories are first-class.** Set `kind: "knowledge"` through the installer profile and Architrave grounds in repository docs, scripts, skills, schemas, tests, and learning artifacts. It does not invent a UI lane or demand Storybook sign-off.

**Execution stays host-owned.** Architrave does not select, rank, recommend, or
persist a model class, tier, reasoning level, context tier, provider, or concrete
model. The user and active host harness own those choices. Architrave contributes
bounded task scope, permissions, evidence requirements, output limits, and
risk-based verification only.

Low-risk mechanical work can close on deterministic evidence when every
criterion is machine-checked. Semantic, UI, contract, architecture, migration,
security/trust, IaC, and high-blast-radius work add one or two independent
reviewers according to risk, without constraining which models the host uses.

**Learning is explicit.** Set the optional `learning` block and Architrave keeps per-run evidence, a concise repo profile, and candidate repeated lessons. Lessons only become standing repo guidance after validation and review.

**YAGNI is enforced.** Architrave uses a minimum-sufficient-change ladder grounded in `knowledge/yagni.md`. It blocks speculative abstractions, unused config, new dependencies, and wrapper layers until the task proves they are needed. It still keeps the practices that make YAGNI safe: refactoring, contracts, tests, validation, security, accessibility, and design-token reconciliation.

**Operations UX is source-backed.** When a feature is an admin console, device/fleet workflow, app catalog/upload, setup/offboarding flow, user/RBAC surface, diagnostic page, queue, scheduled job, or long-running action, Architrave loads `knowledge/operations-ux.md` and routes to **Operations UX**. The rule is simple: no status without source/timestamp/scope, no mutation without preflight and durable job state, no destructive flow without impact/recovery/audit, and no generic dashboard where the product needs object lists, queues, issues, or evidence.

## Benchmarks

Architrave ships a benchmark harness because agent quality has to be measured
against real work, not vibes. The suite in `benchmarks/` runs frozen tasks against
real local repos in detached worktrees, compares agent arms such as
`copilot-baseline` and `copilot-architrave`, and records JSONL rows with
validation results, diff size, output tokens, wall time, artifacts, and optional blinded
LLM-judge scores.

`benchmarks/routing-scenarios.json` exercises delegation and verification
decisions without encoding model guidance. Any benchmark model selection belongs
to the invoking host or user-local experiment configuration, never Architrave's
canonical policy.

It now also includes **Architrave LongBuild** categories, disabled
Claude/Codex arms, recovery/external-checkpoint/parallel/deployment-policy cases,
and a frozen Tessera-shaped fixture with no private code or data.

The first smoke benchmark is intentionally small: a PhonoDeck learning-loop task that asks the agent to capture a real build/relaunch gotcha as durable repo knowledge without touching product code. It proves the harness path end to end.

| Run | Arm | Result | Gates | Judge | Output tokens | Wall time | Diff |
|---|---|---:|---|---|---:|---:|---:|
| `pilot-architrave-learning-20260622T073711Z` | `copilot-architrave` | **PASS** | `checks.sh --quick` + `validate-run.sh` PASS | PASS, 5/5 across correctness / clarity / YAGNI / process / repo fit | 3,893 | 393.9s | +117 LOC / 10 artifact files |

Read that honestly: it is a verified smoke, not a leaderboard. A generic baseline run on the same learning scenario timed out before producing the required run artifacts, which is useful failure data, but we are not publishing a broad win claim until the full curated suite runs with repeats and human review. The important part is the shape of the evidence: every claim is tied to a scenario, a pinned commit, a worktree, deterministic gates, a patch, and an optional judge row.

LongBuild adds Outcome/acceptance PASS, false PASS, human interventions,
unnecessary-question heuristics, false external blockers, repeated work after
resume, peak parallel workers, deployment verification, E2E failures, median,
p90, and variance. The north-star measure is time to verified product outcome
per required human intervention. See [`docs/longbuild.md`](docs/longbuild.md).

Reproduce the harness checks:

```bash
scripts/test-validate-run.sh
scripts/test-validate-learning.sh
scripts/test-promote-lesson.sh
scripts/test-promote-lesson-picker.sh
scripts/test-mark-stale-learning.sh
scripts/test-semantic-learning.sh
scripts/test-validate-run.sh
scripts/test-validate-learning.sh
scripts/test-promote-lesson.sh
scripts/test-promote-lesson.sh-picker
scripts/test-mark-stale-learning.sh
scripts/test-semantic-learning.sh
scripts/test-gates.sh
python3 scripts/bench-architrave.py --scenarios benchmarks/scenarios.json --validate
python3 scripts/bench-architrave.py --scenarios benchmarks/scenarios.json --list
python3 scripts/bench-architrave.py --scenarios benchmarks/routing-scenarios.json --validate
python3 scripts/test-benchmark-tools.py
python3 scripts/test-runtime-v2.py
python3 scripts/test-worker-adapters.py
python3 scripts/test-invariant-engine.py
python3 scripts/test-legibility.py
python3 scripts/test-workspaces.py
python3 scripts/test-longbuild-runtime.py
```

Run one scenario when you are ready to spend Copilot credits:

```bash
ARCHITRAVE_BENCH_SECRET_ENV_VARS='GITHUB_TOKEN,GH_TOKEN,ANTHROPIC_API_KEY,OPENAI_API_KEY' \
        python3 scripts/bench-architrave.py \
                --scenarios benchmarks/scenarios.json \
                --scenario phonodeck-learning-repeated-build-gotcha \
                --arm copilot-architrave \
                --execute --cleanup-worktrees
```

Benchmarks are bounded experiments, not open-ended release jobs. Each agent cell
defaults to a 10-minute timeout, the complete invocation defaults to a 20-minute
wall-time budget, and periodic heartbeats make active work visible. Explicit
flags can raise either limit for a deliberate long-form experiment; once the run
budget is exhausted, Architrave records that result and starts no additional
cells.

The benchmark design follows the same lesson Ponytail surfaced well: the persuasive metric is not "the agent said it used YAGNI." It is the resulting diff, the gates, the token/time trace, and whether a reviewer would accept the change.

## A real app, built this way

**PhonoDeck** — a native macOS music app (SwiftUI) — is the most mature app built this way. Its design lives in **Storybook**; the agents ground in it, reproduce components by their real names, and build the native app to match — the sidebar, the Home recommendations, the now‑playing panel, and the `NowPlayingBar`, all held to Apple's Human Interface Guidelines.

![PhonoDeck — a native macOS music app (SwiftUI): sidebar, Home with recommendations, and the now-playing panel — designed in Storybook, built native](assets/phonodeck.png)

## Design in Storybook first, then build it native

Every change starts in **Storybook** — the fastest, most visual place to design and iterate, and the source of truth the build then matches.

1. **Design the flow in Storybook.** The **UX Architect** lays out the screens and *every* state (empty, loading, populated, error); **UI Visual** styles them with your design tokens. You see it live, tweak it, and confirm — before any app code is written.
2. **Build it for real.** **Architrave** turns the approved design into shipping code. On the **web**, Storybook *is* the build — it develops the real **React** components in isolation, then composes them into pages. On **native** (**SwiftUI**, **WinUI**), Storybook is the spec the native code reproduces, kept in sync by the same design tokens. Either way, the **Adversarial Judge** plus your real build and tests gate it before it's done.

![Designing a flow: information architecture, screens, and every state — sketched in Storybook and grounded in the platform's guidelines, before any native code](assets/flows.png)

This is Architrave's clearest wedge: a general coding agent starts in code; Architrave starts by reproducing the repo's design system in Storybook, gets sign-off, then builds the smallest matching native/web slice. For full-stack work the same pattern becomes contract-first: the service shape is approved before UI and backend drift apart.

## Grounded in official design sources

The design knowledge isn't invented — every platform pack and constitution is **cited to the vendor's own documentation**, so the agents reproduce the real system instead of a community approximation:

- **Apple — macOS / iOS · SwiftUI.** Apple **Human Interface Guidelines**, **WWDC** engineering sessions, **SF Symbols**, and **Apple Design Resources**. Distilled into [`knowledge/apple.md`](knowledge/apple.md) (cited) and the deep [`constitution-apple.md`](constitution-apple.md) — verbatim macOS/iOS type tables, Liquid Glass functional‑layer rules, SF Symbols modes, and the native component catalog.
- **Microsoft — Windows · WinUI 3 / Windows App SDK / WPF.** The **Fluent 2** design system ([fluent2.microsoft.design](https://fluent2.microsoft.design/)), the **Windows apps design** guidance on **Microsoft Learn** ([learn.microsoft.com/windows/apps/design](https://learn.microsoft.com/windows/apps/design/)), the **WinUI / Windows App SDK** reference, **Segoe Fluent Icons**, and **Microsoft Build** sessions. Distilled into [`knowledge/microsoft.md`](knowledge/microsoft.md) (cited) and the deep [`constitution-windows.md`](constitution-windows.md) — the Windows type ramp, Mica/Acrylic/Smoke materials, two‑layer elevation, and the WinUI control catalog.
- **Web — React · component‑driven.** The **W3C WCAG** accessibility standard plus Fluent React / web‑platform conventions, in [`knowledge/web.md`](knowledge/web.md) (cited).

Each constitution closes with a **Citations** section linking the live source pages, and every pack is marked *cited*. The standing rule is **verify against the source before emitting code** — vendor specs (type ramps, materials, control APIs) evolve every release.

## What it does

- 🧭 **Designs the UX, not just the pixels.** The *UX Architect* works out information architecture, navigation, and every state (empty / loading / error) — validated in **Storybook** before anything is built.
- 🎨 **Makes it look native.** *UI Visual* + *Platform Design* hold the UI to the platform's own language — Apple HIG, Microsoft Fluent, web / WCAG — so it feels at home on each OS.
- 🏗️ **Builds the real thing.** *Architrave* turns the approved design or contract into native/web UI, backend/service code, and tests — driven by your repo's actual build + test commands.
- ✂️ **Builds less, on purpose.** The YAGNI ladder blocks speculative abstractions, unused config, new dependencies, and wrapper layers until the task proves they are needed.
- 🔌 **Keeps full-stack work contract-first.** *Service Architect* and *Backend Planner* define the API/data handshake, migration/rollback plan, and approval checklist before implementation.
- 🛡️ **Keeps infrastructure default-deny.** *Infra Engineer* plans by default;
        scoped authorized deployment records a receipt and must match live state.
- 🎯 **Follows your system, never reinvents.** Every change starts from your Storybook/component map, architecture docs/contracts, and existing repo seams; agents touch only the deltas.
- ✅ **Won't ship slop.** An *Adversarial Judge* (LLM‑as‑judge) plus deterministic gates (your real build + tests + token lint + backend/IaC checks) must *both* be green — and design tokens stay reconciled with code.
- 🧩 **One method, every surface.** The same kit runs in the Copilot CLI, the Copilot desktop app, VS Code, **Claude Code**, and the cloud coding agent.

## What it looks like

Install the plugin once — then the agents are available everywhere, and the deterministic gate runs your repo's real build + tests:

![Installing the Architrave plugin in the Copilot CLI, then a green gate run](assets/cli.png)

---

## Why this exists

Hand an AI agent a UI task and it tends to **reinvent**: a brand‑new button, slightly different spacing, a component that ignores the design system you already maintain. You end up cleaning up inconsistent "AI slop" by hand.

Architrave takes the opposite stance — **ground in the system you already have, reproduce it, build only the needed slice, and prove it.** Your Storybook + design tokens are the UI source of truth; your architecture docs + contracts are the backend source of truth; your IaC plan/policy commands are the infrastructure guardrail. Nothing is "done" until it passes your real checks and an automated adversarial review.

The method isn't theoretical — it emerged independently across real apps, **PhonoDeck** (native macOS, SwiftUI) and **Sideport** (web, React + .NET), which had each settled on the same source-of-truth-first, judge-gated workflow. Architrave extracts that shared method into a stack-agnostic kit, retargeted per repo by one small config file.

## Architecture — four layers

```
1. DESIGN SOURCE OF TRUTH      Storybook (component workbench) + design tokens (.tokens.json, W3C DTCG)
        │  validate / tweak the design here FIRST
        ▼
2. KNOWLEDGE PACKS             knowledge/apple.md · microsoft.md · web.md · backend.md · operations-ux.md · design-tokens.md · execution-policy.md  (+ native constitutions)
        │  the Platform Design agent loads the pack named by config.platform
        ▼
3. AGENTS                      Architrave conductor · UI specialists · backend/infra specialists · Adversarial Judge
        ▼
4. RUN + GATES                TaskGraph/EventLog/policy/workers + deterministic/E2E/reality/semantic gates
```

Everything in layers 2–4 is **retargeted per repo by one config file** (`architrave.config.json`). The agents never hard‑code a stack; they read the config and the matching knowledge pack.

Model selection is deliberately outside repository stack config and canonical
agents. The active host and user own it; Architrave records only task scope,
verification evidence, and reviewer identity needed for audit.

## The learning loop

AI agents get better in a repo the same way developers do: they remember the shape of the system, which commands actually work, which assumptions caused mistakes, and which rules are stable enough to teach the next run. Architrave makes that learning visible and reviewable instead of relying on hidden chat context.

- **Run state and artifacts** are episodic memory: canonical `run.json`,
  hash-chained events, one rolling recovery snapshot, compact evidence, and
  receipts. Human-readable views are generated on demand.
- **Repo profile** is semantic memory: `.architrave/learning/repo-profile.md` captures the repo description and validated operational facts future agents should read first.
- **Candidate lessons** are a review queue: `.architrave/learning/repo-lessons.md` records repeated observations with evidence and occurrence counts.
- **Promoted rules** are procedural memory: stable lessons move into `architrave.config.json`, `AGENTS.md`, `.github/instructions/`, docs, or contracts after review.

This keeps memory scoped: config stores stable pointers and policy, profile stores concise repo description, lessons store evidence, and run folders store task history. Secrets are never recorded, and stale facts must be validated against the current branch before use or promotion. Deterministic helpers catch missing files and broken local evidence; `harness/semantic-learning-review.*` asks a judge/provider to compare durable prose claims with current repo evidence, and `harness/apply-semantic-learning-findings.*` safely marks exact reviewed lines as `UNVALIDATED:` when the findings still match the file.

## The design↔code reconciliation model (the hard part)

"Any variation in design or code must be reconciled" is solved by making **design tokens the single source of truth** (see `knowledge/design-tokens.md`). Three token tiers:

- **Reference** (`ref.*`) — raw values (palette, type scale). Context‑free.
- **System / semantic** (`sys.*`) — roles ("label/primary", "surface"). Theming + context (light/dark/RTL/density) lives here.
- **Component** (`comp.*`) — per‑component element decisions, pointing at system tokens.

Both the design (Storybook/Figma) and the code (SwiftUI `Color`/`Font`, WinUI `ResourceDictionary`, CSS vars) **reference the same token names**. A translation step (Style Dictionary / Terrazzo) generates platform code from the tokens. **Drift = when generated platform values diverge from committed code.** The reconcile gate diffs the two and Architrave fixes by regenerating from the tokens (or, if the design legitimately changed, updates the tokens first, then the code).

```
design tweak ──▶ tokens (.tokens.json, SSOT) ──▶ Style Dictionary ──▶ swift / xaml / css
                       ▲                                                    │
                       └──────────── reconcile gate (diff) ◀───────────────┘
```

## Requirements

The kit is Markdown plus one canonical Python implementation.

| Tool | Why it's needed | Install |
|---|---|---|
| **GitHub Copilot** (CLI, desktop app, or VS Code) **or Claude Code** | runs the agents | [github.com/features/copilot](https://github.com/features/copilot) |
| **git** | the reconcile gate diffs generated vs committed code | already installed on most systems |
| **Python 3.11+** | canonical installer/updater, gates, validators, Run v2, workers, legibility, invariants, and benchmarks | [python.org/downloads](https://www.python.org/downloads/) · [Windows](https://www.python.org/downloads/windows/) |
| **Node.js 22+** | repository development/CI only: `npx ajv-cli` validates the published JSON schema and examples | [nodejs.org](https://nodejs.org/) |

> The `.sh` and `.ps1` files contain no business logic. They only discover
> Python, forward arguments/output/exit status, and print an actionable install
> URL when Python is missing.

Your repo's own build/test toolchain (Node for web, Xcode for Apple, .NET for WinUI, …) is whatever your `architrave.config.json` `build`/`test` commands invoke — the gates just run those.

## Set up a repo

After installing the plugin (above), **adopt/ground a repo** — this is also what reaches the Copilot **cloud** agent:

```bash
python /path/to/architrave/tools/install_update.py install .
```

This copies agents, gates, the complete harness, and knowledge packs; scaffolds
config; ignores private Runs and worktrees; injects the grounding stanza; wires
the hook; and drops cloud setup. Existing configs remain valid. The application
profile also copies native constitutions; the knowledge profile omits them.

**Important update rule:** after every Architrave plugin update, run
`python tools/install_update.py update <repo>` in each adopted repo.
Plugin updates do not rewrite copied repo assets. The Python updater refreshes
gates, the active platform-specific workspace hook, harness, knowledge,
profile-appropriate constitutions, the run-artifact ignore, and the managed
`AGENTS.md` stanza while leaving `architrave.config.json` and `.github/agents`
alone by default; pass `--agents` only when deliberately refreshing copied
Architrave agents.

Install and update fail closed when a managed destination is a symbolic link,
junction, reparse point, or wrong path type. Managed files are staged and
replaced instead of overwritten in place, so a target hard link cannot mutate
external content. POSIX update requires valid object JSON and accepts only an
absent `kind` (application profile) or `"kind": "knowledge"`; PowerShell uses
the same contract.

Then point it at your repo — edit `architrave.config.json`:

- For **UI/app work**, set `platform`, `stack`, `designSource` (your Storybook), `designMap`, `tokens`, and the normal `generate` / `build` / `test` commands.
- For **backend/service work**, add `backend` with the solution path, architecture docs, contract location if you have one, backend `applyTo` globs, and backend build/test commands.
- For **infrastructure**, add `iac`; plan is the default. Add `autonomy` policy
        only for explicit bounded operations.
- For **runtime/product verification**, add optional `runtime` Web/Electron/iOS/
        deployment commands and `ops` observation settings.
- Add optional `workers`, `invariants`, and `evaluation` blocks for routing,
        mechanical boundaries, and risk policy. See
        [`kit/examples/runtime-v2.architrave.json`](kit/examples/runtime-v2.architrave.json).
- For **learning**, add `learning` with `runArtifactsPath`, `repoProfilePath`, `lessonsPath`, `capture`, `redactionPolicy: "no-secrets"`, `staleFactPolicy: "validate-before-use"`, `promotionPolicy`, and promotion targets. The installer scaffolds this block for new repos.

For early UI work, `designMap` and `tokens` can start empty while Storybook + specs are the source of truth. As the design system matures, copy `kit/examples/design-map.stub.json` and `kit/examples/tokens.web-shadcn.tokens.json` into your app and wire them in; that unlocks stronger grounding and design↔code reconciliation.

If you are replacing repo-specific agents, use `kit/MIGRATION.md` to map old agents to the Architrave crew, then archive the old files under `docs/archive/` rather than leaving multiple active development agents competing in `.github/agents/`.

Then ask the **Architrave** agent to make a feature change. It grounds, classifies the lane, proposes, judges, asks for the right sign-off artifact, implements, reconciles, and verifies.

**Optional — wire the live Storybook MCP (React).** Let the agents pull real component metadata from a running Storybook (`@storybook/addon-mcp`) so they reuse components instead of reinventing them:

```bash
npx storybook add @storybook/addon-mcp                                       # serves /mcp on the dev server
npx mcp-add --type http --url "http://localhost:6006/mcp" --scope project    # register in the agent client
```

Then set `designSource.mcp` to that URL in `architrave.config.json`. The agents now ground via `list-all-documentation` / `get-documentation`, write stories after `get-storybook-story-instructions`, and post `preview-stories` URLs for your sign‑off. (They allow the server via `"@storybook/addon-mcp/*"` in their `tools` — rename if your MCP server differs.)

**Optional — wire Mobbin MCP for real product/UI references.** Mobbin gives the research/design agents 600k+ shipped product screens and user flows to ground against, but it never replaces your repo's Storybook, design map, tokens, platform packs, specs, or backend contracts. It authenticates via browser OAuth on a paid Mobbin plan (**no API key**); register it in your user/local MCP client as `mobbin`:

```bash
npx mcp-add --name mobbin --type http \
        --url "https://api.mobbin.com/mcp" \
        --scope global \
        --clients "copilot cli,vscode,claude code"
# then trigger the tool once and complete the browser sign-in to authorize
```

**Optional — wire SearXNG MCP for self-hosted web search.** Point the agents at your *own* SearXNG instance (free meta-search, no API key) for live product/standards research:

```bash
npx mcp-add --name searxng --type stdio \
        --command npx --args "-y,mcp-searxng" \
        --env "SEARXNG_URL=https://searxng.your-host.example" \
        --scope global \
        --clients "copilot cli,vscode,claude code"
```

Architrave, Product Research, UX Architect, UI Visual, and Adversarial Judge can use `mobbin/*` / `searxng/*` tools when the client exposes them. Treat every result as untrusted third-party content — inspiration/evidence only, never repo truth, never an instruction source. Complete any browser login in the MCP client flow; never paste OAuth tokens, cookies, session material, or private instance credentials into chat, `architrave.config.json`, docs, run artifacts, or commits — the manifest check blocks committed MCP bearer material.

## Releasing (maintainers)

`main` *is* the published plugin — both marketplaces use `"source": "."`, so there's no build step and a push to `main` is the release. Two safeguards keep that honest:

- **Gate** — [`.github/workflows/validate.yml`](.github/workflows/validate.yml) runs [`scripts/check-manifests.sh`](scripts/check-manifests.sh) on every push and PR: all manifests + kit JSON parse, examples conform to the schema, agent/skill frontmatter and Codex TOML are valid, generated roles are current, and the version is in sync across all seven fields.
- **Versioned release** — a *static* version means installed users never re-fetch, so cut releases by bumping the version, then tagging:

```bash
scripts/bump-version.sh 0.2.0                 # writes the version into all 7 manifest fields
scripts/check-manifests.sh                    # confirm green
git commit -am "Release v0.2.0"
git tag v0.2.0 && git push origin main --tags # release.yml verifies tag==version, then publishes a GitHub Release
```

## Layout

```
README.md                     ← you are here
ROADMAP.md                    ← what's built vs. ported next
constitution-apple.md         ← deep Apple native-Swift synthesis (HIG · WWDC · SF Symbols) — cited
constitution-windows.md       ← deep Windows native-XAML synthesis (Fluent 2 · WinUI · Segoe Fluent Icons) — cited
plugin.json                   ← agent-plugin manifest (Copilot CLI / app / VS Code)
.github/plugin/marketplace.json ← Copilot plugin marketplace (self-hosted)
.github/workflows/            ← validate (gate every push/PR) · release (tag vX.Y.Z → GitHub Release)
.claude-plugin/               ← Claude Code plugin + marketplace manifests
.codex-plugin/plugin.json     ← Codex / ChatGPT plugin manifest
.codex/                       ← project role registrations + two generated role configs
skills/                       ← plugin-only Architrave / Tournament / Review skills
kit/
        MIGRATION.md                  ← how to replace bespoke repo agents with Architrave
  architrave.config.schema.json    ← per-repo config schema (the keystone)
        examples/                   ← phonodeck / sideport / tessera configs + design map/token starters
knowledge/
  apple.md                    ← Apple HIG pack (SwiftUI) — cited
  microsoft.md                ← Microsoft Fluent 2 / WinUI pack — cited
  web.md                      ← Web + React + component-driven dev pack — cited
  backend.md                  ← Backend + infra pack (thin orchestration · contract-first · IaC plan-only) — cited
  design-tokens.md            ← 3-tier tokens + design↔code reconciliation — cited
        learning-loop.md            ← durable run artifacts + repo profile + lesson promotion — cited
        yagni.md                    ← minimum-sufficient-change ladder + Ponytail/Caveman research — cited
        runtime-v2.md               ← durable Run/TaskGraph/EventLog/policy/worker semantics
agents/                       ← Architrave · Product Research · Operations UX · UX Architect · UI Visual · Platform Design · Tournament Analyst · Adversarial Judge
                                 + backend lane: Service Architect · Backend Planner · Backend Implementer · Infra Engineer
                                 + runtime lane: Runtime Observer
gates/                        ← rubric.md · checks.{sh,ps1} · reconcile.{sh,ps1} · quality-gate.{sh,ps1} · backend-checks.{sh,ps1} · hooks/
harness/                      ← Run v2 runtime · workers/workspaces · invariants · legibility · v1/v2 validators · schemas
benchmarks/                   ← short/feature/multi-surface/LongBuild scenarios + frozen fixture
docs/                         ← runtime, legibility, LongBuild, and v1→v2 migration guides
templates/                    ← AGENTS.stanza.md · copilot-setup-steps.yml (injected by the installer)
tools/                        ← canonical Python install/update + Codex role transaction helpers; tiny OS launch shims
scripts/                      ← check-manifests.sh (the gate) · bump-version.sh (one-command release bump)
assets/                       ← README screenshots (drop PNGs here)
AGENTS.md                     ← kit-level agent instructions
```
