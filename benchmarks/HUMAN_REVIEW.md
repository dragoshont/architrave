# Human Review Template

Human review is not a replacement for deterministic gates. It catches things that tests and LLM judges routinely miss: awkward UX, maintainability risk, generic product thinking, over-build, and whether a senior reviewer would accept the change.

Review a small stratified sample first: at least one row per lane and every run where deterministic validation failed or the LLM judge returned `REVISE`/`FAIL`.

## Review Instructions

1. Open the row's `cell_dir`.
2. Read `prompt.md`, `session.md` if present, `diff.patch`, validation logs, and summary row.
3. Score without knowing which arm produced the run when possible. For pairwise review, randomize A/B order.
4. Prefer concrete evidence over vibes. Cite file paths or artifact names.
5. Convert recurring failures into new benchmark scenarios or knowledge/rubric changes.

## Single-Run Annotation

```yaml
run_id:
scenario:
arm_blinded: A|B|unknown
reviewer:
date:

scores:
  correctness: 0 # 0-5
  implementation_clarity: 0
  yagni_minimality: 0
  repo_fit: 0
  process_quality: 0
  ux_or_product_quality: 0

verdict: PASS|REVISE|FAIL
would_accept_pr: true|false
needs_followup_scenario: true|false

evidence:
  - "..."
blockers:
  - "..."
followup_scenario_seed:
  id:
  prompt:
  expected_failure_mode:
```

## Pairwise Annotation

```yaml
scenario:
reviewer:
date:
left_run:
right_run:
winner: left|right|tie|neither
why:
  - "..."
dimension_winners:
  correctness: left|right|tie|neither
  clarity: left|right|tie|neither
  yagni: left|right|tie|neither
  repo_fit: left|right|tie|neither
  process: left|right|tie|neither
```

## Promotion Rule

If two human reviews identify the same failure mode, add or update one of:

- a benchmark scenario;
- `knowledge/*.md`;
- `gates/rubric.md`;
- an agent prompt;
- repo-specific `AGENTS.md` / `.github/instructions`.

Then rerun the frozen scenario before declaring the loop improvement successful.