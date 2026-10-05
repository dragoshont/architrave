#!/usr/bin/env python3
"""Canonical stdlib-only Architrave deterministic gates."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from platform_launch import LaunchError, configured_shell_command

# Internal delivery vocabulary that must not leak into shipping UI strings.
DEFAULT_FORBIDDEN_COPY = (
    r"\bevidence\b",
    r"\breceipts?\b",
    r"\battest(?:s|ed|ation)?\b",
    r"\bqualification\b",
    r"\bcertif(?:ied|ication)\b",
    r"\bprovenance\b",
    r"\bregistry only\b",
    r"\bUNTESTED\b",
    r"\bacceptance criteri(?:on|a)\b",
    r"\bspec (?:status|only|compliant)\b",
)


def repository_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / "architrave.config.json").is_file():
            return candidate
    raise ValueError("architrave.config.json not found")


def load_config(root: Path) -> dict[str, object]:
    try:
        value = json.loads((root / "architrave.config.json").read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid architrave.config.json ({exc})") from exc
    if not isinstance(value, dict):
        raise ValueError("architrave.config.json root must be an object")
    return value


def run_recipe(root: Path, name: str, recipe: object) -> bool:
    if not isinstance(recipe, str) or not recipe.strip():
        return True
    print(f"== {name}: {recipe} ==")
    try:
        command = configured_shell_command(recipe)
    except LaunchError as exc:
        print(f"FAIL  {name} ({exc})")
        return False
    process = subprocess.run(command, cwd=root, check=False)
    if process.returncode:
        print(f"FAIL  {name} (exit {process.returncode})")
        return False
    print(f"ok    {name}")
    return True


def validate_profile(config: dict[str, object]) -> list[str]:
    errors: list[str] = []
    if config.get("kind") == "knowledge":
        for field in ("build", "test"):
            if not isinstance(config.get(field), str) or not str(config[field]).strip():
                errors.append(f"knowledge profile requires {field}")
        forbidden = {
            "platform", "stack", "designSource", "designMap", "tokens", "tokenBuild",
            "knowledgePack", "applyTo", "generate", "screenshot", "backend", "iac", "ops",
        }
        present = sorted(forbidden.intersection(config))
        if present:
            errors.append("knowledge profile forbids " + ", ".join(present))
    elif "kind" in config:
        errors.append("kind must be absent or 'knowledge'")
    else:
        for field in ("platform", "stack", "designSource", "applyTo", "build", "test"):
            if field not in config:
                errors.append(f"application profile requires {field}")
    return errors


def check_json_reference(root: Path, value: object, label: str) -> bool:
    if not isinstance(value, str) or not value.lower().endswith(".json"):
        return True
    path = root / value
    if not path.is_file():
        print(f"warn  {label} {value} (missing)")
        return True
    try:
        json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        print(f"FAIL  {label} {value} (invalid JSON)")
        return False
    print(f"ok    {label} {value}")
    return True


def check_product_copy(root: Path, config: dict[str, object]) -> bool:
    block = config.get("productCopy")
    if block is None:
        return True
    if not isinstance(block, dict) or not isinstance(block.get("paths"), list) or not block["paths"]:
        print("FAIL  productCopy requires a non-empty paths list")
        return False
    try:
        patterns = [re.compile(str(item), re.IGNORECASE) for item in block.get("forbidden") or DEFAULT_FORBIDDEN_COPY]
    except re.error as exc:
        print(f"FAIL  productCopy forbidden pattern ({exc})")
        return False
    files: set[Path] = set()
    for pattern in block["paths"]:
        if not isinstance(pattern, str) or not pattern or Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            print(f"FAIL  productCopy path must be repository-relative: {pattern}")
            return False
        files.update(path for path in root.glob(pattern) if path.is_file())
    findings = []
    for path in sorted(files):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            for compiled in patterns:
                match = compiled.search(line)
                if match:
                    findings.append(f"{path.relative_to(root).as_posix()}:{number}: '{match.group(0)}'")
    for finding in findings:
        print(f"FAIL  product copy uses internal language {finding}")
    if not findings:
        print(f"ok    product copy ({len(files)} files)")
    return not findings


MESSAGE_NOISE = (
    ("hash/id", re.compile(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{12,}\b|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-", re.IGNORECASE)),
    ("pid", re.compile(r"\bpids?\s*[=:#]?\s*\d+", re.IGNORECASE)),
    ("compressed status", re.compile(r"\b[A-Za-z]+\d+/[A-Za-z]+\d+\b")),
)


def message_lint(text: str) -> int:
    """Fail owner-facing text dense with hashes, PIDs, IDs, or compressed status."""
    findings = [(label, match.group(0)) for label, pattern in MESSAGE_NOISE for match in pattern.finditer(text)]
    if len(findings) >= 3:
        for label, token in findings:
            print(f"FAIL  owner message {label}: {token}")
        print("message-lint: FAIL - rewrite in plain sentences; keep at most two identifiers")
        return 1
    print("message-lint: PASS")
    return 0


def checks(root: Path, quick: bool) -> int:
    try:
        config = load_config(root)
    except ValueError as exc:
        print(f"checks: {exc}", file=sys.stderr)
        return 2
    errors = validate_profile(config)
    if errors:
        for error in errors:
            print(f"FAIL  {error}")
        return 1
    if config.get("kind") == "knowledge":
        print("profile knowledge: UI design JSON validation not applicable")
    else:
        design = config.get("designSource")
        if isinstance(design, dict):
            if not check_json_reference(root, design.get("path"), "design source"):
                return 1
        if not check_json_reference(root, config.get("designMap"), "design map"):
            return 1
        if not check_json_reference(root, config.get("tokens"), "tokens"):
            return 1
    if not check_product_copy(root, config):
        return 1
    if quick:
        print("ARCHITRAVE-CHECKS: PASS")
        return 0
    success = True
    for name in ("generate", "build", "test"):
        success = run_recipe(root, name, config.get(name)) and success
    print("ARCHITRAVE-CHECKS: PASS" if success else "ARCHITRAVE-CHECKS: FAIL")
    return 0 if success else 1


def reconcile(root: Path) -> int:
    try:
        config = load_config(root)
    except ValueError as exc:
        print(f"reconcile: {exc}", file=sys.stderr)
        return 2
    if config.get("kind") == "knowledge":
        print("reconcile: UI design reconciliation not applicable for knowledge profile; skipping (PASS)")
        return 0
    recipe = config.get("tokenBuild")
    if not config.get("tokens") or not recipe:
        print("reconcile: tokens/tokenBuild not configured - skipping (PASS)")
        return 0
    if not run_recipe(root, "regenerate from tokens", recipe):
        return 2
    process = subprocess.run(["git", "diff", "--quiet"], cwd=root, check=False)
    if process.returncode == 0:
        print("reconcile: PASS - generated output matches committed code")
        return 0
    print("reconcile: DRIFT - committed code differs from tokens")
    subprocess.run(["git", "--no-pager", "diff", "--stat"], cwd=root, check=False)
    return 1


def backend(root: Path) -> int:
    try:
        config = load_config(root)
    except ValueError as exc:
        print(f"backend-checks: {exc}", file=sys.stderr)
        return 2
    blocks = [
        ("backend-build", (config.get("backend") or {}).get("build") if isinstance(config.get("backend"), dict) else None),
        ("backend-test", (config.get("backend") or {}).get("test") if isinstance(config.get("backend"), dict) else None),
        ("iac-plan", (config.get("iac") or {}).get("plan") if isinstance(config.get("iac"), dict) else None),
        ("iac-policy", (config.get("iac") or {}).get("policy") if isinstance(config.get("iac"), dict) else None),
    ]
    configured = [(name, recipe) for name, recipe in blocks if recipe]
    if not configured:
        print("skip  no backend/iac block in architrave.config.json")
        return 0
    success = all(run_recipe(root, name, recipe) for name, recipe in configured)
    return 0 if success else 1


def quality(root: Path, hook_json: bool) -> int:
    if hook_json:
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            result = checks(root, True)
    else:
        captured = None
        result = checks(root, True)
    if result == 0:
        if hook_json:
            sys.stdout.write('{"continue":true}')
            return 0
        config = load_config(root)
        if config.get("kind") == "knowledge":
            print("quality-gate: knowledge profile config valid.")
        else:
            print("quality-gate: design JSON valid.")
        return 0
    if hook_json:
        detail = captured.getvalue().strip() if captured else ""
        if detail:
            print(detail, file=sys.stderr)
        print("quality-gate: BLOCKING - configured JSON validation failed.", file=sys.stderr)
    else:
        print("quality-gate: BLOCKING - configured JSON validation failed.")
    return 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("gate", choices=["checks", "reconcile", "quality-gate", "backend-checks", "message-lint"])
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--hook-json", action="store_true")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--file", help="message-lint: text file to check (default stdin)")
    args = parser.parse_args()
    if args.gate == "message-lint":
        text = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
        return message_lint(text)
    try:
        root = repository_root(Path(args.repo))
    except ValueError as exc:
        print(f"{args.gate}: {exc}", file=sys.stderr)
        return 2
    if args.gate == "checks":
        return checks(root, args.quick)
    if args.gate == "reconcile":
        return reconcile(root)
    if args.gate == "backend-checks":
        return backend(root)
    return quality(root, args.hook_json)


if __name__ == "__main__":
    raise SystemExit(main())
