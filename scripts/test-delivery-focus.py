#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
agent = (root / "agents/architrave.agent.md").read_text()
execution = (root / "knowledge/execution-policy.md").read_text()
rubric = (root / "gates/rubric.md").read_text()
learning = (root / "knowledge/learning-loop.md").read_text()
stanza = (root / "templates/AGENTS.stanza.md").read_text()
readme = (root / "README.md").read_text()
roadmap = (root / "ROADMAP.md").read_text()
generator = (root / "scripts/generate-codex-agents.py").read_text()
codex_roles = "\n".join(
    path.read_text() for path in sorted((root / ".codex/agents").glob("*.toml"))
)

required = {
    "agent vertical slice": (agent, "smallest demonstrable user-visible vertical slice"),
    "agent support budget": (agent, "at most\n  two consecutive tasks or one full-gate cycle"),
    "agent task gate": (agent, "A supporting task does not independently trigger a full gate"),
    "agent stall": (agent, "no new output for 15 minutes"),
    "direct work": (execution, "at most two files change"),
    "review consolidation": (execution, "two semantic reopens trigger consolidation"),
    "rubric delivery": (rubric, "Delivery focus and verification cadence"),
    "artifact accounting": (learning, "Artifacts are audit support, not delivery currency"),
    "installed stanza": (stanza, "smallest demonstrable"),
    "README bounded tournament": (readme, "A full\n**Tournament of Options** is reserved"),
    "README local model binding": (readme, "concrete model bindings remain host- or user-local"),
    "roadmap bounded tournament": (roadmap, "a Tournament of Options only for materially ambiguous or high-risk choices"),
}

missing = [name for name, (text, phrase) in required.items() if phrase not in text]
if "before task or Outcome completion" in agent:
    missing.append("per-task full-gate phrase remains")
if "Then it runs a **Tournament of Options**" in readme:
    missing.append("README still requires a universal tournament")
if "Mandatory visible intake and Tournament of Options" in roadmap:
    missing.append("ROADMAP still requires a universal tournament")
if "GPT-5.6 Sol MAX" in readme or "Claude Opus 4.8 MAX" in readme:
    missing.append("README still presents concrete model bindings as policy")
if 'model = "' in codex_roles or "model_reasoning_effort" in codex_roles:
    missing.append("generated Codex roles still pin a concrete model")
if "'model = " in generator or "model_reasoning_effort" in generator:
    missing.append("Codex role generator still emits concrete model policy")
if missing:
    raise SystemExit("delivery-focus validation failed: " + ", ".join(missing))

print("delivery-focus validation: PASS")
