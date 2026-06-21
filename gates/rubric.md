# Feature evaluation rubric (the Evaluator)

The criteria the **Adversarial Judge** applies to grade a *proposal* (pre‑implementation) or *implementation* (post‑implementation) against its specs and the established design language. It is the canonical rubric for the judge gates inside the **Architrave** harness. Platform‑agnostic: it is resolved per repo through `uikit.config.json` + the matching platform knowledge pack (`knowledge/apple.md` | `microsoft.md` | `web.md`, plus `knowledge/backend.md` for the backend / infra lane).

Grounded in modern eval practice:
- **Anthropic** — *evaluator–optimizer* loop with clear criteria + stopping conditions; SMART success criteria; LLM‑graded rubrics where the judge **reasons first, then emits a verdict**, graded in a **separate context from the generator**.
- **OpenAI** — an eval is a **dataset + graders**; treat it like **BDD** (specify behavior before building); combine **code graders** (deterministic) with **model graders** (LLM‑as‑judge).
- **IBM** — combine **rule‑based + semantic (LLM‑as‑judge)** evaluation; assess **each step and the whole path**, plus **policy‑adherence, prompt‑injection and bias** dimensions, not just final text.

## Two grading layers (use both)
1. **Deterministic gates (code‑graded — rule‑based):** `gates/checks.sh` / `gates/checks.ps1` (`config.generate` + `config.build` + `config.test` + `config.designMap` / `config.tokens` JSON valid) and `gates/reconcile.sh` / `gates/reconcile.ps1` (design↔code token drift) and the `.github/hooks` checks; for the backend lane, `gates/backend-checks.sh` (build/test + migration safety + secret scan + IaC plan/policy, **never apply**). Objective ground truth; they **override optimistic claims** and must be green.
2. **Semantic gate (LLM‑as‑judge):** this rubric, applied adversarially.

## Before grading: derive acceptance criteria (BDD)
Restate the request + the source‑of‑truth (Storybook + `config.designMap` + the platform pack + `config.tokens`) as a **numbered, testable acceptance‑criteria checklist**. Grade against the checklist, not vibes.

## Rubric dimensions
Score each **Pass / Concern / Fail** with a severity and cite evidence (a spec line, pack section, or doc rule).

1. **Spec & acceptance‑criteria conformance** — every criterion met; no scope drift; honest about anything not done.
2. **Design‑language conformance** — reproduces the existing Storybook component + the `config.designMap` glossary entry (anatomy, tokens, iconography, subtle cues — **no reinvented component, no parallel abstraction**); values come from `config.tokens`, not hard‑coded; `config.designMap` kept in sync.
3. **Platform conformance** — idiomatic for `config.platform` per the knowledge pack (native components/navigation, typography, semantic color + theming for the platform's appearance modes); no platform‑foreign idioms. Cite the pack.
4. **Adversarial robustness & edge cases** — empty / loading / partial / error states (offline, signed‑out, no‑results, expired/revoked auth, unconfigured); concurrency/threading for the `stack`; resilience to **prompt‑injection** in tool/web/service output; never claims a capability the app can't truthfully perform.
5. **Product truth & anti-slop** — reflects real domain workflows and backend/API/IaC capability; no generic SaaS filler, decorative metric cards, meaningless charts, invented KPIs, vague copy, or visual spectacle that hides scarce/blocked/failed operational states.
6. **Security (OWASP) & policy** — no private/undocumented APIs, scraping, hidden/background behavior, or unauthorized network actions beyond the repo's stated policy; secrets only in the repo's ignored secret store, **never in code/logs**; input validated at boundaries.
7. **Accessibility** — screen‑reader labels/order (VoiceOver / Narrator / AT), full keyboard reachability, no color‑only meaning, reduced‑motion respected, contrast + hit‑target minimums **per the platform pack**.
8. **Design↔code reconciliation** — `gates/reconcile.*` clean: generated‑from‑tokens output matches committed code; any design‑value change went through `config.tokens` first.
9. **Tests** — the repo's test pattern (`config.test`); cover the new logic **plus ≥ 1 adversarial/edge case** and capability honesty; deterministic and green.
10. **Verification & ground truth** — `gates/checks.*` green; for UI, a screenshot (`config.screenshot`) matches the Storybook reference; sibling‑instance consistency sweep done.

### Backend‑lane dimensions (apply when `config.backend` / `config.iac` are set — see `knowledge/backend.md`)
11. **Contract conformance** — the implementation honors the agreed contract (`config.backend.contracts`): shapes, errors, auth scope, pagination; UI and backend bind to the *same* contract (no drift); capability honesty (nothing claimed that the service can't perform).
12. **Data & migration safety** — schema/data changes are reversible + idempotent, follow expand → migrate → contract, and ship with an approved rollback; no destructive step without it. Data loss = Blocker.
13. **Idempotency & resilience** — external‑effecting operations are idempotent / retry‑safe; at‑least‑once messaging assumed; honest failure / blocked / scarce states.
14. **IaC safety (plan‑only)** — infra changes are **plan / what‑if / diff only, never applied**; `config.iac.policy` clean; least‑privilege (no wildcard RBAC, no unintended public exposure); **no secret materialized** in code / IaC / logs; identity / network / secret changes carry an explicit human‑approval gate. An `apply`, a leaked secret, or a destructive migration without rollback = automatic **FAIL / Blocker**.

## Severity
**Blocker** (ship‑stopper / policy / spec miss) · **Major** (wrong but recoverable) · **Minor** (quality) · **Nit** (polish).

## Verdict rules
- **PASS** — all acceptance criteria met, **zero Blockers**, deterministic gates green, design↔code reconciled.
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
