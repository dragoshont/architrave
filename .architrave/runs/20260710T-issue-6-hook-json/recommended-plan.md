# Recommended Plan

## Summary

Add structured hook mode to paired quality gates, activate it in both manifests,
refresh active hooks during updates, and verify exact process-level streams.

## Implementation Sequence

1. Add structured mode while preserving direct CLI output.
2. Point platform hook manifests at structured mode.
3. Update both installers/updaters to deliver active platform hooks.
4. Add exact stdout/stderr, exit-code, install, and update fixtures.
5. Run full dual-shell suites, judge, release, re-copy, and rerun editor chat.

## Test Strategy

- Byte-exact success JSON with no stderr.
- Corrupt config: empty stdout, diagnostic stderr, exit 2.
- Direct CLI reminder remains visible.
- POSIX and PowerShell updater output matches the active platform hook source.

## Rollback / Recovery

Revert to the v0.10.2 hook command; agent routing remains functional but logs a
non-blocking warning.

## Human Approval Needed

None. This is a deterministic compatibility fix.