#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
agent = (root / "agents/architrave.agent.md").read_text(encoding="utf-8")
execution = (root / "knowledge/execution-policy.md").read_text(encoding="utf-8")
rubric = (root / "gates/rubric.md").read_text(encoding="utf-8")
learning = (root / "knowledge/learning-loop.md").read_text(encoding="utf-8")
stanza = (root / "templates/AGENTS.stanza.md").read_text(encoding="utf-8")
readme = (root / "README.md").read_text(encoding="utf-8")
roadmap = (root / "ROADMAP.md").read_text(encoding="utf-8")
generator = (root / "scripts/generate-codex-agents.py").read_text(encoding="utf-8")
codex_roles = "\n".join(
    path.read_text(encoding="utf-8") for path in sorted((root / ".codex/agents").glob("*.toml"))
)

required = {
    "agent vertical slice": (agent, "smallest demonstrable user-visible vertical slice"),
    "agent support budget": (agent, "at most\n  two consecutive tasks or one full-gate cycle"),
    "agent task gate": (agent, "A supporting task does not independently trigger a full gate"),
    "agent stall": (agent, "no new output for 15 minutes"),
    "host-owned execution": (execution, "user and the active host harness"),
    "compact records": (execution, "one rolling recovery snapshot"),
    "rubric delivery": (rubric, "Delivery focus and verification cadence"),
    "artifact accounting": (learning, "Artifacts are audit support, not delivery currency"),
    "installed stanza": (stanza, "smallest demonstrable"),
    "README bounded tournament": (readme, "A full\n**Tournament of Options** is reserved"),
    "README host-owned execution": (readme, "Execution stays host-owned"),
    "roadmap bounded tournament": (roadmap, "a Tournament of Options only for materially ambiguous or high-risk choices"),
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
if missing:
    raise SystemExit("delivery-focus validation failed: " + ", ".join(missing))

print("delivery-focus validation: PASS")
