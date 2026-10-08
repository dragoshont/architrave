---
name: architrave
description: "Thin supervision for non-trivial repository changes: direct work first, bounded native children, durable policy/evidence and risk-scaled verification. Not for a one-line edit or a read-only question."
---

Read `architrave.config.json` and the small canonical supervisor contract at
`agents/architrave.agent.md` (the adopted copy is `.github/agents/architrave.agent.md`).
Do not preload every pack. Consult architrave:cto at start and on stall inline.
Choose only the task's relevant sources from the contract's disclosure table.

Small single-lane work stays direct. Resumable/multi-task work uses the canonical
Run API and `knowledge/runtime-v2.md` on demand. Under approved-program continue
in-scope dependencies without asking at phase boundaries. Never modify state
files manually or treat candidate completion as independently verified PASS.

No automatic PostToolUse quality command is installed. After relevant config,
referenced design JSON or configured product-copy changes, and at final
integration, MUST run `python gates/gate_runner.py quality-gate` and retain its
actual exit/output proof. A mandatory failure blocks completion. The same
deterministic validator remains executable; agent prose is not automatic
enforcement. Use targeted build/test checks and required risk-scaled CI, not
full suites each turn. Native permission/scope/depth guards remain intact.
