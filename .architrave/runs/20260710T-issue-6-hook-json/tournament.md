# Tournament of Options

## Option A - Shell One-Liner Wrapper

Small manifest edit, but quoting and stream behavior diverge by platform.

## Option B - New Hook Wrapper Scripts

Clear, but adds another paired executable surface for one mode flag.

## Option C - Structured Mode On Existing Quality Gates

Reuses the existing paired gate, preserves direct CLI behavior, and makes the
hook contract explicit and testable.

## Decision Matrix

| Option | Cross-platform | New surface | Testability | Durability | Decision |
|---|---|---|---|---|---|
| A | low | none | low | low | lose |
| B | high | two scripts | high | medium | lose |
| C | high | one flag per existing gate | high | high | win |

## Winner

Option C, plus active-hook propagation in both updaters.