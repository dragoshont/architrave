# Architrave Install Options for the Rivet Audit

This note is for the corporate laptop where Rivet and at least one real consumer repo are available locally. The preferred path is **Option A**: install Architrave into Copilot from a local Architrave branch checkout that contains the Rivet audit brief.

## Target Workspace

Open a VS Code multi-root workspace with at least:

- the local Rivet repository;
- one real daily consumer repository;
- optionally the local Architrave checkout if it is convenient to inspect or edit the audit brief.

The Architrave plugin still needs to be installed into Copilot. Merely opening the Architrave repo as a workspace folder lets Copilot read files, but it does not necessarily register Architrave as an agent.

## Option A — Preferred: Install from a Local Architrave Branch

Use this when testing a branch or local changes before publishing them.

```bash
git clone https://github.com/dragoshont/architrave.git
cd architrave
git checkout <rivet-audit-branch>

copilot plugin marketplace add "$PWD"
copilot plugin install architrave@architrave
```

Then reload VS Code / Copilot so the Architrave agent definitions are picked up.

Use this opening prompt in the corp workspace:

```text
Use the Rivet 3.0-preview audit brief from the Architrave branch.
You are in a multi-root workspace with Rivet and one daily consumer repo.
Start read-only.
Run Phase 0 and Phase 1 only:
- tool/MCP/VPN preflight;
- repo/SDD/research/tournament/YAGNI/scanner footprint;
- audit artifact folder initialization.
Do not refactor yet.
Do not ask me to summarize anything available in the repos, harness artifacts, commits, wiki, Azure DevOps, or configured tools.
```

## Option B — Install from GitHub Branch or Published Source

Use this if the Copilot plugin marketplace in the corporate environment supports installing from a GitHub source or branch reference. Exact support may vary by Copilot CLI version and corporate policy.

```bash
copilot plugin marketplace add dragoshont/architrave
copilot plugin install architrave@architrave
```

If branch-specific installation is supported in that environment, use the branch/ref form documented by the local `copilot plugin marketplace add --help` output. If it is not supported, use Option A instead.

This path is best when the Rivet audit brief has already been merged or published into the canonical Architrave source.

## Option C — Prompt-Only Fallback

Use this only if plugin installation is blocked by corporate policy.

1. Open the Rivet audit Markdown file in VS Code.
2. Start a normal Copilot chat with the model you intend to use.
3. Paste or reference the audit brief manually.
4. Ask the agent to follow it.

This can still help, but it is weaker than installing Architrave because Copilot may not load Architrave's agent mode, specialist routing, subagent/judge contract, or standing instructions.

## Verification

After Option A or B, verify that Architrave is installed and available before starting the Rivet audit.

```bash
copilot plugin list
copilot plugin marketplace list
```

If Architrave is not visible in VS Code after installation, reload the VS Code window or restart VS Code.

## Recommended First Run

Do not begin with a refactor. Begin with the read-only audit.

```text
Use the Rivet 3.0-preview audit brief.
Run only:
1. Preflight.
2. Footprint measurement.
3. Audit artifact initialization.

Stop before changing code.
Return missing tools, missing MCP servers, VPN/auth blockers, and the initial footprint report.
```

## Why Option A Is Preferred

- It tests the exact Architrave branch intended for Rivet work.
- It does not require publishing before validation.
- It keeps the audit brief, agent behavior, and local plugin payload aligned.
- It is reversible: uninstall the local plugin source and return to the published Architrave marketplace source when done.