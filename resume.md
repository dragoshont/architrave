# Adaptive Execution Handoff

## State

The first Adaptive Execution Policy vertical slice is implemented and ready to commit/push on `main`.

Key architecture decisions:

- Canonical execution intent is provider-neutral and orthogonal: `modelClass`, `reasoning`, `context`, and `verification`.
- `FAST`, `BALANCED`, `DEEP`, and `CRITICAL` are convenience presets only.
- Concrete model IDs remain in user/host-local settings or ignored benchmark configuration.
- Canonical agents use the current host's structured subagent convention. They do not shell out to another harness or depend on a provider SDK.
- No execution runtime, gateway, daemon, database, model inventory, or `architrave.config.json` model block was added.
- Low-risk, mechanically verified FAST/BALANCED work may close on deterministic evidence. Semantic/high-risk work raises the verification floor; full cross-family acceptance still requires verified GPT/Copilot and Claude-family post-review.

Primary implementation surfaces:

- `knowledge/execution-policy.md`
- `agents/architrave.agent.md`
- `agents/adversarial-judge.agent.md`
- `scripts/bench-architrave.py`
- `scripts/judge-bench.py`
- `scripts/summarize-bench.py`
- `benchmarks/routing-scenarios.json`
- `benchmarks/scenarios.schema.json`
- `benchmarks/results.schema.json`
- `harness/schemas/run-summary.schema.json`
- `harness/validate-run.sh` and `harness/validate-run.ps1`
- `scripts/test-benchmark-tools.py`
- paired run-validator fixtures and public documentation

## Verified Evidence

Available Windows checks passed before handoff:

- 30 adaptive benchmark tests.
- 20 PowerShell run-validator positive/negative fixtures.
- 7 installer checks.
- PowerShell config-profile, gate, learning, promotion, stale-learning, and semantic-learning fixtures.
- Python compilation.
- Both benchmark scenario files validated against the JSON Schema.
- Run summary validated against its JSON Schema.
- All tracked JSON parsed and all 12 agent frontmatters validated.
- `git diff --check` passed.
- Exact-final independent GPT-family and Claude-family post-implementation reviews passed with no Blocker or Major findings.

Local benchmark findings:

- Luna/low FAST: 3/3 passed, model and effort honored, median 29.7 seconds, one changed LOC.
- Sol/high on the same FAST task: 3/3 passed with the same outcome, median 220.0 seconds (8.87x slower). One wall-time outlier appears to include host idle/suspension and was not treated as model compute.
- Terra/medium BALANCED after adaptive verification routing: 3/3 passed, only Terra observed, controls honored, median 234.5 seconds.
- Before the verification-floor fix, one Terra run took 885 seconds and invoked extra Sol/Claude work. The policy fix removed that unconditional semantic delegation.

Provisional local recommendation only:

- FAST: Luna/low.
- BALANCED: Terra/medium.
- Variable roles: inherit/default unless task evidence warrants specialization.
- DEEP/CRITICAL: keep strong-model and cross-family intent, but do not pin a concrete model until repeated evidence exists.

Not yet established: Terra versus fast Sol, high versus max on DEEP/CRITICAL, long-context value, unique cross-family defect yield, and role-specific concrete pins.

## Machine Caveats

- Native Claude CLI and Codex were configured to invoke `free-pilot-bridge.exe`; do not use that bridge.
- Use the current VS Code host's structured subagent invocation. Copilot-hosted Claude-family subagents are acceptable.
- CLI mechanics are isolated to the existing benchmark adapter only, not canonical routing policy.
- POSIX `.sh` execution could not run on the old Windows laptop because working Bash and `jq` were unavailable. Ubuntu CI is the required release check.
- `.architrave/bench/`, `.architrave/runs/`, and `.architrave/learning/` are intentionally ignored. Raw local benchmark traces and the detailed run artifact will not be in Git after cloning.

## New Laptop Setup

```powershell
git clone https://github.com/dragoshont/architrave.git
Set-Location architrave
git status -sb
python scripts/test-benchmark-tools.py
pwsh -NoProfile -File scripts/test-validate-run.ps1
pwsh -NoProfile -File scripts/test-installers.ps1
npx --yes ajv-cli@5 validate -s benchmarks/scenarios.schema.json -d benchmarks/routing-scenarios.json
git diff --check
```

On Linux/macOS or CI, also run:

```bash
scripts/check-manifests.sh
scripts/test-validate-run.sh
```

Do not publish/tag a release until the Ubuntu POSIX validation job is green.

## Continuation Prompt

```text
Continue the Architrave Adaptive Execution Policy work from resume.md at repository HEAD.

First read AGENTS.md, resume.md, knowledge/execution-policy.md, ROADMAP.md, and the current git status/log. Verify that the adaptive-execution commit is present on the active branch and that the working tree is clean before changing anything.

Use this VS Code instance's structured subagent convention for specialist and model-family delegation. Keep canonical policy abstract from CLI and SDK mechanics. Do not invoke native Claude CLI or Codex if they route through free-pilot-bridge.exe; do not use that bridge. Copilot-hosted Claude-family subagents are acceptable. Concrete model IDs must remain host/user-local or in ignored benchmark configuration.

Run the available deterministic checks, including the Ubuntu/POSIX checks that were unavailable on the old Windows laptop. Fix any material CI or parity findings at the root cause and rerun focused validation immediately after each edit.

Then inspect open work rather than assuming it is implemented. The next evidence tasks are:
1. Compare Terra/medium with a fast-Sol/medium BALANCED arm using at least three honored-control repeats on the same scenario.
2. Compare high versus max effort on representative DEEP and CRITICAL scenarios.
3. Evaluate cross-family judge unique Blocker/Major yield with blinded producer identity.
4. Test long context only if the host exposes observable context-tier evidence; otherwise keep it explicitly unresolved.
5. Do not implement learned routing until it measurably beats the deterministic semantic policy.

Preserve backward compatibility, deterministic gates, dual-family verification, POSIX/PowerShell parity, and the thin-conductor architecture. Do not add a runtime, model gateway, daemon, database, canonical concrete model pins, or repository model inventory.

Before finishing, run deterministic gates and independent GPT/Copilot-family plus Claude-family post-review. Update README/ROADMAP/CHANGELOG only for behavior that genuinely changes, and report unresolved experiments honestly.
```
