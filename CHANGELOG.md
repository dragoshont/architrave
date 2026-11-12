# Changelog

All notable changes to **Architrave** are documented here. This project follows
[Keep a Changelog](https://keepachangelog.com/) and [Semantic Versioning](https://semver.org/).
Releases at or before **v0.8.12** are on the
[GitHub Releases](https://github.com/dragoshont/architrave/releases) page.

## Unreleased

### Changed

- Replace technical-first Service Architect guidance in place with source-backed
  contextual language, rules, invariants and consistency before contracts.
  Align lead, planner, implementer, worker, Judge/rubric and adoption guidance.
  Routine work gains no role, ceremony, state schema or configuration switch.
- Add read-only application audits through that same architecture/review route,
  with source/code/scenario evidence, valid-alternative challenges and explicit
  unknowns. No compliance score or automatic repair.
- Extend existing calibration with blind domain cases and executable Python/
  functional TypeScript counterexamples, correction/resume regressions and
  installed-role parity checks. These are not loaded-host or empirical proof.

The 1.2 candidate is not release-validated; manifest versions remain 1.1.1.
See `docs/domain-release-evidence.md` for replacement mapping and qualification.

## 1.1.1 (2026-11-11)

### Fixed

- Distinguish ordering dependencies from explicitly consumed producer outputs.
  Selection is explicit; consumer attempts freeze the producer attempts actually
  used. Material replacement stales affected proof/readiness transitively and
  blocks new operation admission. Unselected/equivalent outputs, display renames,
  list order and unrelated revisions retain valid work.
- Expose comparable-check conflicts instead of silently counting a selected pass
  as qualification. Applicable failures in the selected environment participate
  even when omitted from the check list. Linked reruns retain prior failures and
  require bound check/environment identity plus distinct result-artifact evidence.
  Actual integration observations and written progress remain separate from
  qualification and acceptance, including when checks failed or are absent.
  Later checks can be explicitly selected without pretending a second external
  integration occurred; original integration/check history is retained.
- Freeze filesystem-aware per-parent ownership case policy. Known-sensitive
  components stay distinct; case aliases and unknown parents are conservative.
  New mutable scopes reject links/reparse points before directory reads, while
  literal display paths and old assignment history are preserved.

### Compatibility and qualification

- Optional v1 fields do not rewrite old state, receipts or evidence on load.
  Missing consumed/check bindings remain unavailable; old readers reject new
  fields rather than silently accepting them. A deliberate downgrade requires
  closed-owner recovery, not deleting canonical state.
- Added real API/CLI/board and operation-bridge regressions, with negative
  controls for unselected/equivalent outputs, unrelated evidence and native
  case-insensitive lookup. Pure policy tests are not native Windows/Linux proof.
  Neither the collision policy nor reported evidence identities are a sandbox
  or authenticated execution guarantee. See `docs/lifecycle-evidence.md`.

## 1.1.0 (2026-11-11)

### Added

- **Durable lifecycle state.** A bounded, restricted YAML 1.2 snapshot behind
  `architrave_cli.py state` holds stable goals/tasks, original source references,
  scoped corrections/decisions, ownership/attempts, evidence and idempotent
  receipts. Locked revision checks and one atomic replacement prevent competing
  updates and mismatched state/receipt commits. Explicit migration preserves task
  originals and conflicts; `tasks.md` is not a second writable authority.
- **Rich work board bundled with Architrave.** Scoped progress, task map/list,
  task/evidence inspector, shared dark/light theme, source-backed session
  waterfall, separate evidence categories and controlled refresh are shipped
  through the existing installer. Standalone HTML embeds its assets and data;
  no frontend build, CDN, extra plugin or render-time model call is required.
- **Private observation and advisory YAML.** Bounded explicit-session collection
  persists allowlisted facts before display. Missing metrics remain unknown,
  recorded windows disclose coverage, and reported context capacity is never
  reconstructed from prompt size. Optional host-authored AI interpretation has
  validated references, scoped input fingerprints and no lifecycle or permission
  authority; stale interpretation is distinct from current recommendations.
- **Operation-safety continuity.** Explicitly selected legacy Runs retain policy,
  checkpoints, receipts and reconciliation without competing task dispatch.
  New lifecycle-operation capsules reuse those controls with exact target/action
  binding and default deny; retained receipts can be consumed after lost replies
  without reapplying effects.

### Fixed

- Preserve original mutable assignment paths across later task corrections.
  Unknown ownership stays held; stop request, acknowledgement and observed
  terminal execution remain separate.
- Bind candidate checks to reported attempt, candidate/source/base/check-input
  identities, including intended and observed integration. Keep incompatible
  late results inspectable rather than integrating or deleting them.
- Re-evaluate materially stale written readiness while preserving unaffected
  work. Read-only review activity no longer changes implementation progress.
- Retain relevant active/retired/prior-scope constraint and decision correction
  history, with before/after meaning and source references.
- Prevent cross-scope AI content from entering an exported board, even as
  collapsed history. Keep every explicitly selected observation source in
  coverage counts, including sources an older cache has not collected.
- Serialize observation capture/merge/write, preserve fractional source times
  and read exactly the captured file extent. Duplicate delivery, overlapping
  collectors and source replacement do not silently inflate or rewind counters.
- Use the configured macOS host name instead of a network-resolved node label.
  Explicit handoff can record terminal read-only observations, but cannot release
  mutable/unknown scope or uncertain effects. Missing host identity fails explicitly.
- Use a physical temporary directory in legibility fixtures on macOS, where
  `/var` may be a symlink. The exact-target observer's link rejection is unchanged.

### Design decisions and deferred ideas

- YAML carries project facts; formatting and optional AI commentary do not
  invent progress, acceptance, cost, activity or permissions. Code ready,
  current input binding, source review, installation and runtime proof are
  different facts, not one completion percentage or green PASS.
- Keep the viewer modular inside Architrave first. Separate distribution,
  schema adapters and additional native harness embeddings remain future work.
  MCP Apps is a candidate interoperability path, not a promise that every MCP
  client renders widgets or can access local files. Skills guide invocation;
  they do not supply UI capabilities or filesystem grants.
- Preserve host-owned execution, model selection, permissions and lifecycle.
  No new scheduler, universal interception, vector service, default REQ/SPEC
  barrier or automatic approval ceremony is introduced.

### Qualification boundaries

- The complete manifest suite passes on macOS with Python 3.12 and Node 22,
  including AJV, generated-role, runtime and installer checks. Earlier legibility
  failures remain documented with their physical-temp-path fixture correction.
- Real store/CLI/installer and desktop/320px Chromium checks exercise the bundled
  path. Two independent source reviews closed concrete findings after integrated
  repairs. Simulated events and fault injection are evaluation data, not live
  provider execution or measured productivity improvement.
- Installing a package does not refresh already-running sessions. Native Windows,
  additional host embeddings, full-history/context availability and real external
  interruption/lost-reply behavior require their own observations.

## 1.0.6 (2026-11-11)

**Public Windows candidate / prerelease.** Instruction-only clarifications for
the delivery gaps observed after the code-ready pass and final review.

- **Code ready includes in-scope wiring.** An unimplemented adapter or
  unconnected required consumer is unfinished code, not just a runtime
  qualification hold. Missing credentials or an unavailable service do not
  prevent otherwise written source from being Code ready. Explicitly optional
  or owner-deferred integrations stay outside the task.
- **Close review findings on the integrated candidate.** Recheck accepted fixes
  and refresh affected producer/consumer paths if later integration or relevant
  dependencies change them. Reuse unchanged evidence rather than adding a full
  review after every task or harmless merge. Worker claims, tests and matching
  file hashes do not substitute for the reviewer's actual result.
- **Bind publication to the feature, not the coordinator or dependency PR.**
  Carry the actual repository, branch, commit/tree, target and feature paths in
  the existing handoff, then read back the live PR identity and diff.
  Separate code written, review/open findings, publication and observed runtime;
  non-draft or mechanically mergeable does not mean safe to merge.
- Keep the working code-ready-first, final-review-at-the-end loop. No runtime
  code, hooks, task statuses, approval stages, mandatory forms or completion
  barriers are added. Normal host permissions and scoped owner stops remain.
- Wording/contract checks and source review verify the instruction changes,
  not future agent compliance or improved productivity. Broader runtime
  qualification limits from 1.0.5 remain; this is not a full-suite or
  cross-platform acceptance claim.

## 1.0.5 (2026-11-09)

**Public Windows candidate / prerelease.** This patch addresses observed agent
delivery and hook failures; it is not a new execution harness or a guarantee of
unattended completion.

### Fixed

- **Completed work could not close after its analysis was moved.** The obsolete
  SPEC/REQ `task_complete` barrier still required the old requirements file.
  Remove that hook registration and make retained `pre-tool-use` commands inert.
  They no longer read or rewrite old declarations or demand that SPEC.md be
  recreated. Historical evidence and normal host permissions are preserved.
- **The board showed the wrong task source or understated unfinished work.**
  Use tasks.md by default, even when a historical SPEC.md exists, with blank,
  In progress and Code ready statuses. Pin that source through refresh and
  shutdown: a missing task file must not silently switch the board to old REQs.
  Parse optional table pipes without dropping rows; reject malformed tables and
  unsupported statuses before replacing the last valid snapshot.
- **A worker appeared stuck while ownership and checks were unresolved.** A
  real-session audit found legitimate write holds, actual implementation and
  debugging, but also standalone shell sleeps and poor phase visibility.
  Add bounded advice for supported standalone sleeps and distinguish prepared,
  ownership-held, implementation, checking and handback phases. Include the
  reminder in implementation kickoffs; normally send only two coalesced parent
  updates and keep full logs local. Do not replace real progress with status,
  force edits under a write hold, or treat legitimate testing as a stall.
- **Instructions could resurrect the retired SPEC workflow.** Align the lead,
  worker skill, startup pointer, installed stanza and plugin descriptions with
  tasks.md. Preserve original owner requests and corrections without new REQ,
  declaration or approval prerequisites. Legacy Run/requirements commands
  remain explicit opt-in tools.

### Preserved boundaries

- Automatic unchanged-read/search detection from 1.0.4 remains enabled for
  Copilot. Read-loop and standalone-wait messages are local, bounded advisories:
  no tool denial, result rewriting, forced continuation, permission grant or
  false completion. Real backoff, readiness checks, ownership and owner stops
  remain valid.
- Codex/ChatGPT receive the same task and worker guidance through the shared
  release package, not an equivalent Copilot hook runtime. Installing an update
  does not prove that an existing desktop session has reloaded.

### Evidence and remaining harness limits

- Two independent adversarial source reviews passed after the board defects
  were corrected. The affected completion retry was accepted through the host.
  Published source: `b078695105baf061bc614a0dd72c9d3269a12067`.
- Focused Windows checks cover 22 hook checks, 16 board checks (one optional
  browser case skipped), 45 explicit legacy delivery checks and 11 quality-cadence
  checks (three absent-workflow cases skipped), plus instruction contracts.
  Copilot and Codex installation payloads were verified against the public build.
- The full manifest run reported a failure in the unchanged native dispatch
  fixture "one hung batch packet does not hold the other past the deadline".
  Its isolated rerun passed 151 assertions, but the broad run was stopped
  incomplete. This is not a full-suite PASS or cross-platform qualification.
- The detector does not establish semantic lack of progress, interrupt
  model-only reasoning, or guarantee overnight delivery. Copilot session-host
  cancellations and event-acknowledgment timeouts remain host failures, not
  repaired or proven caused by this plugin. Stale plugin-path failures still
  require safe retained paths and verified session reloads, not cache deletion.

## 1.0.4 (2026-11-09)

- Add automatic Copilot `postToolUse` repetition detection: four identical
  read/search results in a bounded 24-observation window inject a corrective
  nudge. A private per-session fingerprint cache survives resume, serializes
  parallel hook calls and suppresses duplicate reminders. Changed results reset
  their request's count; errors report monitoring unavailable without denying
  tools. No forced edits, result rewriting, stop overrides or approval stages.
- Strengthen instruction guidance for grounded prerequisites, direct answers,
  owner stops, and recovery from repeated investigation without meaningful
  progress. File touches alone are not progress; necessary research remains
  valid. Instruction guidance complements the advisory repetition detector;
  neither guarantees model recovery.
- Respect the owner's chosen Autopilot mode for unattended work. Scope past
  errors and pauses to the operations they affect, and reuse existing grants
  rather than inventing new approval requirements.
- Clarify the original reviewer's source-readiness coverage for REQ-60 and
  REQ-63; the historical review clarification is not runtime proof.
- Aim the next authorized action and YAGNI guidance at the full requested
  outcome, including required wiring and safeguards, rather than a partial
  subset or speculative scope.
- Distinguish inherited branch changes from the current session's work, and
  report actual model routing only when the host exposes it.
- Document the default-agent skill and custom-agent entry points without
  assuming that a host goal command invokes the skill automatically.
- Keep the version bump tool's progress output compatible with Windows
  consoles using legacy encodings.
- Document the observed stale plugin-path completion-hook failure
  (`os error 267` on Windows). Updating the package cannot repair a running
  session's reference to a removed directory: retain the path until reload,
  or restore the exact old package with authorization. This is a migration
  workaround, not a fix for the host's plugin-path lifecycle.

## 1.0.2

- Preserve native execution budgets through Python bookkeeping, retain
  unresolved host ownership across failure and cancellation paths, and bound
  bridge preparation, observation, recovery and semantic-review admission.
- Scope native dispatch identities to the canonical repository, Run and task;
  reject malformed parallelism and missing cleanup capabilities before dispatch.
- Keep retry artifacts immutable and conservatively reject overlapping mutable
  glob scopes.
- Require task-bound policy grants and exact-target preflight for iOS install
  and launch recipes. Installation remains uncertain until independent
  reconciliation proves the installed identity.
- Revalidate managed installer and recovery paths, preserve owner content around
  malformed managed stanzas, and adopt the canonical supporting documents.
- Bind delivery preparation to its intake source. Seal changed source before
  collecting fresh delivery observations; legacy reports without an intake
  snapshot also require fresh observations.
- Reject leading-zero core version components in the release tool.
- Decode Windows regression fixtures as UTF-8, satisfy the SDK's preflight
  contract, and distinguish absent CI workflows from failed configured checks.
- Retain the full plugin, including Python and hooks. Source archives and
  synthetic regressions do not establish live-host or cross-platform qualification.

## 1.0.1

- Restore the full Copilot plugin from v1.0.0 after the instructions-only
  reduction: Python gates and harness, session-start and completion hooks,
  agents, skills, extensions, and the repository installer.
- Synchronize the Copilot, Claude and Codex plugin manifests at 1.0.1.
- Retain the qualification limits documented for v1.0.0. Packaging and local
  installation do not establish new cross-platform or live-host guarantees.

## 1.0.0

- Bind candidate integration to actual workspace/destination source, preserve
  the worker index, retain immutable patches and make repeated integration
  idempotent. Shared dispatch checks revalidate budget and ownership inside
  the task-start transaction (REQ-103/105).
- Persist native attempt ownership before dispatch and bind uniquely recovered
  owners before cleanup. Unknown owners retain capacity across restart;
  cancellation, removal and result persistence remain separate (REQ-97/104).
- Consume observed native option comparisons in the existing bounded
  feasibility decision, without imported verdicts or renewed retry allowances
  (REQ-106).
- Add exact original-owner-event approval for lesson application and rollback,
  retaining source/target/content provenance in the existing learning register.
  Missing approval remains proposal-only; no real lesson has been applied as
  part of this implementation (REQ-107).
- Use Not started, Started and Code ready for task progress in the current
  requirements and program board. Code readiness does not require an
  individual review; review the complete feature set at the end. Final
  evidence checks remain separate, and historical records stay readable
  (REQ-105, C-101).
- Write gate CLI stdout/stderr as UTF-8 so redirected native Windows output
  can include actual requirement text without crashing on an ANSI codepage
  (REQ-99).

## 1.0.0-beta.1

Prerelease preparation for the completion-path repairs. Make the path from an owner outcome
to verified delivery more reliable on native Windows and macOS (WSL2 is not a
target). Releases 0.21.33 to 0.21.35 (completion-hook repairs, REQ-91 to
REQ-94) are recorded in the [roadmap](ROADMAP.md) and on GitHub Releases.

- Apply the configured autonomy scope, allow list and confirmation list in Runs
  created by `harness/architrave_runtime.py`, its `create` alias and
  `architrave_cli.py runtime`, as `RunStore.create` does. Each explicit flag
  overrides only its own field. `migrate-v1` keeps its deliberate advisory-only
  scope and takes only the configured allow and confirmation lists (REQ-95).
- Add `execution`, `holds` and one `nextAction` to Run status, derived only from
  canonical state as a conservative, best-effort mirror of `task-start`, which
  stays authoritative. Lease-backed task records are reported apart from host
  execution, which the Run cannot observe, and owner holds never suppress other
  authorized work (REQ-96).
- Bound native dispatch stages: one shared fixed 30 s preflight
  bound, then the lease expiry with a reserved cleanup budget. Failures are
  stage-labelled; `hostCancellationConfirmed` is true only when the host
  confirmed the cancel (removal is reported separately in `cleanup.confirmed`);
  an unresolved owner keeps its recovery identity and blocks retries; and
  `architrave_native_cancel` adopts a late or persisted candidate instead of
  redispatching. Real abort signals are honored, uncertain admissions keep
  capacity, and an empty listing cannot release ownership. Run resume and native
  recovery refuse unconfirmed host ownership. Concurrent cancellation requests
  join one reconciliation instead of racing over the owner and bridge pipe.
  Overlapping dispatches recheck same-task ownership after host preflight;
  cleanup removes only the reservation belonging to that invocation.
  Restart-safe automatic recovery, genuine persistence-hang/lost-reply coverage
  and real-host hang qualification remain unproven (REQ-97, REQ-104).
- Guide the lead to name the transport, integrate children in deliberate waves,
  read `nextAction` or reconcile the lane table after every child return, and
  carry the verbatim owner quote, REQ ids and an honest-conflict exit in each
  sub-session handoff. Guidance only: no new schema, role or ledger (REQ-98).
- Repair repository verification guidance and the native Windows
  `gate_runner.py checks` recipe, and state in the delivery-authenticity guide
  that pause evidence must be an immutable saved copy (REQ-99).
- Accept and synchronize the semver prerelease in `scripts/bump_version.py`
  (REQ-100). The automatic release workflow remains disabled.
- Add a self-contained, accessible use-case map (`assets/use-cases.svg`) to the
  README (REQ-101).
- Remove proven overhead: drop the unused `write_redacted` helper and the
  unconsumed `harness/schemas/improvement.schema.json`; stop writing unread
  learning-promotion keys in the installer template and examples; mark
  `workers.cleanupCompletedWorktrees`, `runtime.boot/stop/reset/logs` and the
  `learning` promotion/stale keys deprecated and ignored, and have `checks`
  warn when a config still sets them (non-failing). Fix nonexistent
  `check-manifests.sh` and `promote-lesson*.{sh,ps1}` references, the stale
  2–8 batch range (2–20 within `workers.maxParallel`) and the README CI claim
  (REQ-102).
- Bind independent review to the reviewed task, scope and report instead of
  the latest reviewer verdict in the session (REQ-103, REQ-105).
- Narrow option comparisons to genuinely differing material options or a
  discriminating recovery. `tournament-review --result` can require a matching
  `--task`/`--source` and checks two to four distinct summarized options.
  A proposed standalone allowance ledger was removed: `--allowance` refuses
  without writing files. Budget and failure identity stay with the owning task;
  authenticated result admission and automatic successor-lineage accounting
  remain unqualified (REQ-106).
- Keep procedural learning proposal-first: `semantic-learning-review
  --execute` and the other `--execute` launchers exit 2 with
  `NATIVE_HOST_REQUIRED` instead of shelling out to an agent CLI.
  Lesson helpers preserve candidate provenance and content/source-bound proposal
  digests. `promote-lesson --apply` and the picker always refuse with
  `AUTHENTICATED_APPROVAL_REQUIRED`: a caller-supplied digest and `--by` cannot
  authenticate owner approval. Authorized application remains a reviewed source
  edit, not an automatic learning side effect (REQ-107).

Limits: no live multi-wave qualification or sustained parallel delivery;
macOS command-level checks do not prove a loaded app; native-bridge hang behavior
is fixture-tested only and its recovery
identity lives in the bridge process; host loading of a prerelease version and
loaded-context refresh are unobserved; the durable Run key owner and ACL are not
verified on Windows. Audit findings F6, F8, F9 and F10 are tracked as issues
(#77, #75, #61, #76); every unaddressed item is an issue (#40 to #87) and the
handover for continuing on another machine is #39. This is not 1.0 final.

## 0.21.32

- Render claimed/queued requirements with the existing gray Open square;
  reserve blue for explicit in-progress work, not the entire assigned scope.
- Ground specifications in original owner outcomes and observable behavior,
  distinguishing prerequisites and supporting tasks from delivered features.
  Apply the same contract through lead/adoption guidance and independent review.
- Bound milestone-free canonical continuation through the existing finite
  feasibility window, sharing spend across criterion-related task/lane renames
  and preserving primary epochs across same-objective redeclarations.
- Keep genuine coordinator successor handoffs valid; do not infer inverted
  ownership merely from sidebar ancestry. Preserve holds and independent work.
- Rehydrate selected full requirements/corrections and existing Handoff after
  Copilot compaction, with just-in-time source retrieval and no second ledger,
  custom compactor, forced reset or automatic user-work commit.
- Report observed compaction outcomes and summarizer usage separately from
  ordinary session calls, retaining legacy packet coverage and explicit
  missingness/request overlap.
- Clarify documented Copilot app commands versus exposed agent capability and
  canonical admission versus unguarded direct-host tools. Do not claim universal
  enforcement, model-specific causation or measured productivity gains.

## 0.21.31

- Add explicit local Copilot session and individual-turn audit collection,
  without requiring repository adoption or a canonical Architrave Run.
- Separate observed token/consumption/context metrics from owner-goal and
  approach judgments. Report native command exits separately from host
  tool success so hidden command failures remain inspectable.
- Use the existing host reviewer for source-bound prompt, instruction,
  approach and prerequisite improvements, with concrete verification and
  tradeoffs. Reconstruct audited log prefixes before accepting analysis.
- Display advisory goal outcomes, findings and retained practices on the
  existing scoped program board, with missing/stale analysis explicit.
- Document the `architrave-review` and internal CLI path, its research basis,
  local privacy boundaries and limits on productivity claims.

No automatic instruction changes, permission expansion, new every-turn hook
or additional completion gate is introduced. Local installation does not
reset running sessions or refresh their already-loaded context.

## 0.21.30

- Bind new delivery declarations to explicit owned sources and relevant
  dependencies; selected-session completion no longer inherits unrelated
  requirements and shared-checkout work. Legacy unscoped checks keep their
  documented repository-wide behavior.
- Preserve unaffected outcome evidence across owner-bound amendments while
  invalidating changed contracts or dependency evidence.
- Support truthful blocked, waiting and handoff termination without accepting
  unfinished delivery, and keep historical completed declarations from forcing
  read-only follow-ups to repair old work.
- Clarify that automated reminders and unavailable-user fallbacks are not owner
  approval, proposals stay inactive until agreed, and generic test permission
  does not authorize new test substitutes. Prioritize a real vertical slice
  before reusable support machinery.

These are scoped closure and decision controls, not automatic understanding of
owner intent or proof that a dependency list is complete. Updating installed
files does not refresh already-loaded sessions; this release does not restart
running sessions.

## 0.21.29

- Make board snapshot generation time, refresh interval and selected requirement
  scope visible. Static or stopped watcher snapshots explain their freshness
  limits; delegated refresh preserves the existing output and coordinator history.
- Keep repository-wide ledger evidence diagnostics visible and actionable without
  presenting missing finding evidence as application failure or waiving checks.
- Accept genuine screenshot-bearing owner requests with their image identity
  while retaining rejection of agent, system and forwarded-message attribution.

The repair does not resolve underlying ledger findings or prove that existing
sessions loaded updated instructions. Update the plugin and safely regenerate
existing boards; loaded-session adoption remains a separate verification.

## 0.21.28

- Scope native correction context to exact requirements, including explicit
  correction-only chains. Retain global rules and unresolved legacy safety
  context without turning historical grants into current authority.
- Require explicit native Run selection and reject managed cross-run scratch
  context and artifact paths, honoring the configured workspace root. Same-run
  resume retains evidence with existing digest/source/authority checks.
- Check selected source citations against HEAD, index and actual worktree
  content, including deleted, staged and assume-unchanged paths, without
  invalidating unrelated edits.
- Reuse optional source-cited project maps and existing learning tools to
  distinguish current accepted architecture from unresolved historical references.
  No mandatory output folder, config or direct-task worktree is introduced.

These are source/control-plane safeguards, not a filesystem sandbox or automatic
semantic history classifier. Update the plugin and restart sessions to load new
guidance; already-loaded hosts are not retroactively updated.

## 0.21.27

- Bind declared delivery acceptance to original owner references, source/config
  identities, candidate dispositions and fresh integration or rendered evidence.
  Approved official emulators and environment selection remain valid.
- Load an 88-word default-session bootstrap and require a scoped program board
  before non-trivial implementation, with an explicit unavailable-board outcome.
  The lead agent shrinks from 1,068 to 1,041 words; no model pin is introduced.
- Add narrow Copilot sessionStart and task_complete hooks, without automatic
  PostToolUse builds or agentStop loops. Owner-bound amendments and withdrawal
  preserve scope history; changed work cannot reuse stale completion evidence.
- Preserve visual/reference intent and extend acceptance-decision cases without
  claiming improved model performance. Retained blind calibration is 18/20.
- Align recipe formatting with the selected shell and correct Windows-specific
  validation expectations without changing executor selection or safety policy.

Non-trivial task detection remains instruction-led. Local evidence is writable,
host hook timeouts can fail open, and source tests do not establish live product
behavior. See [delivery authenticity](docs/delivery-authenticity.md) for limits.
Update the plugin and start a fresh session to load the new defaults; existing
loaded sessions and native hosts are not retroactively certified.

## 0.21.26

- Session boards require explicit REQ selection (`--reqs`), or an intentional
  repository-wide history view (`--all-reqs`). Startup reminders use lane REQs;
  invalid scope fails before watcher registration or output replacement.
- Preserve the tile dashboard, full legend and compact waterfall while removing
  explanatory header prose. Short titles and deduplicated repository names
  replace worktree labels; technical metadata stays under Board details.
- Show context k-tokens inside an outline ring, concentric In/Out rings and a
  separate Cache ring, plus reported model-bound reasoning effort and recorded
  assistant-turn counts. Unknown effort is not inferred.
- Distinguish artifact identity, declared review binding, semantic acceptance,
  generated snapshots, consumer observations and cumulative session history.
  Print preserves exact values, full names and all errors.
- Extend source/actor-provenance calibration without claiming model-performance
  improvement. Background-command/REQ linking remains unimplemented.

Updating a checkout does not update an installed plugin. Update the plugin and
start a fresh session; restart/regenerate existing boards with explicit REQ
scope. Historical requirements remain in their repository ledger.

## 0.21.25

- Evidence-first analysis guidance for source authority, passage entailment,
  settled owner intent, correction propagation, constrained forecasts, usable
  handoffs and revision assets, loaded through existing lead/research/review seams.
- Twelve synthetic decision/artifact cases extend existing semantic calibration;
  retained failures and rationale contamination remain explicit limitations,
  not proof of improved productivity or eliminated reasoning errors.
- Semantic scoring now fails missing/mismatched results and missed unverified
  responsibilities instead of printing uncertainty misses while returning success.
- Benchmark question counts are explicitly lexical. `question_mentions` and
  basis/unknown-necessity fields supplement the unchanged legacy
  `unnecessary_questions` integer; unattended defaults remain unchanged.

## 0.21.24

- `requirements --done` fails on a done lane without a session ID and, where
  local session logs exist, on a done lane whose session is not logged on this
  machine (run `--done` where the lanes ran). Hidden subagents have no session
  UUID, so a lane is a visible session or the coordinator's own direct work;
  the gate cannot see hidden subagents a named session used internally.
- The program-board watcher registers itself in the coordinator session's
  `files/program-board.watch`. `requirements` notes, with the full start
  command, when the coordinator of running lanes (a session in no lane row whose
  log created or messaged them) has no live board for that ledger; live means
  the pid exists and the output is fresh. Lanes, reviewers and other sessions
  are not reminded; never a failure.
- `program_board.py --session` must be a session UUID; the pointer write is
  covered by the watcher's cleanup.
- Watcher liveness uses one helper that never signals on Windows (signal 0 is
  CTRL_C_EVENT there) and counts a live process of another user as running.

## 0.21.23

- Review notes can name the reviewer session: `review: <session-uuid> <verdict>`
  (digit-first UUIDs included) is checked against
  `session-state/<uuid>/events.jsonl` — exact directory, kickoff agent selected
  before the first turn must be a reviewer role (exact name), and the ruling of
  the session's last report (task_complete summary or message to another
  session) must match. A ruling is the first labelled line (`Verdict: X`), else the first line
  opening with an upper-case verdict; quoted, backticked, `>` and table text
  and mid-sentence verdict words never count. Earlier
  notes naming the same session need only match one of its reports; use a fresh
  reviewer session per delivery. A contradiction fails `requirements`.
- Where local session logs exist, `requirements --done` and the board's
  "review missing" count only verified PASS notes; role names and sessions from
  other machines no longer close a lane. Elsewhere notes stay unverified and
  accepted. This catches mistakes, not deliberate forgery.
- `review.crossFamily` is enforced at `--done` where logs exist: the lane's and
  reviewer's sessions must share no model family across every model they used
  (`auto` or an unlogged model is unverifiable).
- One cap rule: `workers.maxParallel` clamps to 20 in gate, board and Run
  runtime; zero, negative or non-integer values fail the gate and fall back to
  three at runtime.
- Board: overview counts lanes missing a review (matches `--done`); session
  facts are cached by log size and mtime and evidence lookups cache only hits,
  so `--watch` sees new verdicts; a log truncated and regrown in place is
  re-read (first-bytes fingerprint); docs say current context, not peak.

## 0.21.22

- A lane is `done` only after one independent review of its delivery, recorded
  on each of its REQs; `requirements --done` fails on a done lane without a PASS,
  and the board marks such lanes "review missing".
- Every lane and every independent review MUST run as a visible sidebar
  session when the host offers one; hidden subagents only for short read-only
  lookups outside any lane. A running lane without a host session ID already
  fails the `requirements` gate.
- Active-lane cap raised: `workers.maxParallel` default 3, owner-approved up to
  20 (schema, Run runtime, native dispatch and batch; the lane gate clamps to 20).
- Review gaps use one shared rule on the board and in `requirements --done`:
  a done lane needs a PASS review on every open REQ and any lane needs one on
  every accepted REQ (withdrawn/superseded skipped; Findings verifiers no
  longer count as reviews). Notes attach to REQs, so one PASS covers every lane
  listing that REQ.
- Program board: squares of a done lane that are not yet accepted show green
  hatching ("delivered, awaiting acceptance") instead of claimed blue.
- Program board: logs are read incrementally (only new bytes per refresh;
  a shrunk or replaced file is re-read);
  context flags are judged against each session's first prompt (recorded even
  when events are clipped) and the remaining room, so fresh small-window
  sessions are never flagged and large-baseline sessions can still reach the
  hard flag; `rotate.json` keeps the first-flagged time; the coordinator re-checks a flagged
  child with `get_session` and tells the owner if no boundary comes within an
  hour.

## 0.21.21

- Context rotation reworked after an independent killer review and online
  research (REQ-43): rotate at task boundaries; the board's backstop uses
  current context (info at ≥30%/300k, "rotate at next task boundary" at ≥45%),
  not peak; compaction is no longer a trigger; the claim moves before the
  successor starts. The coordinator can rotate itself with a detached
  `architrave:architrave` successor (verified live), only between waves.
- Review marks hardened: the gate parses every `review:` note, requires the
  latest to be PASS for accepted REQs and rejects owner-named reviewers; the
  board counts a REQ reviewed only on a PASS note (free-text heuristic
  removed); the session ✓ is grey and means a reviewer ran, not its verdict.
- Board: atomic pid lock with safe stale recovery; unchanged logs cached.

## 0.21.20

- Context rotation: the program board flags sessions "rotate soon" (peak
  context ≥30% of limit or ≥300k) and "rotate now" (≥45% or two compactions),
  with a gold ↻ and a `<board>.rotate.json` list. The execution policy gives
  the rotation steps: Handoff and push, worktree successor from that SHA with
  `--expect`, claim move, archive after. Mechanical trigger; the judge only
  checks Handoff quality for mid-REQ rotations. Based on a feasibility study of
  the live Ode sessions.

## 0.21.19

- Program board: a session whose last action was the host's "Task completed"
  (no model turn after it) shows a green bar and "task completed", even before
  its lane row is updated; a later turn makes it active again.

## 0.21.18

- Review marks on the program board: session rows show ✓ when the session ran
  a reviewer (○ when none); REQ squares get a white corner when independently
  reviewed; lanes show "reviewed k/n" and a gold border when accepted work has
  no recorded review; the overview counts accepted but unreviewed REQs.
- Ledger rule: record each independent review in the REQ's Evidence as
  `review: <reviewer> <PASS|REVISE|FAIL>`; the `requirements` gate checks the
  format and refuses acceptance on a REVISE/FAIL without a later PASS.

## 0.21.17

- Program board hardening (independent review REVISE fixed): REQs in no lane
  get a "Not in a lane" rectangle so rings match the overview; evidence commits
  match inside joined text and results are cached; malformed log lines are
  skipped and a failed refresh keeps the last good board; one watcher per
  output (pid lock) that exits when no sessions are found; child sessions from
  all session-creating tools are followed recursively; the session count
  matches the timeline; "program min" is the program's span. README shows the
  board.

## 0.21.16

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

## 0.21.15

- Delegated work defaults to visible child sessions (Copilot app sidebar via
  `create_session`) without the owner asking; hidden native subagents only for
  short read-only lookups or reviews, or when visible sessions are unavailable.

## 0.21.14

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

## 0.21.13

- Semantic-preservation calibration suite (REQ-39): `benchmarks/semantic-cases.json`
  (10 cases with listed responsibilities, 4 hard cases where the judge must find
  the requirement sentences) and `scripts/score-semantic-cases.py`, scored by id.
  First run: the 0.21.12 judge and the 0.21.11 baseline both scored 10/10 on the
  easy cases; on the hard cases 7/7 vs 6/7, one run each. Not a demonstrated
  improvement.
- Live parallel lanes (REQ-30): two child sessions in different repositories
  delivered in parallel. Start children with kickoff mode `interactive` so
  permission prompts reach the owner.

## 0.21.12

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

## 0.21.11

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
