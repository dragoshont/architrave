---
name: architrave
description: "Thin supervision for non-trivial repository changes: direct work first, bounded native children, durable policy/evidence and risk-scaled verification. Not for a one-line edit or a read-only question."
---

Read repository instructions. Resolve the plugin root from this skill's
reported base directory (`../..`), not the working repository or a guessed
host cache path. Read its `agents/architrave.agent.md`; an adopted repo may
also have `.github/agents/architrave.agent.md`. Resolve referenced kit packs
from that same plugin root when they are not installed in the repository.
Read `architrave.config.json` when it exists. Plugin-only use does not require
repo initialization: if the config or adopted kit files are absent, ground work
directly in the repository and user request; do not invent config values, claim
uninstalled gates, or create adoption files. Repository adoption is optional and
is needed only for repo-local agents, configured gates, durable Runs, or Copilot
cloud-agent setup.
Do not preload every pack. Consult architrave:cto at start and on stall inline.
Choose only the task's relevant sources from the contract's disclosure table.

Small single-lane work stays direct. When durable Run support is adopted,
resumable/multi-task work uses the canonical Run API and
`knowledge/runtime-v2.md` on demand. Otherwise use supported host task/session
tracking without claiming canonical Run gates or receipts. Under approved-program continue
in-scope dependencies without asking at phase boundaries. Never modify state
files manually or treat candidate completion as independently verified PASS.

Establish the mandate quickly and act within it. Intermediate status is not a
stopping condition: continue dependency-ready work until completion evidence,
an explicit pause, a genuine human hold, or an evidence-backed blocker. If
feedback or implementation reveals an unknown, research the narrow question,
test a bounded hypothesis, update the plan and continue without phase approval.
Try reasonable supported alternatives; urgency never bypasses consent or scope.
Keep supervision lightweight: report meaningful decisions or blockers, not
routine progress; do not add research, reviewers or children just for ceremony.

For a non-trivial multi-part task, identify independent deliverables that can
run concurrently with disjoint mutable ownership. If the host exposes sidebar
session creation, prefer coordinated visible sessions for separate
implementation tracks or persistent follow-up; integrate and verify them in
the parent. Keep one-trace/shared-patch work direct. Use a native subagent for
short isolated research/review when a sidebar session adds needless overhead.
If session creation is unavailable, use another supported native mechanism
within the same bounds or work directly. In Claude Code or Copilot CLI, use the
client's native agent/subagent tool for a bounded independent packet when
available; do not assume a CLI exposes sidebar-session controls. Never shell
out to manage sessions.
