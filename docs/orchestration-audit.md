# Orchestration audit

Audit date: 2026-10-04. The comparison pins
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
| Orchestration bytes | 227,187 | 33,940 | **85.06%** |
| Approximate tokens (`bytes / 4`) | 56,797 | 8,485 | **85.06%** |
| Actual-code files | 3 | 3 | 0% |
| Actual-code bytes | 484 | 484 | 0% |
| Orchestration:code bytes | 469.395:1 | 70.124:1 | **85.06% lower** |

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
git worktree add --detach ../architrave-metrics-after d10a199d610fd9c3c717456b582a5c60bb62df24
python scripts/measure-basic-sh-sdd.py --source ../architrave-metrics-baseline --output ../architrave-metrics --label baseline --manifest benchmarks/results/orchestration-baseline.json
python scripts/measure-basic-sh-sdd.py --source ../architrave-metrics-after --output ../architrave-metrics --label after --manifest benchmarks/results/orchestration-after.json
python scripts/validate-orchestration-metrics.py --expected-after d10a199d610fd9c3c717456b582a5c60bb62df24
git worktree remove --force ../architrave-metrics-baseline
git worktree remove --force ../architrave-metrics-after
```

The runner creates a fresh git fixture for each label and uses the checkout's
actual `RunStore`, `WorkspaceManager`, and `execute_work_packet` implementations.
Scratch trial output is intentionally outside the repository.

Validation completed:

- `python scripts/test-runtime-v2.py`: 57 passed, 1 platform skip.
- `python scripts/test-workspaces.py`: 12 passed.
- `python scripts/test-worker-adapters.py`: 24 passed, 4 platform skips.
- `python scripts/test-legibility.py`: 19 passed.
- `python scripts/test-longbuild-runtime.py`: passed.
- `python scripts/test-benchmark-tools.py`: 34 passed.
- Python install/update safety suite: 6 passed.
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
| Corrections leave old tasks active | Versioned canonical objective; `objective.replaced` defers old tasks, releases leases, fails active workers, resets lanes/target, and requires a next cheapest test | Adds compact state fields; artifact count remains 10 and byte reduction remains 85.06% |
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
