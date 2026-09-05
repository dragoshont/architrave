#!/usr/bin/env python3
"""Small deterministic Codex CLI double for structural packaging tests."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


def main() -> int:
    args = sys.argv[1:]
    home = Path(os.environ["CODEX_HOME"])
    root = Path(os.environ["ARCHITRAVE_ROOT"])
    if args[:5] == ["plugin", "marketplace", "add", str(root), "--json"]:
        print(json.dumps({"name": "architrave"}))
        return 0
    if args[:4] == ["plugin", "add", "architrave@architrave", "--json"]:
        installed = home / "plugins" / "architrave"
        skills = installed / "skills"
        if installed.exists():
            shutil.rmtree(installed)
        for name in ("architrave", "architrave-review", "architrave-tournament"):
            target = skills / name
            target.mkdir(parents=True)
            source = root / "skills" / name / "SKILL.md"
            shutil.copyfile(source, target / "SKILL.md")
        print(json.dumps({"pluginId": "architrave@architrave", "installedPath": str(installed)}))
        return 0
    if args[-3:] == ["debug", "prompt-input", "x"]:
        print("architrave:architrave:")
        return 0
    if args[-3:] == ["mcp", "list", "--json"]:
        print(json.dumps([{"name": "architrave_fixture", "enabled": True}]))
        return 0
    print(f"unsupported fake codex invocation: {' '.join(args)}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
