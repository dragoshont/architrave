# Route Ribbon

The optional Copilot canvas makes route changes readable without becoming a
second control plane. The renderer is **one portable file**:
`.github/extensions/architrave-ribbon/extension.mjs`, with inline HTML/CSS/JS and
only the host-provided `@github/copilot-sdk` plus Node built-ins.
Python remains the canonical implementation of Run semantics.

## Install or refresh (explicit opt-in)

```text
python <kit>\tools\install_update.py canvas-install <target-repository>
```

The same command refreshes the renderer with exact packaged bytes. On POSIX,
use the equivalent native path separators. It writes only the managed project
extension file; existing managed-path/junction/symlink checks and atomic
transactions apply. It does not install/update the user's plugin, change
configuration, or touch product code, Run state or host settings.
Normal `install` / `update` do **not** opt consumers into a canvas. Refresh it
explicitly after kit updates. The kit repository itself discovers the committed
project extension directly, so it does not need `canvas-install`.

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
observations without mutating the Run. Updates are serialized per domain and
must match the entire saved display snapshot's digest. A competing or stale
reader receives `ribbon_snapshot_conflict`, even if both updates have the same
Run revision; reread the saved document and obtain a fresh canonical projection
before retrying. Never simply resubmit stale evidence with a newer digest.
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
| Product verified | Current task criteria have qualifying source-bound legibility PASS. Historical or unbound evidence cannot become current product verification. |
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

## Persistence and lifecycle

Python creates `domainKey = <repository-path SHA-256 prefix>:<runId>`. This is
workspace/Run identity, **not** a cross-machine synchronization identity.
Moving the repository changes the key. The Copilot session supplies its
`workspacePath`; the extension stores only its own display artifacts at
`<workspacePath>/artifacts/architrave-ribbon/<SHA-256(domainKey)>.json`.
No repository Run storage or user-global state is used. Missing host artifact
storage is an explicit error.

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
