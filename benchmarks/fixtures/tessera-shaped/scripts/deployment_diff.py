import json
from pathlib import Path


root = Path(__file__).resolve().parents[1]
desired = json.loads((root / "deploy" / "release.json").read_text())
current = json.loads((root / "deploy" / "live.json").read_text())
print(json.dumps({"changed": desired != current, "before": current, "after": desired}, sort_keys=True))