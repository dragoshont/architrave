import argparse
import json
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("--field")
args = parser.parse_args()
state = json.loads((Path(__file__).resolve().parents[1] / "deploy" / "live.json").read_text())
print(state.get(args.field, "") if args.field else json.dumps(state, sort_keys=True))