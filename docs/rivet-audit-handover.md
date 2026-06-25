# Rivet Audit Branch Handover

This handover is for the `rivet-3-preview-audit` branch of Architrave.

## Current State

- Branch: `rivet-3-preview-audit`
- Purpose: private/corp-side Rivet audit kickoff material and Architrave improvement planning.
- Clean public Architrave release: `v0.8.12`.
- Unsafe public release `v0.8.11` was deleted because it briefly included Rivet-specific docs in the package.
- The Rivet docs are intentionally kept only on this branch, not on `main`.

## Files On This Branch

- `docs/rivet-3-preview-audit.md`
  - Main corp-laptop audit prompt.
  - Covers SDD, deep research, tournament, YAGNI, NuGet upgrade, .NET upgrade, vulnerability scanner, judge/evaluator, TDD/characterization testing, and follow-through harness / anti-scaffolding.
- `docs/rivet-derived-architrave-improvement-plan.md`
  - Reviewed plan for possible Architrave-core improvements derived from the Rivet discussion.
  - Plan is not implemented yet.
  - Final review reached PASS after revisions.
- `docs/rivet-corp-install-options.md`
  - How to install this branch locally into Copilot on the corp laptop.
  - Includes fresh-install steps for machines where Architrave is not installed yet.

## Important Release History

- `v0.8.11` was published and then removed.
  - It contained the Rivet docs in the public Architrave package.
  - The GitHub release, remote tag, and local tag were deleted.
- `v0.8.12` is the clean public package.
  - It does not contain the Rivet docs.
  - The docs remain available on this branch.

## Corp Laptop Setup

Use the branch directly as a local plugin source:

```bash
git clone https://github.com/dragoshont/architrave.git
cd architrave
git checkout rivet-3-preview-audit

copilot plugin marketplace add "$PWD"
copilot plugin install architrave@architrave
```

If there is already an `architrave` marketplace entry:

```bash
copilot plugin uninstall architrave || true
copilot plugin marketplace remove architrave || true
copilot plugin marketplace add "$PWD"
copilot plugin install architrave@architrave
```

Then reload VS Code.

## Corp Workspace Shape

Open a VS Code multi-root workspace with:

- the local Rivet repository;
- one real daily consumer repository;
- optionally this Architrave checkout.

Use the Architrave agent in Copilot Chat.

## First Prompt To Run

```text
Use the Rivet 3.0-preview audit brief at docs/rivet-3-preview-audit.md from the Architrave branch.
Also use docs/rivet-derived-architrave-improvement-plan.md and docs/rivet-corp-install-options.md.

You are in a multi-root workspace with Rivet and one daily consumer repo.

Start read-only.

Run only:
1. Phase 0 — Preflight
2. Phase 1 — Footprint measurement
3. Audit artifact initialization

Do not refactor yet.
Do not change code yet.
Do not ask me to summarize anything available in the repos, harness artifacts, commits, wiki, Azure DevOps, or configured MCP/tools.

Return:
- missing tools / missing MCP servers;
- VPN/auth blockers;
- initial footprint report;
- proposed audit artifact path;
- next recommended phase.
```

## Core Audit Goal

Rivet was built to avoid scaffold-only agent behavior. Preserve that goal.

The audit must determine whether Rivet's current harness JSON files actually enforce follow-through or merely document plans. Runs should end in a real terminal state:

- `validated_implementation`
- `validated_analysis`
- `blocked_with_remediation`
- `deferred_with_owner_reason`
- `abandoned_superseded`

The audit should explicitly find historical runs where contracts, plans, JSON, or placeholder files were created without implementation, validation, or a clear blocker.

## Architrave-Core Plan Status

`docs/rivet-derived-architrave-improvement-plan.md` is a plan only. It should not be treated as implemented.

Proposed future Architrave-core improvements:

- task-risk router;
- tool/MCP preflight;
- TDD / characterization-test hook;
- source ledger and evidence index;
- subagent artifact handoff;
- visible YAGNI;
- long-running deep-audit mode.

These should be implemented only after a separate design/implementation pass and release.

## Return To Clean Public Architrave

After the Rivet audit branch is no longer needed:

```bash
copilot plugin uninstall architrave
copilot plugin marketplace remove architrave
copilot plugin marketplace add dragoshont/architrave
copilot plugin install architrave@architrave
```

This returns to the clean public package (`v0.8.12` or later), which does not include the Rivet docs.

## Validation Done Before This Handover

- `scripts/check-manifests.sh` passed on this branch.
- `git diff --check` passed for the docs edits.
- Clean public `v0.8.12` release was verified to exclude Rivet docs.
- Branch `rivet-3-preview-audit` was verified to retain the Rivet docs.