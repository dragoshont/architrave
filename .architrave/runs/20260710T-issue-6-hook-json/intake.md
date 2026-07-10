# Intake

## Understanding

Fix Architrave's PostToolUse hook so successful output is valid JSON, failures
block with diagnostics, and existing adopted repositories receive the active
hook through the normal updater.

## Acceptance Criteria

1. Success emits exactly `{"continue":true}` on stdout.
2. Invalid config emits diagnostics on stderr, no stdout, and exits 2.
3. Direct CLI quality-gate output remains human-readable.
4. POSIX and PowerShell behavior and streams match.
5. Install and update paths refresh the active platform-specific workspace hook.
6. A fresh Social Ops editor chat completes without the non-JSON warning.

## Grounding Sources

- Architrave issue #6.
- VS Code 1.128 bundled HookExecutor and official hooks documentation.
- Rooted Social Ops session and workspace Copilot log.
- `gates/quality-gate.*`, hook manifests, updaters, and paired fixtures.

## Assumptions

- Exit 0 JSON and exit 2 stderr are shared across VS Code, Copilot CLI, and
  Claude-compatible hook formats.

## Blocking Questions

None.