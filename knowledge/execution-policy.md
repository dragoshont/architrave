# Adaptive execution policy

Architrave recommends the execution intent a bounded task deserves. The current host remains responsible for model availability, concrete model selection, reasoning controls, context-window mechanics, authentication, and invocation.

This policy is provider-neutral. Canonical agents and `architrave.config.json` must not contain personal, enterprise, or time-sensitive model IDs.

## Semantic intent

Represent execution intent with four orthogonal dimensions:

| Dimension | Values | Meaning |
|---|---|---|
| `modelClass` | `inherit`, `fast`, `default`, `strong` | Relative capability recommendation, not a model name. Prefer `inherit` unless a bounded task proves specialization useful. |
| `reasoning` | `low`, `default`, `high`, `max` | Desired reasoning intensity. `max` is an evidence-based escalation, not a quality synonym. |
| `context` | `narrow`, `default`, `long` | Retrieval and context strategy. `long` is explicit escalation; it is not permission to load an entire repository. |
| `verification` | `default`, `independent`, `cross-family` | Additional verification intent. Existing deterministic, security, approval, and semantic gate floors still apply. |

`default` means use Architrave's existing task/lane policy and the host default. It never means skip required gates.

## Convenience presets

Presets are provisional shorthand over the dimensions, not a second routing system:

| Preset | `modelClass` | `reasoning` | `context` | `verification` |
|---|---|---|---|---|
| `FAST` | `fast` | `low` | `narrow` | `default` |
| `BALANCED` | `default` | `default` | `default` | `default` |
| `DEEP` | `strong` | `high` | `default` | `independent` |
| `CRITICAL` | `strong` | `high` | `default` | `cross-family` |

Use a preset label only when all four dimensions match its row. When one dimension is adjusted, record the dimensions directly and omit the preset label. In particular, `max` reasoning and `long` context are not built into `CRITICAL` until benchmark evidence shows that they improve the relevant outcomes.

## Selection order

Choose intent once during intake; do not add a separate routing model call.

1. Apply explicit user intent that does not weaken safety.
2. Classify the bounded task from the task signals below.
3. Use the specialist's provisional role hint only when task evidence does not decide.
4. Otherwise use `BALANCED` for non-trivial work and `inherit/default` dimensions when specialization is unproved.
5. Apply mandatory repository, lane, trust-boundary, and approval floors afterward. Floors may only strengthen verification.

`selectionReason` should name the winning task signal and any floor that changed the result.

### Task signals

- **FAST:** local, low-ambiguity, read-only or low-risk mechanical work with deterministic ground truth.
- **BALANCED:** ordinary implementation/debugging against known patterns or contracts with bounded impact.
- **DEEP:** ambiguous architecture, competing hypotheses, cross-cutting synthesis, difficult root-cause work, migrations, or broad research.
- **CRITICAL:** security/authorization/trust boundaries, data loss, destructive or irreversible impact, high-blast-radius infrastructure decisions, or significant final acceptance where a false PASS is costly.

Task signals override role hints in either direction. A narrow contract lookup can be FAST; an authorization change implemented by a routine coding specialist is CRITICAL.

## Provisional role hints

These are hypotheses to benchmark, not pins:

| Role/work | Starting hint |
|---|---|
| Architrave conductor | `inherit`; stay thin and delegate bounded work only when useful |
| Explore; narrow extraction; deterministic command/test work | `FAST` |
| Backend Implementer; bounded UI Visual; narrow Product Research; routine Runtime Observer | `BALANCED` |
| UX Architect; Operations UX; Service Architect; Backend Planner; significant research; difficult diagnosis | `DEEP` |
| Infra Engineer | `DEEP`, raised to `CRITICAL` for identity, network, secrets, destructive, or irreversible decisions |
| Adversarial Judge | `DEEP`, raised to `CRITICAL` when false acceptance is costly |

## Host-native delegation

Use the current host's structured custom-agent/subagent invocation when it exists. Pass the bounded task, relevant evidence, expected output, and semantic intent through that host mechanism. Do not make a canonical agent shell out to another harness or depend on a provider SDK.

If the host exposes a per-invocation model or effort override, a local binding may use it. If not, let the subagent inherit and record that the override was unobserved or unavailable. Host-specific adapters, including the existing benchmark runner, may translate local experiment bindings at their boundary; those mechanics are not universal policy.

Use subagents for isolated context, independent parallel work, specialist expertise, noisy reconnaissance, or independent verification. Avoid them for one-file edits, straightforward commands, and sequential work where delegation costs more than it protects.

## Context strategy

- `narrow`: targeted search and only the files needed to answer or edit.
- `default`: relevant implementation slice, governing contract, and nearby tests.
- `long`: broader architecture or multi-source evidence only after focused retrieval is insufficient.

Prefer fresh specialist and judge contexts, concise handoffs, repository search, repo profiles, and durable artifacts over coordinator context accumulation. A large model context window does not justify filling it. CRITICAL verification loads the evidence needed to verify the claim, not the implementer's whole conversation.

## Verification floor

Verification intent is ordered `default < independent < cross-family`. The effective value is the selected intent raised by existing repository/lane/task requirements.

- `default` requires the configured deterministic gates. They may be sufficient for low-risk FAST/BALANCED knowledge, command, test, or mechanical work only when every acceptance criterion has strong mechanical ground truth.
- Raise to `independent` when architecture fit, capability honesty, ambiguous behavior, or another semantic criterion remains after deterministic checks. It adds one fresh-context reviewer and must not be called a full semantic gate.
- Raise to `cross-family` for security/trust boundaries, authorization/identity, data loss, destructive or irreversible impact, migrations, high-blast-radius infrastructure, significant final acceptance, or any repository/lane rule that already requires a full semantic gate.
- A full semantic gate retains Architrave's existing meaning: independent verified GPT/Copilot-family and Claude-family PASS records.

The deterministic-only path is unavailable when the work changes user-facing design, API/data contracts, architecture boundaries, migrations, authorization, secrets, infrastructure, runtime state, or other behavior whose correctness is not completely machine-checked. Record the exact mechanical evidence when using it. Do not run an advisory judge as ceremony when it cannot change a mechanically determined outcome.

A stronger model never replaces deterministic safety/security validation, migration checks, plan-only infrastructure rules, read-only runtime rules, or human approval.

## Fallback and escalation

**Fallback** changes a concrete local binding because the preferred model/control is unavailable, restricted, or unsupported. It must preserve the same semantic intent where possible. If the host cannot honor an override, inherit safely and record the limitation.

**Escalation** strengthens semantic intent because observable evidence shows the current intent is insufficient: repeated failure, unresolved root cause, continuing deterministic failures, a REVISE/FAIL verdict, contradictory evidence, or newly discovered blast radius. A model asking for a stronger model is not evidence.

Escalation is bounded: move only the dimensions supported by evidence and stop after three escalation/revise attempts for the same gate. `max` or `long` requires explicit user direction, demonstrated failure/context need, or at least three representative benchmark repeats showing a material quality gain.

## Local bindings and evidence

Conceptual precedence is explicit user override, then local host binding, then Architrave semantic recommendation, then inherited host/session behavior. Actual host policy and availability constraints still win.

Use native subagent conventions, not an Architrave runtime:

- **VS Code / Copilot hosts:** prefer the structured subagent invocation's model preference for a bounded call. Otherwise use a user-local custom-agent `model` and `reasoning-effort` binding; if neither is present, inherit the parent model. A host may reject a subagent model above the parent's permitted tier.
- **Claude Code hosts:** prefer a per-invocation subagent model, then a user-local agent's `model` and `effort`, then the local subagent default, then the parent model. Organization policy may substitute or clamp unavailable choices.
- **Other hosts:** use the closest native custom-agent/subagent mechanism. If none exposes a binding, pass only semantic intent in the delegation and inherit.

Do not add these host-specific fields to canonical Architrave agents. User-local definitions or host settings may bind them to placeholders such as `<fast-model>`, `<default-model>`, and `<strong-model>` for that machine. A missing, renamed, restricted, or unsupported concrete choice falls back to inherited host behavior and is recorded as unobserved or substituted.

For non-trivial adaptive runs, keep concise evidence in the existing run summary: selected intent and reason, requested binding when known, observed model/vendor/effort when exposed, fallback/escalation evidence, judge provenance, and available duration/token/tool metrics. Do not store hidden reasoning, secrets, or a transcript.

Benchmark data must keep these separate:

- scenario-expected intent (a provisional classification hypothesis);
- arm-requested semantic treatment and local concrete binding;
- producer-reported selection (a claim from its run artifact);
- host-observed model/vendor/effort telemetry.

An expected profile never changes base pass/fail. A concrete recommendation requires at least three representative repeats and must exclude rows whose compared controls were mismatched or unobserved.