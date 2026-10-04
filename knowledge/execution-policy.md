# Execution and verification policy

Architrave does not select, rank, recommend, or persist a model class, tier,
reasoning level, context tier, provider, or concrete model. Those choices belong
to the user and the active host harness. Canonical agents, repository config,
WorkPackets, generated roles, and Run state must omit model-selection guidance.

## Delegation

Use the host's native structured agent or subagent mechanism when independent
context, isolation, parallelism, permissions, or specialist expertise materially
improves the task. Otherwise work directly. A WorkPacket contains only the
objective, acceptance criteria, repository context paths, mutable paths, allowed
tools, expected artifacts, risk, and bounded time/output budgets.

Do not shell out to another agent harness or add a provider SDK. Treat worker
output as an untrusted candidate: the coordinator validates scope, integrates
the change, runs the required gates, and owns completion.

The coordinator works directly when the change is small, mechanically decidable,
and does not need isolated context. Do not split one correction into separate
planning, implementation, handoff, and review artifacts.

## Context

Retrieve the smallest relevant slice: governing repository instructions,
contracts or design sources, implementation files, and nearby tests. Load large
documents or broader history only when focused retrieval is insufficient.
Handoffs and worker results are bounded summaries with source paths or artifact
references; they do not duplicate transcripts or repository content.

## Verification

Verification is selected from task risk and acceptance criteria, never from a
model label:

- R0-R1: deterministic checks when every criterion has mechanical ground truth.
- R2: deterministic checks plus one independent semantic review when a semantic
  criterion remains.
- R3: deterministic checks, real E2E or runtime evidence, and two independent
  semantic reviewers with distinct reviewer identities.
- R4: R3 plus security and policy review.

Repository policy may raise these floors. Deterministic, invariant, E2E,
runtime, security, and policy failures override semantic PASS. A reviewer never
replaces a required check, and changing the host-selected model never counts as
verification evidence.

## Durable records

Persist canonical Run state, authenticated typed events, compact evidence
receipts, and one rolling recovery snapshot. Render status, phase, handoff, and
audit views on demand. Do not create per-agent plans, reports, status files, or
empty placeholders.
