from pathlib import Path
import shutil


root = Path(__file__).resolve().parents[1]
shutil.copyfile(root / "deploy" / "release.json", root / "deploy" / "live.json")
print("sandbox deployment applied")