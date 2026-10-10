#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
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
tournament_agent = (root / "agents/tournament-analyst.agent.md").read_text(encoding="utf-8")
generator = (root / "scripts/generate-codex-agents.py").read_text(encoding="utf-8")
codex_roles = "\n".join(
    path.read_text(encoding="utf-8") for path in sorted((root / ".codex/agents").glob("*.toml"))
)

required = {
    "on-demand vertical slice": (execution, "smallest demonstrable user-visible vertical slice"),
    "on-demand support budget": (execution, "at most two consecutive tasks or one\nfull-gate cycle"),
    "on-demand task gate": (execution, "A supporting task does not\nindependently trigger a full gate"),
    "on-demand stall": (execution, "no new output for 15 minutes"),
    "host-owned execution": (execution, "user and\nthe active host harness"),
    "compact records": (execution, "one rolling recovery snapshot"),
    "rubric delivery": (rubric, "Delivery focus and verification cadence"),
    "artifact accounting": (learning, "Artifacts are audit support, not delivery currency"),
    "installed stanza": (stanza, "smallest\ndemonstrable"),
    "README bounded tournament": (readme, "A full\n**Tournament of Options** is reserved"),
    "README host-owned execution": (readme, "Execution stays host-owned"),
    "roadmap bounded tournament": (roadmap, "a Tournament of Options only for materially ambiguous or high-risk choices"),
    "on-demand reference parity": (execution, "parity test against that\nreference on the real flow, before any hardening"),
    "on-demand primary stall": (runtime_pack, "`STALLED_PRIMARY_CRITERION`"),
    "on-demand diagnostic specificity": (execution, "Collapsing distinct causes into one generic failure code is a gate"),
    "execution lenient parsing": (execution, "Default-deny is not a parsing policy"),
    "execution proportional ceremony": (execution, "R0/R1 single-path fixes need no\nper-change pin, receipt, or qualification Run"),
    "execution approved quit": (execution, "escalate a graceful quit to SIGTERM after a timeout without a new hold"),
    "rubric product copy": (rubric, "Internal evidence, spec, status, certification, or receipt\n    language in user-facing UI strings"),
    "agent consults cto": (agent, "Consult architrave:cto at start and on stall"),
    "skill consults cto": (lead_skill, "Consult architrave:cto at start and on stall"),
    "stanza consults cto": (stanza, "Consult architrave:cto at start and on stall"),
    "cto agent routes": (cto_agent, "never implements"),
    "cto skill outcome": (cto_skill, "Outcome over ceremony"),
    "cto skill push-back": (cto_skill, "KEEP/CUT/DEFER verdict"),
    "agent push-back": (agent, "Push back KEEP/CUT/DEFER with one reason"),
    "tournament skill baselines": (tournament_skill, 'include a "do nothing" baseline and a "smallest viable" option'),
    "tournament skill beats nothing": (tournament_skill, "why the chosen\noption beats doing nothing"),
    "tournament typed result": (tournament_skill, "typed as `DO_NOTHING` and `SMALLEST_VIABLE`"),
    "review prefers host-native": (review_skill, "Prefer the host-native reviewer"),
    "review records reviewer": (review_skill, "--reviewer\nhost-native|architrave-judge --family"),
    "agent host-native review": (agent, "`architrave-review`; `gates/rubric.md`"),
    "direct-work threshold": (agent, "Use direct work for one continuous trace"),
    "visible-session parallelism": (agent, "prefer coordinated, user-visible sessions"),
    "default child bounds": (agent, "three (lower host limits win); depth: one"),
    "repeat-failure stop": (agent, "twice without new evidence stops the lane"),
    "progressive disclosure": (lead_skill, "Do not preload every pack"),
    "skill session parallelism": (lead_skill, "prefer coordinated visible sessions"),
    "plugin-only use needs no repo initialization": (lead_skill, "Plugin-only use does not require\nrepo initialization"),
    "unadopted repo fallback": (agent, "if the config or adopted kit\nfiles are absent"),
    "adopted stanza fallback": (stanza, "if this stanza is copied without the rest of the kit"),
    "optional repo adoption": (readme, "Optional repo adoption"),
    "README CLI delegation fallback": (readme, "Claude Code or Copilot CLI"),
    "mandate-driven continuation": (agent, "a status update is not a stopping"),
    "mid-development research": (execution, "Feedback and unknowns during implementation"),
    "mandate safety boundary": (lead_skill, "urgency never bypasses consent or scope"),
    "execution CLI delegation fallback": (execution, "Claude Code or Copilot CLI"),
    "stanza session parallelism": (stanza, "prefer coordinated\nsidebar sessions"),
    "on-demand feasibility": (cto_skill, "On-demand feasibility reset"),
    "adaptive window": (cto_skill, "Estimate a finite time/turn/output window"),
    "explicit owner ceiling": (cto_skill, "deadlines/ceilings win"),
    "no clock reset": (cto_skill, "Unchanged evidence cannot renew the window"),
    "tournament agent baselines": (tournament_agent, 'include a "do nothing" baseline and a "smallest viable" option'),
}

missing = [name for name, (text, phrase) in required.items() if phrase not in text]
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

runtime = (root / "harness" / "architrave_runtime.py").read_text(encoding="utf-8")
if '"model": value.get("model")' in runtime:
    missing.append("WorkPackets still persist model selection")
for path in sorted((root / "agents").glob("*.agent.md")):
    text = path.read_text(encoding="utf-8")
    if "disable-model-invocation" in text or "\nmodel:" in text:
        missing.append(f"{path.relative_to(root)} still contains model-selection metadata")
if '"CTO"' not in agent.split("---", 2)[1]:
    missing.append("conductor does not route to the CTO agent")
if any(line.startswith("tools:") for line in agent_frontmatter.splitlines()):
    missing.append("conductor restricts the host-provided default tool set")
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
