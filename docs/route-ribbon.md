# Route Ribbon

The optional Copilot canvas makes route changes readable without becoming a
second control plane. The renderer is **one portable file**:
`.github/extensions/architrave-ribbon/extension.mjs`, with inline HTML/CSS/JS and
only the host-provided `@github/copilot-sdk` plus Node built-ins.
Python remains the canonical implementation of Run semantics.

## Session companion (included in v0.14.1)

The same file declares two surfaces. **`architrave-session`** is the default,
passive session companion: empty input (`{}`), no actions, no Run schema.
**`architrave-ribbon`** remains the explicit canonical snapshot surface described
below. Normal session startup never calls `list_canvas_capabilities` or exposes
the large Run snapshot schema to the model. No additional agent, skill, tool,
hook, `additionalContext`, `session.send`, permission handler or scheduler is
registered. Canvas declarations still contribute their short discovery entries.

The user-approved, default-on **Session instrument** is included in v0.14.1 through
the release owner's integration. Source preparation does not publish a version
or install anything into a running user's environment. To adopt published,
reviewed source across ordinary
sessions, explicitly run:

```text
python <kit>\tools\install_update.py companion-install <existing-Copilot-home>
```

The target is the actual existing `$COPILOT_HOME` directory (normally
`~/.copilot`), not a repository. Only
`extensions/architrave-ribbon/extension.mjs` is installed/refreshed, using the
existing guarded transaction. Preferences are preserved. No full plugin
agent/skill catalogs, native bridge, Run runtime, dependencies or permissions
are installed. User extensions are a documented cross-repository discovery
path; the named Architrave agent is not required. Project extensions of the
same name shadow user extensions. A session-only copy is the candidate-proof
path, not cross-session adoption.

The Copilot legacy `plugin.json` explicitly contributes the dedicated
`.github/extensions/architrave-ribbon` directory through the documented
[`extensions` component path field](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference#component-path-fields).
It does not set `exclusive` or suppress built-in/user/project providers.
`companion-install` remains an explicit standalone alternative, not a required
second copy after plugin installation. Hosts without extension discovery or a
canvas renderer do not acquire those capabilities from the manifest.

### Session instrument design

The production `architrave-session` surface implements the approved Apple-like
direction rather than shipping the illustrative preview. A compact telemetry
rail exposes the selected model, effort setting and exact host-reported context
occupancy. One quiet indeterminate ribbon represents session activity; it has
no phase labels, completion denominator or percentage. Unknown counts hide the
meter instead of rendering zero. The separate canonical Run ribbon continues
to use explicit validated projections, never the preview's five-stage route.

Expandable subagent lanes show descriptive name, role, **Assigned** slice,
host lifecycle and explicitly labelled requested/resolved/observed model.
Detailed identity and effort stay in the disclosure. Keyed DOM rows retain
their open state and keyboard focus across telemetry updates. Empty and
unavailable child states differ; app-native child visibility remains explicitly
separate. No illustrative children or made-up verified totals are shipped.

Typography, fine dividers and restrained surfaces follow documented host theme
tokens. The OS light/dark preference is only a fallback; host theme attributes
take precedence. Reduced motion replaces the animated activity ribbon with
static hatching. Color accompanies text rather than being the only state cue.
The 44px close control is named **Close this session** for assistive technology.
Disconnection stops activity motion and labels retained readings last-observed;
successful close prevents subsequent client refreshes from reviving activity.
Preferences and detailed observation timestamps remain under one disclosure.

The visual update changes no canvas declarations, server routes, event
subscriptions, permission handling or startup behavior. It adds no model-facing
instructions, tool calls, runtime dependencies or context payloads.

### Startup and lifecycle

After joining, the extension subscribes to host events and reads
`session.rpc.model.getCurrent()` once if available. It attempts one
`session.rpc.canvas.open()` for `architrave-session`, only if automatic display
is enabled, this session has not opened/dismissed it, and `canvas.listOpen()`
reports no other open panel. The provider identity comes from the supported
`session.rpc.extensions.list()` process-ID mapping and is explicitly supplied
to `canvas.open`; the returned instance must confirm that identity before
`opened` is saved. A per-workspace interprocess display lock serializes startup
copies. Existing panels and observed canvas races suppress navigation. There
are no per-prompt retries, recurring timers/polling, model calls or status injections.

`<session.workspacePath>/artifacts/architrave-ribbon/session.json` stores only
`opened`/`dismissed`/`autoOpenSuppressed` booleans. Suppression is separate from
successfully opening or user dismissal. A failed open does not claim success.
Closing the host panel or **Close this session**
persists dismissal. Reload/resume of that workspace cannot re-trigger the
one-shot auto-open; existing panel rehydration is the host's responsibility.
A true new session/clear with a new workspace is eligible again. A
`session.context_cleared` event clears displayed usage/activity without reopening
or erasing dismissal. If the host clears in-place, no new panel is forced.

The checkbox under **Display preferences & source** writes only the user's
`$COPILOT_HOME/extensions/architrave-ribbon/artifacts/preferences.json` with
`{"enabled":false}` (or true). It takes effect for future automatic opens;
enabling does not take focus or override this session's dismissal. Manually
open `architrave-session` from the host canvas catalog to change the preference
again. Host extension enable/disable settings also remain authoritative.
Startup reads existing preferences but never creates user-global storage.
Malformed/oversized/non-regular preference files suppress opening with an
explicit provider diagnostic, rather than ignoring opt-out. Session preference
files are bounded to 1 KiB; telemetry is memory-only, not a persisted log.

### Telemetry and context budget

Selected model and effort are the host's current configuration, **not** proof
of the provider that executed a request. Root `assistant.usage` events supply
the **last observed** model and effort. Subagent/background/compaction usage is
not substituted for the main conversation. Model changes invalidate previous
usage/effective identity; context clear invalidates usage. Reasoning **effort**
is a setting, never chain-of-thought text.

Root `session.usage_info` events supply `currentTokens` and `tokenLimit` directly,
with optional system/conversation/tool-definition attribution. Until an actual
event arrives, counts and capacity are unavailable; there is no hardcoded 48k
and no transcript reconstruction, file-byte estimate or cache discount.
The context meter is occupancy, **not task completion**; its observation time
is disclosed. An indeterminate activity line and up to 32 active tool labels
reflect only observed activity. Permission/input/error/idle states do not invent
a milestone denominator or worker timeline. Canonical progress stays on the
separate explicitly fed ribbon.

Only allowlisted bounded fields are retained. Tool arguments/results, questions,
answers, messages, reasoning and error bodies are never copied into UI state.
Loopback HTTP and SSE keep display state outside model context. At most one
state fetch plus one coalesced refresh per iframe is in flight; animation is CSS
only and respects reduced motion. No telemetry endpoint is an agent action.
Detailed Run schemas/actions are disclosed only when that separate surface is
explicitly requested. Calling its capabilities is not lightweight mode.

### Children and assigned slices

The **Session subagents** section reads `session.rpc.tasks.list()` once at
startup and on `session.background_tasks_changed`, with at most one request and
one queued refresh. It retains up to 32 `type: "agent"` entries from this
session's task registry: descriptive name, role, lifecycle, requested/resolved
model and the explicit task description as **Assigned slice**. Assigned work is
not observed current activity or completion. Model/effort/context observations
are applied only to confirmed host task IDs; events received during discovery
are bounded and reconciled, never displayed as unconfirmed children. Newer
completion/model events outrank an older in-flight metadata response.

Details start collapsed; root usage is never replaced by a child's usage.
Prompts, responses, tool results and raw progress logs returned by the SDK are
discarded, not stored or fed back to the model. An unavailable metadata read
marks retained rows last-observed rather than current. There are no task
mutations, automatic workers or new task graph.

**App-native project/chat child sessions are different.** No ownership-scoped
child metadata/invalidation route has been qualified for this passive
extension. The SDK also offers a native tool-execution pipeline; the host's
app tools appearing in its metadata is not proof of extension execution
permission, context-free results or owned-child event coverage. The canvas
therefore says their visibility is unavailable; it does not infer them from
client tasks or substitute subagents. No private app database/files/IPC or
unrelated-session enumeration is used. This is a qualification boundary, not a
claim that every supported future host integration is impossible.
One live `tools.execute(get_session)` read for the owning root session succeeded
and produced an external-tool request without a model-issued call reference.
That does not establish context-cost attribution or an owned-child invalidation
stream; the companion does not adopt it as a polling or enumeration workaround.
The live extension-role probe returned four shell tasks and no agents, proving
the read is allowed but **not** native populated-child rendering.

The suggested <=500 incremental startup-token and <=1000 active-lightweight
targets require a same-host comparison including actual tool/skill/agent and
canvas catalogs. They are **not measured guarantees**. The first scoped
Copilot app 1.0.93-1 proof received live usage of 193119/922000 tokens with
system=12513, conversation=155497, tools=25109. These absolute counts prove
delivery, not companion overhead or suitability for 48k. The full Architrave
plugin/catalog contribution is not attributable from those counts; standalone
one-file user adoption is the smallest documented separation, not evidence of
zero total host context cost.

### Qualification boundaries

Supported session-scoped scaffold/reload proved an extension may call
`model.getCurrent`, canvas list/listOpen/open, without hooks or permissions.
An exact first candidate then received real ephemeral usage and displayed
selected model/effort. Missing initial observed-model identity stayed
**Not observed**. These receipts do not establish fresh-session startup,
clear/resume/reload restoration, global adoption or incremental-token budgets.
Focused SDK fixtures exercise these branches separately; live qualification
must state which lifecycle and context comparisons were actually observed.

The integrated function candidate (`98c1d5df` renderer SHA-256 prefix, after
inheriting PR8 `6b15d16`) rendered through its actual host loopback server in
Edge at 1280px and 360px. Both widths, plus documented light-token overrides,
had no horizontal overflow or script errors; keyboard focus, 40px close control
and reduced-motion behavior were observed. Usage was 302206/922000, selected
model `gpt-6.1-sol`, effort `high`; effective identity remained **Not observed**.
This proves the no-agent/empty-child surface, not populated native children.

The qualified session renderer (`1362f855b39cf5e03a7123a91f91065792590189e9583b501451ca162a25d8f9`)
was separately staged session-only and reloaded through the supported host
tools. A live `architrave-session` panel displayed model/effort/context, and its
visible **Close this session** button was clicked. After another supported
reload, an independent joined observer's `canvas.listOpen()` reported no
companion. The extension-owned session artifact was exactly
`{"opened":true,"dismissed":true}`. This proves dismissal survives provider
reload without automatic reopening. The global checkbox was not touched.
The previous renderer's loopback endpoint also became unavailable after reload.

A fresh proof chat was created idle and the session-scoped file staged before
its first **model turn**, but after the CLI's `session.start`. Initial discovery
therefore did not include it. One supported reload loaded it and reached its
one-shot open path. This is **post-reload**, not pristine new-session discovery.

A subsequent isolated **project** proof used checkout `4dd45e1` with that exact
renderer present before CLI creation. The first prompt, settled second context
and supported foreground navigation exposed only browser/editor/terminal canvases: `architrave-session` and
the separately installed native-extension tools were absent. No manual open or
reload was used. These three bounded observations establish a project-session
extension-discovery/loading boundary on the observed host, not a renderer
failure or proof that user-scope discovery is incompatible. No further fresh
session retries or private host/CLI toggles are warranted by unchanged evidence.
The requested default-on ordinary-session feature is **not accepted** from
source and fixtures alone. User-scope activation and a controlled small-context
comparison still need supported-host, authorized published-source qualification;
candidate global installation is not a substitute.

The follow-up also preserves the committed release safety batch `f8dcf02`.
It tightens canonical BLOCKS validation and extends maximum-domain persistence
regressions, without changing the passive session path. The integrated renderer
digest is `d522d55572059a413765e86239a3f389e969891b68e50360f3953d5cb16ebdf2`.
Earlier live receipts remain bound to their recorded renderer hashes, not
automatically reissued as exact-source proof for this integration. The release
owner's requested reviews and CI remain separate; this merge is not publication.

Source review found startup-dismissal and asynchronous child-discovery races;
targeted regressions now cover late panel activity, pending ownership reads,
queued discovery, and stale-list/model/completion interleavings. Completion's
first-dispatched model cannot overwrite a later observed call. Reviews and
fixtures do not establish cross-family release acceptance or close the remaining
pristine-startup, clear/resume, global-opt-out, populated-child or context-budget
claims. No candidate user/global deployment or publication was performed.

Focused follow-up command:
`node --experimental-vm-modules scripts/test-session-companion.mjs`.
`python scripts/test-ribbon.py` includes standalone adoption/opt-out-preservation
checks. Fixture/mock success is not native-host evidence.

For the optional real-browser contract, make Python Playwright and an existing
Chromium/Edge executable available to the test process, then set
`COMPANION_VISUAL_OUTPUT` to an artifact directory and optionally
`COMPANION_BROWSER` to that executable before running the same Node test.
It invokes `scripts/test-session-instrument.py` against a temporary fixture
server and cleans the server up afterward. Its synthetic HTTP state never
becomes native-host telemetry. The batched 1280px-light/360px-dark check covers
eight activity states, unavailable telemetry, long names and counts, theme
overrides, motion, keyboard focus across updates and display controls. The
approved design received one coherent surface/copy correction and a final
confirmation; measured muted-text contrast was at least 5.17:1 light and
7.38:1 dark. This does not qualify pristine startup, host-global adoption or a
48k context footprint.

## Managed Route Ribbon install or refresh (explicit opt-in)

```text
python <kit>\tools\install_update.py canvas-install <target-repository>
```

The same command refreshes the renderer with exact packaged bytes. On POSIX,
use the equivalent native path separators. It writes only the managed project
extension file; existing managed-path/junction/symlink checks and atomic
transactions apply. It does not install/update the user's plugin, change
configuration, or touch product code, Run state or host settings.
Normal per-repository `install` / `update` do **not** install this project canvas. Refresh it
explicitly after kit updates. The kit repository already contains the project
extension, so it does not need `canvas-install`; file presence alone does not
prove host discovery, as the pristine-project qualification above demonstrates.
The v0.14.1 renderer includes the approved default-on passive Session companion,
also contributed by the packaged plugin. This is distinct from the managed
Route Ribbon opt-in above; `canvas-install` still has repository-only reach.
Actual published-plugin activation in a fresh app remains **unqualified**.

Reload extensions through the supported Copilot extension tooling, inspect
`architrave-ribbon`, then discover canvas capabilities for `architrave-ribbon`.
Discovery requires the host's canvas renderer capability and extension SDK.
Plugin installation alone is not proof of canvas discovery. No unsupported
plugin manifest fields, Codex canvas or Claude canvas support are advertised.
On other hosts use normal text `status` / `checkpoint`; do not invent a canvas.

## Feed a compact projection

```text
python harness\architrave_runtime.py ribbon-snapshot <run-id>
```

The normal CLI envelope is `{ "status": "ok", "result": <snapshot> }`. Pass only
`result`, not the envelope, to the canvas. The command loads authenticated state
and events using existing Run APIs. It neither advances milestones nor grants
acceptance. A concurrent Run transition is an explicit snapshot-race error;
retry the read, never repair Run files manually.

Open with `{ "domainKey": snapshot.domainKey, "snapshot": snapshot }`. An initial
snapshot is optional: opening by domain alone shows persisted data or an honest
empty state. To update an open panel, call `get_snapshot` with `{}`; it returns
`{ "snapshot": savedProjection, "digest": savedDisplayDigest }`. Then call
`update_snapshot` with `{ "snapshot": freshProjection, "expectedDigest":
savedDisplayDigest }` (null when no snapshot exists). The digest is a display
compare-and-swap identity, not a Run revision or acceptance receipt.
Domain mismatch, invalid graph,
unknown fields, stale revision/objective/time and oversized data fail explicitly.
Re-opening is focus, not an update. Supply a fresh projection through the action
after a meaningful transition; do not generate HTML each turn.

Equal canonical Run revisions intentionally allow fresh capture/source/freshness
observations without mutating the Run. Updates are serialized per domain across
provider processes with an exclusive display-only lock and
must match the entire saved display snapshot's digest. A competing or stale
reader receives `ribbon_snapshot_conflict`, even if both updates have the same
Run revision; reread the saved document and obtain a fresh canonical projection
before retrying. Never simply resubmit stale evidence with a newer digest.
An active writer produces an explicit busy response if its bounded lock wait
expires. A dead writer's lock is recovered under an exclusive recovery guard.
An orphan recovery guard or unidentifiable lock requires manual display-artifact
inspection; it is never permission to alter canonical Run files.
Lower revision, objective version or capture time remains
`ribbon_stale_snapshot` even with a current digest. The digest survives provider
reload because it is derived from the persisted display document. Identical
content is an idempotent update, not new evidence or progress. No new scheduler,
canonical counter, telemetry service or Run authority is introduced.

The schema is discoverable through `list_canvas_capabilities`. It bounds a
snapshot to 64 KiB, 80 steps and 12 evidence references per step. Text is redacted
and bounded in the Python projection; excess steps/evidence fail rather than
silently dropping history. **Do not feed transcripts, secrets, authentication
prompts or arbitrary file paths.** The renderer never reads a Run file, accepts
an arbitrary filesystem path, spawns a worker, or changes acceptance/policy/holds.

## Truth and state meanings

| State / signal | Meaning |
|---|---|
| Scoped done | Canonical task completion; prerequisite success is not product success. |
| Product verified | Current task criteria have qualifying source-bound legibility PASS and no governing current failed check. Earlier completion/observations remain history after a failure; neither product verification nor its milestone remains current. |

Only authenticated, current source-bound failures govern the route. Failures
from an older source remain visible as history after baseline reconciliation;
malformed or tampered evidence raises an error, not an ordinary stale label.
Capture-time baseline freshness requires both matching HEAD and no Git-visible
public workspace drift. Canonical private/control metadata uses the existing
private-root exclusion, not an arbitrary implementation allowlist.
| Active | Canonical in-flight work, not proof that all other host sessions are idle. |
| Blocked | Current human/resource/dependency blocker; superseded blockers are history. |
| Deferred / bypassed | Not done; reason and dependencies remain inspectable. |
| Dead end / stop | Explicit terminal state or authenticated repeated-failure stop; not inferred from silence. |
| Retry | Known failure/evidence fingerprints and recorded hypothesis; new-evidence attempts are not automatically loops. |
| Milestone | Current source/task/criterion-bound product observation, not path-touch activity. |

The source hash/commit, objective version, revision and capture time are shown.
Freshness is **at capture time**; the canvas cannot detect later repository
changes until another projection is supplied. The canvas validates shape and
semantics, not cryptographic provenance of arbitrary agent input. Agents must
use the canonical Python projection. Display labels never become production
PASS or an authenticated host observation.

Wall elapsed is measured from Run creation to snapshot capture and includes
waits. The earliest current lane feasibility deadline is shown separately; it
is not a synthetic global Run deadline or active effort estimate.
Segment widths are estimated relative weights (the canonical projection uses
equal weight 1, not inferred complexity). Active effort, wait duration, tokens
and cost remain **Unknown**: this slice has no authenticated host-usage coverage.
No file-byte/token conversion, provider SDK, polling daemon or telemetry store.

## Parallel workstreams

The overview remains a segmented ribbon, not a serial execution plan. When
multiple stream groups exist, stacked labelled lanes expose each stream's
slices, state/blockers, scoped outcome and source/owner drilldown. A single
stream remains compact. Groups derive from canonical task lane plus work kind:
delivery is separate from exploratory diagnostic/research, reference, review
and operations. Unknown/unassigned lane identifiers are labelled, not guessed.
Existing scheduling/deferral rules are unchanged; unrelated research that the
Run deferred is displayed deferred, while an approved independent feasibility
probe keeps its actual active state.

Canonical cross-stream prerequisites project as **BLOCKS** and must match the
step dependency graph: every cross-stream pair is required, and omitted or
extra same-stream BLOCKS pairs are rejected. An agent may add explicit **INFORMS** relationships as
`display-only annotation`: they describe how findings support a decision,
never create prerequisites or modify acceptance/policy. Completed investigation
is scoped work, not a shipped/product-verified milestone; rejected routes stay
stopped and historical relationships never become current blockers.

Each stream has an explicit display source reference (domain/Run/revision/
objective/capture/commit/hash/freshness). Canonical single-Run projections share
that Run's source; manually composed views can supply independently sourced
snapshots without auto-scanning repositories or merging canonical state.
Stream source identity/order is guarded during display updates. Owner identity
and canonical owner start/finish are shown when reported; absent values remain
Unknown/Unassigned. These spans include waiting, not active effort.
Two active labels do not prove measured wall-clock concurrency. Parallel weights
are never summed into elapsed wall time or overall completion.

## Persistence and lifecycle

Python creates `domainKey = <repository-path SHA-256 prefix>:<runId>`. This is
workspace/Run identity, **not** a cross-machine synchronization identity.
Moving the repository changes the key. The Copilot session supplies its
`workspacePath`; the extension stores only its own display artifacts at
`<workspacePath>/artifacts/architrave-ribbon/<SHA-256(domainKey)>.json`.
No repository Run storage is used for projections. Their storage remains
session-local; only the companion's explicit display preference is user-global.
Missing host artifact storage is an explicit error.

`instanceId` owns only an ephemeral panel/server. Two panels with the same
domain share saved data. Reload/reconnect opens with the original runtime input
and reads the latest saved snapshot; it does not overwrite it with stale initial
input. A fresh panel ID also rehydrates that domain. Persistence lasts as long
as that owning session artifact workspace is retained; no promise of restoration
after host deletion or a new session workspace.

Observed Copilot CLI/app 1.0.93-1 reload reconnects the provider, but an already
open panel was **not automatically reopened** in this qualification session.
Use supported `open_canvas` again (same or fresh panel ID) to rebuild its
loopback server and rehydrate saved domain data before invoking actions.
Automatic host rehydration is host-dependent, not a shipped guarantee.
The built-in browser preview's inspection API was not shared with this
workspace. A separate isolated headless Edge check read the actual loaded
extension loopback page: desktop/mobile screenshots, no viewport overflow,
keyboard inspector interaction, source hash visibility without a milestone,
zero script errors, and documented light-theme token contrast were verified.
That proves the renderer on a public fixture, not a consumer product PASS.

Each panel serves on `127.0.0.1` with an ephemeral port and random capability
path. Host/origin/method guards, no external assets, CSP, bounded observers and
plain-text DOM construction isolate untrusted snapshot content. Display updates
notify already-open panels via SSE; **notifications are not a live Run feed**.
Refresh reads the saved projection only. Close and process signals release
connections/servers. At most eight panels and sixteen observers per panel.
Errors remain visible; previously displayed content can remain stale.

## Grounding and verification

The segmented ribbon/evidence inspector carries the accepted prototype design,
not its private scenarios. References:
[GitHub workflow visualization](https://docs.github.com/en/actions/how-tos/monitor-workflows/use-the-visualization-graph)
and [Temporal workflow visualization](https://temporal.io/blog/lets-visualize-a-workflow).

Focused checks: `python scripts/test-ribbon.py` and
`node --experimental-vm-modules scripts/test-ribbon.mjs`. SDK fixtures establish
validation/storage/HTTP behavior, not native canvas proof. Release qualification
must separately record supported discovery/open/action/reload observations and
required independent family provenance. Preparation alone does not authorize
tagging, publication, consumer adoption or release acceptance.

Candidate qualification found and batch-fixed Unicode length parity and an
omitted source hash. Retained review also led to display-digest conflict
protection and an explicit `RIBBON_HISTORY_EMPTY` projection error with focused
regressions. Host completion events subsequently confirmed OpenAI and Anthropic
reviewer identities; that identity evidence alone is not a source PASS.
Final full-source verdicts and required CI are separate qualification evidence.
Candidate preparation must not be treated as permission to merge, tag, publish
or adopt into consumer sessions.
