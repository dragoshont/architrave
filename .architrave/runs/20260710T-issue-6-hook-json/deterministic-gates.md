# Deterministic Gates

## checks

- POSIX and PowerShell focused gate fixtures: PASS.
- Full manifest and exact Windows-workflow PowerShell suites: PASS after repair.
- POSIX updater copies `gates/hooks/design-guard.json` into the active
	`.github/hooks/design-guard.json`: PASS.
- PowerShell updater copies `design-guard.windows.json` into the active hook:
	PASS.
- POSIX success output is a 17-byte UTF-8 `{"continue":true}` record with no
	newline or stderr; failure has empty stdout, diagnostic stderr, and exit 2:
	PASS.
- PowerShell uses direct .NET redirected process pipes and raw UTF-8 byte-array
	comparison to assert the same 17-byte contract: PASS.
- Direct CLI output still includes quick-check details plus the human reminder:
	PASS.
- Fresh POSIX and PowerShell installs create the active platform hook: PASS.
- Both updaters replace the active platform hook and fail closed when delivery
	is impossible: PASS.

## backend-checks

Not applicable.

## reconcile

Not applicable to hook contract.

## other

- Rooted Social Ops editor session proves knowledge routing.
- v0.10.2 log proves the original non-JSON warning.
- README updater contract, issue #3 phase/runtime facts, and repo profile were
	refreshed: PASS.
- Both issue #3 and issue #6 run validators: PASS.
- Final full POSIX and exact Windows-workflow PowerShell suites: PASS.
- Semantic gates, release, active-hook re-copy, and warning-free rerun: pending.