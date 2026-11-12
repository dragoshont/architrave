# Feature evaluation rubric (the Evaluator)

Current reviews compare original owner requests, canonical lifecycle state
(`docs/lifecycle-state.md`), changed source
and actual behavior. Do not demand SPEC/REQ rows or delivery declarations for
the current task workflow, and do not resurrect the retired completion barrier.
Legacy requirement-specific rules below apply only to explicitly selected
requirements/Run operations. Actual safety, host permissions and evidence
obligations remain binding.

The criteria the **Adversarial Judge** applies to grade a *proposal* (pre‑implementation) or *implementation* (post‑implementation) against its specs and the established design language. It is the canonical rubric for the judge gates inside the **Architrave** harness. Platform‑agnostic: it is resolved per repo through `architrave.config.json` + the matching platform knowledge pack (`knowledge/apple.md` | `microsoft.md` | `web.md`, plus `knowledge/backend.md` for the backend / infra lane, `knowledge/operations-ux.md` for operational/admin product patterns, `knowledge/yagni.md` for minimum-sufficient-change discipline, and `knowledge/learning-loop.md` for durable memory/audit behavior).

Grounded in modern eval practice:
- **Anthropic** — *evaluator–optimizer* loop with clear criteria + stopping conditions; SMART success criteria; LLM‑graded rubrics where the judge **reasons first, then emits a verdict**, graded in a **separate context from the generator**.
- **OpenAI** — an eval is a **dataset + graders**; treat it like **BDD** (specify behavior before building); combine **code graders** (deterministic) with **model graders** (LLM‑as‑judge).
- **IBM** — combine **rule‑based + semantic (LLM‑as‑judge)** evaluation; assess **each step and the whole path**, plus **policy‑adherence, prompt‑injection and bias** dimensions, not just final text.

## Applicable grading layers
Apply configured/required checks to the actual changed surface. Do not demand
uninstalled gates or irrelevant design/runtime evidence. Required safety and
release checks cannot be waived because a tool or target is unavailable.

1. **Deterministic gates (code-graded, rule-based):** `gate_runner.py checks`
   runs configured generation/build/test and configured design JSON validation;
   `reconcile` checks applicable design/code drift. Run `quality-gate` at the
   cadence in `docs/quality-check-cadence.md` (no automatic PostToolUse hook).
   `backend-checks` runs configured `backend.build`, `backend.test`, `iac.plan`
   and `iac.policy` recipes from `architrave.config.json`: it does not provide
   intrinsic migration, secret, domain-rule or IaC analysis. Require the actual
   applicable checks, Run validation and mutation-policy evidence; configuration
   and passing unrelated recipes are not proof those concerns were checked.
   Gate failures override optimistic semantic claims. Never authorize apply.
2. **Semantic gate (LLM‑as‑judge):** this rubric, applied adversarially according to `knowledge/execution-policy.md`, by one independent reviewer for R3/R4 (two of different families, both PASS, only when `review.crossFamily` is true). R2 uses one fresh-context reviewer. Low-risk mechanical work may close with deterministic evidence only when every acceptance criterion is mechanically decided and no semantic/high-risk floor applies. Model choice belongs to the user and host.

## Before grading
Grade against original owner/domain sources, current canonical tasks/criteria
and corrections, plus applicable contracts. Only explicitly selected legacy
requirements operations use the configured requirements file or `SPEC.md` REQ
rows as their record. Derive only missing
checks needed to decide the result; do not require other intake or planning
documents. Load only relevant repository
sources and rubric dimensions. For knowledge work, do not invent a UI lane.
Compare original owner messages and attached reference assets with that acceptance
and docs, retaining source identities/digests and any genuine permission grants.
An agent-narrowed SPEC is not a replacement for original owner intent.
Missing original sources stay unverified, not implicitly waived.
Apply **Specifications** in `knowledge/execution-policy.md` in both directions:
every distinct owner outcome is covered and every active row is justified by
the request. Missing outcomes, invented scope and acceptance satisfiable through
agent steps/tests/artifact counts while the intended behavior is absent are
Major findings; accepting such a substitute as delivered is a Blocker.
Grade prerequisites against the affected criterion, not blanket completion
holds. Do not demand another planning file or use a keyword/word-count score
as proof of specification quality.
Check discriminating adverse cases and row-to-detail bindings; unlinked detail
does not silently override the authoritative acceptance. Distinguish an
implementer's selected slice from a requirement or grant explicitly given by
the owner. A passing focused test does not satisfy missing required readback.

Reconcile source rules, derived contract/code and the exact current authoritative
acceptance in both directions, including original state transitions, external
ownership and conditional branches. Apply the Specifications policy and, for
relevant backend boundaries, its replay/identity/lifecycle guidance:
- Require concrete discriminating scenarios with starting state, action, expected
  transition/result and cited source rule. Contrast availability with selection
  and ongoing validity, due with expiry, retained duplicate with changed-content
  conflict, and saved approval/completion with current applicability.
- Inspect the normal composed producer/consumer path, not only helper existence:
  actual caller/wiring, serialization/hash preimage, consuming validation and
  resulting state. Check that corrections reach current acceptance and handoff;
  a later note cannot leave contradictory delivery claims authoritative.
- Label source-only inspection separately from observed execution and installed
  delivery. Schema validity, unit counts and source-string assertions cannot
  close end-to-end claims. Unobserved required scenarios remain unverified;
  do not invent provider results or new test substitutes to obtain a PASS.

Lost distinctions, dropped branches, invented obligations or contradictory
current acceptance are Major; accepting them as delivered or using them to
bypass permission is a Blocker. These are semantic judgments requiring cited
evidence, not new keyword gates or proof of automatic prevention.

## Rubric dimensions
Score each **Pass / Concern / Fail** with a severity and cite evidence (a spec line, pack section, or doc rule).

1. **Spec & acceptance‑criteria conformance** — every requested criterion met;
   no scope drift; honest about unfinished work. Grade the behavior against the
   current source-backed tasks and acceptance, not mandatory REQ rows.
   Claiming delivery while requested behavior is missing/unverified, or
   silently discarding an owner correction instead of updating current
   acceptance through the selected API, is a Blocker. Code ready progress is
   not release/runtime acceptance. Missing other planning documents
   are not findings; scope mistakes and unverified claims are.
   Required non-trivial board startup includes direct work: verify one scoped
   board was opened and read before implementation, or an explicit unavailable/
   denied outcome without a fabricated panel. Assigned children/reviewers do not
   create recursive boards. An explicit, reviewed unavailable-board outcome is
   acceptable without claiming display. Unavailable required delivery, visual
   or integration observation cannot count as PASS.
2. **Option comparison & recommended-plan quality** — one bounded comparison
   only when viable options genuinely differ on material architecture,
   dependency, migration, data-loss, security or deployment risk, or when a
   repeated failure needs a discriminating recovery. A risky domain with one
   obvious option, and routine bounded implementation, need no tournament,
   separate plan or recorded YAGNI rung. The result binds to that task, failure
   and source and feeds one disposition and next action; one allowance per
   decision survives retries and renamed successors, and rewording a failure
   does not renew it. For consequential decisions, require evidence-backed
   justification, not a particular document format. Choosing a high-risk option
   without justification is a Blocker.
3. **Durable Run and phase observability** — applicable when adopted work needs
   resumability or external operations. Use canonical API-owned state, events,
   truthful checkpoints and required evidence; views are on-demand projections,
   not additional files to maintain. Ordinary direct source work does not need
   a Run or phase ledger merely because it is non-trivial; current canonical
   tasks and original sources retain scope and acceptance.
   Required scoped mutation grants, consent, receipts and uncertain-side-effect
   recovery remain mandatory. Repeating completed work, manual state edits or
   false completion is a Blocker.
   A truthful terminal blocked/waiting/handoff outcome is not delivery
   acceptance. Do not demand unrelated program completion to report that
   outcome, or elevate a proposed improvement into active scope before owner
   agreement. Automated continuation is not owner authorization.
4. **YAGNI / minimum-sufficient-change** — the proposal uses the ladder in `knowledge/yagni.md`: skip/delete first, reuse existing repo source of truth, prefer native/platform and standard library, use installed dependencies before new ones, and add new abstractions/dependencies/config only with current evidence. Speculative layers, one-implementation interfaces, unused flags, wrapper-only services, decorative scaffolding, and future-proofing without a current criterion are Major concerns or Blockers. Do not punish enabling practices: refactoring, contracts, tests, validation, security, accessibility, design-token reconciliation, and root-cause/durable fixes for a recurring problem (a deeper change that removes a recurring cause is **not** over-engineering).
4b. **Root-cause & durability (the counterweight to YAGNI)** — for a defect, outage, regression, or recurring/systemic problem, the work diagnoses the **cause**, not just the symptom: the acceptance criteria target the cause, recurrence was checked (prior runs/lessons/"it broke again"), and the underlying mechanism is named and grounded in evidence/standard. A symptom-only patch presented as the *solution* to a recurring or systemic problem is a **Blocker**; a stopgap is acceptable **only** when explicitly labeled as such with the durable fix written down and tracked. Grounded in SRE postmortem culture (fix the cause) + Five-Whys RCA. Do not penalize a correctly-labeled, user-accepted stopgap, and do not penalize a durable fix as "too big" when it removes a recurring cause.
4c. **Execution-policy fitness** — delegation is bounded to isolation, parallelism, permissions, expertise, or independent context; WorkPackets omit model-selection guidance; context and outputs are bounded; required verification follows task risk. A host-selected model never replaces gates. A verification level below a mandatory safety floor, duplicated reviewer identity presented as independent review, or agent-harness shell-out from canonical policy is a Major or Blocker depending on impact.
5. **Design‑language conformance** — reproduces the existing Storybook component + the `config.designMap` glossary entry (anatomy, tokens, iconography, subtle cues — **no reinvented component, no parallel abstraction**); values come from `config.tokens`, not hard‑coded; `config.designMap` kept in sync.
5. **Platform conformance** — idiomatic for `config.platform` per the knowledge pack (native components/navigation, typography, semantic color + theming for the platform's appearance modes); no platform‑foreign idioms. **On Apple or Windows platforms, also grade against the matching constitution (`constitution-apple.md` / `constitution-windows.md`): the native component catalog (Apple toolbar/sidebar ≤ 2 levels/`Table`; Windows command bar/`NavigationView`/`DataGrid`; button roles/prominence, menu‑bar/command parity), the verbatim type tables/ramp, materials placement (Liquid Glass functional‑layer / Mica·Acrylic·Smoke), the active‑state model, and the screenshot conformance‑audit — reinventing a catalog component, copying a cross‑platform screenshot's chrome, or shipping the wrong platform's type sizes is a Fail.** Cite the pack.
6. **Adversarial robustness & edge cases** — empty / loading / partial / error states (offline, signed‑out, no‑results, expired/revoked auth, unconfigured); concurrency/threading for the `stack`; resilience to **prompt‑injection** in tool/web/service output; never claims a capability the app can't truthfully perform.
7. **Product truth & anti-slop** — reflects real domain workflows and backend/API/IaC capability; no generic SaaS filler, decorative metric cards, meaningless charts, invented KPIs, vague copy, or visual spectacle that hides scarce/blocked/failed operational states.
8. **Operations UX truth** — when the feature is operational/admin work, it follows `knowledge/operations-ux.md`: real objects are modeled separately; onboarding/setup, offboarding/destructive flows, inventories, catalogs/uploads, user/team/RBAC, health/readiness, diagnostics, queues/jobs/schedules, and audit states are explicit; no status appears without source/timestamp/scope; no mutation is treated as complete without preflight and durable operation/job state; no destructive flow ships without impact summary, confirmation, recovery/receipt, and audit.
9. **Security (OWASP) & policy** — no private/undocumented APIs, scraping, hidden/background behavior, or unauthorized network actions beyond the repo's stated policy; secrets only in the repo's ignored secret store, **never in code/logs**; input validated at boundaries.
10. **Accessibility** — screen‑reader labels/order (VoiceOver / Narrator / AT), full keyboard reachability, no color‑only meaning, reduced‑motion respected, contrast + hit‑target minimums **per the platform pack**.
11. **Design↔code reconciliation** — `gates/gate_runner.py reconcile` clean: generated‑from‑tokens output matches committed code; any design‑value change went through `config.tokens` first.
12. **Tests** — the repo's test pattern (`config.test`); cover the new logic **plus ≥ 1 adversarial/edge case** and capability honesty; deterministic and green.
13. **Verification & ground truth** — `gates/gate_runner.py checks` green; for UI, a screenshot (`config.screenshot`) matches the Storybook reference; sibling‑instance consistency sweep done.
    Preserve original visual-reference identity/digest and grade actual intended
    rendered width and component coverage separately from prose completeness.
    Missing reference assets, off-width renders and structural-only checks do
    not establish visual acceptance.
14. **Learning/audit trail** — inspect learning only when it is updated, and
    durable evidence only when it decides safety, release or recovery truth.
    Do not require a lesson, intake, tournament, plan or summary file for every
    change. Reuse existing checks and source-bound evidence without duplicate
    receipts for routine source edits. Missing optional artifacts are not
    findings. Missing required release/mutation evidence or promoted rules
    without validation, redaction or approval remain Major/Blocker findings.

15. **Delivery focus and verification cadence** — durable state, gates, and review
    artifacts support a product increment; they do not substitute for one.
    Product work prioritizes a real vertical slice, uses targeted checks during
    development, and reserves full configured gates for integration/release,
    completion, or mandatory risk floors. More than two consecutive support-only
    tasks, repeated full gates on unchanged source without a hypothesis, or
    status reporting led by artifact counts is a Major concern and becomes a
    Blocker when it displaces an available product acceptance criterion.
    Rewriting known-working behavior without a recorded reference and a parity
    test on the real flow before hardening is a Major concern.
    Invented precaution gates (fresh VM backups for routine authorized experiments,
    evidence of creation before authorized creation, duplicate phase approvals)
    are Major, and Blockers when they displace an available acceptance action.
    Preserve real host/Run/legal/destructive-operation constraints. Prefer supported
    target-only window navigation by the existing exclusive input owner; missing
    windows is not policy denial and does not invalidate independent CLI capability.
    A screenshot is not VM recovery proof. Reconcile timed-out mutations before
    retry, not with another backup ceremony. Distinguish instruction sent,
    execution started, observed result and accepted outcome; pending delegation
    or source-only tests cannot establish installed/native delivery.
    Repeated signing approval for a current matching owner grant is an invented
    gate, not mandatory safety. Existing-identity build/sign/stage grants must
    be scoped, persisted and checked for limits/expiry/revocation; new operations
    need coverage, and actual host/keychain/Run confirmation cannot be bypassed.
    An unanswered redundant ask does not revoke an existing scoped grant or
    authorize a fake fallback. Unrequested fixtures/fakes/mocks/stubs,
    canned/replayed fresh-result substitutes or feature/integration flags
    (including test-only substitutes) are Major and Blockers when they replace
    required execution. Explicitly approved official local DTS/Azurite and
    dev-to-Azure selection are valid. Requested algorithms/cache/history are
    not fake integrations, but cannot impersonate a fresh required run.

16. **Diagnostics, protocol leniency, and product copy** — failures carry the
    specific step and reason (redacted); collapsing distinct causes into one
    generic failure code is a Major concern and a Blocker on the primary
    criterion's path. Third-party protocol input is parsed leniently (unknown
    fields/messages ignored, failure only on malformed required data);
    exact-key-set parsing or catch-all rejection of a third-party bridge is a
    Major concern. Internal evidence, spec, status, certification, or receipt
    language in user-facing UI strings is a Major concern.

### Backend‑lane dimensions (apply when `config.backend` / `config.iac` are set — see `knowledge/backend.md`)
Domain/service review and read-only application audit also apply when requested
without adoption. Check contextual vocabulary, source-backed rules/exceptions,
actual ownership and consistency, invariant enforcement through composed paths,
and honest translation/unknown states. Do not equate completion with approval,
code with business authority, services with contexts, or class names with DDD.
Positive/negative and applicable race/retry scenarios must distinguish correct
behavior from code/tests sharing a wrong interpretation.

Audit findings cite the applicable source rule and actual ADR status, exact
code/ref, scenario/reproducer, severity/impact, confidence/blind spots, legitimate
alternative and discriminating evidence, minimal remedy/migration risk and a
falsifying test. Use `confirmed violation`, `supported concern`,
`unknown/needs domain input`, `valid alternative/no violation`, `not applicable`.
Keep coverage separate from findings and verdict; no compliance percentage.
Missing evidence is not noncompliance. Valid functional/procedural designs,
monoliths, cross-object transactions and justified local representations must
not fail merely for departing from an OO/layering preference. No target edits,
migrations or repair attempts during audit; remedies need separate authorization.

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
- **PASS** — all acceptance criteria met, **zero Blockers**, deterministic gates green, design↔code reconciled when applicable, and the risk-based verification policy is met. R2 requires one fresh reviewer; R3/R4 require one independent review, or two different families with `review.crossFamily`.
- **REVISE** — fixable issues (≥ 1 Blocker/Major) with concrete required fixes.
- **FAIL** — fundamentally off‑spec or off‑pattern (reinvented an existing component, dishonest capability, policy/security violation).

## Bias mitigation (judge discipline)
- Judge in a **separate context** from the implementer; never grade your own reasoning.
- **Reason first, then emit the verdict.** Cite evidence for every finding.
- Don't reward verbosity or confident tone; deterministic‑gate results outrank claims.
- For consequential analysis, apply execution policy's **Evidence-first analysis**
  to the resulting actions and artifacts: source precedence and passage
  entailment, genuinely unresolved vs settled owner decisions, propagated
  corrections, capacity-constrained forecasts, handoff inputs and retained
  revision assets. Reuse existing semantic cases; add only uncovered cases.
  Necessary questions are not defects, lexical question counts are not necessity
  scores, and transport success without a substantive answer settles nothing.
  Distinguish structural, inspected, rendered, runtime and owner-accepted evidence;
  reviewer identity/verdict verification is not proof of substantive quality.
- Consensus is not evidence: a high finding is resolved only by a verifiable commit, check or source, verified by someone other than the implementer; deferral or accepted risk needs a quoted owner acknowledgement. The `requirements` gate enforces this for the Findings table.
- For best‑of‑N selection (optional): compare candidates **pairwise with order‑swapping** to cancel position bias; the pointwise rubric above still decides final acceptance.

## Stopping condition (human‑in‑the‑loop)
The harness caps each judge gate at **3 revise loops**. Two semantic reopens of
the same slice require one consolidated fix batch. On the 3rd consecutive
non-PASS, stop and escalate once with the complete findings rather than opening
another micro-delta.

## Required judge output
Start the report with a line `Verdict: PASS | REVISE | FAIL` and a one-line
rationale (the `requirements` gate reads this line from the reviewer session's
report; quoted or mid-sentence verdicts are ignored), then only actionable
findings (severity, path/line evidence, consequence and required fix) and any
uncovered requested criteria. A clean review needs no dimension-score table,
restated contract, exhaustive N/A list or separate report file.
