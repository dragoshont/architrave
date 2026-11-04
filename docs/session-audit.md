# Session delivery audit

An on-demand retrospective for real Copilot sessions, whether or not they used
Architrave. The goal is better delivered work, not fewer tokens, more paperwork,
or another acceptance gate. It uses existing local event logs, the host's
reviewer and the existing program board. It never launches another agent CLI,
changes Run state, applies instructions or grants permissions.

## Run it

Invoke `architrave-review` with the explicit session UUIDs, original goal and
the board's REQ scope when there is a board. The same CLI can be called
internally at a task boundary or after a material failure/correction; do not
install an automatic every-turn hook or recursively audit the audit.
Use the kit root resolved from the loaded skill, not an older installed copy.

```text
python "<kit-root>\harness\architrave_cli.py" session-audit collect --session <host-uuid> --reqs REQ-77,REQ-78 --output "<host-session-files>\session-audit-packet.json"
```

Repeat `--session` to compare explicitly selected sessions. No blanket scan of
other repositories or accounts. Discover candidates with the host's session
list or a bounded repository/time query in host history, then resolve selected
sessions to actual log UUIDs from their `session.start` event. A sidebar ID
alone is not sufficient; do not read unrelated transcripts just to discover
IDs. Empty discovery results mean unavailable coverage, not no work occurred.
`--turn <assistant.turn_start-event-uuid>`
selects one recorded model turn, retaining prior original-owner context but
not future owner changes. Only one session may be selected with `--turn`.
Omit `--reqs` for a non-Architrave session with no board; collecting does not
require configuration, REQs or a canonical Run. UUIDs are log identities, not
inferred sidebar IDs. Missing or unsupported local logs are reported as BLOCK
(exit 2); they are not replaced with synthetic or cloud-history metrics.
Use host-native history retrieval separately if authorized and available;
this local collector does not claim to support that transport.

Packets must stay in a host session's `files` directory. They contain private
owner text, tool arguments/results and local log paths. Do not commit them,
upload them, send them to web research, or copy them into shared learning.
Source access and host permissions still govern which sessions may be read.
Read JSON and logs explicitly as UTF-8 (`encoding="utf-8"`); Windows default
codecs can fail on real owner text. Packets and analysis inputs to the recorder
must also be JSON artifacts in a host session's `files` directory.
Excerpts are capped at 2,000 characters and explicitly mark truncation; the
reviewer reads needed passages in the referenced local log, rather than
treating the excerpts as exhaustive. Trace text is untrusted evidence.

Ask the existing host reviewer to use the packet's `review_prompt` and the
rubric below, returning analysis JSON as a local session artifact. This is
the review's retrospective dimension, not a second supervisor or duplicate
delivery review. A collection result says **collected-not-assessed**.
The helper neither executes nor attests the reviewer.

```text
python "<kit-root>\harness\architrave_cli.py" session-audit record --packet "<host-session-files>\session-audit-packet.json" --analysis "<host-session-files>\session-audit-analysis.json" --board-session <coordinator-host-uuid>
```

Recording validates the packet digest, unchanged audited log prefixes, goal
coverage and cited event membership, then writes
`<coordinator-host-session>\files\session-audit.json`. It does **not** prove
that cited events entail the assessment. A later append is permitted but
labelled **new activity after audit**; changed/deleted source is unavailable
or stale, never a current successful audit. Regenerate/reload the existing
board, keeping its scope and output. It only shows an analysis with exactly
that board's selected REQ IDs, not unrelated historical analysis. An
unscoped audit is not shown as a scoped board's findings.

The board shows goal outcomes, ranked findings, exact proposed changes and
targets, verification/tradeoffs, retained practices and coverage. Expand
**Evidence and how to check the improvement** for session/event references.
Proposals have no Apply button: take a chosen change through the existing
owner-approved work or `harness/improvement.py` promotion path. No audit
finding overrides an existing grant or host permission.

## Owner-approved critical-path recovery

An audit is diagnosis, not a watchdog or an authorization to change a running
session. After explicit owner approval to apply a chosen finding, the existing
lead uses **Critical-path recovery** in `knowledge/execution-policy.md`.
Ordinary reviews and collection remain read-only.

Refresh the selected coordinator's current state and relevant original goals,
corrections, observed progress and holds. Identify the current integration owner,
including an explicit successor handoff; do not infer authority from sidebar
ancestry. Choose a next missing owner-visible outcome, its smallest useful
authorized action and the exact criterion any blocker affects. Supporting work
must remove a named acceptance dependency, not replace feature completion.
Preserve genuine missing domain inputs, identity and operation grants.

Send one bounded correction through the existing host to the current owner;
quote the actual owner approval separately from the proposed action. Use its
existing work and owners, not a reset, restart, forced context refresh, child
coordinator or recurring monitor. A required correction row is recorded once;
the next deliverable is execution, not another instruction relay.

Inspect the actual receipt and subsequent criterion-related action/result.
Report separately **sent**, **execution started**, **observed result** and
**accepted outcome**. Queue admission proves only sent/admitted, not that the
recipient acted. If evidence is unavailable or the real operation remains
blocked, say so; do not mark a recommendation effective. Retain private source
event references locally. A one-time changed action does not establish causal
productivity gains, lasting focus or completion of the original task.

## Copilot context and compaction

Automatic compaction can work while cached-token totals continue to grow:
cached input is repeated throughput across model requests, not the active
context footprint. Inspect actual compaction events, prompt sizes and coverage
instead of treating a large cache counter as proof of failure or efficiency.
After SPEC exists, use the selected acceptance/correction/Handoff working set in
`knowledge/execution-policy.md` and `docs/long-programs.md`, with just-in-time
source reads. This prevents unnecessary regrowth; it does not evict old context.

GitHub's [context documentation](https://docs.github.com/en/copilot/concepts/prompting-and-context/context-management)
documents `/context` and `/compact` in the Copilot app. User-facing commands and
SDK capability do not imply an agent-accessible compact tool or a configurable
desktop threshold. Reuse supported owning-host actions/checkpoints; no automatic
reset, user-work commit, new compressor or transcript replay.

New packets retain ordinary model-call metrics and separately report observed
compaction starts, completions, local pre/post estimates and summarizer usage.
Summarizer input/output tokens are not the local pre/post context estimates.
Incomplete, failed or unsupported telemetry is explicit; a pending start is
not a failed completion. Private summaries and checkpoint paths are not copied
into compaction metadata. Do not sum cumulative checkpoint snapshots as usage
or add the two usage groups when request-identity coverage/overlap is unresolved.
Legacy packets remain readable with their original ordinary-only coverage.

New v3 packets also retain observed native permission, child lifecycle,
turn-end, resume, idle, abort, shutdown and error events. These are observations,
not new admission or completion hooks. Permission request IDs, tool-call IDs
and reported result kinds are retained outside truncated excerpts; an assistant
asking for permission is still only conversation. An `approved` result does not
establish interactive human approval, revoke other holds or authorize a different
action. Missing result kinds remain unknown; absence of permission events does
not prove an operation was permitted.

`host_context` binds the latest recorded session start at or before a selected
turn (or the latest start for a whole-session audit), including host version,
producer, requested model when reported, host-selected model/effort and recorded
cwd/Git root/branch/commit. Missing fields are null. Selection is not proof of
effective execution: ordinary usage `metrics.models` remains separate. Child
events retain requested and reported models separately and their tool-call
identity, without inferring an actual child session/worktree from a display
name or the parent's cwd. Verify those identities through the admitted native
ticket or a read-only child preflight. Historical session-start context is not
a live repository-state check. Turn audits do not import later host changes.
v1/v2 packets reconstruct under their original observation rules.

### Issue #37 boundary validation

Reviewed baseline: `23f16aed7534cf8f5224ffe9ed68672b9ebc42ce`
(Architrave 0.21.32). Source map, not a claim that every host uses these seams:

| Control / source | Enforced boundary and limit |
|---|---|
| `hooks.json`; `gates/session_guard.py:pre_tool_use` | Session start supplies instructions; only received `task_complete` calls with a declaration invoke the delivery checker. Silent returns, disconnected hosts and direct tool calls are not universally intercepted. No Stop loop or every-turn guard |
| `harness/native_host.py:requirements_kickoff`; `harness/architrave_runtime.py:begin_native_worker`, `start_task`, `bind_native_owner` | Canonical admission checks selected requirements, context, ownership, worktree/base, grants and finite budgets before native dispatch; binds the actual host handle. Direct host tools do not automatically enter this path |
| `harness/architrave_runtime.py:accept_native_candidate`, `complete_task`, `resume` | Observed completed/idle/failed/cancelled returns are candidates, not accepted delivery; ticket, objective, source and owned diff checks reject stale/replayed results. Resume rechecks canonical state. A text progress update is not a terminal host receipt |
| `harness/architrave_runtime.py:_assert_primary_admission`, `record_feasibility`, `advance_milestone`, `feasibility_usage` | Existing criterion-wide feasibility/milestone accounting bounds recovery across renamed tasks and successor lanes. Unknown turns do not become zero; source touches and renamed observations cannot renew progress. This is not a direct-host watchdog |
| `gates/delivery_check.py:check_session`; `docs/delivery-authenticity.md` | Current selected scope, owner anchors/corrections, shared dependency inventory, observed proof and independent digest-bound review govern acceptance. Unchanged outcomes can retain proof; changed inputs need fresh proof. Empty diff is not failure if the original outcome is already independently verified |
| `knowledge/execution-policy.md`, Specifications / Context / Critical-path recovery | Choosing the correct next action, retaining one integration owner, rehydrating selected authority and continuing independent work are instructions. They do not prove execution. Stale summaries, audit findings and automated reminders grant no scope or permission |
| `harness/session_audit.py:collect_session`; `harness/native_host.py:routing_observation` | Local audit retains observed lifecycle/permission events and native command exit telemetry; native bridge separates requested/effective routing. Missing model, command exit, child identity or host telemetry stays unknown. This cloud assignment has no joined app tasks/canvas API or Copilot CLI for a fresh matched replay |

**Demonstrated gap and narrow fix.** On one fixed prefix of this authorized
cloud assignment's real local log, the baseline collector retained zero of
118 `permission.requested` and 118 `permission.completed` events. v3 retains
all of them, including the reported `approved` kinds, and host identity.
No private transcript, request ID, session ID or path is published. This is
same-source collector before/after evidence, not a replay of model behavior.
Host version was 1.0.80; host-selected model was `gpt-6.1-sol`, selected effort
`medium`. Requested model and effective usage-reported model were unavailable.
At that cutoff, log elapsed time was 270.602 seconds; model duration, tokens
and nano-AIU were unavailable, not zero. No native compaction was observed.
These are collection coverage measurements, not task completion or efficiency.

Local regression coverage uses existing suites. Protocol-level test inputs
exercise event parsing only; they are not live provider/session evidence:

| Required scenario | Existing checks / observed coverage |
|---|---|
| Acknowledged correction, zero action; retained goal, wrong blocker | `test-delivery-focus.py` checks next-action guidance; `test-native-host.py` checks finite shared recovery and unknown turns. Actual corrected-model next-action behavior is **unverified** |
| One lane blocked, another runnable | Native-host sibling lifecycle and human/global-hold regressions; delivery scoped-done checks. Real independent-lane progression is **unverified** |
| Green test, unrelated functionality inside allowed paths | Delivery-audit substitute scanning, delivery-check unclassified/missing observation and digest-bound review checks. Path containment or green tests alone cannot establish semantic relevance; a live adversarial change is **unverified** |
| Conversational permission versus native approval, denial, unknown | Review-launcher parsing regression separates assistant text from native events and preserves unknowns. Native approval events observed locally; actual human interaction and live denial/unknown scenarios are **unverified** |
| Stale/duplicate return; legitimate successor after resume | Native-host stale ticket/replay, same-run recovery, retained-owner and criterion-wide renamed-task budget tests; delivery-check amendment/proof freshness tests. Live successor replay is **unverified** |
| Scoped successful closeout with unrelated checkout activity | Delivery-check scoped inventory, retained unchanged outcomes, scoped-done and completed-scope freshness regressions. Real declared closeout in this host is **unverified** |

**Matched model pilot: not run; REQ-91 remains open.** No Sol/Terra routing
recommendation follows from this assignment or from Codex anecdotes. A fresh
paired pilot needs an authorized real C# target plus a longer assignment with
a correction/handoff; do not invent a C# application in this Python kit to
satisfy the workload. Use isolated worktrees from the same exact starting
commit, the same host/version, Architrave build, acceptance, source/dependency
scope, grants and verification. Ask the owning host for each explicitly
requested model without changing user pins; record host-reported selection,
effective usage model and reasoning controls separately, including differences
and unknowns. Do not infer native compaction from cache usage.

For each attempt, audit selected local logs through the existing collector and
have an independent reviewer assess original outcomes, actual selected diff and
verification. Record verified in-scope completion, time to first *relevant*
action, human interventions, unrelated edits, repeated blockers, conversational
asks and native approval/denial interruptions. Relevance and blocker identity
need event-backed semantic review, not exact-call counts. Report log elapsed
time separately from model duration and each usage category, with missingness
and all attempts retained. If the patch affects a scenario, rerun it with the
same model before/after where feasible; separate that comparison from model
routing. Keep private packets local and publish only reviewed sanitized
aggregates/public source references. A small pilot supports only those tasks.

If a delegated turn cannot prompt the owner, escalate the exact blocked action
through the supported parent/owner-visible host path, retaining target, scope,
native denial/request and uncertainty. An owner grant does not bypass host
policy. Continue independent authorized criteria. Uncertain side effects need
live reconciliation before retry; unresolved work uses existing Handoff/CTO
paths and retains partial edits and the original finite recovery budget.

## Analysis shape

The analysis is a JSON object with exactly these fields:

| Field | Content |
|---|---|
| `packet_sha256` | Digest emitted by collection |
| `reviewer` | Reported host reviewer identity; not an authenticated attestation |
| `summary` | Short outcome-first synthesis, including non-delivery or uncertainty |
| `goals` | One or more assessments per attributable original owner message; split multi-goal messages semantically |
| `findings` | Supported actionable improvements, or an empty list |
| `strengths` | Practices to preserve, or an empty list |

Each goal has exactly `session`, `owner_event`, `goal`, `status`, `evidence`,
`events`. Status is `delivered`, `partial`, `not-delivered` or `unverified`.
`events` is a nonempty list of packet event IDs in that same session.
`owner_event` must name an attributable original owner message. Automated
reminders and cross-session instructions are not new owner goals. If none
can be attributed, return no goal claims and explicitly explain the gap.
At least one assessment per message is structurally checked; exhaustive
coverage of several goals inside one message is the reviewer's responsibility.

Each finding has exactly `session`, `events`, `severity`, `category`,
`observation`, `change`, `target`, `verification`, `tradeoff`, `confidence`.
Severity and confidence are `high`, `medium` or `low`; category is `prompt`,
`instruction`, `approach` or `prerequisite`. All text fields are nonempty.
Specify actual proposed wording/approach and its destination, not "improve
the prompt". Verification names a comparable real task and the outcome and
resource measures to check; counterfactual savings remain hypotheses.
Each strength has exactly `session`, `events`, `practice`.
Use event references for both failures and practices worth preserving.
No fabricated sample assessment is supplied as a substitute for a real one.

## Outcome-first rubric and metrics

| Dimension | Evidence and interpretation |
|---|---|
| Owner-goal fidelity | Original requests/corrections versus delivered artifact or behavior. REQ acceptance, final messages and passing tests are claims/support, not automatically ground truth |
| Work quality | Does what was asked, does it well and does not break existing behavior. Check the real consumer and relevant regression evidence; avoid test gaming |
| Approach/focus | First useful vertical slice, appropriate tool/context choice, recovery, justified delegation, unnecessary scope expansion or ceremony. Semantic event-backed judgment, not keyword scoring |
| Consumption | Uncached input = reported input minus cache reads; cache writes remain new input. Cached input and output stay separate. Missing/invalid usage remains unknown, not zero |
| Time | Log elapsed time includes pauses/user/tool waits; model duration sums reported API-call time and may overlap. Neither measures human effort |
| Recovery | Recorded host tool failures, separately reported command exits (including nonzero exits hidden by host success), unmatched starts and exact repeated tool/argument calls. Exit telemetry coverage is explicit; missing telemetry is not success. These are inspection candidates, not automatic waste or semantic command-error rates |
| Context/tool overhead | Latest prompt size, model limit, reported effort and tool-schema tokens when logged. No invented compute/reasoning metric or universal context threshold |
| Cost | Reported Copilot nano-AIU only where every selected usage record contains it. Not USD, subscription cost or the generic host `cost` multiplier |
| Improvement | Concrete change, evidence, confidence, prerequisite, tradeoff and verification. Keep successful practices and necessary safety work |

There is deliberately no weighted "performance score", worker leaderboard,
universal token budget, estimated wasted-token total or causal savings claim.
Session totals are not current-task costs. Turn selection gives a bounded
measurement, not precise attribution of every input token to a cause.
Compare outcome/quality and cost together for similar tasks, with the same
acceptance, model/harness versions and environment. Include all attempts,
human corrections and missingness; never divide cumulative cost by arbitrary
REQ counts to rank teams. For repeated comparable trials report sample size,
first-attempt success and reliability separately. `pass@k` and all-trials
success answer different questions; neither is meaningful for a single
retrospective. Use matched before/after real tasks and owner calibration
before promoting instructions; correlation alone does not show causation.

## Research basis

Retrieved 2026-11-03 (local date). Vendor advice, empirical papers and social
signals are different evidence tiers; none proves Architrave improved.

| Source | Evidence tier / date | Implication and limitation |
|---|---|---|
| [Anthropic: Demystifying evals for AI agents](https://www.anthropic.com/research/demystifying-evals-for-ai-agents) | Vendor engineering, 2026-01-09 | Separate transcript from environmental outcome; combine deterministic, model and human grading; evaluate over-engineering and cost. Evaluate model plus harness, not the model alone |
| [Anthropic: Building effective agents](https://www.anthropic.com/research/building-effective-agents) | Vendor engineering, 2024-12; page now warns tooling has changed | Start with simple composable patterns and justify added complexity by task performance. Not evidence that every workflow should be simplified identically |
| [OpenAI: Evaluate agent workflows](https://developers.openai.com/api/docs/guides/agent-evals) | Current vendor documentation; publication date not stated | Use traces to diagnose tool/handoff/policy issues and refine prompts/routing, then repeatable datasets. Architrave reuses the host, not OpenAI cloud telemetry |
| [Gloaguen et al.: Evaluating AGENTS.md](https://arxiv.org/abs/2602.11988v3) | Empirical preprint, revised 2026-09-29 | Context files did not generally improve task success and raised inference cost over 20% on average in studied settings; non-standard coding practices can be useful. Not a blanket instruction-file ban or measured effect on Copilot/Architrave |
| [Kapoor et al.: AI Agents That Matter](https://arxiv.org/abs/2407.01502) | Empirical/research analysis, 2024-07-01 | Evaluate cost alongside accuracy, avoid holdout leakage and benchmark shortcuts; use comparable conditions. Do not infer productivity from benchmark rank |
| [METR: Experienced open-source developer productivity](https://arxiv.org/abs/2507.09089v2) | RCT, 16 developers / 246 tasks, revised 2025-07-25 | Early-2025 tools increased completion time 19% in this specific setting despite perceived speedup. Measure actual outcomes/time; do not extrapolate to all developers or newer models |
| [Simon Willison's coding-agent tips / linked Hacker News discussion](https://simonwillison.net/2025/Oct/25/coding-agent-tips/) | Practitioner/social signal, 2025-10-25 | Runnable relevant tests, interactive access and informative failures help; broad docs may be less useful. Anecdote, not a controlled effect size or consensus |

The November 2 Architrave updates (REQ-66..76) repaired scope freshness,
board attribution and completion amplification. Their local checks prove
specific controls and instruction wording, not reduced ceremony or improved
delivered-work quality across sessions. Audit actual trajectories before
claiming that those repairs changed behavior. An audit that demands another
fixture program, extra gate or broader scope without owner need would
reproduce the failure it is meant to diagnose.
