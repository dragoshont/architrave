# Deterministic Gates

## checks

- `scripts/test-config-profiles.sh`: PASS. Knowledge positive, missing build/test,
	invalid kind, every forbidden field, three legacy examples, and a legacy
	missing-platform negative were exercised with AJV Draft 7.
- `scripts/test-installers.sh`: PASS. Default application profile, exact
	canonical knowledge scaffold, AJV validation, copied full gates, idempotency,
	existing-config preservation, help, and invalid profile handling passed.
- `scripts/test-gates.sh`: PASS. Exact knowledge messages passed and configured
	build/test commands executed.
- `scripts/check-manifests.sh`: PASS with all existing fixtures and the new
	repository-profile fixtures.
- `scripts/test-manifest-scanner.sh`: PASS. It forces the grep fallback, proves
	a clean scan with ignored paths, proves synthetic MCP and legacy-name
	positives exit 1, and proves a scanner operational error fails closed with
	diagnostics. It optionally exercises ripgrep parity when available. The
	fixture is invoked by the manifest suite.
- Agent YAML/frontmatter and explicit knowledge-routing assertions: PASS.
- `git diff --check` and `bash -n gates/*.sh harness/*.sh tools/*.sh
	scripts/*.sh`: PASS.
- PowerShell execution is not available on this Mac. Paired scripts are wired to
	the existing Windows validation and release jobs with Node 22; execution
	remains a Phase 2 release gate.

## backend-checks

Not applicable.

## reconcile

PASS in the knowledge gate fixture with the explicit message that UI design
reconciliation is not applicable.

## other

- Canonical knowledge example validates in AJV. Python `jsonschema` was not
	installed, so the optional second local Draft-7 validator was skipped.
- Manifest scanner clean path: PASS without ripgrep installed.
- Manifest scanner adversarial path: PASS. An isolated copied repo containing a
	synthetic MCP token failed with the expected finding. The false-pass bug is
	tracked in Architrave issue #5 and fixed by a grep fallback.
- `harness/validate-run.sh` for this run: PASS.
- Plugin and marketplace descriptions are byte-equivalent and agent frontmatter
	parses: PASS.
- `CHANGELOG.md` records these changes under `Unreleased`; manifests remain
	truthfully at v0.9.1 until Phase 2.
- `.architrave/learning/repo-profile.md` was revalidated and refreshed from the
	stale v0.7.0 fact to current v0.9.1 and issue #3 working-tree evidence.
- Release workflow, plugin update, consumer migration, and direct VS Code chat
	proof belong to Phase 2 and have not started.
- Initial v0.10.0 main validation run `29121656406` exposed a PowerShell fixture
	oracle defect: `Write-Host` output was visible but not captured by `2>&1`.
	Product gates passed up to that assertion. The fixture now captures all streams
	with `*>&1`; v0.10.0 remains an immutable failed tag and the correction is
	queued as v0.10.1. Local PowerShell execution remains unavailable, so CI is the
	executable proof.
- v0.10.1 run `29121855261` made POSIX green and advanced native Windows through
	the complete schema-profile suite, then failed inside the generated knowledge
	repo's copied full gate. The fixture had discarded that gate output. A
	main-only diagnostic commit now captures the direct staged-diff preflight and
	full gate output before any further release tag.
- Local PowerShell 7.6.3 was installed after that run. It reproduced the exact
	generated `AGENTS.md` blank-line failure. `install.ps1` and `update.ps1` now
	use `Set-Content -NoNewline` for their already newline-terminated managed
	block. `test-installers.ps1` passes install, copied gates, idempotency,
	existing-config preservation, and `update.ps1 -Agents` whitespace checks.
- The exact Windows workflow command list passes locally across config,
	installer, run, learning, promotion, stale-learning, semantic-learning, and
	gate fixtures. The correction is queued as v0.10.2.
- v0.10.2 release run `29122741495` passed POSIX, native Windows, tag/version,
	and GitHub Release publication. The installed Copilot plugin updated from
	v0.9.0 to v0.10.2.
- A rooted VS Code editor session in `/Users/dragoshont/Repo/social-ops`
	returned `KIND=knowledge UI=not-configured` from the repo-local Architrave
	agent. Its log also exposed issue #6: PostToolUse success output was plain text
	and triggered `Hook command returned non-JSON output`.
- The paired quality gates now provide `--hook-json` / `-HookJson`, emit exactly
	`{"continue":true}` on success, and preserve exit-2 stderr diagnostics on
	failure. Both POSIX and PowerShell hook success/failure fixtures and the full
	dual-shell suites pass locally. The fix is queued as v0.10.3.