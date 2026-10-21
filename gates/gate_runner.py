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
    return errors + validate_components(config.get("components"))


REPO_NAME = re.compile(r"^(?!\.+/)[A-Za-z0-9._-]+/(?!\.+$)[A-Za-z0-9._-]+$")
# Agent session scratch: clones here vanish with the session and hide forks from their real repository.
SCRATCH_PARTS = ((".copilot", "session-state"), (".copilot", "chats"), (".codex", "sessions"), (".claude", "projects"))


def validate_components(components: object) -> list[str]:
    if components is None:
        return []
    if not isinstance(components, list) or not components:
        return ["components must be a non-empty list"]
    errors: list[str] = []
    names: set[str] = set()
    for index, item in enumerate(components):
        if not isinstance(item, dict):
            errors.append(f"components[{index}] must be an object")
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name:
            errors.append(f"components[{index}] requires name")
        elif name in names:
            errors.append(f"duplicate component {name}")
        else:
            names.add(name)
        for field in ("repo", "upstream"):
            value = item.get(field)
            if (field == "repo" or value is not None) and not (isinstance(value, str) and REPO_NAME.match(value)):
                errors.append(f"component {name} {field} must be owner/name")
        if item.get("upstream") and str(item.get("upstream")).lower() == str(item.get("repo")).lower():
            errors.append(f"component {name} repo must not be its read-only upstream")
    for item in components:
        if isinstance(item, dict):
            for used in item.get("consumes") or []:
                if used not in names:
                    errors.append(f"component {item.get('name')} consumes unknown component {used}")
    return errors


def github_name(url: str) -> str | None:
    url = url.strip()
    match = (re.match(r"^[a-z][a-z0-9+.-]*://(?:[^@/]+@)?([^/:]+)(?::\d+)?/(.+)$", url, re.IGNORECASE)
             or re.match(r"^(?:[^@/]+@)?([^/:]+):(?!/)(.+)$", url))
    if not match or match.group(1).lower() != "github.com":
        return None
    name = re.sub(r"\.git$", "", match.group(2).rstrip("/"), flags=re.IGNORECASE)
    return name.lower() if REPO_NAME.match(name) else None


def git(path: Path, *args: str) -> str | None:
    process = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, check=False)
    return process.stdout.strip() if process.returncode == 0 else None


def component_path(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return (path if path.is_absolute() else root / path).resolve()


def in_scratch(path: Path) -> bool:
    parts = path.parts
    return any(parts[i:i + 2] == pair for pair in SCRATCH_PARTS for i in range(len(parts) - 1))


def check_component(root: Path, item: dict[str, object]) -> tuple[bool, Path | None]:
    name, repo = item["name"], str(item["repo"]).lower()
    if not item.get("path"):
        print(f"skip  {name}: no local path")
        return True, None
    path = component_path(root, str(item["path"]))
    if in_scratch(path):
        print(f"FAIL  {name}: {path} is agent session scratch; clone {repo} to a normal checkout")
        return False, None
    if git(path, "rev-parse", "--git-dir") is None:
        print(f"FAIL  {name}: {path} is not a git checkout")
        return False, None
    branch = git(path, "branch", "--show-current") or ""
    keys = ([f"branch.{branch}.pushRemote"] if branch else []) + ["remote.pushDefault"] + ([f"branch.{branch}.remote"] if branch else [])
    remote = next((value for value in (git(path, "config", "--get", key) for key in keys) if value), "origin")
    push_urls = (git(path, "remote", "get-url", "--push", "--all", remote) or "").splitlines() or ["missing"]
    upstream = str(item.get("upstream") or "").lower()
    for push_url in push_urls:
        target = github_name(push_url)
        if target != repo:
            hint = "read-only upstream; " if target and target == upstream else ""
            print(f"FAIL  {name}: {branch or 'HEAD'} pushes to {remote}={push_url} ({hint}expected {repo}); "
                  f"set the push remote to {repo}")
            return False, path
    unpushed = git(path, "rev-list", "--count", "HEAD", "--not", "--remotes") or "0"
    dirty = len((git(path, "status", "--porcelain") or "").splitlines())
    note = f"{branch or 'detached'}, {unpushed} unpushed commits, {dirty} changed files"
    print(f"{'warn' if unpushed != '0' or dirty else 'ok  '}  {name}: {note}")
    return True, path


def components(root: Path, run_tests: bool) -> int:
    try:
        config = load_config(root)
    except ValueError as exc:
        print(f"components: {exc}", file=sys.stderr)
        return 2
    items = config.get("components")
    if items is None:
        print("components: none configured - skipping (PASS)")
        return 0
    errors = validate_components(items)
    for error in errors:
        print(f"FAIL  {error}")
    if errors:
        return 1
    success = True
    for item in items:
        ok, path = check_component(root, item)
        success = ok and success
        if not run_tests:
            continue
        if item.get("ui") and not item.get("service"):
            print(f"FAIL  {item['name']}: ui tests need a service test first")
            success = False
            continue
        if ok and path is None and (item.get("service") or item.get("ui")):
            print(f"FAIL  {item['name']}: tests are configured but there is no local path to run them in")
            success = False
        if not ok or path is None:
            continue
        if item.get("service") and not run_recipe(path, f"{item['name']} service", item["service"]):
            if item.get("ui"):
                print(f"skip  {item['name']} ui (service failed)")
            success = False
            continue
        success = run_recipe(path, f"{item['name']} ui", item.get("ui")) and success
    print("ARCHITRAVE-COMPONENTS: PASS" if success else "ARCHITRAVE-COMPONENTS: FAIL")
    return 0 if success else 1


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
    parser.add_argument("gate", choices=["checks", "reconcile", "quality-gate", "backend-checks", "message-lint", "components"])
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--test", action="store_true", help="components: run service then ui tests")
    parser.add_argument("--hook-json", action="store_true")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--file", help="message-lint: text file to check (default stdin)")
    args = parser.parse_args()
    if args.gate == "message-lint":
        from architrave_runtime import owner_message_lint

        text = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
        lint = owner_message_lint(text)
        for finding in (lint or {}).get("findings", []):
            print(f"FAIL  owner message identifier: {finding}")
        print(f"message-lint: {lint['code']} - {lint['message']}" if lint else "message-lint: PASS")
        return 1 if lint else 0
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
    if args.gate == "components":
        return components(root, args.test)
    return quality(root, args.hook_json)


if __name__ == "__main__":
    raise SystemExit(main())
