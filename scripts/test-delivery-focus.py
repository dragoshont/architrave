#!/usr/bin/env python3
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]


def contains_guidance(text: str, phrase: str) -> bool:
    return " ".join(phrase.split()) in " ".join(text.split())


agent = (root / "agents/architrave.agent.md").read_text(encoding="utf-8")
agent_frontmatter = agent.split("---", 2)[1]
execution = (root / "knowledge/execution-policy.md").read_text(encoding="utf-8")
yagni = (root / "knowledge/yagni.md").read_text(encoding="utf-8")
backend = (root / "knowledge/backend.md").read_text(encoding="utf-8")
board_source = (root / "harness/program_board.py").read_text(encoding="utf-8")
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
    "lead foregrounds development loop": (agent, "## Development loop"),
    "lead honors owner loop corrections": (agent, "explicit owner changes take precedence"),
    "policy one implementation case": (execution, "Select one implementation case at a time"),
    "policy grounded case design": (execution, "high- and low-level designs when present"),
    "policy authorized scoped commits": (execution, "Commit scoped work when authorized"),
    "policy unknown specification child": (execution, "bounded read-only sidebar child"),
    "policy missing implementation blocks readiness": (execution, "Unresolved specifications or missing implementation block Code ready"),
    "policy qualification differs from readiness": (execution, "Written implementation may be Code ready while qualification or permission holds remain"),
    "lead qualification differs from readiness": (agent, "Code ready means written implementation, not verified delivery"),
    "lead two final reviews by default": (agent, "run two independent final sidebar reviews by default"),
    "lead findings become task corrections": (agent, "route accepted findings as task corrections to fresh implementers"),
    "lead ambiguity decision releases hold": (agent, "Release only after a task correction records"),
    "lead regression when no check exists": (agent, "one real regression if none"),
    "lead challenges invented blockers": (agent, "surface real, not invented, blockers"),
    "lead keeps stops despite continuation": (agent, "Scoped stops override automatic continuation"),
    "lead honors grants without extending old holds": (agent, "Honor existing grants; do not extend past errors or pauses to unaffected work"),
    "lead prohibits extra approval stages": (agent, "Never add approval stages or re-ask to proceed with authorized work unless the owner requests it"),
    "lead respects unattended mode": (agent, "Honor the owner's selected mode; keep unattended autopilot runs in autopilot"),
    "lead acts after stalled rereads": (agent, "stop redundant rereads; advance the next missing"),
    "policy defines material ambiguity": (execution, "An ambiguity is material when existing sources leave open observable behavior"),
    "policy non-material choices follow conventions": (execution, "Settle non-material choices from existing code and conventions"),
    "policy ambiguity routes by kind": (execution, "an owner-intent choice goes to the owner and stays held until answered"),
    "policy ambiguity tournament": (execution, "risk may justify a visible tournament"),
    "policy correction releases hold": (execution, "task correction citing its evidence before releasing the hold"),
    "policy behavior before test support": (execution, "Analyze the acceptance and implement the behavior before adding test support"),
    "policy one real regression": (execution, "add one focused regression check that exercises the real behavior"),
    "policy test work is not progress": (execution, "work that does not move an acceptance criterion is not case progress"),
    "policy two final reviews by default": (execution, "run two independent read-only sidebar reviews"),
    "policy independent frozen reviews": (execution, "give both reviewers the same frozen revision, keep each unaware of the other's verdict"),
    "policy findings become corrections": (execution, "record each accepted finding that changes expected behavior as a source-linked task correction"),
    "policy fresh implementers fix findings": (execution, "Route accepted fixes to fresh implementer sidebar sessions"),
    "policy fix round cap": (execution, "After two fix rounds that leave serious findings open"),
    "policy both review verdicts": (execution, "confirm both final verdicts are PASS"),
    "policy tournament covers held interpretations": (execution, "held specification interpretations that differ on those risks"),
    "tournament compares held interpretations": (tournament_skill, "compare the sidebar research child's technical interpretations"),
    "tournament leaves owner intent to owner": (tournament_skill, "Owner-intent choices go to the owner"),
    "worker fixes only accepted finding": (work_skill, "implement only the accepted finding and its task correction"),
    "worker behavior before test support": (work_skill, "Implement the behavior before test support"),
    "worker classifies ambiguity": (work_skill, "it is an owner-intent choice, or the options differ on material technical risk"),
    "worker does not promote assumptions": (work_skill, "do not promote an agent assumption or recommendation into a requirement"),
    "worker preserves assigned base": (work_skill, "Missing sources on another ref do not authorize changing the assigned base"),
    "worker recovers stalled rereads": (work_skill, "reuse findings and change the next action or report the exact blocker"),
    "worker does not invent renewed approval": (work_skill, "do not turn an old error or a stop on other work into a new approval request"),
    "worker keeps unattended autopilot": (work_skill, "unattended autopilot work stays in autopilot"),
    "worker yields instead of synthetic waiting": (work_skill, "do not keep an idle worker alive with shell sleeps"),
    "worker emits progress boundaries": (work_skill, "At implementation-written, check-start, terminal check-result and handback boundaries"),
    "worker coalesces routine updates": (work_skill, "Normally coalesce into two short parent updates"),
    "worker avoids status and log flooding": (work_skill, "no periodic status or full logs"),
    "lead includes a worker kickoff reminder": (agent, "Include this reminder in implementation kickoffs"),
    "kickoff keeps worker logs local": (agent, "Normally coalesce code/check-start and result/handback updates; keep full logs local"),
    "lead includes in-scope wiring in code readiness": (agent, "Include in-scope producer/consumer wiring"),
    "worker distinguishes missing wiring from external inputs": (work_skill, "An unimplemented adapter or unbound in-scope consumer is unfinished code"),
    "worker readiness does not require live credentials": (work_skill, "Missing credentials or unavailable targets can hold runtime verification, not otherwise written source"),
    "review recheck follows integrated source": (review_skill, "Recheck accepted fixes on the integrated candidate"),
    "review refresh is scoped to affected paths": (review_skill, "Refresh only affected findings and producer/consumer paths"),
    "publication carries actual feature identity": (execution, "actual candidate repository, branch and commit/tree, intended target, feature path set and PR identity"),
    "publication is not merge acceptance": (execution, "Published, non-draft and mechanically mergeable do not mean review passed or safe to merge"),
    "closeout states dimensions without new status system": (execution, "Report code written, review result/open findings, publication identity and observed runtime separately"),
    "worker retains frozen-check ownership": (work_skill, "Keep any actual frozen-check/overlapping-path hold"),
    "worker uses focused failure selectors": (work_skill, "rerun its narrow selector before another broad suite"),
    "parent separates preparation from implementation": (execution, "make that a bounded preparation assignment first"),
    "parent distinguishes phases": (execution, "preparation, ownership-held, implementation, checking, and stable handback"),
    "wait signal is not semantic stall enforcement": (execution, "not infer semantic lack of progress or guarantee that a worker responds"),
    "lead verifies actual behavior": (agent, "Verify the requested behavior and report real holds truthfully"),
    "README readiness differs from qualification": (readme, "Code ready records written implementation, not successful runtime qualification"),
    "handoff qualification stays operation-specific": (long_programs, "qualification/permission holds remain operation-specific, not automatic code-readiness blockers"),
    "adopted non-trivial boundary": (stanza, "For non-trivial work use"),
    "adopted trivial-work exemption": (stanza, "Read-only questions and trivial edits need no board or sidebar"),
    "adopted board boundary": (stanza, "Open/read one tasks board when available"),
    "policy task-scoped final review": (execution, "review count, coverage split and host routing"),
    "policy resumes loop phase": (execution, "At every resumption, recover that loop"),
    "adopted development loop": (stanza, "Development loop: one case"),
    "skill routes development loop": (lead_skill, "**Development loop**"),
    "skill prohibits extra approval stages": (lead_skill, "Never add approval stages for authorized work"),
    "skill preserves real stops and permissions": (lead_skill, "Honor host permissions, stops and scoped grants"),
    "worker returns unclear contracts": (work_skill, "Return unclear specifications to the parent"),
    "claimed is queued not active": (board_source, '"claimed": "open"'),
    "explicit implementation stays blue": (board_source, '"in-progress": "active"'),
    "spec owner outcomes": (execution, "contract for the owner's requested outcomes"),
    "spec discriminating criteria": (execution, "Include discriminating cases, not just a happy path"),
    "spec one acceptance authority": (execution, "explicitly bind that row to its named detail"),
    "spec truthful attribution": (execution, "a reasonable selection is not a new owner instruction"),
    # These assert guidance presence, not semantic correctness or installed behavior.
    "spec distinct lifecycle predicates": (execution, "availability, selection for new work and validity for ongoing use"),
    "spec conditional ownership": (execution, "external ownership and conditional branches"),
    "spec correction reaches acceptance": (execution, "update or explicitly supersede affected authoritative acceptance"),
    "spec current permission": (execution, "Saved approval or completion is historical evidence, not current permission"),
    "spec composed delivery": (execution, "normal composed producer/consumer path"),
    "backend non-circular identity": (backend, "exclude the resulting hash from its own preimage"),
    "backend replay before projection": (backend, "resolve a retained replay before comparing mutable projections"),
    "backend due is not expiry": (backend, "A due timestamp is not expiration"),
    "review exact current acceptance": (rubric, "exact current authoritative acceptance"),
    "review boundary scenarios": (rubric, "starting state, action, expected transition/result"),
    "review source-only distinction": (rubric, "Label source-only inspection separately from observed execution"),
    "review schema is not delivery": (rubric, "Schema validity, unit counts and source-string assertions cannot close end-to-end claims"),
    "spec local prerequisites": (execution, "exact criterion a missing input, permission or runtime"),
    "adoption observable acceptance": (stanza, "preserve owner-goal"),
    "spec independent semantic coverage": (rubric, "every distinct owner outcome is covered"),
    "task guidance via skill": (lead_skill, "Track requests, corrections and progress through the canonical state API"),
    "lead keeps integration ownership": (agent, "until an explicit coordinator handoff"),
    "lead recovery triggers": (agent, "At corrections, handoffs, repeated failures or stalled rereads"),
    "lead next owner outcome": (agent, "next missing owner-visible outcome"),
    "policy recovery is an action": (execution, "Record the correction once when required, then execute"),
    "policy children do not direct parent": (execution, "a child supplies a bounded result, not authority over its parent"),
    "policy legitimate successor": (execution, "the predecessor may implement a bounded slice for the successor"),
    "context selected full acceptance": (execution, "selected full acceptance rows, necessary dependency rows"),
    "context pending effects survive": (execution, "pending tools/workers/queued actions, uncertain side effects"),
    "compaction is not cross-worktree handoff": (execution, "Same-session context compaction is not a coordinator/worktree handoff"),
    "context retrieval does not evict": (execution, "it does not evict already-loaded context before host compaction"),
    "policy blockers stay local": (execution, "Attach a blocker to the exact dependent operation and acceptance criterion"),
    "policy operation not verb": (execution, "Do not turn a submission restriction into a blanket transport-verb ban"),
    "policy source and delivery differ": (execution, "A handoff or source check is not the end-to-end outcome"),
    "review remains read-only during recovery": (review_skill, "The review remains read-only"),
    "review hands approved recovery to lead": (review_skill, "the existing lead applies critical-path recovery"),
    "automated reminders are not owner authority": (agent, "Automated reminders and unavailable-user fallbacks are not owner approval"),
    "proposed work is not active scope": (agent, "Proposals stay inactive until agreed"),
    "generic test approval is not substitute approval": (agent, "Generic test approval does not authorize new substitutes"),
    "first real slice before machinery": (agent, "Prove one real vertical slice before supporting machinery"),
    "separate blocked from accepted delivery": (execution, "A truthful blocked, waiting or handoff outcome is not delivery acceptance"),
    "continuation preserves waiting state": (execution, "Automated continuation does not reopen a terminal non-delivery outcome"),
    "extra work needs an acceptance dependency": (execution, "Name the failing original acceptance criterion before adding adjacent work"),
    "proposals do not become active requirements": (execution, "Do not turn an analysis-before-agreement request into an active implementation REQ"),
    "baseline checks do not broaden mandate": (execution, "A broad check finding unrelated baseline failures does not expand the mandate"),
    "review respects non-delivery termination": (rubric, "A truthful terminal blocked/waiting/handoff outcome is not delivery acceptance"),
    "original owner acceptance": (execution, "Compare original owner messages and attached reference assets against REQs and docs"),
    "visual acceptance separately measured": (execution, "intended rendered width and component coverage separately from prose"),
    "no substitute fresh execution": (execution, "No new fixtures, fakes, mocks, stubs, canned or replayed result substitutes"),
    "explicit emulator allowance": (execution, "Official local DTS/Azurite and dev-to-Azure selection"),
    "prior grants survive unanswered asks": (execution, "An unanswered redundant ask neither revokes an existing grant nor authorizes a fake fallback"),
    "direct work board startup": (agent, "including direct work"),
    "board observation when available": (lead_skill, "Open and read one tasks board when available"),
    "worker no recursive board": (work_skill, "Do not start a recursive program board"),
    "review compares original sources": (review_skill, "original owner messages and attached reference assets"),
    "review no recursive board": (review_skill, "Do not start a recursive program board"),
    "backend no substitute implementation": (implementer, "No unrequested fixtures, fakes, mocks, stubs or feature/integration flags"),
    "rubric rejects narrowed reconstruction": (rubric, "An agent-narrowed SPEC is not a replacement for original owner intent"),
    "cto duplicate signing gates": (cto_agent, "Remove duplicate signing approval gates"),
    "cto skill signing reuse": (cto_skill, "Reuse existing scoped signing grants"),
    "rubric signing reuse": (rubric, "Repeated signing approval for a current matching owner grant"),
    "cto active edits are not handoff": (cto_agent, "A dirty ledger during active editing is not by itself broken coordination"),
    "cto hold resolution": (cto_agent, "Resolved holds stay resolved"),
    "lead hold resolution": (execution, "Superseded Handoff/Verify text must not resurrect a resolved blocker"),
    "backend one scope boundary": (implementer, "DO NOT implement beyond the mandate-covered scope or contract"),
    "backend no phase ceremony": (planner, "all covered dependency-ready slices may continue without new phase approvals"),
    "backend no ledger prerequisite": (implementer, "use them rather than demanding another artifact"),
    "infra no circular backup": (infra, "not a mandatory fresh VM snapshot"),
    "observer no circular backup": (observer, "no circular creation-evidence gate"),
    "lead action advances full acceptance": (agent, "next missing owner-visible outcome toward full acceptance with authorization"),
    "policy action advances full acceptance": (execution, "next authorized action that advances the requested outcome toward its full acceptance"),
    "YAGNI requires the full acceptance": (yagni, "full acceptance, including wiring and safeguards, without speculative scope"),
    "lead desktop owner": (execution, "existing exclusive input owner"),
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
    "claim persists before dispatch": (execution, "records owner and claimed status; commit that change before dispatch"),
    "successor pins predecessor": (execution, "`--handoff --expect <predecessor-sha>`"),
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
    "fresh refs before resuming": (execution, "validates current component refs and acceptance evidence"),
    "commit-based rotation": (execution, "committed with `requirements --handoff` passing, before rotation or hand-off"),
    "scratch is not the ledger": (execution, "Worktree-local scratch such as SDD `progress.md` is a cache, never the ledger"),
    "predecessor stops relaying": (execution, "stops relaying"),
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
    "lead routes scheduled retirement": (execution, "Retire assigned scheduled automation under the Context rules"),
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
    "visible-session parallelism": (agent, "Every lane and every independent review MUST run\n  as a visible sidebar session"),
    "spec is source of truth": (execution, "The repository requirements file (config `requirements`, else `SPEC.md`) is the source of truth"),
    "tasks source of truth": (agent, "Use `.architrave/state.yaml` as the task source of truth"),
    "task statuses": (agent, "Task statuses are blank, `In progress`, or `Code ready`"),
    "trace to tasks": (agent, "Commits, child kickoffs, handoffs and reports name the tasks they serve"),
    "corrections retained": (agent, "Preserve owner corrections and never silently narrow an ask"),
    "obsolete completion gate retired": (agent, "The retired SPEC/REQ completion hook is not a prerequisite"),
    "tasks skill": (lead_skill, "Do not create SPEC.md, REQ rows or delivery declarations"),
    "tasks stanza": (stanza, "Use `python harness/architrave_cli.py state`"),
    "worker task discipline": (work_skill, "Work to assigned task/attempt IDs and acceptance from canonical `state context`"),
    "rubric grades REQs": (rubric, "Non-trivial work without REQ rows with testable acceptance is a Major finding"),
    "rubric done blocker": (rubric, "Claiming done while an in-scope REQ is not `Code ready` with final evidence and combined review"),
    "rubric legacy acceptance": (rubric, "`accepted` with evidence), or acting on an owner correction"),
    "README spec-driven lead": (readme, "Research. Decide. Build. Challenge. Deliver."),
    "first vertical slice": (execution, "first useful end-to-end product slice"),
    "no forced declarations": (agent, "Do not create SPEC.md, REQ rows, delivery declarations"),
    "product progress reporting": (agent, "Report what the product can now do"),
    "small task graph": (execution, "Keep the live task graph small"),
    "primary criterion stall signal": (execution, "When an adopted Run reports `STALLED_PRIMARY_CRITERION`"),
    "stall blocks unrelated tasks": (execution, "blocks new tasks not bound to that criterion"),
    "stall is not an idle timer": (execution, "is not an idle timer"),
    "README describes automatic criterion stall": (readme, "An adopted Run can flag a primary product criterion as stalled"),
    "installed product focus": (stanza, "Build behavior first; show evidence."),
    "README product-first guidance": (readme, "focused on one outcome"),
    "default child bounds": (agent, "default three, owner-approved up\n  to twenty (lower host limits win); depth: one"),
    "repeat-failure stop": (agent, "twice without new evidence stops the lane"),
    "progressive disclosure": (lead_skill, "Do not preload every pack"),
    "load lead only once": (lead_skill, "unless that contract is already loaded"),
    "plugin-only use needs no repo initialization": (lead_skill, "Plugin-only use does not require\nrepo initialization"),
    "unadopted repo fallback": (agent, "without adoption, use repository sources and the user mandate, not invented adoption"),
    "plugin-only edit authority": (agent, "Plugin-only source edits follow the user's mandate"),
    "adopted lead quality gate": (agent, "In an adopted repo, MUST execute"),
    "adopted stanza fallback": (stanza, "If copied alone, follow repository instructions without claiming adoption"),
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
    "policy batch single repository": (execution, "Native batch dispatch, Run claims and mutable-path conflict checks are single-repository"),
    "policy multi-repo lanes": (execution, "one isolated writer session per component repository"),
    "policy effective push target": (execution, "resolve the branch's effective push target before the first write"),
    "policy private default remote": (execution, "remote.pushDefault"),
    "policy child capability preflight": (execution, "Before assigning a child, confirm it can run the commands"),
    "policy inline unreachable context": (execution, "inline the needed acceptance and rules in the kickoff"),
    "policy shared build slot": (execution, "Heavy builds share one coordinator-owned slot"),
    "policy disk floor": (execution, "stop starting new work below the floor"),
    "policy one committed ledger": (execution, "keeps one committed requirements ledger in its coordination repository"),
    "policy ledger dependency order": (execution, "cross-repository order comes from that ledger's REQ dependencies"),
    "policy branch push remote": (execution, "branch.<name>.pushRemote"),
    "policy no private push via origin": (execution, "never push private work by naming `origin`"),
    "policy no respawn or bypass": (execution, "do not respawn the same lane or route around the denial"),
    "policy disk check before builds": (execution, "check it before builds"),
    "policy parallel source continues": (execution, "parallel lanes continue source edits and already-built non-visual checks"),
    "policy exclusive owners": (execution, "Exclusive desktop input, installed apps, VMs, signing and publication keep one owner each"),
    "lead multi-repo lanes": (execution, "Native batch is single-repository"),
    "lead child capability": (execution, "confirm the child can run its commands and read its ledger"),
    "lead shared resources": (execution, "heavy builds and disk floors are shared resources"),
    "lead continues from canonical state": (agent, "otherwise read `state context --tasks <ids>`"),
    "lead never re-dispatches duplicates": (agent, "never re-dispatch duplicates"),
    "lead integrates after every peer": (agent, "Integrate only once every peer is terminal or reconciled"),
    "lead goal-preserving handoff": (agent, "Handoffs carry the verbatim owner quote, task scope and an honest-conflict exit"),
    "policy names transport": (execution, "Name the active transport (visible sidebar sessions or the native bridge)"),
    "policy deliberate integration wave": (execution, "integrate only after every peer in the wave is terminal or reconciled, including a rejected dispatch"),
    "policy frozen base and worker check": (execution, "A completion notification never permits mutating the frozen base early"),
    "policy post-return next action": (execution, "After every child return, session resume and integration, read `nextAction`"),
    "policy duplicate return reconciled": (execution, "never re-dispatched or re-integrated"),
    "policy goal-preserving handoff": (execution, "the verbatim owner quote and REQ ids"),
    "policy honest-conflict exit": (execution, "an honest-conflict exit (report the conflict rather than silently reinterpret the ask)"),
    "policy continuation adds no ceremony": (execution, "These rules add no schema, role, ledger, mandatory form or recursion"),
}

missing = [name for name, (text, phrase) in required.items() if not contains_guidance(text, phrase)]
# These fixtures protect instruction contracts, not live agent/tool behavior.
precaution_scenarios = {
    "expired revoked or mismatched signing grant": (
        execution,
        ("Revoked, expired or mismatched grants cannot authorize execution",),
        ("An expired or revoked grant may still execute",)),
    "separate grant already covers install": (
        execution,
        ("do not re-ask when the owner already explicitly covered them",),
        ("Always re-ask even when the owner already covered it",)),
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
    "invented blockers do not override grounded holds": (
        execution,
        ("identify the governing owner direction, current contract or safety policy, host restriction, or demonstrated technical dependency",
         "an agent assumption, existing implementation, child recommendation or earlier summary is not itself a new requirement",
         "remove an unsupported hold and take the next authorized action",
         "real permission and safety holds and uncertain side effects still block their dependent operations"),
        ("Treat every suggested precaution as a mandatory prerequisite",
         "Ignore actual permission denials to keep work moving")),
    "real approval waits differ from explanations": (
        execution,
        ("Plan-only scope or an explicit instruction to wait for approval remains binding",
         "an explanation of a plan during already-authorized work is not itself an approval gate"),
        ("An explanation always requires new phase approval",
         "Proceed with writes while an explicit approval wait is pending")),
    "past errors do not invent approval requirements": (
        execution,
        ("Check the current scoped grants and the actual scope of any pause",
         "A past error or a stop on different work is not a new approval requirement",
         "a current denial still blocks its operation",
         "An expired runtime credential blocks the dependent execution, not separately authorized design or source work"),
        ("An earlier permission error always requires fresh owner approval",
         "An unrelated pause stops every operation")),
    "unattended work respects the owner's mode": (
        execution,
        ("Honor the owner's selected mode; keep unattended work in autopilot when chosen",
         "Do not switch to interactive merely to keep work moving",
         "report the actual denied operation and continue other authorized work"),
        ("Start child sessions with `create_session` kickoff mode `interactive`",
         "Bypass host permissions for unattended work")),
    "known shortfall differs from missing evidence": (
        execution,
        ("An observed result that contradicts a clear acceptance criterion is unmet, not merely unconfirmed",
         "missing or unreliable evidence remains unverified",
         "Code ready is still distinct from acceptance"),
        ("A demonstrated acceptance shortfall is merely unconfirmed",
         "Missing evidence is a passing result")),
    "answer direct questions without stalling work": (
        execution,
        ("Answer direct questions at the next available turn boundary from current evidence",
         "cite a questioned prerequisite's source or label it an inference",
         "identify the active case and count only owner-requested outcomes actually completed",
         "Observe a running action without duplicating it"),
        ("Wait for all running work to finish before answering a direct question",)),
    "owner-requested pipeline honors genuine constraints": (
        execution,
        ("dispatch the next eligible, independent assignment as capacity frees",
         "owner-set limits, actual dependencies, exclusive paths and required frozen-wave integration",
         "an advisory backlog heuristic is not a hard limit",
         "Never create redundant work solely to fill a slot"),
        ("Ignore real ownership restrictions to keep every worker busy",)),
    "model route requires host observation": (
        execution,
        ("distinguish the requested model or tier from the host-reported actual route, fallback and client version",
         "Missing telemetry neither authorizes guessing nor blocks ordinary implementation",
         "leave it unverified if the host does not expose the actual route"),
        ("Assume the requested model ran when telemetry is missing",)),
    "review findings require supported consequences": (
        execution,
        ("Require a governing criterion, relevant source and concrete consequence for each accepted finding",
         "speculation is not a verified defect"),
        ("A plausible suggestion is automatically a verified defect",)),
    "repeated rereads are not implementation progress": (
        execution,
        ("Repeated unchanged investigation without a relevant new fact, decision, acceptance delta or newly verified blocker is stalled work",
         "even when summaries retain the next action",
         "A file touch or unrelated edit alone is not product progress",
         "Surface the stall, reuse retained findings and reconcile the current case once",
         "Necessary investigation that answers a new question remains valid",
         "Compaction alone is not failure",
         "then implement a dependency-ready slice or name the exact missing fact or hold",
         "Do not substitute a coding deadline or summary-count quota for progress"),
        ("Always start coding within fifteen minutes",
         "Two summaries always require a reset",
         "Any file touch proves product progress",)),
    "context pressure is not a proven cause or permission to reset": (
        execution,
        ("Separate observed context pressure from a proven cause",
         "not a guaranteed cure",
         "preserve uncommitted work",
         "never route around denials or assume a reset safely transfers that work"),
        ("A larger context window guarantees recovery",
         "Discard uncommitted work to escape a stall",)),
    "stopped build does not forbid independently authorized edits": (
        execution,
        ("Apply an owner stop to the named operation and scope",
         "not an invented global read-only restriction or permission to resume affected implementation",
         "Continue separately authorized analysis or edits outside that stop"),
        ("A paused build always makes the whole session read-only",)),
    "automatic continuation does not clear an owner stop": (
        execution,
        ("using available provenance, not wording alone",
         "Automatic continuation does not clear a stop or authorize false completion",
         "Do not mark unfinished delivery complete to silence reminders",
         "repeat paused-status replies without a material change",
         "verify the host-reported mode",
         "do not bypass a denied mode control"),
        ("Automatic completion reminders authorize resuming stopped implementation",
         "Mark unfinished work complete to silence the host",)),
    "completed investigation is distinct from a paused feature": (
        execution,
        ("An explicit owner redirect from building to investigation changes the current request",
         "not the unfinished feature's readiness",
         "Truthfully close a completed investigation through the supported completion path",
         "implementation remains paused and incomplete",
         "do not relabel or bypass an existing delivery check"),
        ("Finishing an investigation proves the paused feature is delivered",
         "A paused feature always prevents completion of an owner-requested investigation",)),
    "missing sources do not choose a different branch baseline": (
        execution,
        ("Verify the intended base before moving a session branch to another workstream",
         "inspect other refs without moving HEAD when sufficient",
         "if the intended base is unresolved, ask before importing that history",
         "Already-authorized branch operations need no repeat approval",
         "separate inherited commits and base diff from changes produced by this session",
         "qualify unpushed counts by observed remote freshness"),
        ("Missing source files automatically authorize merging another workstream",)),
    "delegated install still pending": (
        execution,
        ("instruction sent, execution started, observed result and accepted outcome",
         "Pending delegation is not delivery", "Source/test success is not installed/native success"),
        ("An instruction sent proves delivery",)),
    "unclear case does not block independent cases or permit guessing": (
        execution,
        ("hold that behavior rather than infer a contract",
         "Continue the next independent ready case while research proceeds",
         "report that limitation and preserve the hold"),
        ("Guess the missing contract to finish the case",)),
    "missing specification or implementation still blocks final review": (
        execution,
        ("After all in-scope cases are code ready",
         "Unresolved specifications or missing implementation block Code ready",
         "Only an explicit owner scope correction can remove an in-scope case"),
        ("Missing implementation may be silently omitted",)),
    "written implementation with a qualification hold can receive source review": (
        execution,
        ("Written implementation may be Code ready while qualification or permission holds remain",
         "Such holds stay attached to their exact dependent operation and acceptance criterion",
         "they do not prevent independent source review"),
        ("A held case is not code ready",
         "Runtime qualification must pass before Code ready",)),
    "code readiness never waives dependent delivery holds": (
        execution,
        ("still block dependent deployment or delivery acceptance",
         "Code ready does not grant permission or prove acceptance"),
        ("Code ready authorizes deployment",)),
    "mechanical work does not acquire a mandatory semantic review": (
        execution,
        ("Trivial edits and mechanical changes fully proven by deterministic evidence need no semantic review unless the owner or risk policy requires it",
         "Required checks and higher review floors remain mandatory"),
        ("All development requires a sidebar review",)),
    "accepted review findings route to fresh implementers with corrected REQs": (
        execution,
        ("record each accepted finding that changes expected behavior as a source-linked task correction",
         "Route accepted fixes to fresh implementer sidebar sessions grouped by owned area, never to the reviewers",
         "the original reviewers re-check only the affected findings",
         "stop and bring the exact conflict to the owner"),
        ("Reviewers fix their own findings",)),
    "material ambiguity resolves by recorded decision": (
        execution,
        ("hold that behavior rather than infer a contract",
         "an owner-intent choice goes to the owner and stays held until answered",
         "task correction citing its evidence before releasing the hold"),
        ("Release the hold once research returns",)),
    "parallel research preserves implementation and delivery boundaries": (
        execution,
        ("Requested parallel research does not authorize parallel implementation or early delivery",
         "Parallel implementation must follow the mandate"),
        ("Research delegation marks the affected case code ready",)),
    "review and deployment settings stay task-specific": (
        execution,
        ("run two independent read-only sidebar reviews",
         "Preserve the owner's requested review count, coverage split and host routing",
         "Review routing, deployment stack and destination are task-specific",
         "Address findings, rerun affected checks and refresh affected review evidence before authorized deployment"),
        ("Every project requires the same reviewers and deployment stack",)),
    "resume restores loop rather than summary authority": (
        execution,
        ("current case, its next action, held cases and resolving children",
         "remaining cases, and final review/delivery phase",
         "not just the latest assistant summary"),
        ("A progress reply terminates the development loop",)),
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
for name, text, stale in (
    ("blanket held-case readiness returned", execution, "A held case is not code ready"),
    ("long-program blanket readiness returned", long_programs,
     "held cases do not count as code ready for final review/deployment"),
    ("lead conditional final review returned", agent, "owner-/risk-required final reviews"),
    ("policy conditional final review returned", execution,
     "when required by the owner or risk policy"),
    ("policy universal review-tier denial returned", execution,
     "No new progress file, harness or universal review tier follows"),
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
if len(agent.split()) > 1250:
    missing.append("lead exceeds its bounded lifecycle-contract budget")
if agent.find("## Development loop") > agent.find("## Core contract"):
    missing.append("development loop is buried after the core contract")
loop_contract = execution.split("## Development loop", 1)[-1].split("## Specifications", 1)[0]
for task_specific in ("Fusion", "Docker", "PostgreSQL"):
    if task_specific in loop_contract:
        missing.append(f"development loop hard-codes task-specific {task_specific}")
for phrase in ("visible intake block", "non-trivial work has canonical",
               "Missing artifacts are a Major concern"):
    if contains_guidance(rubric, phrase):
        missing.append(f"rubric still mandates blanket ceremony: {phrase}")
for manifest in ("plugin.json", ".claude-plugin/plugin.json", ".github/plugin/marketplace.json", ".codex-plugin/plugin.json"):
    if "Task-driven" not in (root / manifest).read_text(encoding="utf-8"):
        missing.append(f"{manifest} description does not lead with task-driven development")
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
