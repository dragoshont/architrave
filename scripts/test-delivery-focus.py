#!/usr/bin/env python3
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]


def contains_guidance(text: str, phrase: str) -> bool:
    return " ".join(phrase.split()) in " ".join(text.split())


agent = (root / "agents/architrave.agent.md").read_text(encoding="utf-8")
agent_frontmatter = agent.split("---", 2)[1]
execution = (root / "knowledge/execution-policy.md").read_text(encoding="utf-8")
rubric = (root / "gates/rubric.md").read_text(encoding="utf-8")
learning = (root / "knowledge/learning-loop.md").read_text(encoding="utf-8")
stanza = (root / "templates/AGENTS.stanza.md").read_text(encoding="utf-8")
readme = (root / "README.md").read_text(encoding="utf-8")
roadmap = (root / "ROADMAP.md").read_text(encoding="utf-8")
lead_skill = (root / "skills/architrave/SKILL.md").read_text(encoding="utf-8")
runtime_pack = (root / "knowledge/runtime-v2.md").read_text(encoding="utf-8")
cto_agent = (root / "agents/cto.agent.md").read_text(encoding="utf-8")
cto_skill = (root / "skills/architrave-cto/SKILL.md").read_text(encoding="utf-8")
tournament_skill = (root / "skills/architrave-tournament/SKILL.md").read_text(encoding="utf-8")
review_skill = (root / "skills/architrave-review/SKILL.md").read_text(encoding="utf-8")
work_skill = (root / "skills/architrave-work/SKILL.md").read_text(encoding="utf-8")
long_programs = (root / "docs/long-programs.md").read_text(encoding="utf-8")
sdd_skill = (root / "skills/subagent-driven-development/SKILL.md").read_text(encoding="utf-8")
tournament_agent = (root / "agents/tournament-analyst.agent.md").read_text(encoding="utf-8")
generator = (root / "scripts/generate-codex-agents.py").read_text(encoding="utf-8")
planner = (root / "agents/backend-planner.agent.md").read_text(encoding="utf-8")
implementer = (root / "agents/backend-implementer.agent.md").read_text(encoding="utf-8")
infra = (root / "agents/infra-engineer.agent.md").read_text(encoding="utf-8")
observer = (root / "agents/runtime-observer.agent.md").read_text(encoding="utf-8")
codex_roles = "\n".join(
    path.read_text(encoding="utf-8") for path in sorted((root / ".codex/agents").glob("*.toml"))
)

required = {
    "lead signing grant reuse": (agent, "Reuse scoped owner signing authorization"),
    "cto duplicate signing gates": (cto_agent, "Remove duplicate signing approval gates"),
    "cto skill signing reuse": (cto_skill, "Reuse existing scoped signing grants"),
    "rubric signing reuse": (rubric, "Repeated signing approval for a current matching owner grant"),
    "cto active edits are not handoff": (cto_agent, "A dirty ledger during active editing is not by itself broken coordination"),
    "cto hold resolution": (cto_agent, "Resolved holds stay resolved"),
    "lead hold resolution": (agent, "Superseded Handoff/Verify text must not resurrect a resolved blocker"),
    "backend one scope boundary": (implementer, "DO NOT implement beyond the mandate-covered scope or contract"),
    "backend no phase ceremony": (planner, "all covered dependency-ready slices may continue without new phase approvals"),
    "backend no ledger prerequisite": (implementer, "use them rather than demanding another artifact"),
    "infra no circular backup": (infra, "not a mandatory fresh VM snapshot"),
    "observer no circular backup": (observer, "no circular creation-evidence gate"),
    "lead proportional action": (agent, "smallest useful authorized action"),
    "lead no invented snapshot": (agent, "Optional backups or VM snapshots are not prerequisites"),
    "lead desktop owner": (agent, "existing exclusive input owner"),
    "lead evidence stages": (agent, "instruction sent, execution started, observed result and accepted outcome"),
    "policy precaution source": (execution, "Name the source of a mandatory hold"),
    "policy circular checkpoint": (execution, "Creating an authorized checkpoint cannot require evidence that it already exists"),
    "policy experimental host": (execution, "Dedicated experimental hosts make optional safeguards proportional"),
    "policy skipped snapshot": (execution, "When the owner accepts proceeding without an optional fresh VM snapshot"),
    "policy window discovery": (execution, "Zero visible windows is not a permission denial"),
    "policy independent CLI": (execution, "Missing UI evidence does not block an independent supported CLI path"),
    "policy timeout": (execution, "Reconcile a timed-out mutation against live target state before retrying"),
    "policy screenshot truth": (execution, "A screenshot proves only what is visible"),
    "policy manual fallback": (execution, "one exact manual action"),
    "cto remove invented holds": (cto_agent, "Remove agent-added holds"),
    "cto desktop steering": (cto_agent, "route target-only navigation to the existing exclusive input owner"),
    "cto stage truth": (cto_agent, "instruction sent, execution started, observed result and accepted outcome"),
    "cto skill precautions": (cto_skill, "Optional safeguards are not mandatory gates"),
    "worker proportionality": (work_skill, "Do not invent backup, snapshot or phase-approval prerequisites"),
    "runtime checkpoint distinction": (runtime_pack, "A Run checkpoint is not a VM snapshot"),
    "rubric overprecaution": (rubric, "Invented precaution gates"),
    "claim persists before dispatch": (agent, "records owner and claimed status; commit that change before dispatch"),
    "successor pins predecessor": (agent, "`--handoff --expect <predecessor-sha>`"),
    "execution pins predecessor": (execution, "`--handoff --expect <predecessor-sha>`"),
    "SDD cache authority": (sdd_skill, "cache subordinate to the committed requirements Handoff"),
    "SDD recovery authority": (sdd_skill, "Rebuild it from that Handoff and git log, never create a second source of truth"),
    "CTO current coordinator": (cto_agent, "Identify the current coordinator and its committed ledger"),
    "CTO predecessor reports stale": (cto_agent, "never steer from old or predecessor coordinator reports"),
    "CTO source-bound evidence": (cto_agent, "accepted evidence must reference the current source or commit and the primary criterion"),
    "CTO counts not proof": (cto_agent, "Growth in the accepted count is not proof"),
    "CTO same pass action": (cto_agent, "Act on obvious loops and idle owners with dependency-ready unclaimed REQs in the same pass"),
    "CTO stall timing limited": (cto_agent, "The three-pass rule applies only to criterion stalls"),
    "CTO mandate dispatch comparison": (cto_agent, "Compare the latest verbatim owner objective and holds with what was actually dispatched"),
    "CTO corrections require change": (cto_agent, "Send a correction only with new evidence or a different concrete action"),
    "host automation reset warning": (long_programs, "Saving or replacing a session automation prompt resets its next run time; edit the schedule rarely"),
    "fresh refs before resuming": (agent, "validates current component refs and acceptance evidence"),
    "commit-based rotation": (agent, "committed with `requirements --handoff` passing, before rotation or hand-off"),
    "scratch is not the ledger": (agent, "Worktree-local scratch such as SDD `progress.md` is a cache, never the ledger"),
    "predecessor stops relaying": (agent, "stops relaying"),
    "state lives in committed file": (execution, "committed requirements file on the coordinator's branch"),
    "no second ledger": (execution, "never start a second ledger"),
    "document handoff gate": (long_programs, "python gates/gate_runner.py requirements --handoff"),
    "bootstrap from durable corrections": (execution, "requirements, correction rows and Handoff"),
    "history is not runtime proof": (execution, "Historical source refs and old audit claims are not fresh runtime evidence"),
    "component role and refs": (execution, "execution role (which side/process runs it), working branch/base when non-default"),
    "reuse component map": (execution, "existing `components` map and requirements/Handoff"),
    "effective write target": (execution, "effective push remote and every push URL"),
    "no default-branch rescue assumption": (execution, "Do not assume the default branch contains rescued work"),
    "redirect identity before destruction": (execution, "Resolve rename redirects and confirm the current canonical repository identity before destructive GitHub operations"),
    "preserve dirty component work": (execution, "Preserve dirty work and other owners' branches"),
    "precursor vs product path": (execution, "known-working precursor/lab/handwritten path from the intended generated/product path"),
    "actual implementation evidence": (execution, "Evidence identifies the source ref/artifact and entry point that actually ran"),
    "preserve proven baseline": (execution, "Preserve the proven baseline until replacement passes the real-flow parity check"),
    "thin project kickoff": (execution, "project kickoff chiefly supplies the objective, requirements entry point, component refs and project-specific decisions"),
    "retire only scoped schedules": (execution, "disable only the assigned scheduled automation"),
    "retirement lifecycle trigger": (execution, "accepted, superseded or its owner is archived"),
    "no retired loop resurrection": (execution, "Do not restart retired monitor loops without a new mandate"),
    "retirement preserves evidence": (execution, "Preserve source and evidence; retirement is not permission for broad cleanup"),
    "retirement respects host": (execution, "If host controls or authorization are unavailable, report the blocker"),
    "lead routes scheduled retirement": (agent, "Retire assigned scheduled automation under the Context rules"),
    "document thin kickoff": (long_programs, "Link the Architrave contract rather than copying its workflow, verification and permission rules"),
    "document accepted retirement": (long_programs, "Retire only assigned schedules whose work is accepted, superseded or whose owner is archived"),
    "child explicit skill handoff": (agent, "Do not assume a subagent or sidebar session inherited parent skill context"),
    "portable worker guidance": (execution, "not a new WorkPacket schema or host-specific preload field"),
    "worker no nested supervision": (work_skill, "No child spawning"),
    "worker verified research": (work_skill, "verify relevant passages"),
    "worker voice evidence": (work_skill, "author-voice fidelity\nunconfirmed"),
    "worker no unauthorized sending": (work_skill, "sending/publishing is\nexplicitly authorized"),
    "worker skill load provenance": (work_skill, "Do not claim invocation success from a file read"),
    "on-demand vertical slice": (execution, "smallest demonstrable user-visible vertical slice"),
    "on-demand support budget": (execution, "at most two consecutive tasks or one\nfull-gate cycle"),
    "on-demand task gate": (execution, "A supporting task does not\nindependently trigger a full gate"),
    "on-demand stall": (execution, "no new output for 15 minutes"),
    "host-owned execution": (execution, "user and\nthe active host harness"),
    "compact records": (execution, "one rolling recovery snapshot"),
    "rubric delivery": (rubric, "Delivery focus and verification cadence"),
    "artifact accounting": (learning, "Artifacts are audit support, not delivery currency"),
    "installed stanza": (stanza, "That lead contract owns delegation, verification and stop rules"),
    "README bounded option comparison": (readme, "Compare alternatives when\n  an architecture choice"),
    "README host-owned execution": (readme, "Model and reasoning choices remain in your host settings"),
    "execution bounded tournament": (execution, "it is not a prerequisite for routine bounded work"),
    "execution host-native delegation": (execution, "use the\nclient's native agent/subagent tool for a bounded independent packet"),
    "execution no nested agent CLI": (execution, "Do not shell out to another agent harness"),
    "roadmap bounded tournament": (roadmap, "a Tournament of Options only for materially ambiguous or high-risk choices"),
    "on-demand reference parity": (execution, "parity test against that\nreference on the real flow, before any hardening"),
    "on-demand primary stall": (runtime_pack, "`STALLED_PRIMARY_CRITERION`"),
    "on-demand diagnostic specificity": (execution, "Collapsing distinct causes into one generic failure code is a gate"),
    "execution lenient parsing": (execution, "Default-deny is not a parsing policy"),
    "execution proportional ceremony": (execution, "R0/R1 single-path fixes need no\nper-change pin, receipt, or qualification Run"),
    "execution approved quit": (execution, "escalate a graceful quit to SIGTERM after a timeout without a new hold"),
    "rubric product copy": (rubric, "Internal evidence, spec, status, certification, or receipt\n    language in user-facing UI strings"),
    "cto on demand": (agent, "Use the CTO skill only for an established stall"),
    "no startup ceremony": (agent, "no mandatory startup checklist"),
    "skill delegates contract": (lead_skill, "It is the canonical lead contract"),
    "stanza delegates contract": (stanza, "not both copies"),
    "cto agent routes": (cto_agent, "never implements"),
    "cto skill outcome": (cto_skill, "Outcome over ceremony"),
    "cto oversight on request": (cto_agent, "Only when the owner explicitly asks you to watch programs across sessions"),
    "cto oversight goal first": (cto_agent, "Commits, audits,\n   SPEC-only edits and status messages are activity, not progress"),
    "cto oversight ledger gate": (cto_agent, "--handoff` (one committed ledger"),
    "cto oversight review per task": (cto_agent, "one independent review and a committed REQ Evidence/Handoff"),
    "cto oversight owner-only": (cto_agent, "Never decide owner-only items"),
    "cto oversight no implement": (cto_agent, "Steer, don't implement"),
    "cto oversight host schedule": (cto_agent, "add an Architrave scheduler or daemon"),
    "cto skill oversight": (cto_skill, "Oversight (owner-requested only)"),
    "lead routes cto oversight": (agent, "owner-requested cross-session oversight"),
    "cto oversight claims": (cto_agent, "Flag work claimed done\n   without proof, promised steps never taken"),
    "cto oversight trusted checkpoints": (cto_agent, "Never resolve Run checkpoints, `confirmationRequired` operations, scoped\n   grants or typed trusted checkpoints"),
    "readme oversight checkpoints": (readme, "Run checkpoints, confirmation-required operations, scoped grants and typed trusted checkpoints (signing, MFA, safe write target, human judgment) always stay with you"),
    "cto checkpoint kinds": (cto_agent, "(signing, MFA, safe write target,\n   human judgment)"),
    "cto oversight loops": (cto_agent, "is a loop. Break it with one different\n   concrete action"),
    "cto oversight needless approval": (cto_agent, "An approval request for something already inside that direction is\n   unnecessary"),
    "cto oversight output mode": (cto_agent, "This mode returns the oversight table below,\nnot the single correction"),
    "cto single correction scoped": (cto_agent, "Outside oversight mode, return exactly one short correction"),
    "cto oversight cadence": (cto_agent, "This mode requires a\nhost-owned schedule every 30 minutes, or every 60 when passes run long"),
    "cto oversight gate scope": (cto_agent, "its configured and risk-floor gates"),
    "cto skill correction scoped": (cto_skill, "then (outside oversight mode) one\ncorrection"),
    "cto oversight quality gates": (cto_agent, "`quality-gate` where\n   required"),
    "cto skill push-back": (cto_skill, "KEEP/CUT/DEFER verdict"),
    "scope discipline": (agent, "Owner corrections replace old scope"),
    "tournament skill baselines": (tournament_skill, 'include a "do nothing" baseline and a "smallest viable" option'),
    "tournament skill beats nothing": (tournament_skill, "why the chosen\noption beats doing nothing"),
    "tournament typed result": (tournament_skill, "typed as `DO_NOTHING` and `SMALLEST_VIABLE`"),
    "review prefers host-native": (review_skill, "Prefer the host-native reviewer"),
    "review records reviewer": (review_skill, "--reviewer host-native|architrave-judge --family"),
    "review recording scoped": (review_skill, "For an adopted canonical Run"),
    "direct review no Run": (review_skill, "do not create a Run, receipt or report solely to record a review"),
    "agent host-native review": (agent, "`architrave-review`; `gates/rubric.md`"),
    "direct-work threshold": (agent, "Use direct work for one continuous trace"),
    "explicit role wins": (agent, "An explicit request for a named agent overrides the direct-work preference"),
    "skill is not agent execution": (execution, "loading instructions is not agent execution"),
    "explicit chat project": (execution, "select the project explicitly when the parent is a chat"),
    "actual child destination": (execution, "compare the host-returned repository/workspace and intended branch/base"),
    "isolated branch identity": (execution, "verify their intended base, not identical branch names"),
    "worker verifies destination": (work_skill, "Before writing, verify cwd, repository identity and branch/base"),
    "no unchanged denied retries": (execution, "Never retry permission-denied operations unchanged"),
    "visible-session parallelism": (agent, "prefer coordinated, user-visible sessions"),
    "spec is source of truth": (execution, "The repository requirements file (config `requirements`, else `SPEC.md`) is the source of truth"),
    "spec-driven default": (agent, "Spec-driven by default. The repository requirements file is the source of truth"),
    "spec trivial exemption": (agent, "Exempt: read-only questions and trivial one-line edits"),
    "trace to REQs": (agent, "Commits, child kickoffs, hand-offs and reports name the REQ ids they serve"),
    "corrections recorded first": (agent, "as a typed `add|revise|retract|supersede` correction row before acting on it"),
    "done is accepted REQs": (agent, "`python gates/gate_runner.py requirements --done` passes"),
    "spec-driven skill": (lead_skill, "Work is spec-driven"),
    "spec-driven stanza": (stanza, "Spec-driven: record requests and owner corrections as REQ rows"),
    "worker REQ discipline": (work_skill, "Work to the assigned REQ ids and their acceptance"),
    "rubric grades REQs": (rubric, "Non-trivial work without REQ rows with testable acceptance is a Major finding"),
    "rubric done blocker": (rubric, "Claiming done while an in-scope REQ is not `accepted` with evidence"),
    "README spec-driven lead": (readme, "Architrave is a spec-driven development control plane"),
    "first vertical slice": (execution, "first useful end-to-end product slice"),
    "spec is short": (agent, "a bounded task may be one\n  to three rows"),
    "product progress reporting": (agent, "Report what the product can now do"),
    "small task graph": (execution, "Keep the live task graph small"),
    "primary criterion stall signal": (agent, "When an adopted Run reports `STALLED_PRIMARY_CRITERION`"),
    "stall blocks unrelated tasks": (agent, "blocks new tasks not bound to that criterion"),
    "stall is not an idle timer": (execution, "is not an idle timer"),
    "README describes automatic criterion stall": (readme, "An adopted Run can flag a primary product criterion as stalled"),
    "installed product focus": (stanza, "Build the requested behavior first"),
    "README product-first guidance": (readme, "focused on one outcome"),
    "default child bounds": (agent, "default three, owner-approved up\n  to eight (lower host limits win); depth: one"),
    "repeat-failure stop": (agent, "twice without new evidence stops the lane"),
    "progressive disclosure": (lead_skill, "Do not preload every pack"),
    "load lead only once": (lead_skill, "unless that contract is already loaded"),
    "plugin-only use needs no repo initialization": (lead_skill, "Plugin-only use does not require\nrepo initialization"),
    "unadopted repo fallback": (agent, "if the config or adopted kit files are absent"),
    "plugin-only edit authority": (agent, "Plugin-only source edits follow the user's mandate"),
    "adopted lead quality gate": (agent, "In an adopted repo, MUST execute"),
    "adopted stanza fallback": (stanza, "If this stanza is copied without the rest of the kit"),
    "centralized verification contract": (stanza, "That lead contract owns delegation, verification and stop rules"),
    "optional repo adoption": (readme, "## Optional repository setup"),
    "README CLI delegation fallback": (readme, "In a CLI, Architrave uses native subagents when available"),
    "README host-tool limits": (readme, "not missing tools or\nMCP servers"),
    "README worktree boundary": (readme, "not an\nOS security sandbox"),
    "README explicit checks": (readme, "Checks must be configured and invoked"),
    "mandate-driven continuation": (agent, "a status update is not a stopping"),
    "upfront challenge": (agent, "At intake, attack the request"),
    "material questions only": (agent, "Ask only questions whose answers change\nthe work"),
    "mid-development research": (execution, "Feedback and unknowns during implementation"),
    "mandate safety boundary": (agent, "urgency never bypasses consent or scope"),
    "execution CLI delegation fallback": (execution, "Claude Code or Copilot CLI"),
    "short child assignment": (execution, "A short native child assignment needs only an objective, owned scope, relevant context and expected result"),
    "durable packet safety unchanged": (execution, "Durable WorkPackets still obey their existing schema and admission checks"),
    "no invented lookup budgets": (execution, "do not invent per-child budget, receipt or planning fields for a brief lookup"),
    "no blank artifact penalties": (rubric, "Missing optional artifacts are not findings"),
    "no extra planning documents": (rubric, "Missing other planning documents are not findings"),
    "no universal Run": (rubric, "Ordinary direct source work does not need a Run or phase ledger"),
    "compact review output": (rubric, "A clean review needs no dimension-score table"),
    "required evidence preserved": (rubric, "Missing required release/mutation evidence"),
    "learning optional": (learning, "Missing optional learning artifacts are not a finding"),
    "on-demand feasibility": (cto_skill, "On-demand feasibility reset"),
    "adaptive window": (cto_skill, "Estimate a finite time/turn/output window"),
    "explicit owner ceiling": (cto_skill, "deadlines/ceilings win"),
    "no clock reset": (cto_skill, "Unchanged evidence cannot renew the window"),
    "tournament agent baselines": (tournament_agent, 'include a "do nothing" baseline and a "smallest viable" option'),
}

missing = [name for name, (text, phrase) in required.items() if not contains_guidance(text, phrase)]
# These fixtures protect instruction contracts, not live agent/tool behavior.
precaution_scenarios = {
    "existing identity standing build sign stage grant": (
        execution,
        ("Reuse the current owner grant for the existing signing identity and bounded build/sign/stage workflow",
         "Persist the scoped owner direction in existing requirements corrections",
         "Do not manually edit canonical Run policy",
         "Check target, identity, operations, limits, expiry and revocation",
         "Do not ask for fresh signing or phase approval on every repeat build"),
        ("Signing always requires fresh owner approval",)),
    "signing grant does not expand operations or bypass keychain": (
        execution,
        ("A new identity, keychain access-policy change, distribution, notarization, publication, installation or daemon change needs coverage in the grant",
         "Actual host/keychain confirmation cannot be bypassed",
         "Never read, export or log signing secrets or key material",
         "Local identities and project-specific grants stay in the target project's records"),
        ("Standing signing consent authorizes arbitrary repositories",)),
    "authorized install, optional snapshot declined": (
        execution,
        ("When the owner accepts proceeding without an optional fresh VM snapshot",
         "continue the authorized install", "Required Run checkpoints, host controls and legal consent remain mandatory"),
        ("Always require a fresh VM snapshot before installation",)),
    "checkpoint creation needs before-state, not its own result": (
        execution,
        ("Creating an authorized checkpoint cannot require evidence that it already exists",
         "Record the actual pre-action state", "then verify its result"),
        ("Require fresh-checkpoint creation proof before permitting checkpoint creation",)),
    "zero windows, supported independent CLI": (
        execution,
        ("Zero visible windows is not a permission denial",
         "Missing UI evidence does not block an independent supported CLI path",
         "existing exclusive input owner", "Preserve unrelated windows and running VM state"),
        ("Zero windows means permission denied", "Ask the owner to click before trying supported window controls")),
    "human-only prompt or no control": (
        execution,
        ("If controls are unavailable or a prompt is genuinely human-only",
         "one exact manual action", "do not retry blindly"),
        ("Bypass human-only prompts",)),
    "RPC timeout may have created snapshot": (
        execution,
        ("Reconcile a timed-out mutation against live target state before retrying",
         "Unknown completion blocks a duplicate mutation, not independent safe work"),
        ("Retry timed-out mutations immediately",)),
    "delegated install still pending": (
        agent,
        ("instruction sent, execution started, observed result and accepted outcome",
         "Pending delegation is not delivery", "Source/test success is not installed/native success"),
        ("An instruction sent proves delivery",)),
}


def scenario_supported(text, required_phrases, forbidden_phrases):
    return all(contains_guidance(text, phrase) for phrase in required_phrases) and not any(
        contains_guidance(text, phrase) for phrase in forbidden_phrases
    )


for name, (text, positive, negative) in precaution_scenarios.items():
    if not scenario_supported(text, positive, negative):
        missing.append(f"precaution scenario: {name}")
    normalized = " ".join(text.split())
    for phrase in positive:
        mutant = normalized.replace(" ".join(phrase.split()), "REMOVED", 1)
        if scenario_supported(mutant, positive, negative):
            missing.append(f"scenario misses removed rule: {name}: {phrase}")
    for phrase in negative:
        if scenario_supported(text + "\n" + phrase, positive, negative):
            missing.append(f"scenario accepts contradictory rule: {name}: {phrase}")

for name, text, stale in (
    ("backend one-phase cap", planner, "At most one phase should be approved"),
    ("backend unconditional ledger gate", implementer, "If the plan is missing a phase ledger"),
    ("backend contradictory phase stop", implementer, "rather than improvising architecture or silently starting the next phase"),
):
    if contains_guidance(text, stale):
        missing.append(name)
for name, (text, phrase) in required.items():
    reflowed = "\n\t".join(text.split())
    if contains_guidance(text, phrase) != contains_guidance(reflowed, phrase):
        missing.append(f"whitespace-sensitive rule: {name}")
if contains_guidance("scoped permission is mandatory", "scoped permission is optional"):
    missing.append("guidance matcher accepts substantive changes")
for text, stale in (
    (sdd_skill, "Create the ledger with its identity as the first line"),
    (sdd_skill, "trust the ledger and `git log` over your own recollection"),
    (cto_agent, "never the same correction twice"),
    (cto_agent, "three passes without a criterion delta"),
    (long_programs, "successor starts from that commit, runs the same command"),
):
    if contains_guidance(text, stale):
        missing.append(f"stale lessons contract: {stale}")
for name, text in (("skill", lead_skill), ("stanza", stanza)):
    if len(text.split()) > 200:
        missing.append(f"{name} duplicates too much of the lead contract")
for phrase in ("visible intake block", "non-trivial work has canonical",
               "Missing artifacts are a Major concern"):
    if contains_guidance(rubric, phrase):
        missing.append(f"rubric still mandates blanket ceremony: {phrase}")
for manifest in ("plugin.json", ".claude-plugin/plugin.json", ".github/plugin/marketplace.json", ".codex-plugin/plugin.json"):
    if "Spec-driven" not in (root / manifest).read_text(encoding="utf-8"):
        missing.append(f"{manifest} description does not lead with spec-driven development")
if "exhaustive requirement ledger" in agent or "do not require a separate specification" in execution:
    missing.append("anti-spec wording returned to the lead contract")
if "before task or Outcome completion" in agent:
    missing.append("per-task full-gate phrase remains")
if "Then it runs a **Tournament of Options**" in readme:
    missing.append("README still requires a universal tournament")
if "Mandatory visible intake and Tournament of Options" in roadmap:
    missing.append("ROADMAP still requires a universal tournament")
if 'model = "' in codex_roles or "model_reasoning_effort" in codex_roles:
    missing.append("generated Codex roles still pin a concrete model")
if "'model = " in generator or "model_reasoning_effort" in generator:
    missing.append("Codex role generator still emits concrete model policy")

canonical_files = [
    root / "README.md",
    root / "ROADMAP.md",
    root / "agents" / "architrave.agent.md",
    root / "knowledge" / "execution-policy.md",
    root / "knowledge" / "runtime-v2.md",
    root / "templates" / "AGENTS.stanza.md",
    root / "harness" / "schemas" / "run-v2.schema.json",
    root / "harness" / "schemas" / "run-summary.schema.json",
]
for path in canonical_files:
    text = path.read_text(encoding="utf-8")
    for forbidden in (
        "modelClass",
        "FAST",
        "BALANCED",
        "DEEP",
        "CRITICAL",
        "reasoning-effort",
        "reasoningEffort",
        "contextTier",
        "GPT-5",
        "Opus 4",
    ):
        if forbidden in text:
            missing.append(f"{path.relative_to(root)} still contains {forbidden}")

for text, stale in (
    (cto_skill, "Report only what is off, then one correction"),
    (cto_agent, "\nReturn exactly one short correction"),
    (cto_agent, "may wake you"),
    (cto_agent, "acceptance run, one independent review"),
    (agent, "owner-requested reset; no mandatory startup checklist"),
):
    found = stale in text if stale.startswith("\n") else contains_guidance(text, stale)
    if found:
        missing.append(f"stale CTO contract text: {stale.strip()}")

runtime = (root / "harness" / "architrave_runtime.py").read_text(encoding="utf-8")
if '"model": value.get("model")' in runtime:
    missing.append("WorkPackets still persist model selection")
for path in sorted((root / "agents").glob("*.agent.md")):
    text = path.read_text(encoding="utf-8")
    if "disable-model-invocation" in text or "\nmodel:" in text:
        missing.append(f"{path.relative_to(root)} still contains model-selection metadata")
if '"CTO"' not in agent.split("---", 2)[1]:
    missing.append("conductor does not route to the CTO agent")
for path in sorted((root / "agents").glob("*.agent.md")):
    frontmatter = path.read_text(encoding="utf-8").split("---", 2)[1]
    if re.search(r"^['\"]?tools['\"]?\s*:", frontmatter, re.MULTILINE):
        missing.append(f"{path.relative_to(root)} restricts the host tool set (blocks session spawn/notify)")
if not cto_agent.startswith('---\nname: "CTO"\n') or not cto_skill.startswith("---\nname: architrave-cto\n"):
    missing.append("CTO agent or skill frontmatter is not registered")
if not (root / "skills/architrave-cto/agents/openai.yaml").is_file():
    missing.append("CTO skill metadata is missing")
installer = (root / "tools/install_update.py").read_text(encoding="utf-8")
if '"cto",' not in installer.split("GATE_FILES", 1)[0]:
    missing.append("installer does not ship the CTO agent to every profile")
if missing:
    raise SystemExit("delivery-focus validation failed: " + ", ".join(missing))

print("delivery-focus validation: PASS")
