# Recommended Plan

## Summary

Implement one strict knowledge profile, test the generated contract on POSIX and
PowerShell, release it, migrate `social-ops`, and verify the real VS Code editor
chat path.

## Implementation Sequence

1. Add the schema branch, canonical example, and exhaustive profile fixtures.
2. Add explicit installer profile support and end-to-end generated-config tests.
3. Make paired gates and relevant agents profile-aware.
4. Update docs and release metadata.
5. Run deterministic and dual semantic gates.
6. Release v0.10.0, refresh `social-ops` with agents, and run direct UI proof.

## Test Strategy

- Every forbidden field fails individually.
- Missing knowledge build/test and invalid kinds fail.
- Existing application examples remain valid.
- Both installers produce a config that validates and passes the copied gates.
- Linux and Windows workflow fixtures pass.
- A unique-marker `code chat` request proves repo-local agent routing.

## Rollback / Recovery

Revert the release commit and keep `social-ops` on its v0.9.1 compatibility
config. Existing application configs never require migration.

## Human Approval Needed

The third GPT proposal review remained REVISE. The user instructed autonomous
continuation; all remaining findings are mandatory implementation scope.