import json
from pathlib import Path


root = Path(__file__).resolve().parents[1]
state = json.loads((root / "deploy" / "live.json").read_text())
if state.get("status") != "healthy":
    raise SystemExit("sandbox deployment is unhealthy")
print("healthy")