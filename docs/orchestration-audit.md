# Orchestration audit

## v0.13.0 thin-supervisor decision (2026-10-06)

Baseline is actual `origin/main` v0.12.4, `c7229b1`; the worktree was clean.
**KEEP:** Python Run state, authenticated events/evidence, recovery, criteria,
scoped default-deny mutation, target identity, primary-stall controls and gates.
**CUT:** duplicated lead/stanza prose, mandatory CTO spawning and native task
polling. **DEFER:** provider SDKs, daemons, generic schedulers, transcript/context
managers and forced cross-host symmetry. **REPLACE:** unconditional pack loading
with one small supervisor contract, and global-revision native tickets with
authenticated sibling-lifecycle commutation plus unchanged task/policy/hold/source
checks. The packaged bridge is explicitly installed at user scope; it is not
auto-discovered as an unconfigured second plugin extension.

Doing nothing retains measured startup duplication and a reproduced native
parallel-admission failure. The smallest viable option above reuses the existing
Python runtime and host SDK. A new orchestrator/runtime would cost more, duplicate
host capabilities and provide no additional verified product outcome.

### Current official host contracts

Inspected official documentation and installed SDK/CLI contracts, not search
summaries or old cross-host assumptions:

- [Copilot app](https://docs.github.com/en/copilot/concepts/copilot-surfaces/github-copilot-app):
  isolated worktree sessions, local/cloud sandboxes, per-session model/reasoning,
  BYOK and host-owned lifecycle. [Slash commands](https://docs.github.com/en/copilot/reference/github-copilot-app-reference/slash-commands)
  expose Fleet, context, compact/clear and orchestration. The installed SDK's
  `tasks.startAgent` accepts a user model pin, not per-task reasoning/cwd/tool
  permissions. `TaskAgentInfo.resolvedModel` and native lifecycle events can
  report effective selection, turns and usage; absence is unavailable, not zero.
  SDK pre-tool hooks identify child session origins. The bridge consumes those
  signals, forbids child-originated session/task spawning, counts active host
  children (including outside the current dispatch), and keeps finite bounds.
  Worktrees are isolation, not an invented security sandbox.
- [Codex subagents](https://developers.openai.com/codex/multi-agent/):
  current app/CLI clients expose native child threads, activity, steering/close
  and inherited permission/model/reasoning settings; user custom-agent/spawn
  settings may override them. These capabilities do not imply a joined
  Architrave transport equivalent to Copilot's.
- [Official plugin packaging/install](https://developers.openai.com/plugins/build/plugins):
  the compatibility `.codex-plugin/plugin.json` remains supported, with local
  `.agents/plugins/marketplace.json` catalogs and native CLI registration/install.
  Desktop execution/discovery must be observed separately. No private app files,
  credential edits, SDK workers or nested agent CLI adapters are used.

No local model was downloaded or provider credentials changed. Optional effort
requests inherit when the transport lacks a corresponding control. Concrete
model names belong only to user/host configuration and observed worker evidence.

### Controlled experiment and context accounting

`scripts/bench-thin-supervisor.py` freezes dependency-free Task A (whitespace
slug normalization) and Task B (independent validation and summary modules).
Prepare each arm in a fresh git fixture; implement A directly; invoke B through
the actual joined host's `architrave_native_batch`; then finish/integrate and
independently run the configured tests. The Python helper **never launches an
agent**. Baseline uses untouched v0.12.4 Python/dispatch behavior, with only a
bounded `Promise.all` invocation helper to invoke its existing handlers together.
An initial serial diagnostic was not the controlled comparison or a statistical
repeat. Two real baseline host tasks were admitted and then cancelled after the
global revision binding failed; candidate siblings returned bounded candidates.

The exact same startup/disclosure paths are enumerated for both arms:
managed stanza, lead agent, lead skill, CTO checklist, runtime, execution policy,
YAGNI and learning packs. Count both the selected lead and explicit lead skill
conservatively for this cross-host workflow. Baseline entry surfaces total
27,366 UTF-8 bytes; forced non-trivial documents total 71,434 bytes. New forced
CTO/runtime/execution loads are included for durable Task B, not hidden by moving
prose. Source-byte accounting is not a claim about the host's complete injected
system prompt or tokenizer.

The compact result is `benchmarks/results/thin-supervisor.json`. It separates
actual native owners/concurrency/turns and deterministic acceptance from static
byte proxies, failed baseline artifact counts, and unavailable token/cost/context
telemetry. Both arms use the same foreground builder with fresh fixtures;
parent-context start/peak/end and growth are **unavailable**, so no parent-token
or cost saving is claimed. B elapsed time uses authenticated native start/finish
events, not the builder's unrelated implementation/tooling interval. A wall
time is unavailable. This is one controlled comparison, not a leaderboard.

Final-source Windows qualification after the review corrections has A PASS with
zero children; B PASS with two concurrent joined children, zero retries,
78 seconds of native execution, and 2,204 bytes of compact worker records.
It retains ten artifacts / 52,026 bytes. The earlier 57-second candidate run
preceded the last review corrections and is not the final qualification.
Baseline B admitted two host owners
but failed the revision binding in 8 seconds. Failure time is not a speed win.
The host reported 295,861 combined child usage tokens for final qualification; split
input/output, parent context and baseline usage remain unavailable.

| Enumerated source text | v0.12.4 bytes | v0.13.0 bytes | Reduction |
|---|---:|---:|---:|
| Entry surfaces | 27,366 | 7,916 | 71.07% |
| Startup including inline CTO | 30,622 | 9,770 | 68.09% |
| Forced durable B loads | 71,434 | 37,291 | 47.80% |
| All enumerated disclosure surfaces | 71,434 | 52,816 | 26.06% |

This meets the startup target/stretches without pretending all optional prose
was deleted. Durable B clears 35% but not the 50% stretch. The successful native
run retains ten orchestration artifacts; comparing its bytes with an aborted
baseline would be misleading.

The install check must hash the **installed payload**, not trust CLI catalog
version text. Direct repo-path installs were observed to report v0.13.0 while
the cached payload still matched v0.12.4, including after a commit. The verified
installation uses the supported local-marketplace mechanism pointed at a
persistent user-scope archive of the reviewed commit. Windows Copilot and Mac
Copilot/Codex payloads match reviewed code commit `d029a86`, v0.13.0; native bridge
pins are verified on both hosts. A new plugin session is required to replace an
already-loaded legacy context. Mac app/Codex desktop execution is not inferred.

Independent native review initially required four corrections: substantive
observations rather than changing receipt provenance, specific failure causes
and primary diagnostics, observing early turns before admission, and deriving
report success from measurements. These were fixed in one bounded review cycle;
the final source verdict is PASS. A fresh independent final-source review now
also passes in an Anthropic context (`claude-sonnet-5`, reported by the actual
host event), alongside the OpenAI final-source PASS. `review.crossFamily`
remains enabled; the two-family source-review condition is fulfilled. Desktop
qualification is R3 rather than a risk downgrade, and still requires actual
host execution. Source review does not certify inaccessible desktop execution.

### Publication checkpoint

The existing Run records `mac-copilot-app-owner-smoke` and
`codex-desktop-owner-smoke` as genuine external owner checkpoints. Both supported
user-scope plugins are installed/enabled at v0.13.0 and their runtime assets
match reviewed source; desktop UI/native execution remains unobserved.
Open a new Copilot app thread at
`/Users/dragoshont/.architrave/vnext-113c6e36/owner-smoke/candidate/b`
and a new Codex desktop thread at
`/Users/dragoshont/.architrave/vnext-113c6e36/owner-smoke-codex/candidate/b`.
These are independent frozen fixtures; Task A is in each sibling `../a`.
Use the exact prompts below and return observed
native child activity and final acceptance evidence. Do not treat supported CLI
discovery as desktop execution or bypass a missing transport.

Publication is held until those required desktop observations are resolved.
Remote main was still `c7229b1` and no `v0.13.0` tag existed at qualification.
After the checkpoints pass, publish without rewriting refs, wait for actual CI,
then install the published GitHub-source/package and verify payloads again.

### One owner desktop smoke prompt

If Codex desktop execution is unavailable to the builder, open the isolated
benchmark repository in a **new Codex desktop thread**, select the installed
Architrave plugin, and paste this one prompt:

```text
Use Architrave in this isolated benchmark repository. Confirm the installed
plugin version and skill discovery first; do not change credentials/providers.
Task A: in sibling ../a/slug.py normalize runs of whitespace to one hyphen, trim leading/
trailing whitespace, lowercase, and preserve empty input. Work directly; run
python -B verify.py a from ../a. Task B: in this b workspace read verify.py and delegate validate.py and
summary.py to exactly two native children in parallel, with non-overlapping
mutable ownership, depth one, 240 seconds / 12 turns / 2000 output bytes each.
Children may not spawn children. Return compact envelopes, not transcripts.
Integrate and run python -B verify.py b. Use host model defaults unless my host
configuration explicitly overrides them. Report actual child activity, model
selection only if reported, acceptance, blockers and unavailable telemetry.
Stop on two identical failures without new evidence. Never claim CLI discovery
or fixture tests prove desktop execution.
```

For **Mac Copilot app**, the official foreground CLI smoke does not prove the
app's joined transport: A ran directly; B was not dispatched because native
extension tools were absent. No task/product failure is inferred from that.
Open the fresh isolated `owner-smoke/candidate/b` fixture in the Mac app and
paste this bounded prompt:

```text
Use the installed Architrave v0.13.0 in this isolated benchmark workspace.
Reload supported extensions and confirm architrave_native_batch is actually
available; if absent, stop and report NOT DISPATCHED, never fake a transport.
Run Task A directly in sibling ../a: slug must lowercase and join whitespace-
split words with one hyphen; run python -B verify.py a. For Task B, invoke the
joined native batch for run frozen-b, tasks validate and summary, exactly two
children, depth one, 240 seconds / 12 turns / 2000 output bytes each. No extra
agents or CLI workers. Wait for compact candidates, integrate non-overlapping
paths and independently run python -B verify.py b. Report actual host owner,
concurrency, acceptance, effective model only if reported, and unavailable
telemetry. Do not touch primary repos, credentials or providers; stop here.
```

Audit date: 2026-10-04; source-derived footprint refreshed for the native-host
repair on 2026-10-05. The comparison pins
[Pi `2003871`](https://github.com/earendil-works/pi/tree/200387122ca450d6387f033949423114a270b96c)
and
[OpenCode `907b3bc`](https://github.com/anomalyco/opencode/tree/907b3bc518fa48e90e8ec24dd327d13eee71c36c).

## Measured basic-sh SDD trial

The same dependency-free shell backend plus static UI task was run through Run
v2, isolated WorkPackets, workspace candidate collection/integration,
deterministic gates, criteria updates, and Outcome verification before and after
the change. Acceptance required the shell endpoint to return
`{"status":"ready","source":"basic-sh"}`, its contract to expose `/api/status`,
and the UI to fetch that endpoint and render an accessible live status target.

| Metric | Baseline | After | Reduction |
|---|---:|---:|---:|
| Orchestration files | 55 | 10 | **81.82%** |
| Orchestration bytes | 227,187 | 34,310 | **84.90%** |
| Approximate tokens (`bytes / 4`) | 56,797 | 8,578 | **84.90%** |
| Actual-code files | 3 | 3 | 0% |
| Actual-code bytes | 482 | 482 | 0% |
| Orchestration:code bytes | 471.342:1 | 71.183:1 | **84.90% lower** |

Both runs completed with `API-001=PASS`, `UI-001=PASS`,
`Run status=COMPLETED`, and `python tests/verify.py` printing
`basic-sh acceptance: PASS`.

The baseline generated 31 full-state snapshots (318,421 bytes), nine eager
human projections, six worker files, and four workspace files. The compact run
keeps one rolling recovery snapshot, no eager projections, one result per
worker, and one patch per mutable workspace.

Reproduction command used for both runs:

```bash
git worktree add --detach ../architrave-metrics-baseline 165da5284e0fff5ecfa7b1fff18593c949ad8fd3
git worktree add --detach ../architrave-metrics-after 8c415eadd043a94385255aa74fccfeb881c64c60
python scripts/measure-basic-sh-sdd.py --source ../architrave-metrics-baseline --output ../architrave-metrics --label baseline --manifest benchmarks/results/orchestration-baseline.json
python scripts/measure-basic-sh-sdd.py --source ../architrave-metrics-after --output ../architrave-metrics --label after --manifest benchmarks/results/orchestration-after.json
python scripts/validate-orchestration-metrics.py --expected-after 8c415eadd043a94385255aa74fccfeb881c64c60
git worktree remove --force ../architrave-metrics-baseline
git worktree remove --force ../architrave-metrics-after
```

The runner creates a fresh git fixture for each label and uses the checkout's
actual `RunStore`, `WorkspaceManager`, and `execute_work_packet` implementations.
Scratch trial output is intentionally outside the repository.

Initial slimming validation (historical; release validation is rerun for each repair):

- `python scripts/test-runtime-v2.py`: 58 passed, 1 platform skip.
- `python scripts/test-workspaces.py`: 12 passed.
- `python scripts/test-worker-adapters.py`: 24 passed, 4 platform skips.
- `python scripts/test-legibility.py`: 19 passed.
- `python scripts/test-longbuild-runtime.py`: passed.
- `python scripts/test-benchmark-tools.py`: 34 passed.
- Python install/update safety suite: 9 passed.
- Five synthetic focus/correction regressions: passed.
- Gate, Run validator, learning validator, config-profile, review-launcher,
  Codex role, and Codex runtime suites: passed.
- `python scripts/test-delivery-focus.py`: passed.
- `powershell -File scripts/test-validate-run.ps1`: compact v1/v2 cases passed.
- `python scripts/generate-codex-agents.py --check`, Python compilation, JSON
  parsing, `git diff --check`, and direct compact Run validation: passed.

Python stdlib is now the canonical implementation for install/update, gates,
Run/learning validation, orchestration, review launchers, and platform command
selection. The remaining `.sh`/`.ps1` entrypoints only locate Python and forward
argv/output/exit status. Portable Node/npm was restored for the documented
repository-development `npx ajv-cli` schema check.

Substantive shell/PowerShell files over 20 lines fell from **55 files / 4,833
lines** on the baseline to **33 files / 1,877 lines**. The remaining non-Python
exceptions are release/manifest bootstrapping, legacy learning promotion/recovery
utilities, and their compatibility tests; the product orchestration,
install/update, deterministic gates, Run/learning validators, and review
launchers are Python-backed.

## Long-running-session failure controls

Two generic failure classes were converted into synthetic regressions without
copying private session data:

- a working implementation was ignored while diagnostics and compatibility
  machinery expanded without a minimal acceptance result;
- an explicit product-test correction was displaced by an unrelated
  communications/infrastructure lane and wrong-target execution.

Implemented controls:

| Failure mode | Enforced control | Metric / footprint impact |
|---|---|---|
| Corrections leave old tasks active | Versioned canonical objective; `objective.replaced` defers old tasks, releases leases, fails active workers, resets lanes/target, and requires a next cheapest test | Adds compact state fields; v0.12.3 push-back verdicts keep 10 artifacts and an 84.90% byte reduction |
| Working baseline bypassed | Replacement architecture/compatibility tasks require registered reuse path, evidence, and exact difference under test | Evidence references only; no duplicated baseline prose |
| Hardening/review before acceptance | Non-security infrastructure/review, large changes, and non-minimal diagnostics are deferred until the minimal slice passes; two review reopens force a batch | Prevents repeated micro-review artifacts |
| Wrong provider/build | Target preflight binds provider/store, artifact, version/hash, environment/workspace, and acceptance target; mismatch pauses and blocks launch/test/install | One compact identity object plus referenced evidence |
| Objective displacement | Maximum two active lanes; communications/research/infrastructure default to deferred and cannot displace product | Lane IDs only |
| Opaque checkpoints | On-demand bounded checkpoint contains objective, criteria, last product evidence, blocker, cheapest test, active lanes, deferred work | No persistent projection file |

Cross-session status may add evidence but cannot invoke objective replacement
without explicit user direction.

Independent branch review also closed these concrete defects: pre-focus Run v2
state now migrates in place with a signed `run.migrated` event and recovery
snapshot; objective replacement preserves uncertain side effects for mandatory
reconciliation and safely cancels obsolete external waits; gates/checkpoints are
objective-version-bound; target and reuse gates require dedicated verified
receipts; unrelated work cannot bypass deferral by claiming the product lane;
POSIX recipes preserve Bash compatibility; invalid design-source JSON fails the
gate; and every launch shim verifies Python 3 before forwarding.

## Implemented changes

| Change | Measured or expected reduction | Quality impact / risk |
|---|---|---|
| Replace per-transition snapshot directory with atomic `recovery.json` | 31 files / 318,421 bytes to 1 file / 10,960 bytes in the measured run | Preserves last-known-good recovery; removes historical duplicate state copies because authenticated events retain history |
| Stop eager `intake`, tournament, plan, phase, gate, judge, observer, and summary projections | 9 files / 1,489 bytes removed in the measured run; much larger savings on real prose-heavy runs | Canonical Outcome, criteria, tasks, policy, evidence, and events remain; status/events are queried on demand |
| Collapse stdout, stderr, and result into one compact worker record with 2,000-character previews | 6 worker files to 2 in the measured run | Keeps bounded diagnostics and truncation status; task evidence must be registered separately rather than hidden in logs |
| Keep one candidate patch and put changed paths in canonical events/state | 4 workspace files to 2 | Patch remains independently attestable; removes duplicate status JSON |
| Compact JSON writes | Reduces canonical and recovery bytes without changing schema | Human inspection moves to CLI views |
| Remove model from WorkPackets and semantic model-class presets from canonical policy | Removes routing fields and repeated selection prose | Model selection is user/host-owned; verification remains risk- and evidence-driven |
| Replace named model-family requirements with distinct independent reviewer identities | No material artifact increase | Preserves independent review without constraining provider/model choice |
| Slim legacy Run v1 initialization to one compatibility summary | Eight eager Markdown files removed for new v1 records | v1 remains valid/migratable; new stateful work should use Run v2 |

## Pi and OpenCode comparison

| Axis | Pi | OpenCode | Architrave decision |
|---|---|---|---|
| Prompt/context | Named, patchable system sections; skills load bodies on demand ([system prompt](https://github.com/earendil-works/pi/blob/200387122ca450d6387f033949423114a270b96c/packages/coding-agent/src/core/system-prompt.ts), [skills](https://github.com/earendil-works/pi/blob/200387122ca450d6387f033949423114a270b96c/packages/coding-agent/docs/skills.md)) | Rules plus agent prompts and MCP/tool descriptions ([agents](https://opencode.ai/docs/agents/)) | Keep repository grounding, but retrieve lane detail on demand and avoid repeated handoffs |
| Persistence | One append-only JSONL v3 session tree outside the repo ([session format](https://github.com/earendil-works/pi/blob/200387122ca450d6387f033949423114a270b96c/packages/coding-agent/docs/session-format.md)) | Normalized SQLite session/message/context state outside the repo | Keep in-repo ignored audit state because policy/evidence are product-build records, but reduce it to canonical state + events + rolling recovery |
| Delegation | Deliberately no built-in subagents or plan mode; extensions may add them ([README](https://github.com/earendil-works/pi/blob/200387122ca450d6387f033949423114a270b96c/README.md)) | Build/plan primary agents, general/explore/scout subagents, parent-linked child sessions ([agents](https://opencode.ai/docs/agents/)) | Retain bounded specialists only when isolation, permissions, expertise, parallelism, or independent context justify them |
| Planning/spec | No structured plan artifact | Plan is primarily a permission posture | Retain machine-readable Outcome, Acceptance Matrix, and TaskGraph; remove duplicate prose plans |
| Compaction | Append-only compaction/branch-summary entries retain raw history, kept boundary, token usage, and cumulative file indexes ([compaction](https://github.com/earendil-works/pi/blob/200387122ca450d6387f033949423114a270b96c/packages/coding-agent/docs/compaction.md)) | Hidden compaction agent produces one anchored summary and recent tail | Treat host conversation compaction as host-owned; keep Architrave Run events compact and append-only |
| Resume/recovery | Replay JSONL tree; fork/clone/tree navigation | Resumable sessions, child navigation, revert/unrevert | Retain stronger atomic state, pending-event recovery, HMAC chain, side-effect reconciliation, and checkpoints |
| Permissions | No built-in permission system; relies on process/container permissions ([security](https://github.com/earendil-works/pi/blob/200387122ca450d6387f033949423114a270b96c/packages/coding-agent/docs/security.md)) | Granular ordered allow/ask/deny rules ([permissions](https://opencode.ai/docs/permissions/)) | Retain default-deny Run mutation grants and receipts; host tool permissions remain an additional boundary |
| Observability | Session events and optional extension hooks | SSE/server logs, database queries, trace output | Retain authenticated typed events and evidence binding; render reports on demand |
| Extensibility | In-process extensions, tools, commands, providers, skills ([extensions](https://github.com/earendil-works/pi/blob/200387122ca450d6387f033949423114a270b96c/packages/coding-agent/docs/extensions.md)) | Plugins, hooks, tools, skills, agents | Retain structural agents/gates/knowledge packs; avoid a second provider runtime |
| Project footprint | Zero core per-run project files | Runtime state outside repo; repo config is optional | Ten files in the measured durable run, justified by audit/recovery requirements |

## Missing-feature priorities

| Priority | Feature | Why |
|---|---|---|
| P1 quality | Explicit host-compaction contract for long worker sessions | Pi and OpenCode handle context overflow directly. Architrave should document required host behavior and fail clearly when a host cannot resume/compact, rather than implement another transcript runtime. |
| P1 quality | Ordered path/tool permission patterns at the host adapter boundary | OpenCode's `allow/ask/deny`, external-directory, secret-file, and repeat-call guards complement Run mutation policy. Add only where host APIs expose enforceable controls. |
| P2 quality | Referenced full command output with capped previews | Current compact worker records cap previews. Large full logs should be retained only when a gate registers them as evidence, by reference and digest. |
| P3 convenience | Child-session navigation and interactive branch trees | Useful for exploratory chat, but not required for durable build correctness. |
| P3 convenience | Broader plugin/event API | Pi/OpenCode are richer interactive harnesses; Architrave should not duplicate them without proven build-quality need. |

## Follow-up opportunities

- Add a host-capability receipt describing compaction/resume and enforce it only
  for runs whose expected duration can exceed one host context.
- Add an on-demand Markdown renderer if users need exportable audit reports;
  keep rendered views untracked and disposable.
- Measure a long multi-worker fixture to tune the 2,000-character worker preview
  and decide when full output merits a registered evidence artifact.
