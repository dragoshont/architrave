# Changelog

All notable changes to **Architrave** are documented here. This project follows
[Keep a Changelog](https://keepachangelog.com/) and [Semantic Versioning](https://semver.org/).
Releases at or before **v0.8.12** are on the
[GitHub Releases](https://github.com/dragoshont/architrave/releases) page.

## 0.21.21

- Coordinator self-rotation: the coordinator can start its own successor with
  `create_session` `detached: true` and `agent: "architrave:architrave"`
  (verified live); the successor re-points running children to itself. The old
  coordinator is archived by the owner.


- Context rotation: the program board flags sessions "rotate soon" (peak
  context ≥30% of limit or ≥300k) and "rotate now" (≥45% or two compactions),
  with a gold ↻ and a `<board>.rotate.json` list. The execution policy gives
  the rotation steps: Handoff and push, worktree successor from that SHA with
  `--expect`, claim move, archive after. Mechanical trigger; the judge only
  checks Handoff quality for mid-REQ rotations. Based on a feasibility study of
  the live Ode sessions.


- Program board: a session whose last action was the host's "Task completed"
  (no model turn after it) shows a green bar and "task completed", even before
  its lane row is updated; a later turn makes it active again.


- Review marks on the program board: session rows show ✓ when the session ran
  a reviewer (○ when none); REQ squares get a white corner when independently
  reviewed; lanes show "reviewed k/n" and a gold border when accepted work has
  no recorded review; the overview counts accepted but unreviewed REQs.
- Ledger rule: record each independent review in the REQ's Evidence as
  `review: <reviewer> <PASS|REVISE|FAIL>`; the `requirements` gate checks the
  format and refuses acceptance on a REVISE/FAIL without a later PASS.


- Program board hardening (independent review REVISE fixed): REQs in no lane
  get a "Not in a lane" rectangle so rings match the overview; evidence commits
  match inside joined text and results are cached; malformed log lines are
  skipped and a failed refresh keeps the last good board; one watcher per
  output (pid lock) that exits when no sessions are found; child sessions from
  all session-creating tools are followed recursively; the session count
  matches the timeline; "program min" is the program's span. README shows the
  board.


- Program board: `python3 harness/program_board.py --watch 120`, started by the lead for every non-trivial task
  renders a compact side-panel page for the browser canvas: overview, one
  rectangle per lane with a square per REQ coloured by ledger status, and how
  the coordinator and its child sessions ran over time with each session's
  tokens, peak context against the limit, and model and wall minutes. Reads the requirements file and local
  session logs only; refreshes every two minutes and stops after two quiet hours.
  Runs the gate's structural checks, rings accepted REQs whose evidence commits
  don't resolve, splits new and cached tokens, lists lane sessions logged
  elsewhere, and follows child sessions recursively. Replaces the Route Ribbon
  as the lead's default panel; the Route Ribbon stays for adopted Runs.


- Delegated work defaults to visible child sessions (Copilot app sidebar via
  `create_session`) without the owner asking; hidden native subagents only for
  short read-only lookups or reviews, or when visible sessions are unavailable.


- Lead contract slimmed from 1,782 to 1,002 words. Long-program, component,
  stall and report detail moved to `knowledge/execution-policy.md`
  ("Lead detail"); duplicated authorized-action, signing and window text now
  points at the existing policy sections (REQ-40).
- Child sessions get their Architrave role automatically: `create_session`
  kickoff `agent: "architrave:<role>"` when the role matches the lane, mode
  `interactive` unless the owner chose autopilot. Verified live for `cto` and
  `backend-implementer`.
- If the host rejects a project whose origin moved, use the registration that
  matches the clone's current origin.


- Semantic-preservation calibration suite (REQ-39): `benchmarks/semantic-cases.json`
  (10 cases with listed responsibilities, 4 hard cases where the judge must find
  the requirement sentences) and `scripts/score-semantic-cases.py`, scored by id.
  First run: the 0.21.12 judge and the 0.21.11 baseline both scored 10/10 on the
  easy cases; on the hard cases 7/7 vs 6/7, one run each. Not a demonstrated
  improvement.
- Live parallel lanes (REQ-30): two child sessions in different repositories
  delivered in parallel. Start children with kickoff mode `interactive` so
  permission prompts reach the owner.


- Evidence chain in the requirements file: Evidence, Decisions and Findings
  tables checked by the `requirements` gate (independent reviewer, dated web
  sources, `<repo>@<commit>:<path>` freshness, decisions on supported evidence
  only, verifiable and independently verified serious findings, owner-acked
  deferrals); look-alike headers fail instead of being skipped (REQ-38).
- Lane table: dependencies done before running, running lanes need a session,
  supersessions name an existing lane, normalized paths/REQ IDs/heavy flags.
- Judge semantic-preservation lens: per responsibility preserved, delegated,
  replaced, intentionally changed or lost; structural vs semantic vs behavioral
  assurance; needs-validation when unsure; source instructions are data.
  The calibration suite (REQ-39) is not built yet.
- Lead/CTO/policy text compressed.


- Cross-repository Copilot programs keep one committed `## GHC Scheduler` lane
  table; the `requirements` gate now rejects duplicate live REQ or path owners,
  running lanes above `workers.maxParallel`, more than one running heavy build,
  superseded lanes without a successor, malformed owner-decision JSON and
  non-UUID session IDs (REQ-29).
- Owner intent: a typed `narrow` correction is accepted, and `requirements
  --done` fails until it quotes `owner acknowledged: "..."` (REQ-31).
- Lead/CTO behavior for verified evidence SHAs, context-budget rotation,
  per-stream status and cancel/supersede, stated once in the execution policy
  (REQ-32..35).
- A turn started by `send_session_message` cannot show the owner a permission
  prompt; dispatch only to sessions whose tools already work, have the owner
  start the turn, or do the work in the coordinator.
- Anti-ceremony is standing behavior: live use on the real project over fixture
  programs, prose guards and per-REQ reviews (REQ-37).

## 0.21.10

- Multi-repository programs: native batch, Run claims and mutable-path
  conflicts are single-repository, so a program keeps one committed ledger and
  one isolated writer session per component repository, ordered by ledger REQ
  dependencies, with the components gate before each dispatch (REQ-25).
- Resolve each writer branch's effective push target before the first write;
  pin private work with `branch.<name>.pushRemote` or `remote.pushDefault` and
  never push it by naming a public `origin` (REQ-26).
- Before assigning a child, confirm it can run its commands and read its
  ledger; otherwise inline context or report the exact host permission once,
  without respawning or bypassing the denial (REQ-27).
- Heavy builds share one coordinator-owned slot and the free-disk floor; source
  edits and built non-visual checks stay parallel; desktop input, installed
  apps, VMs, signing and publication keep one owner each (REQ-28).

## 0.21.9

- Lead and CTO reuse current scoped owner authorization, including standing
  permission, for existing-identity build/sign/stage work instead of requesting
  signing approval for every repeat build. Persist grants through existing
  corrections and required Run policy APIs; check scope/limits/expiry/revocation.
- New identities, keychain policy, distribution/notarization/publication and
  install/daemon changes need grant coverage. Actual host/keychain prompts and
  trusted Run checkpoints remain mandatory; no key-material access or portable
  project-specific signing permission (REQ-24).

## 0.21.8

- Lead and CTO choose the smallest useful authorized action: no invented fresh
  VM snapshot gates, circular checkpoint evidence or repeated phase approvals.
  Dedicated experiments keep optional safeguards proportional; actual
  host/Run/legal/destructive-operation constraints remain.
- Prefer discovered supported target-only window control through the existing
  exclusive input owner. Zero windows is not permission denial; a supported
  independent CLI path need not wait for UI evidence.
- Reconcile timed-out mutations before retry without another backup ceremony.
  Distinguish instruction sent, execution started, observed result and accepted
  outcome, including source versus installed/native and loaded-session identity.
- Repair adjacent backend phase/ledger prerequisites and infra/observer
  checkpoint-versus-backup wording. REQ-20..23 (remapped from branch REQ-16..19).



## 0.21.7

- `requirements --claim` now writes ownership and `claimed` status for open rows;
  commit before dispatch from one coordinator. Conflicting sequential claims fail.
- `requirements --handoff --expect <predecessor-sha>` rejects stale successors.
  SDD scratch is a cache subordinate to committed requirements Handoff.
- CTO oversight acts on loops/idle ready owners in the same pass, verifies
  current-coordinator state, verbatim owner scope/holds and source-bound criterion
  evidence, and sends corrections only with new evidence or action.
- Document automation prompt edits resetting the next run time.

## 0.21.6

- CTO oversight also checks claims against commits and evidence, breaks loops
  with one different concrete action, and answers unnecessary approval
  requests, while never resolving Run checkpoints, confirmation-required
  operations, scoped grants or typed trusted checkpoints (C-09).
- README documents program oversight.
## 0.21.5

- CTO gains an owner-requested program oversight mode: goal-progress-first
  passes across host sessions on a host-owned 30/60-minute schedule, ledger
  `--handoff` and gate checks, safe parallelism nudges, routine unblocking with
  an owner-only queue, at most one steering message per session per pass;
  it still never implements (REQ-15, C-08).
## Unreleased

## [0.21.4] - 2026-10-24

### Added
- `requirements --handoff` gates session rotation: it fails on uncommitted
  requirements or on progress in this checkout's git-ignored SDD ledger newer
  than the committed requirements, and warns about such a ledger in a sibling
  worktree (each judged against its own branch, by author time).

### Changed
- Rotation is commit-based: commit Handoff and pass `--handoff`; the successor
  starts from that commit and continues the same file; the predecessor hands
  off once and stops relaying. Worktree-local scratch is never the ledger.

## [0.21.3] - 2026-10-23

### Fixed
- Requirements `--claim` and `--done` fail instead of silently passing when no
  ledger resolves. Diagnostics identify the resolved root and config, and flag
  a child SPEC.md requirements table ignored by a parent config. Plain
  requirements validation keeps its optional skip behavior.

## [0.21.2] - 2026-10-23

### Changed
- Fresh multi-repo kickoffs verify current component refs, write targets and
  acceptance evidence from durable requirements/corrections/Handoff; historical
  audits and working precursors do not prove the intended product path ran.
- Keep project kickoffs thin by linking Architrave's existing workflow,
  ownership, permission and real-flow verification contract.
- Retire only assigned completed/superseded schedules through authorized host
  controls, preserving evidence without reviving retired monitors or expanding
  cleanup.

## [0.21.1] - 2026-10-23

### Removed
- Installer backward compatibility: retired-shim cleanup, legacy quality-hook
  detection/retirement (`retire-hooks`), quarantine machinery and old
  transaction-format fallbacks. Transactional and symlink safety remain.
- Remaining PowerShell references in active docs (only rejection checks remain).

### Changed
- REQ-08 accepted: live `architrave_native_dispatch` with REQ binding and a
  native gate PASS; the `--prepare-live` fixture is now requirements-bound.

## [0.21.0] - 2026-10-23

### Removed
- **Python only.** Every `.sh` and `.ps1` launcher is gone: gates, harness
  helpers, installer, release and test scripts. Run them with Python instead:
  `python gates/gate_runner.py <gate>`, `python harness/architrave_cli.py <command>`,
  `python harness/improvement.py <action>`, `python tools/install_update.py install|update`.
  Windows needs only Python; PowerShell-style flag aliases (`-Quick`, `-Profile`, …)
  and the installer's `--entrypoint` option are removed.

### Changed
- The four shell-only learning helpers are now Python subcommands of
  `harness/architrave_cli.py` (`init-run`, `mark-stale-learning`,
  `semantic-learning-review`, `apply-semantic-learning-findings`); jq is no longer needed.
- Command launching on Windows falls back to `cmd`, never PowerShell.
- `install_update.py update` removes the previously installed `gates/` and
  `harness/` launchers; user-owned scripts are left alone.
- The manifest validator rejects any tracked `.sh`/`.ps1` outside vendored skills.

## [0.20.1] - 2026-10-23

### Fixed
- Requirement claims now coordinate every worktree of one clone through a shared
  lock and checkout registry under the git common directory (separate clones are
  still not coordinated).
- A prose `SPEC.md` is no longer adopted as the requirements file; only one with a
  `| ID | ... | Status |` table is.
- Completion fails closed with `REQ_SOURCE_MISSING` when bound tasks exist but the
  requirements file is gone; withdrawn/superseded REQs count as resolved.
- Starting an already-claimed task re-checks the file's owner column.
- Gate failure logs go to a private per-user directory, keep the newest 20 and
  sanitise component names; PowerShell recipes emit UTF-8.
- Improvement ledger: retiring a global instruction needs owner approval; CLI
  writes use compare-and-swap so concurrent edits are not lost.

## [0.20.0] - 2026-10-23

### Changed
- **Spec-driven by default again.** The lead contract, rubric, execution policy, skills, AGENTS stanza and every manifest description now lead with spec-driven development: non-trivial work starts from REQ rows with testable acceptance in `SPEC.md` (or config `requirements`), work traces to REQ ids, owner corrections are typed rows recorded before acting, and done means `requirements --done` passes. This restores the spec-first core removed in 0.11.1.
- The requirements gate defaults to `SPEC.md`; `checks` and `quality-gate` validate the requirements file whenever one exists.
- Gate recipes print only `ok` on success and the last 40 lines plus a full-log path on failure (`ARCHITRAVE_GATE_VERBOSE=1` restores passthrough).
- README leads with the spec-driven workflow and lists the full capability set.

### Added
- Run v2 REQ binding: tasks and WorkPackets carry `reqs`; with a requirements file the runtime rejects unbound, unknown or closed REQs, records claims in the EventLog, refuses duplicate claims and refuses Run completion until bound REQs are accepted. Native dispatch requires `reqs` and seeds the kickoff with acceptance and corrections.
- `harness/improvement.py` (`propose`, `check --phase before|after`, `approve`, `list`, `prune-review --model`): self-improvement proposals need executable-first promotion, before/after evidence and human approval; global instruction targets need `--owner-approved`; per-model harness pruning review.
- `SPEC.md` for Architrave itself.

## [0.19.0] - 2026-10-23

### Added
- Vendored six third-party skills, unchanged and with their upstream licence
  files: `verification-before-completion`, `systematic-debugging`,
  `subagent-driven-development` and `writing-skills` from obra/superpowers
  (MIT), and `skill-creator` and `webapp-testing` from anthropics/skills
  (Apache-2.0). The README lists source commits and licences.

## [0.18.0] - 2026-10-23

### Added
- `python gates/gate_runner.py requirements` validates the long-program
  requirements file. Each REQ needs testable acceptance, an accepted REQ needs
  evidence, a superseded or withdrawn REQ needs a typed correction
  (`add|revise|retract|supersede`), and `## Handoff` needs Next, Failed
  approaches and Verify. The components gate applies the same checks.
- `--claim <ids> --owner <lane>` refuses duplicate, accepted or closed lanes
  and prints acceptance plus corrections to seed kickoffs. `--done` fails until
  every active REQ is accepted.
- `kit/examples/requirements.md` template and `docs/long-programs.md`, a
  plain-language guide with research sources.

### Changed
- The lead contract adds a get-bearings start, an escalate-to-owner rule for
  conflicting directives, and "code and tests outrank notes".
- The learning loop prefers executable promotion, records failed approaches,
  and requires human-gated skill or instruction changes.

## [0.17.0] - 2026-10-23

### Added
- Long-program mode in the lead contract: work spanning more than one
  repository, more than one day or more than two children needs an adopted Run
  or one repository-resident requirements file before spawning. Owner
  corrections are appended to it, kickoffs and hand-offs name it, and repeatedly
  compacted coordinators rotate into fresh sessions seeded from it.
- `requirements` config key. The components gate fails when two or more
  components are mapped without a non-empty requirements file outside session
  scratch.

### Changed
- The active-child cap is `workers.maxParallel`: default 3, owner-approved up
  to 8. It is enforced by both the runtime and native dispatch, and
  `architrave_native_batch` accepts up to 8 packets.
- The "no exhaustive ledger" rule now applies only to bounded single tasks.
  A periodic check that sees no requirement change is not progress.

## [0.16.0] - 2026-10-21

### Added
- Optional `components` map in `architrave.config.json` for work spanning
  several repositories, and `gate_runner.py components [--test]`: fails a
  checkout in agent session scratch or one whose branch does not push to its
  `repo` (naming a read-only `upstream`), warns on unpushed or uncommitted
  work, and runs each `service` check before its `ui` check. The lead contract
  keeps one writer per component and splits multi-component threads into fresh
  sessions. Example: `kit/examples/coordination.architrave.json`.

### Planned
- Add a public Run cancel/supersede transition and make invalid unstarted-task
  intake terminal instead of retry-ready.

## [0.15.1] - 2026-10-19

### Fixed
- Removed `tools:` allowlists from every agent. They hid host session tools, so
  a role such as the Adversarial Judge could not spawn a session or notify its
  parent. Agents now inherit the host's tool set; read-only roles stay
  read-only by contract. A check rejects new `tools:` lists.

## [0.15.0] - 2026-10-18

### Added
- OpenCode worker host (`harness/opencode_host.py`): runs one WorkPacket in a
  session of an already-running local `opencode serve` through its HTTP API,
  bound to the task worktree, returning only a candidate. Loopback only, no
  redirects or proxies; host permissions and model choice stay with OpenCode,
  and pending permission prompts are reported, never answered.
- Lead contract: challenge the request at intake and ask only questions whose
  answers change the work.

### Fixed
- An OpenCode session that cannot be confirmed stopped keeps its task lease, so
  the task is not redispatched until `worker-recover`.

## [0.14.4] - 2026-10-18

### Changed
- Centralized the lead contract and shortened skill/repository entrypoints.
- Removed blanket intake, Run, acceptance-matrix and learning-artifact demands
  for ordinary direct source work; required safety/release evidence remains.
- Made child assignments proportional and CTO consultation on-demand.
- Made prose assertions whitespace-insensitive, retaining substantive checks.
- Aligned judge guidance, the generated Codex role and benchmark prompts with
  product-first work and compact reviews.
- Refreshed README setup, capabilities and the accessible workflow diagram,
  replacing outdated synthetic screenshots without product version labels.

### Fixed
- Explicit named-agent requests cannot be silently replaced by inline skills.
- Mutable children must verify their actual repository, workspace and intended
  branch/base before writes, and stop on identity mismatch or unavailable host
  authorization rather than retrying unchanged.

### Limitations
- These orchestration rules guide host behavior; they are not new automatic
  hooks or an OS sandbox. No runtime authorization or admission code changed.
- Existing sessions may retain old instructions; use a fresh session after
  updating the plugin. Static instruction-size reduction is not measured
  token-cost savings.

## [0.14.3] - 2026-10-11

### Added
- Three explicit-only, host-neutral skills for authoring agent roles, skills,
  and least-privilege MCP integration designs.
- Three repository-fixture benchmark scenarios covering agent-role maintenance, skill
  authoring, and MCP integration design; only scenario preflight was run.
- A concise README Executive Summary of Architrave's supported delivery and
  verification capabilities.

### Changed
- Clarified that worker worktrees and scope checks are not an OS security
  sandbox.

## [0.14.2] - 2026-10-10

### Added
- One lightweight, explicit-only `architrave-work` skill for bounded development,
  evidence-backed research and writing grounded in author-provided voice samples.
- Child skill handoffs include relevant named guidance and verified paths rather
  than assuming a subagent/sidebar session inherits the parent's loaded skills.

### Changed
- Lead agent inherits all host-available tools; specialist tool scopes remain.
- Plugin-only work no longer requires repository adoption. Kit guidance resolves
  from the reported plugin skill base, not guessed host cache paths.
- Independent implementation tracks prefer supported coordinated sidebar
  sessions, falling back to native subagents in CLI clients.
- Mandate-driven continuation and focused mid-development research, without
  routine status rituals or treating urgency as authorization.

### Limitations
- Existing host sessions may retain stale skill paths. A readable plugin payload
  or successful fresh-session load does not prove an old session was refreshed.

## [0.14.1] - 2026-10-08 (candidate)

### Added
- Optional, single-file Copilot Route Ribbon canvas: segmented steps, evidence
  inspector, visibly bypassed/deferred routes, human/resource/dependency holds,
  explicit dead ends and fingerprint-backed retry stops. No private demo history.
- Read-only `ribbon-snapshot` Python Run projection with capture/source/objective
  provenance and current product milestone identity. Scoped done is not product
  verified; superseded blockers remain historical.
- Domain-keyed display snapshot persistence and supported canvas reload
  rehydration, bounded input/request guards, loopback-only serving and cleanup.
- Explicit `canvas-install TARGET` to install or refresh the portable renderer
  through existing managed-path safety. Normal adoption remains unchanged.
- Display-digest compare-and-swap updates allow equal-Run-revision refreshes
  while rejecting competing/stale display writes, with ordering and reload
  regressions. Empty event history fails with an explicit projection error.
- Fresh source-bound native semantic execution through the joined host, using
  owned reviewer results, actual first-dispatched model metadata and one-use
  owner/challenge-bound authenticated producer receipts.
- Optional stacked workstream lanes with independent slice/source/owner states,
  canonical cross-stream BLOCKS and non-authoritative INFORMS annotations.
- Passive Session instrument with the approved restrained visual grammar,
  host-reported model/effort/context and expandable owned-child lanes. The
  documented Copilot extension contribution preserves standalone preferences
  and provider-qualified one-shot startup without automatic workers or prompts.

### Changed
- Automatic PostToolUse quality registration is retired. The same deterministic
  quick validator runs explicitly after relevant config/design/product-copy
  changes and final integration, with mandatory checkpoint/CI evidence.
- Removed packaged quality-hook definitions and obsolete packaging/documentation
  references. Exact legacy recognition remains in installer code for safe cleanup.
- Removed native tool-blocking hooks. Host permissions remain host-owned;
  explicit native tool admission/source/evidence checks and passive Route
  Ribbon/Session companion event observation remain.
- Install/update retires only exact recognized legacy definitions transactionally;
  custom/mixed/unknown hooks are preserved with manual action. A hooks-only
  `retire-hooks --dry-run TARGET` preview supports post-release owner cleanup;
  public quality-gate CLI compatibility and explicit native tool checks remain.

### Limitations
- Copilot canvas capability required; no Codex/Claude canvas claim. Agent-fed
  snapshots, not live telemetry. Active effort, wait duration, tokens and cost
  remain Unknown; relative segment weights are explicitly estimates.
- Preparation does not authorize consumer installation, tagging or publication.

### Fixed
- Governing failed checks revoke current ribbon verification/milestones without
  erasing earlier completion history. Failed product observations are retained
  canonically and cannot be relabelled PASS; repeat observations keep immutable
  logs and visual artifacts.
- Display CAS is protected across provider processes, with dead-writer recovery.
  Native source inventories use byte-bounded frames; semantic cleanup preserves
  admitted results and separately retains owned recovery progress.
- Hook retirement preserves post-backup custom edits, retains legacy crash
  recovery, and reports manual action for custom-only/malformed definitions.
  The canonical rubric uses the explicit executable quality-check cadence.

## [0.14.0] - 2026-10-07

### Added
- On-demand CTO feasibility reset for owner requests or established stall,
  repeated-failure and budget signals. The agent chooses finite evidence-driven
  time/turn/output bounds with one rationale; no universal review duration,
  mandatory reviewer or POC.
- `feasibility-record` stores one compact decision/snapshot in the existing Run
  task, clamps to task/owner/global limits, rejects unchanged-evidence renewals
  and clock resets, and renders expired decisions as partial/PARK. Human holds,
  candidates, recovery and mutation policy remain unchanged.
- Provenance-separated runtime/adoption status; canonical worker lists never
  prove all host sessions idle. Supported joined-task visibility is explicitly
  session-scoped; missing loaded-context evidence remains UNKNOWN.
- Source/task/criterion-bound intermediate product milestone advancement and
  one-use owner primary-path correction, with unchanged acceptance/baselines,
  human holds, side effects and adaptive budgets.

### Changed
- Path touches remain activity proxies, not product milestones. Source drift
  labels stale stall projections; live bound leases suppress idle/stall advice.
- CTO corrections distinguish hypotheses, reproduction and verified evidence,
  with cheapest parity probes before risky advice and actionable bounded
  owner handoffs.
- Generic process-growth management is deferred; risky experimental commands
  need supported exact-owned-tree controls, never broad name-based cleanup.

## [0.13.0] - 2026-10-06

### Changed
- Thin supervisor core and managed adoption stanza; lane, review, tournament,
  learning and deep recovery instructions load only when needed. CTO is an
  inline checklist by default, not a mandatory extra worker.
- Copilot native transport waits on supported lifecycle events, not polling.
  Authenticated unrelated sibling lifecycle transitions commute; task ownership,
  objective/policy, human holds, source checks and evidence binding still fail
  closed.
- Default active task cap is three (or a lower configured cap); native child
  spawning is denied by the supported pre-tool hook, with finite time/turn/output
  budgets and compact candidate returns.
- Retries need a new hypothesis or relevant observed evidence. Two identical
  failure/evidence fingerprints stop the lane; explicit recovery cannot reset it.
- Optional user model pins pass through the host; reported effective selection
  stays in worker evidence. Unsupported effort/model telemetry is not invented.

### Added
- Frozen direct/parallel benchmark tasks and a Python measurement helper that
  never launches an agent; one compact result record separates native execution
  from deterministic fixtures and unavailable telemetry.
- Supported Codex local marketplace catalog and host-specific install/discovery
  guidance, without private desktop hooks or forced host symmetry.

## Highlights since 0.11.0 (0.12.x)
- Slim footprint: generated orchestration is about 82% fewer files and 85% fewer
  bytes than v0.11.0, pinned and re-measured from source on every release.
- Native host worker: agent WorkPackets run through the joined Copilot host's
  tasks RPC with bounded candidates and independently observed gates; there is
  no agent CLI fallback.
- Outcome rules and the stall detector: reference parity first, lenient
  third-party parsing, specific diagnostics, proportional ceremony, and
  `STALLED_PRIMARY_CRITERION` when work stops touching the failing path.
- CTO role: `architrave:cto` and its checklist are consulted at Run start and
  on stall, and return one plain correction.
- Deterministic outcome controls: observed-only primary evidence, a loop cap of
  three failed attempts, a real-signal budget, push-back verdicts before work,
  and owner-message lint.
- Host-native review: the host's own reviewer is preferred over the Architrave
  judge; two model families are required only with `review.crossFamily`.

## [0.12.4] - 2026-10-06

### Fixed
- The Windows workspaces concurrency test is now load-tolerant (test-only; no
  runtime change).

## [0.12.3] - 2026-10-05

Deterministic only: no new agents, workflows, dependencies, or model calls.
Feature freeze after this release.

### Added
- Push-back verdicts: `task-add --pushback KEEP|CUT|DEFER:reason`. New Runs
  refuse to start a task without one (`PUSHBACK_MISSING`), and CUT/DEFER never
  dispatch. Structure is enforced; reason quality is not. Tournament results
  must include typed `DO_NOTHING` and `SMALLEST_VIABLE` options and
  `winnerBeatsDoNothing` (`tournament-review --result`).
- Run budget from real signals: optional `evaluation.budget` limits for turns
  (Run transitions), commits, dispatches, and minutes. Status reports
  `BUDGET_80`/`BUDGET_100`/`BUDGET_UNKNOWN` (diverged history). At 100%, new
  dispatches stop.
- Owner-summary lint in status and checkpoint (`OWNER_MESSAGE_LINT_FAIL` for
  three or more full SHAs, PIDs, run IDs, or UUIDs), also available as
  `gates/gate_runner.py message-lint`.
- Semantic reviews record `reviewer: host-native|architrave-judge` and their
  family. The review skill prefers the host-native reviewer over
  `adversarial-judge` (never both), and a duplicate same-family R3/R4 PASS is
  rejected (`DUPLICATE_REVIEW_FAMILY`).
- `PRODUCT_OUTCOME_CONFIRMED` external checkpoint type for typed user
  confirmation of a product outcome.
- `review.crossFamily` config (default false): R3/R4 need one independent review
  on the host default or auto model; two different families only when set, as
  in Architrave's own repository config.
- `effort: low|default|high` capability signal on tasks (`task-add --effort`)
  and reviews (`gate-record --effort`). It maps to the host auto tier or
  reasoning effort when exposed, and is a recorded no-op on Copilot native
  tasks today. It never names a model.

### Changed
- The primary criterion passes only on a runtime-bound reality/e2e receipt or
  `PRODUCT_OUTCOME_CONFIRMED`; CI/test results, auth/MFA/policy checkpoints, and
  self-authored evidence are rejected (`PRIMARY_EVIDENCE_NOT_OBSERVED`).
- Loop cap: three failed attempts on the primary criterion (commits don't
  reset) raise `PRIMARY_STALLED` with the best attempt and caveats, and block
  new work on it. The default stall threshold is now 3.

## [0.12.2] - 2026-10-05

### Added
- **CTO** agent (`architrave:cto`) and `architrave-cto` skill checklist. The
  conductor consults it at Run start and on stall.
- Primary-criterion stall detector: `run --primary-criterion/--primary-path` or
  `primary-set`. After 5 consecutive commits/worker results that miss the
  criterion's code path, status reports `STALLED_PRIMARY_CRITERION` and
  `task-start` refuses unrelated tasks.
- Replacement/port tasks record their tested `reference`; parity on the real
  flow is the first gate.
- Opt-in `productCopy` check in `gates/checks` (and the quality-gate hook) for
  internal evidence/spec/status language in UI strings.

### Changed
- Policy text: default-deny covers mutation and side effects only; parse
  third-party protocol input leniently; failures carry a specific step and
  reason; R0/R1 fixes need only the focused test plus CI; approved operations
  may escalate a graceful quit to SIGTERM without a new hold.

## [0.12.1] - 2026-10-05

### Fixed
- Structured worker CLI failures clean up outside the CLI catch: locked tamper
  recovery takes no CLI arguments, and preparation-failure workers close through
  public APIs.

## [0.12.0] - 2026-10-05

### Changed
- Durable agent WorkPackets use the native host adapter (joined Copilot tasks
  RPC) with bounded candidates, observed source-bound gates, safe orphan and
  tooling recovery, and preserved human holds. Nested agent CLI recipes were
  removed.
- Portable adoption on Windows and macOS with Python 3.9+, plus a refreshed,
  source-pinned orchestration footprint benchmark.

### Added
- Trusted external target attestation (including cross-host SSH), closed-resource
  reconciliation, challenge-bound policy amendments, and public challenge
  renewal.

## [0.11.3] - 2026-10-05

### Added
- Public `target-attest` Run v2 command for exact
  `SAFE_WRITE_TARGET_REQUIRED` observation through a user-level trusted
  executor registry.
- Stdlib-only exact filesystem observer and `executor-install` enrollment path
  with absolute Python/adapter paths, SHA-256 pins, exact provider/checkpoint
  allowlists, and exact target identities outside the target repository.
- Fixed SSH relay mode for canonical Runs whose exact read-only target is on a
  different trusted host, without copying Run state or runtime keys.
- Public trusted historical side-effect reconciliation for exact
  `applied-closed` and `closed-unknown` outcomes without replay or
  repository-local self-attestation.
- Public one-use challenge renewal for unchanged, unstarted pending exact-target
  checkpoints when the original returned nonce is lost.
- End-to-end regressions for repository-local and modified adapters, provider,
  principal, task/challenge and observed-identity mismatches, replay, timeout,
  malformed output, oversize output, and successful atomic proof consumption.

### Security
- Target attestation rechecks Run, objective version, state revision, task,
  checkpoint, provider, principal, challenge hash, target binding, and intended
  identity at commit time.
- Adapter execution uses argv without a shell, a minimal environment,
  non-repository working directory, bounded request/stdout/stderr, and a
  configured timeout. Caller-supplied observed JSON is not accepted.

## [0.11.2] - 2026-10-04

### Added
- Public `policy-amend-request` and `policy-amend` Run v2 commands for additive,
  exact-scope mutation grants and confirmation-required operations.
- Replay-protected amendment checkpoints bound to Run, objective version,
  revision, principal, provider, exact delta, reason, and one-time challenge.
- Public CLI regressions for the `public-candidate:edit` to `repository:edit`
  correction and authorization, replay, stale-state, cross-Run, transaction,
  worker/coordinator spoof, and active-mutation rejection paths.

### Changed
- Policy mutation authorization is enforced inside the transaction commit
  boundary with a store-private capability.
- A successful amendment releases its policy-blocked task to `READY` without
  replaying the action; active or uncertain mutation state fails closed.

- Model selection is entirely user/host-owned; canonical agents, Run state,
  WorkPackets, schemas, templates, and docs no longer specify model classes,
  tiers, providers, reasoning levels, context tiers, or concrete models.
- Run v2 now persists canonical state, authenticated events, one rolling
  recovery snapshot, and compact evidence only. Human views are on demand.
- Python stdlib is now canonical for install/update, gates, Run/learning
  validation, review launchers, and orchestration; OS scripts are launch shims.
- Versioned objective replacement, reuse-first redesign gating, target identity
  preflight, two-lane isolation, bounded checkpoints, and review batching guard
  long-running work against correction loss and objective drift.

## [0.11.1] - 2026-09-09

### Added
- Delivery-first scheduling with an explicit support-work budget, targeted-first
  gate cadence, bounded semantic reopen rules, and stalled-command thresholds.
- Focused policy validation covering canonical agent, execution, rubric,
  learning, and installed AGENTS-stanza behavior.
- Figma MCP tool patterns in the canonical lead agent.

### Changed
- Full tournaments are reserved for risky or materially ambiguous decisions;
  routine bounded work records a direct plan and YAGNI rung.
- Small safe two-file mechanical changes stay with the coordinator when an
  existing targeted check fully decides acceptance.
- Status reporting leads with usable product behavior and accepted product
  criteria; infrastructure and audit evidence are reported separately.
- Learning artifacts are emitted at useful boundaries rather than after every
  micro-action.

### Fixed
- Supporting tasks no longer independently trigger full configured gates.
- Repeated micro-review loops now consolidate after two reopens and stop after
  a third non-PASS.

[0.11.3]: https://github.com/dragoshont/architrave/compare/v0.11.2...v0.11.3
[0.11.2]: https://github.com/dragoshont/architrave/compare/v0.11.1...v0.11.2
[0.11.1]: https://github.com/dragoshont/architrave/compare/v0.11.0...v0.11.1

## [0.11.0] - 2026-09-05

### Added
- Host-native bounded delegation and risk-based verification policy.
- Benchmark treatments for delegation, verification, and observable execution telemetry.
- Optional run-summary execution evidence with paired POSIX/PowerShell validation.
- Durable `architrave.run.v2` control plane with Outcome, Acceptance Matrix,
  TaskGraph, typed HMAC-authenticated EventLog, checkpoints, resume,
  challenge-bound external waits,
  default-deny mutation policy, and v1 migration.
- Bounded Copilot/Claude/Codex/shell workers, isolated worktree management,
  mechanical invariants, product/deployment legibility, risk-based evaluation,
  registered evidence binding, PNG blank-screen analysis, and mutation receipts.
- Architrave LongBuild benchmark categories, frozen Tessera-shaped fixture,
  recovery/external-checkpoint/parallel/deployment-policy scenarios, and durable
  outcome/intervention metrics.
- First-class Codex/ChatGPT plugin manifest with three plugin-only Agent Skills.
- Project-scoped Tournament Analyst and Adversarial Judge roles generated from
  canonical agents, with opt-in POSIX/PowerShell install and update support.
- Bounded, nonce-verified independent semantic review launchers.
- Disposable Codex runtime fixtures for plugin skill discovery, role routing,
  exactly-one MCP invocation, and hostile-output resistance.
- Installers and updaters ignore `.architrave/runs/` and
  `.architrave/worktrees/` by default while learning remains tracked.

### Changed
- Execution benchmarks now emit periodic progress heartbeats, cap each
  agent cell at 10 minutes and each invocation at 20 minutes by default, and
  stop launching cells when the configurable run budget is exhausted.
- The lead agent is materially smaller and delegates lane detail to retrievable
  knowledge. Phase Ledger is now a Run projection rather than an autonomy wall.
- Infrastructure/runtime remains plan/read-only by default but explicit bounded
  Run policy can authorize a target/operation with receipt and verification.
- Manifest validation and version bumping now synchronize seven version fields
  and enforce Codex JSON/YAML/TOML, generator, transaction, launcher, and
  structural runtime checks.
- Codex role documentation explicitly distinguishes the read-only command
  sandbox override from inherited parent permission, skill, and MCP authority.
- The `knowledge` profile now installs only its five-agent crew (`architrave`,
  `adversarial-judge`, `tournament-analyst`, `product-research`, and
  `runtime-observer`) without native-app constitutions. Explicit agent refresh
  migrates existing knowledge repos by removing only non-crew agent basenames
  packaged by the kit, preserving target-only custom agents and Codex roles.

### Fixed
- Benchmark validation now accepts the already-supported Claude and Codex
  runners, and frozen fixture paths resolve consistently relative to their
  scenario file.
- POSIX updates now require `jq` and fail before writes on malformed,
  non-object, or unsupported-profile configuration instead of falling back to
  application behavior. PowerShell enforces the same `kind` contract.
- Tournament review verification now supports nonce generation without
  `uuidgen`, accepts exact CRLF evidence lines, and rejects missing or duplicate
  completion markers consistently across POSIX and PowerShell.

### Security
- Benchmark judging is now fail-closed and tool-free, nonce-delimits untrusted evidence, blinds producer identity, verifies observed judge family, and prevents stale verdict reuse across judge configurations.
- Installers and updaters now validate every managed destination, reject
  symbolic links, junctions, reparse points, and unsupported path types, and
  revalidate immediately before each write or deletion. Per-file staged
  replacement also prevents target hard links from mutating external content.
- Cross-platform adversarial fixtures verify external directory/file sentinels
  and target snapshots remain unchanged when managed paths or configuration are
  unsafe.
- Focused managed-path tests now run on Windows plus Linux x64 and arm64 during
  validation and release, covering Unicode paths, FIFOs, links, device nodes,
  hard links, and containment behavior.

[0.11.0]: https://github.com/dragoshont/architrave/releases/tag/v0.11.0

## [0.10.3] - 2026-07-10

### Fixed
- PostToolUse design guards now invoke the paired quality gates in structured
  hook mode, emitting `{"continue":true}` on success and exit 2 with stderr
  diagnostics on invalid configuration.
- POSIX and PowerShell fixtures parse the successful hook JSON and verify the
  blocking failure contract, eliminating VS Code's non-JSON hook warnings.

[0.10.3]: https://github.com/dragoshont/architrave/releases/tag/v0.10.3

## [0.10.2] - 2026-07-10

### Fixed
- PowerShell install and update paths no longer append a second newline to the
  managed `AGENTS.md` block, so freshly adopted repositories pass
  `git diff --check` on Windows.
- The PowerShell installer fixture now validates the full generated repo and an
  `update.ps1 -Agents` refresh with actionable captured output.

[0.10.2]: https://github.com/dragoshont/architrave/releases/tag/v0.10.2

## [0.10.1] - 2026-07-10

### Fixed
- PowerShell profile-aware gate fixtures now capture the information stream
  emitted by `Write-Host`, so Linux and Windows CI can assert the messages that
  were already visible in job output.

[0.10.1]: https://github.com/dragoshont/architrave/releases/tag/v0.10.1

## [0.10.0] - 2026-07-10

### Added
- First-class `kind: knowledge` configuration for repositories with docs, skills, schemas, and automation but no UI or service lane.
- Explicit `--profile knowledge` / `-Profile knowledge` installer support backed by a canonical example.
- Paired POSIX and PowerShell regression fixtures for schema profiles, installers, and profile-aware gates.

### Changed
- The lead agent, Adversarial Judge, managed `AGENTS.md` stanza, checks, reconciliation, and quick quality gate now classify the repository profile before applying UI rules.
- Linux and Windows validation/release workflows exercise knowledge-profile installation end to end.

[0.10.0]: https://github.com/dragoshont/architrave/releases/tag/v0.10.0

## [0.9.1] — 2026-07-02

Dual-judge semantic gates are now packaged as their own release so installed clients refetch the
updated Architrave instructions instead of staying on the existing v0.9.0 package.

### Changed
- Full semantic gates now require two independent judge-family passes by default: one Copilot/GPT
  family judge and one Claude family judge.
- Semantic review helpers default to running both configured providers, with explicit Copilot and
  Claude command guidance.
- Copilot and Claude marketplace manifests describe the dual-judge gate posture consistently.

[0.9.1]: https://github.com/dragoshont/architrave/releases/tag/v0.9.1

## [0.8.13] — 2026-06-28

Native‑app **constitutions**: deep, source‑cited rule bases that ground Architrave when it builds or
reverse‑engineers native desktop/mobile apps, so it **reuses system components instead of guessing or
reinventing them** — including when you hand it a task or a screenshot.

### Added
- **`constitution-apple.md`** — Apple **HIG / SwiftUI** (macOS · iOS). Verbatim macOS/iOS type tables
  (macOS Body 13 pt ≠ iOS Body 17 pt), Liquid Glass functional‑layer + material rules, SF Symbols
  rendering modes/variants/weights, the native component catalog (toolbar regions · sidebar ≤ 2 levels ·
  `Table` vs `List` · button roles · menu‑bar parity), the window active‑state model, a SwiftUI
  reverse‑engineering protocol, and a **shared‑screenshot HIG‑audit** pass. Grounded in the live HIG,
  WWDC sessions, and SF Symbols.
- **`constitution-windows.md`** — Microsoft **Fluent 2 / WinUI 3 / Windows App SDK / WPF (.NET)**. The
  Segoe UI Variable type ramp, Mica/Acrylic/Smoke materials + the two‑layer elevation model, the 4‑epx
  grid, Segoe Fluent Icons, the native component catalog (`NavigationView` · `CommandBar` · `DataGrid` ·
  inspector), WinUI 3 vs WPF/.NET deltas, a XAML reverse‑engineering protocol, and a **shared‑screenshot
  Fluent‑audit** pass. Grounded in Microsoft Learn, Fluent 2, and Build sessions (elevation values and
  DWM/backdrop APIs verified against the live docs).

### Changed
- The UI crew now grounds in the matching constitution per `config.platform`: **UX Architect**,
  **UI Visual**, **Platform Design**, **Adversarial Judge**, and **Architrave** load
  `constitution-apple.md` (Apple) or `constitution-windows.md` (Windows) and run its screenshot
  conformance‑audit before reproducing a shared task/screenshot. The `web` / no‑constitution paths are
  unchanged (the constitution is an additive layer on the platform knowledge pack).
- `gates/rubric.md` grades platform conformance against the matching constitution — reinventing a catalog
  component, copying a cross‑platform screenshot's chrome, or shipping the wrong platform's type sizes is
  a **Fail**.
- `knowledge/apple.md` and `knowledge/microsoft.md` each point to their deep constitution.
- The installer/updater (`tools/install.*`, `tools/update.*`) copy `constitution-*.md` into each adopted
  repo's root, and the injected `AGENTS.md` stanza references them (so the Copilot **cloud** agent picks
  them up too).

### Upgrade notes
- In an **already‑adopted repo**, run `tools/update.sh` (or `tools/update.ps1` on Windows) after updating
  the plugin — this copies the constitutions in and refreshes the `AGENTS.md` stanza. A plain
  `copilot plugin update architrave` refreshes the plugin's agents but **not** the per‑repo copied assets,
  so the root‑level constitutions won't appear until you run the updater.

[0.8.13]: https://github.com/dragoshont/architrave/releases/tag/v0.8.13
