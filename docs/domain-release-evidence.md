# Unified domain/service extension: evidence and limits

This is the **unreleased 1.2 candidate**, not a validated 1.2.0 release.
The installed/released version remains 1.1.1. This records changes and
qualification; it is not another architecture policy or lifecycle authority.
The existing Service Architect and `knowledge/backend.md` supply guidance;
`.architrave/state.yaml` remains API-owned.

## Candidate and replacement matrix

Baseline: `e4135ef5ee1e6d500accb11809c2bb27f16ede58`, freshly fetched
`origin/main`, initially clean. Branch: `dragoshont-microsoft-domain-driven-release`.
The original input is the owner-supplied `ARCHITRAVE_1_2_DDD_RELEASE_SPEC.md`,
including its in-place replacement amendment. No release/publication is implied.

The per-source map below uses the baseline above for old locations and the
working candidate for new locations (same path unless stated). A new test or
fixture has no old instruction to replace. Validation keys:
**F** = `python scripts/test-delivery-focus.py` (structural guidance);
**I** = `python scripts/test_install_update.py` (temporary adoption/update);
**C** = `python scripts/test-codex-roles.py` (generated parity);
**B** = `python scripts/test-benchmark-tools.py` (actual artifact/scorer consumers);
**D** = `python scripts/test-domain-fidelity.py` (synthetic code paths);
**L** = `python scripts/test-lifecycle.py` (state API);
**M** = `python scripts/check_manifests.py` (complete registered suite).
**Review** means source inspection against the owner amendment and primary
source report, not automated semantic proof. The final reviews below found
corrections; integrated rechecks remain required.

| Source and old location/instruction | New authoritative location / removed overlap | Corresponding validation and boundary |
| --- | --- | --- |
| `agents/service-architect.agent.md`: grounding/design/output, technical contracts and mandatory tournament/ADR first | `Grounding and proportionality`, `One design path`, `Read-only existing-application audit`, `Output`: meaning/invariants before derived contracts; same callable role | I copies to `.github/agents/service-architect.agent.md`; D and live audit exercise source-fed reasoning; Review; native loading held |
| `knowledge/backend.md`: sections 1-3, automatic specialist chain and technical-first sequence | Sections 1-3 and 9: proportional direct work, sourced meaning/consistency, same-route audit; sections 4-8 retain safety/seams | I byte parity; D counterexamples; Review; no intrinsic domain scanner |
| `agents/architrave.agent.md`: intake/routing lacked explicit domain binding | Intake/routing points to existing Service Architect and pack; no second mechanism | F, I; Review; no live intake guarantee |
| `skills/architrave/SKILL.md`: lead summary lacked unified domain route | Lead contract points to the same role/pack and proportional source discovery | F, M packaging; Review; plugin skill load held |
| `agents/backend-planner.agent.md`: mandatory tournament/plan sequence | `Produce a proportional plan` and `Output`: source/context/invariant-bound slices; no mandatory tournament/ledger | I; Review; bounded plan reasoning not mechanically proven |
| `agents/backend-implementer.agent.md`: contract-only grounding/phase guidance | `Grounding`, `Phase discipline`, `Output`: preserve rules/exceptions/consistency and composed-path checks | I; D illustrates acceptance paths; Review |
| `skills/architrave-work/SKILL.md`: common/development handoff omitted domain bindings | Common/Development preserve scoped source, context, corrected rules and proof | F, L correction/resume tests; Review; live worker adherence held |
| `knowledge/execution-policy.md`: development/specification guidance omitted contextual invariant bindings | Existing development/specification guidance carries domain meaning through criteria/corrections | F, L; Review; no new state schema |
| `knowledge/learning-loop.md`: promotion guidance lacked domain decision distinction | Promotion guidance separates sourced domain decisions from speculative patterns | F, M learning fixtures; Review |
| `agents/adversarial-judge.agent.md`: approach/output lacked source-backed domain dispositions | `Approach`/`Output Format`: valid alternatives, decision status, unknowns, falsifiers; same verdict route | I, C; D/B substrate; Review; no compliance percentage |
| `skills/architrave-review/SKILL.md`: general review scope/output | Existing review contract includes read-only application audit and evidence-linked dispositions | F, M packaging; source-fed audit and Review; mutation not authorized |
| `gates/rubric.md`: grading/default SPEC clauses and technical-only backend assessment | `Applicable grading layers`, source-backed task acceptance and domain dimensions; actual `backend.build`/`backend.test`/`iac.plan`/`iac.policy`, no invented alias | F; selector `gates/gate_runner.py:backend` and config schema inspected; B/D support examples, not semantic enforcement |
| `.codex/agents/architrave-judge.toml`: generated old Judge body | Same generated role from canonical Judge; no separate domain reviewer | C and I `test_update_agents_codex_and_idempotency`; native Codex load held |
| `templates/AGENTS.stanza.md`: adoption routing summary | Same stanza names unified domain-aware route and read-only audit | I installed stanza inclusion; F; no second lifecycle source |
| `AGENTS.md`: repository overview/backend description | Same overview names authoritative contextual rules and existing Service Architect | F/M; Review; repository instructions not host-load proof |
| `README.md`: backend description and `Updates` plain refresh | Unified route; `Updates` distinguishes partial preservation from reconciled, authorized `--agents`/`--codex` adoption and native identity readback | I baseline-role preservation/refresh; Review; load hold explicit |
| `kit/MIGRATION.md`: `Migration Pattern` optional role refresh | Candidate-specific reconciliation, authorized replacement, actual role/pack identity and native loading | I same supported CLI route; Review; customizations never silently overwritten |
| `knowledge/yagni.md`: `Positioning consequence`, full-stack starts with contract | Same section establishes source/domain meaning before deriving contract; routine work reuses settled meaning | F/Review; no modeling ceremony |
| `ROADMAP.md`: no candidate qualification entry | Unreleased unified-domain work and outstanding qualification | Review against retained logs/holds; M version still 1.1.1 |
| `CHANGELOG.md`: no unreleased domain entry | Unreleased implementation and evidence limitations | Review; M; not a release claim |
| `plugin.json`: description | Same manifest describes source-grounded/domain-aware existing route | M manifest/version checks; no version bump |
| `.github/plugin/marketplace.json`: metadata/plugin descriptions | Same distribution metadata, one existing plugin | M; no host-load claim |
| `.claude-plugin/plugin.json`: description | Same plugin description, existing role inventory | M; native loading held |
| `.claude-plugin/marketplace.json`: metadata/plugin descriptions | Same marketplace and route | M; native loading held |
| `.codex-plugin/plugin.json`: description/interface description | Same plugin/skills inventory, unified guidance | M/C; native loading held |
| `benchmarks/README.md`: artifact/tournament counts as process quality | `Domain fidelity`, `What We Measure`, dataset/portfolio: outcomes, source-grounded contracts and explicit-only Run/learning experiments | B; Review; artifact existence is not correctness |
| `benchmarks/scenarios.json`: routine backend and other ordinary tasks required optional Run/learning paths | Same scenario IDs/checks; routine artifact requirements removed, backend status meaning precedes derived contract; explicit legacy experiments retained | B `test_routine_scenarios_do_not_require_optional_process_artifacts` and `test_explicit_experiments_and_failed_checks_retain_failure_evidence`; no actual external-repo agent trial claimed |
| `benchmarks/semantic-cases.json`: existing calibration only; D10 initially underspecified authority | Added `domain_cases` D01-D13; D10 requests exact persisted repository-relative authority path, not label | B blind/strict-protocol tests; historical actual answers remain raw 12/13 |
| `scripts/score-semantic-cases.py`: existing regular/hard/analysis modes | Same scorer adds `--domain`, blind expected-value exclusion and strict typed comparison | B `SemanticCalibrationTests`; not rationale grading |
| `scripts/test-benchmark-tools.py`: existing scorer/runner regressions | Same test classes extend domain protocol and real scenario/artifact/validation failure consumers | B; deterministic consumer checks, not agent adherence |
| `scripts/test_install_update.py`: existing adoption tests; corrected tests initially required historical `git show` at runtime (F5) | Same profile/update tests verify and load bundled real baseline bytes, prove plain preservation then explicit canonical refresh, including Codex Judge; reject corrupted fixture content | I in ordinary and depth-one current-source checkouts; no runtime history/network dependency; installer defaults unchanged; temporary copies not native load |
| `scripts/fixtures/adoption-baseline-1.1.1.json`: absent | Test-only JSON contains exactly the four baseline roles, backend pack and Codex Judge already consumed by I, with source repository/commit and per-file SHA256 | Exact Git-blob extraction/byte round-trip at authoring; I checks payload hashes before use; historical instructions are inert data outside active role/skill discovery |
| `scripts/test-lifecycle.py`: existing scoped corrections/recovery tests | `test_domain_correction_stales_late_worker_and_proof_not_unrelated_work`, `test_domain_resume_keeps_context_exception_and_resolved_source_without_new_store` | L actual store/CLI; live interruption still unobserved |
| `scripts/test-delivery-focus.py`: assertions required retired default REQ ceremony | Existing required-guidance map tests source-backed tasks, missing behavior and progress vs acceptance | F; structural consistency only |
| `scripts/check_manifests.py`: existing Python inventory/full suite | Same inventory and suite register domain fixture Python and domain tests | M complete suite; no checker framework added |
| `benchmarks/fixtures/domain-audit/domain.md`: absent | New synthetic accepted R1-R4, proposed ADR and unknown policy inputs | D and one source-fed audit; not owner-app authority |
| `benchmarks/fixtures/domain-audit/review.py`: absent | New intentionally defective approval/version paths and valid controls | D negative/positive/race reproduction; defects not repaired |
| `benchmarks/fixtures/domain-audit/status.ts`: absent | New defective legacy translation plus valid functional guards/unknown-preserving translation | D executes TypeScript; live audit; no OOP mandate |
| `scripts/test-domain-fidelity.py`: absent | New focused actual Python/TypeScript counterexample and control tests | D (4 tests); not an agent grader |
| `docs/domain-release-evidence.md`: absent | This evidence map, research corrections and separate source/behavior/host/release status | Review against retained primary report, logs and audit; no competing policy or ledger |

Adopted canonical roles live under `.github/agents/`; shared pack/rubric/stanza
locations retain their names. Plugin skills come from the host's effective
plugin path; generated Codex roles require `--codex`. Follow the reconciled,
authorized migration in `README.md` and `kit/MIGRATION.md`. Default-preserving
update is deliberately partial. Compare actual content identities and reviewed
local deltas, then verify native loading before declaring that only the unified
route is active on a target. Byte equality alone cannot close that criterion.

Modeling concepts are questions, not mandatory structures: identity may warrant
an entity, value equality a value type, atomic rules a consistency boundary,
business behavior a function/service, meaningful occurrences events. Functional/
procedural modules, transactions and monoliths remain valid. No new dependency,
DDD configuration flag, approval stage or lifecycle field is justified.

## Research qualification

Independent read-only verification covered all R01-R20 references on 2026-11-12.
Retained full report SHA256:
`7d35ca273193627c0fc93b8c6f5c1e7370c5f83c5dd750fb5e89c5a495376d23`.
Sources are evidence, not permission. Access failure is not fabrication evidence;
bibliographic verification is not a full-text read.

| Reference | Inspected primary evidence | Consequence/limit |
| --- | --- | --- |
| R01 [Bounded Context](https://martinfowler.com/bliki/BoundedContext.html) | Main Fowler article | Context-specific models/language; objects or functions; not service-per-context |
| R02 [DDD Aggregate](https://martinfowler.com/bliki/DDD_Aggregate.html) | Complete short Fowler article | Consistency unit, not aggregate-per-table or compulsory class |
| R03 [Microsoft tactical DDD](https://learn.microsoft.com/en-us/azure/architecture/microservices/model/tactical-domain-driven-design) | Entity/value/aggregate/service/event sections | Distinguish rules from orchestration; microservices advice is contextual |
| R04 [DDD Crew starter](https://github.com/ddd-crew/ddd-starter-modelling-process) | Introduction, adaptation and early discovery | Iterative/customizable; no required eight-step workflow |
| R05 [Context mapping](https://github.com/ddd-crew/context-mapping) | Primary README and [Virtual DDD republication](https://virtualddd.com/ddd-crew/context-mapping/) retrieved | Translation and deliberate sharing are alternatives; the republication's linked `https://ddd-crew.github.io/context-mapping/` returned 404, not the republication itself |
| R06 [Bounded Context Canvas](https://github.com/ddd-crew/bounded-context-canvas) | Purpose, language, communication, decisions and unknowns | Useful questions, not required canvas, bus or async workflow |
| R07 [Aggregate Design Canvas](https://github.com/ddd-crew/aggregate-design-canvas) | README sections 1-9 | Invariants, exceptions and concurrency; not compulsory event sourcing |
| R08 [Spec Kit](https://github.github.com/spec-kit/quickstart.html) | Quickstart | Intent clarity only; do not import lifecycle/ceremony |
| R09 [OpenSpec](https://openspec.dev/docs/schemas/spec-driven) | Artifact/proposal/scenario guidance | No invented requirements or second schema/state |
| R10 [Automating Domain-Driven Design](https://arxiv.org/html/2603.26244v1) | Full-text methods/results/discussion/limits | One industrial case, error propagation/over-fragmentation; not universal benefit |
| R11 ICSA Event Storming experiment | Official conference abstract/program only | Abstract reports 240 students/60 teams and critical omissions; full-text effects unverified |
| R12 [DOI](https://doi.org/10.1109/TSE.2026.3706446) | Publisher-deposited Crossref bibliography only | Correct title: *Better Together: An LLM-Assisted Approach to Designing Software Architectures Using Attribute-Driven Design*, IEEE TSE 52(10), 2970-2985; no methods/results claim |
| R13 [ADR violation detection](https://arxiv.org/html/2602.07609v1) | Full-text methods/results/limitations | Reject no-retrieved-evidence-to-noncompliance and Proposed/WIP-to-accepted shortcuts |
| R14 [Clean Architecture conformance](https://doi.org/10.3390/computers15100657) | Crossref title/abstract; publisher 403 | Not universal DDD evidence; full-text methods/metrics unverified |
| R15 [Springer DOI](https://doi.org/10.1007/s10515-026-00638-5) | Publisher 406, metadata 429 | Access-limited/unverified; no substantive attribution |
| R16 [SmellBench](https://arxiv.org/html/2605.07001v2) | Full-text methods/results/discussion and partial threats | 47.7% means 31/65 detector findings including cascading/false-positive reductions, not confirmed defects; reject repair-first audit lifecycle |
| R17 [ArchUnit](https://www.archunit.org/), [ArchUnitNET](https://archunitnet.readthedocs.io/en/stable/), [ArchUnitPython](https://www.archunit.net/python/), [Import Linter](https://import-linter.readthedocs.io/en/stable/), [dependency-cruiser](https://github.com/sverweij/dependency-cruiser) | Respective overview/configuration/scope evidence | Python project is real/distinct; match languages and declared rules; no installation justified or maintenance qualification claimed |
| R18 [Microsoft mutation testing](https://learn.microsoft.com/en-us/dotnet/core/testing/mutation-testing), [Stryker](https://stryker-mutator.io/docs/) | Microsoft article and Stryker introduction | Test sensitivity is not business correctness; no score/dependency mandate |
| R19 [fast-check](https://fast-check.dev/docs/introduction/), [Hypothesis](https://hypothesis.readthedocs.io/en/latest/) | Introduction/overview | Optional property-testing methods, not required architecture tooling |
| R20 [Multiple Canonical Models](https://martinfowler.com/bliki/MultipleCanonicalModels.html), R01/R05 | Complete Fowler article and context/translation sources | Exclude supplied fabricated title; local representations need not duplicate policy ownership |

R10/R13/R16 are preprints, not independently verified peer-reviewed results.
R12 is Attribute-Driven Design, not Domain-Driven Design. R13 agreement over
shared retrieval is not independent correctness. Detector-count reduction is
not production defect resolution. These cautions inform audit judgments, not
new product machinery.

## Runnable qualification and interpretation

Use Python 3.11+ for complete release checks; TypeScript execution needs Node
22.7+ with default module detection and `--experimental-strip-types`.
Node 22.23.5 was exercised locally; older versions were not executed here.

```text
python scripts/test-domain-fidelity.py
python scripts/test-benchmark-tools.py SemanticCalibrationTests
python scripts/test-lifecycle.py
python scripts/test_install_update.py
python scripts/test-codex-roles.py
python scripts/check_manifests.py
python gates/gate_runner.py quality-gate
python scripts/score-semantic-cases.py --domain --blind
python scripts/score-semantic-cases.py --domain <answers.json>
```

The explicitly synthetic `benchmarks/fixtures/domain-audit` application contains
intentional defects: workflow completion bypasses evidence; evidence revocation
changes the version but approval commit ignores it; external unknown/completed
states become approval. Valid functional TypeScript guards/translations and an
unspecified retention policy provide counterevidence/unknown cases.
Tests execute positive, negative, actor, translation and synchronized concurrent
paths. A passing substrate test reproduces the counterexample: it does **not**
mean the defect is fixed or an agent recognized it.

The existing scorer's `--domain` mode checks typed final artifacts and nonempty
rationale on 13 blind cases. It does not evaluate rationale quality, actual tool
actions, costs or runtime correctness. Expected answers stay out of blind output.
Live audit/review must separately inspect original rules and composed code.
Temporary installer byte equality is not native host loading.

## Release status and holds

Source implementation is written. Both independent final reviews of frozen
candidate `sha256:bd98e611505a21ef206e4aa0f947c8a72b423b76bbff00523ade2db688599b17`
returned **REVISE**; this working-tree correction still needs integrated checks
and independent rechecks. Both contexts reported GPT-6 Astra (`gpt-6-astra`),
so different-family qualification is not established.

The following actually ran on 2026-11-12 with session-local Python 3.13.18 and
Node 22.23.5. Full-suite outcomes describe the retained pre-correction candidate
and immutable baseline separately, not an unexecuted corrected-candidate suite:

| Executed check | Observed outcome | Evidence boundary |
| --- | --- | --- |
| Current `scripts/check_manifests.py` (complete, not scan-only) | PASS, versions synchronized at 1.1.1; `ddd-current-manifests.log` | Pre-correction candidate; all registered runtime/lifecycle/dashboard/installer/role fixtures, not loaded-host proof |
| Immutable baseline `scripts/check_manifests.py` (complete, separate checkout) | PASS; `ddd-immutable-baseline-manifests.log` | Baseline source qualification, not matched agent trials |
| `scripts/test-domain-fidelity.py` | 4 tests passed, TypeScript executed (not skipped) | Synthetic actual code counterexamples/alternatives, not an agent grader |
| `scripts/test-benchmark-tools.py SemanticCalibrationTests` | 7 tests passed | Answer/grader integrity, not rationale validity |
| Two new lifecycle domain correction/resume selectors | 2 tests passed | Actual store/CLI behavior, not live model interruption performance |
| Existing installer profile/update selectors and `test-codex-roles.py` | Passed | Temporary canonical byte restoration and generated-role distribution |
| `scripts/test-delivery-focus.py`, generator `--check`, skill after-evaluation | Passed | Structural/word-budget checks; skill proposal still needs human approval |
| `gates/gate_runner.py quality-gate` | PASS, knowledge profile; `ddd-current-quality.log` | Pre-correction configuration validity; UI design checks not applicable, no built-in domain scanner |

Full logs are retained under coordinator session
`1ea84954-12b8-4284-ba43-902c1d60402f/files/`. An earlier interrupted baseline
run mixed changing sources and remains invalid; the separate immutable baseline
PASS above replaces it as baseline source evidence, not as improvement evidence.

One actual source-fed synthetic audit is retained in session
`5223e5ab-977e-4567-9215-cbdc25865b9c/files/audit.md` and `answers.json`.
It reproduced source-backed defects and identified valid alternatives and
unknowns. Audit SHA256:
`9968098d2e2737a2b6bed10513711b974e6a712dfa5f805d842a491616106182`;
answers SHA256:
`7837d2a56636d72c8d030bbdf1535a533373bf02ec1500b894659c364bf6c42b`.
The unchanged answers scored **raw 12/13, mechanical only**. D10 used
`canonical state` instead of the exact `.architrave/state.yaml` literal, despite
correctly retaining the resolved decision and rejecting stale `tasks.md`.
Its corrected blind prompt now explicitly requests the file path; neither the
old answer nor its score is rewritten. This is sample size one, not a native
host load, repeated matched comparison or measured improvement.

A separate source-fed proportionality probe actually changed only a session
artifact's `requestTimeoutSeconds` from 5 to 8, preserving `retryCount: 2`.
Full JSON and byte-delta checks passed; no added question, approval, agent or
modeling ceremony occurred. Candidate lead/skill hashes stayed stable; the host
reported `gpt-6-astra`. Report:
`4f83d521-09e6-480f-a5a8-2d608bb2fcb9/files/ddd-proportionality-report.md`,
SHA256 `ff02be10e75634cc28404ce873ccab7b887929c4d9a30550fb1b7c4cf2e672e9`.
This is one synthetic local-edit trial, not a loaded-host test, repeated matched
comparison or improvement claim.

Independent reports are retained in sessions
`ac7d0f73-f279-4bd8-9a80-1c4fefead56b/files/ddd-final-review-1.md` and
`7fe4c8c8-55b6-4097-bc16-57c6256f5c46/files/ddd-final-review-2.md`.
Accepted findings cover safe role adoption, actual gate fields, routine
benchmark ceremony, D10 protocol, R05 attribution and this per-source map.
Corrections are not reviewer PASS; all mandatory release acceptance remains
evidence-dependent.

The first integrated recheck resolved F1-F4 but reproduced **F5**: both installer
selectors failed in a depth-one current-source checkout because their runtime
`git show` required the unavailable baseline object. The bounded F5 correction
bundles only the six already-consumed real 1.1.1 files as inert JSON test data.
They were extracted byte-for-byte from
`https://github.com/dragoshont/architrave` at the baseline commit above; the bundle
records that provenance and each payload's SHA256, checked before test use.
No installer behavior, active role inventory, dependency or runtime fetch changed.

On 2026-11-12 the same two selectors passed both normally and in an actual
depth-one clone of a temporary snapshot of all current tracked sources plus
untracked candidate files. The clone reported `--is-shallow-repository=true`;
`git cat-file -e e4135ef5ee1e6d500accb11809c2bb27f16ede58^{commit}` returned 128.
Plain-update preservation, authorized `--agents`/`--codex` canonical refresh,
idempotency and custom-role safety assertions remain intact. The new
corrupted-payload regression passed in both checkouts; delivery-focus and
`git diff --check` passed. Complete extraction, before/after commands and outputs
are retained in worker session
`87442eb4-db8e-4d6e-a6e7-21894694bf67/files/f5-baseline-provenance.log`,
`f5-shallow-before.log`, `f5-shallow-after.log` and `f5-normal-checks.log`.
Temporary snapshot/clone paths were removed; no product commit was made.
These are focused source checks, not final full-suite integration, independent
affected recheck, native host loading or release qualification; those remain
separate parent-owned work and holds.

- Architrave is the known current implementation/validation target. A separate
  application audit is **deferred**, not a prerequisite or blocker for this
  repository's source work. Real-application/held-out release qualification
  remains unexecuted; synthetic examples do not satisfy that evidence gap.
- Host loading: **unverified**. Copilot/Codex/Claude executables are unavailable
  on this host's PATH; source and temporary installation checks cannot substitute.
  Loaded installed 1.1.1 Service Architect SHA256 was
  `93fc477ffc8f5994b757dcd4c9aad36d999ceae7146939386253480a769bf11c`,
  equal to baseline source, not the current modified role.
- Matched repeated baseline/current trials and measured benefit: **not yet
  established**. No improvement, causal or compliance-percentage claim is made.
- Native C#, declared dependency-cycle enforcement, real-app held-out examples,
  broad live interruption behavior and other unexecuted H/I scenarios remain
  unverified, not implicit passes.
- Independent integrated rechecks and applicable different-family proof remain
  held; two independent GPT-family contexts do not establish the latter.
- Version bump/release/publication: **held** until required qualification and
  scoped authorization. Skill-improvement proposals need human approval;
  evaluation is not merge consent.

An audit must leave its target unchanged. Recommendations route through
authorized task corrections, not audit-time repairs.
