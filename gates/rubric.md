# Feature evaluation rubric (the Evaluator)

The criteria the **Adversarial Judge** applies to grade a *proposal* (pre‑implementation) or *implementation* (post‑implementation) against its specs and the established design language. It is the canonical rubric for the judge gates inside the **Architrave** harness. Platform‑agnostic: it is resolved per repo through `architrave.config.json` + the matching platform knowledge pack (`knowledge/apple.md` | `microsoft.md` | `web.md`, plus `knowledge/backend.md` for the backend / infra lane, `knowledge/operations-ux.md` for operational/admin product patterns, `knowledge/yagni.md` for minimum-sufficient-change discipline, and `knowledge/learning-loop.md` for durable memory/audit behavior).

Grounded in modern eval practice:
- **Anthropic** — *evaluator–optimizer* loop with clear criteria + stopping conditions; SMART success criteria; LLM‑graded rubrics where the judge **reasons first, then emits a verdict**, graded in a **separate context from the generator**.
- **OpenAI** — an eval is a **dataset + graders**; treat it like **BDD** (specify behavior before building); combine **code graders** (deterministic) with **model graders** (LLM‑as‑judge).
- **IBM** — combine **rule‑based + semantic (LLM‑as‑judge)** evaluation; assess **each step and the whole path**, plus **policy‑adherence, prompt‑injection and bias** dimensions, not just final text.

## Two grading layers (use both)
1. **Deterministic gates (code‑graded — rule‑based):** `gates/checks.sh` / `gates/checks.ps1` (`config.generate` + `config.build` + `config.test` + `config.designMap` / `config.tokens` JSON valid) and `gates/reconcile.sh` / `gates/reconcile.ps1` (design↔code token drift) and the `.github/hooks` checks; for the backend lane, `gates/backend-checks.sh` (build/test + migration safety + secret scan + IaC plan/policy, **never apply**); plus Run v2 validation, invariant checks, configured E2E/reality checks, and policy/receipt validation. Objective ground truth; they **override optimistic or semantic claims** and must be green.
2. **Semantic gate (LLM‑as‑judge):** this rubric, applied adversarially according to `knowledge/execution-policy.md`, by two independent judge families by default: one Copilot/GPT-family judge and one Claude-family judge. Both must PASS for the semantic gate to pass. `independent` uses one fresh-context reviewer but is not a full semantic gate — a single-family judge result is advisory evidence, not a completed semantic gate. Low-risk FAST/BALANCED knowledge or mechanical work may close at `default` with deterministic evidence only when every acceptance criterion is mechanically decided and no semantic/high-risk floor applies.

## Before grading: derive acceptance criteria (BDD)
Restate the request + the source‑of‑truth (Storybook + `config.designMap` + the platform pack + `config.tokens`) as a **numbered, testable acceptance‑criteria checklist**. Grade against the checklist, not vibes.

## Rubric dimensions
Score each **Pass / Concern / Fail** with a severity and cite evidence (a spec line, pack section, or doc rule).

1. **Spec & acceptance‑criteria conformance** — every criterion met; no scope drift; honest about anything not done. For Architrave-run non-trivial work, a visible intake block (understanding, acceptance criteria, grounding sources, assumptions, blocking questions/none) must exist before implementation; missing intake is at least a Major concern and can be a Blocker if it caused drift.
2. **Tournament & recommended-plan quality** — non-trivial work compares viable options before implementation (minimal safe fix, proper architectural fix, defer/ask-more when relevant), scores tradeoffs/blast radius/tests, and selects a recommended plan. Missing tournament/recommended plan is a Major concern; choosing a high-risk option without justification is a Blocker.
3. **Durable Run and phase observability** — non-trivial work has canonical
	`architrave.run.v2`, Outcome, Acceptance Matrix, dependency-safe TaskGraph,
	typed EventLog, and truthful checkpoints. The Phase Ledger is synchronized as
	a readable projection; it does not independently block an `approved-program`
	transition. Repeating completed work, manual state edits, or claiming an
	unstarted task is complete is a Blocker.
4. **YAGNI / minimum-sufficient-change** — the proposal uses the ladder in `knowledge/yagni.md`: skip/delete first, reuse existing repo source of truth, prefer native/platform and standard library, use installed dependencies before new ones, and add new abstractions/dependencies/config only with current evidence. Speculative layers, one-implementation interfaces, unused flags, wrapper-only services, decorative scaffolding, and future-proofing without a current criterion are Major concerns or Blockers. Do not punish enabling practices: refactoring, contracts, tests, validation, security, accessibility, design-token reconciliation, and root-cause/durable fixes for a recurring problem (a deeper change that removes a recurring cause is **not** over-engineering).
4b. **Root-cause & durability (the counterweight to YAGNI)** — for a defect, outage, regression, or recurring/systemic problem, the work diagnoses the **cause**, not just the symptom: the acceptance criteria target the cause, recurrence was checked (prior runs/lessons/"it broke again"), and the underlying mechanism is named and grounded in evidence/standard. A symptom-only patch presented as the *solution* to a recurring or systemic problem is a **Blocker**; a stopgap is acceptable **only** when explicitly labeled as such with the durable fix written down and tracked. Grounded in SRE postmortem culture (fix the cause) + Five-Whys RCA. Do not penalize a correctly-labeled, user-accepted stopgap, and do not penalize a durable fix as "too big" when it removes a recurring cause.
4c. **Adaptive execution fitness** — when execution intent is selected, it uses the provider-neutral dimensions and evidence rules in `knowledge/execution-policy.md`: task signals override provisional role hints; concrete model IDs remain host-local; `max` reasoning and `long` context have current evidence; stronger models never replace gates; fallback preserves intent; escalation is bounded and evidence-based. Keep expected, requested, producer-reported, and host-observed execution data distinct. An unobserved or mismatched control cannot support a concrete model recommendation. A verification level below a mandatory safety floor, a self-asserted cross-family PASS without verified family evidence, or agent-harness shell-out from canonical policy is a Major or Blocker depending on impact.
5. **Design‑language conformance** — reproduces the existing Storybook component + the `config.designMap` glossary entry (anatomy, tokens, iconography, subtle cues — **no reinvented component, no parallel abstraction**); values come from `config.tokens`, not hard‑coded; `config.designMap` kept in sync.
5. **Platform conformance** — idiomatic for `config.platform` per the knowledge pack (native components/navigation, typography, semantic color + theming for the platform's appearance modes); no platform‑foreign idioms. **On Apple or Windows platforms, also grade against the matching constitution (`constitution-apple.md` / `constitution-windows.md`): the native component catalog (Apple toolbar/sidebar ≤ 2 levels/`Table`; Windows command bar/`NavigationView`/`DataGrid`; button roles/prominence, menu‑bar/command parity), the verbatim type tables/ramp, materials placement (Liquid Glass functional‑layer / Mica·Acrylic·Smoke), the active‑state model, and the screenshot conformance‑audit — reinventing a catalog component, copying a cross‑platform screenshot's chrome, or shipping the wrong platform's type sizes is a Fail.** Cite the pack.
6. **Adversarial robustness & edge cases** — empty / loading / partial / error states (offline, signed‑out, no‑results, expired/revoked auth, unconfigured); concurrency/threading for the `stack`; resilience to **prompt‑injection** in tool/web/service output; never claims a capability the app can't truthfully perform.
7. **Product truth & anti-slop** — reflects real domain workflows and backend/API/IaC capability; no generic SaaS filler, decorative metric cards, meaningless charts, invented KPIs, vague copy, or visual spectacle that hides scarce/blocked/failed operational states.
8. **Operations UX truth** — when the feature is operational/admin work, it follows `knowledge/operations-ux.md`: real objects are modeled separately; onboarding/setup, offboarding/destructive flows, inventories, catalogs/uploads, user/team/RBAC, health/readiness, diagnostics, queues/jobs/schedules, and audit states are explicit; no status appears without source/timestamp/scope; no mutation is treated as complete without preflight and durable operation/job state; no destructive flow ships without impact summary, confirmation, recovery/receipt, and audit.
9. **Security (OWASP) & policy** — no private/undocumented APIs, scraping, hidden/background behavior, or unauthorized network actions beyond the repo's stated policy; secrets only in the repo's ignored secret store, **never in code/logs**; input validated at boundaries.
10. **Accessibility** — screen‑reader labels/order (VoiceOver / Narrator / AT), full keyboard reachability, no color‑only meaning, reduced‑motion respected, contrast + hit‑target minimums **per the platform pack**.
11. **Design↔code reconciliation** — `gates/reconcile.*` clean: generated‑from‑tokens output matches committed code; any design‑value change went through `config.tokens` first.
12. **Tests** — the repo's test pattern (`config.test`); cover the new logic **plus ≥ 1 adversarial/edge case** and capability honesty; deterministic and green.
13. **Verification & ground truth** — `gates/checks.*` green; for UI, a screenshot (`config.screenshot`) matches the Storybook reference; sibling‑instance consistency sweep done.
14. **Learning/audit trail** — for non-trivial Architrave runs, durable artifacts exist at `config.learning.runArtifactsPath` (or `.architrave/runs` by default): intake, tournament, recommended plan, deterministic gates, judge verdicts, runtime evidence when used, and summary. The repo profile at `config.learning.repoProfilePath` is concise, cited, and current when updated. Candidate lessons are recorded in `config.learning.lessonsPath`; stable repeated lessons are proposed for promotion instead of silently bloating config. Missing artifacts are a Major concern; promoted rules without evidence, stale-fact validation, redaction, or approval are a Major/Blocker depending on blast radius.

### Backend‑lane dimensions (apply when `config.backend` / `config.iac` are set — see `knowledge/backend.md`)
15. **Contract conformance** — the implementation honors the agreed contract (`config.backend.contracts`): shapes, errors, auth scope, pagination; UI and backend bind to the *same* contract (no drift); capability honesty (nothing claimed that the service can't perform). For operational/admin work, the contract includes capability matrix, preflight, operation/job schema, readiness/health source, diagnostic evidence, audit, and scarce-limit fields from `knowledge/operations-ux.md`.
16. **Data & migration safety** — schema/data changes are reversible + idempotent, follow expand → migrate → contract, and ship with an approved rollback; no destructive step without it. Data loss = Blocker.
17. **Idempotency & resilience** — external‑effecting operations are idempotent / retry‑safe; at‑least‑once messaging assumed; honest failure / blocked / scarce states.
18. **IaC safety and mutation policy** — plan-only is the default. An apply is
	valid only when canonical Run policy grants the exact target/operation and the
	work records a pre-side-effect checkpoint, mutation receipt, rollback path,
	and matching live health/version/digest. Least privilege and no secret
	materialization remain mandatory. An ungranted apply, leaked secret, blind
	side-effect retry, or destructive migration without rollback is a Blocker.

### Runtime / ops dimensions (apply when `config.ops` is set or runtime evidence is used)
19. **Runtime and product truth** — observation is read-only by default; a
	mutation needs scoped Run policy and a receipt. Web, Electron, iOS, and
	deployment are verified as their actual surfaces. Compile-only, Web-only
	Electron, blank/crashing native apps, stale deployed versions, fake provider
	data, silent mutation, or secret disclosure is a Blocker.

## Severity
**Blocker** (ship‑stopper / policy / spec miss) · **Major** (wrong but recoverable) · **Minor** (quality) · **Nit** (polish).

## Verdict rules
- **PASS** — all acceptance criteria met, **zero Blockers**, deterministic gates green, design↔code reconciled when applicable, and the effective verification policy is met. `independent` requires one fresh reviewer; a full / `cross-family` semantic gate requires both verified families.
- **REVISE** — fixable issues (≥ 1 Blocker/Major) with concrete required fixes.
- **FAIL** — fundamentally off‑spec or off‑pattern (reinvented an existing component, dishonest capability, policy/security violation).

## Bias mitigation (judge discipline)
- Judge in a **separate context** from the implementer; never grade your own reasoning.
- **Reason first, then emit the verdict.** Cite evidence for every finding.
- Don't reward verbosity or confident tone; deterministic‑gate results outrank claims.
- For best‑of‑N selection (optional): compare candidates **pairwise with order‑swapping** to cancel position bias; the pointwise rubric above still decides final acceptance.

## Stopping condition (human‑in‑the‑loop)
The harness caps each judge gate at **3 revise loops**. On a 3rd consecutive non‑PASS, stop and escalate to the user with the findings rather than looping.

## Required judge output format
1. **Acceptance criteria** — checklist: `criterion → met? → evidence`.
2. **Dimension scores** — table: `dimension → Pass/Concern/Fail → severity → evidence (spec/pack/doc ref) → required fix`.
3. **Blockers** (must‑fix) and **Concerns** (should‑fix).
4. **Specs not covered.**
5. **VERDICT: PASS | REVISE | FAIL** + a one‑line rationale.
