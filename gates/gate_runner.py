#!/usr/bin/env python3
"""Canonical stdlib-only Architrave deterministic gates."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time


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


GATE_TAIL_LINES = 40


def run_recipe(root: Path, name: str, recipe: object) -> bool:
    if not isinstance(recipe, str) or not recipe.strip():
        return True
    print(f"== {name}: {recipe} ==")
    try:
        command = configured_shell_command(recipe)
    except LaunchError as exc:
        print(f"FAIL  {name} ({exc})")
        return False
    process = subprocess.run(
        command, cwd=root, check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    output = process.stdout or ""
    if os.environ.get("ARCHITRAVE_GATE_VERBOSE") == "1":
        print(output, end="")
    if process.returncode:
        lines = output.splitlines()
        log = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", prefix=f"{log_slug(name)}-", suffix=".log", delete=False, dir=gate_log_dir()
        )
        with log:
            log.write(output)
        if os.environ.get("ARCHITRAVE_GATE_VERBOSE") != "1":
            if len(lines) > GATE_TAIL_LINES:
                print(f"... {len(lines) - GATE_TAIL_LINES} earlier lines in {log.name}")
            print("\n".join(lines[-GATE_TAIL_LINES:]))
        print(f"FAIL  {name} (exit {process.returncode}; full log: {log.name})")
        return False
    print(f"ok    {name}")
    return True


GATE_LOG_KEEP = 20


def log_slug(name: str) -> str:
    return (re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.") or "recipe")[:40]


def gate_log_dir() -> str:
    """Private per-user failure-log directory, keeping only the newest GATE_LOG_KEEP logs."""
    path = Path(tempfile.gettempdir()) / f"architrave-gate-logs-{os.getuid() if hasattr(os, 'getuid') else 'user'}"
    path.mkdir(mode=0o700, exist_ok=True)
    logs = sorted(path.glob("*.log"), key=lambda item: item.stat().st_mtime)
    for old in logs[:max(0, len(logs) - GATE_LOG_KEEP + 1)]:
        old.unlink(missing_ok=True)
    return str(path)


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
    requirements = config.get("requirements")
    if requirements is not None and not (isinstance(requirements, str) and requirements):
        errors.append("requirements must be a non-empty path")
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


REQ_COLUMNS = ("id", "requirement", "acceptance", "owner", "status", "evidence")
REQ_ACTIVE = {"open", "claimed", "in-progress", "blocked", "accepted"}
REQ_CLOSED = {"superseded", "withdrawn"}
CORRECTION_TYPES = {"add", "revise", "retract", "supersede", "narrow"}
HANDOFF_FIELDS = ("next", "failed approaches", "verify")


def markdown_tables(text: str) -> list[list[list[str]]]:
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in text.splitlines() + [""]:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [cell.strip() for cell in stripped[1:-1].split("|")]
            if not all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells if cell):
                current.append(cells)
        elif current:
            tables.append(current)
            current = []
    return tables


def section(text: str, title: str) -> str:
    match = re.search(rf"^##\s+{re.escape(title)}\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S | re.I)
    return match.group(1) if match else ""


def parse_requirements(text: str) -> tuple[dict[str, dict[str, str]], list[dict[str, str]], list[str]]:
    """Parse the long-program requirements file: REQ table, typed corrections and handoff."""
    reqs: dict[str, dict[str, str]] = {}
    corrections: list[dict[str, str]] = []
    errors: list[str] = []
    for table in markdown_tables(text):
        header = [cell.lower() for cell in table[0]]
        if header[: len(REQ_COLUMNS)] == list(REQ_COLUMNS):
            for cells in table[1:]:
                row = dict(zip(REQ_COLUMNS, cells + [""] * len(REQ_COLUMNS)))
                rid = row["id"]
                if not re.fullmatch(r"REQ-[A-Za-z0-9_.-]+", rid):
                    errors.append(f"row id {rid!r} is not REQ-<id>")
                elif rid in reqs:
                    errors.append(f"{rid} is listed twice")
                reqs[rid] = row
        elif header[:4] == ["id", "type", "target", "change"]:
            corrections.extend(dict(zip(("id", "type", "target", "change"), cells + [""] * 4)) for cells in table[1:])
    if not reqs:
        errors.append("no requirements table with columns | ID | Requirement | Acceptance | Owner | Status | Evidence |")
    for rid, row in reqs.items():
        status = row["status"].lower()
        if status not in REQ_ACTIVE | REQ_CLOSED:
            errors.append(f"{rid} status {row['status']!r} is not one of {', '.join(sorted(REQ_ACTIVE | REQ_CLOSED))}")
        if status in REQ_ACTIVE and not row["acceptance"]:
            errors.append(f"{rid} has no testable acceptance")
        if status == "accepted" and not row["evidence"]:
            errors.append(f"{rid} is accepted without evidence")
        if status in REQ_CLOSED and not any(rid in c["target"] for c in corrections):
            errors.append(f"{rid} is {status} but no correction row records why")
    for item in corrections:
        if item["type"].lower() not in CORRECTION_TYPES:
            errors.append(f"correction {item['id']} type {item['type']!r} is not one of {', '.join(sorted(CORRECTION_TYPES))}")
        for target in re.findall(r"REQ-[A-Za-z0-9_.-]+", item["target"]):
            if target not in reqs:
                errors.append(f"correction {item['id']} targets unknown {target}")
    handoff = section(text, "Handoff")
    for field in HANDOFF_FIELDS:
        match = re.search(rf"^[ \t>*_-]*{field}[ \t*_]*:[ \t*_]*(\S.*)$", handoff, re.M | re.I)
        if not match:
            errors.append(f"## Handoff needs a non-empty '{field.capitalize()}:' line")
    return reqs, corrections, errors


LANE_COLUMNS = ("lane", "repo", "project id", "branch", "push target", "req ids", "depends on", "session id",
                "assignment id", "state", "mutable paths", "heavy build", "preflight", "preflight evidence",
                "preflight reported", "owner-only decisions", "superseded by")
LANE_STATES = {"ready", "running", "blocked", "idle", "superseded", "stopped", "done"}
NARROW_ACK = re.compile(r"owner acknowledged:\s*[\"\u201c]\S", re.I)


def lane_errors(text: str, reqs: dict[str, dict[str, str]], max_parallel: int) -> list[str]:
    """Enforce the committed GHC lane table: one live owner per REQ and path, caps and terminal supersede."""
    errors: list[str] = []
    lanes = [dict(zip(LANE_COLUMNS, cells + [""] * len(LANE_COLUMNS)))
             for table in markdown_tables(text) if [c.lower() for c in table[0]][:3] == ["lane", "repo", "project id"]
             for cells in table[1:]]
    live = [lane for lane in lanes if lane["state"].lower() not in {"stopped", "done"}]
    req_owner: dict[str, str] = {}
    paths: list[tuple[str, str, str]] = []
    for lane in lanes:
        name, state = lane["lane"], lane["state"].lower()
        if state not in LANE_STATES:
            errors.append(f"lane {name} state {lane['state']!r} is not one of {', '.join(sorted(LANE_STATES))}")
        if state == "superseded" and lane["superseded by"] in {"", "-"}:
            errors.append(f"lane {name} is superseded without 'Superseded by'")
        try:
            if not isinstance(json.loads(lane["owner-only decisions"] or "[]"), list):
                raise ValueError
        except ValueError:
            errors.append(f"lane {name} 'Owner-only decisions' is not a JSON array")
        for rid in re.findall(r"REQ-[A-Za-z0-9_.-]+", lane["req ids"]):
            if rid not in reqs:
                errors.append(f"lane {name} references unknown {rid}")
    for lane in live:
        for rid in re.findall(r"REQ-[A-Za-z0-9_.-]+", lane["req ids"]):
            if rid in req_owner:
                errors.append(f"{rid} is owned by live lanes {req_owner[rid]} and {lane['lane']}")
            req_owner[rid] = lane["lane"]
        for raw in lane["mutable paths"].split(","):
            path = raw.strip().strip("/")
            if path in {"", "-"}:
                continue
            for repo, other, owner in paths:
                if repo == lane["repo"] and (path == other or path.startswith(other + "/") or other.startswith(path + "/")):
                    errors.append(f"lanes {owner} and {lane['lane']} both own {lane['repo']}:{path}")
            paths.append((lane["repo"], path, lane["lane"]))
    running = [lane for lane in live if lane["state"].lower() == "running"]
    if len(running) > max_parallel:
        errors.append(f"{len(running)} running lanes exceed workers.maxParallel={max_parallel}")
    heavy = [lane["lane"] for lane in running if lane["heavy build"].lower() == "yes"]
    if len(heavy) > 1:
        errors.append(f"heavy-build slot held by several running lanes: {', '.join(heavy)}")
    return errors


DEFAULT_REQUIREMENTS = "SPEC.md"
REQ_TABLE_HEADER = re.compile(r"^\|\s*ID\s*\|.*\|\s*Status\s*\|", re.IGNORECASE | re.MULTILINE)


def configured_requirements(root: Path, config: dict[str, object]) -> object:
    """Spec-driven default: the configured file, else a root SPEC.md that contains a REQ table.

    A prose SPEC.md without the `| ID | ... | Status |` header is not adopted; set `requirements`
    explicitly to make an existing file the ledger.
    """
    value = config.get("requirements")
    if value:
        return value
    path = root / DEFAULT_REQUIREMENTS
    try:
        text = path.read_text(encoding="utf-8-sig") if path.is_file() else ""
    except (OSError, UnicodeError):
        return None
    return DEFAULT_REQUIREMENTS if REQ_TABLE_HEADER.search(text) else None


def requirements_path(root: Path, value: object) -> tuple[Path | None, str | None]:
    path = component_path(root, str(value))
    if in_scratch(path):
        return None, f"{path} is agent session scratch; keep it in a repository"
    if not path.is_file() or not path.read_text(encoding="utf-8-sig").strip():
        return None, f"{value} is missing or empty"
    return path, None


def check_requirements(root: Path, value: object, count: int) -> bool:
    """A multi-component program needs one repo-resident requirements file that survives sessions."""
    if not value:
        if count < 2:
            return True
        print("FAIL  requirements: several components are mapped but no `requirements` file is configured; "
              "add a repository requirements file (REQ ids, acceptance, owner, status) before dispatching children")
        return False
    path, error = requirements_path(root, value)
    if error:
        print(f"FAIL  requirements: {error}")
        return False
    _, _, errors = parse_requirements(path.read_text(encoding="utf-8-sig"))
    for item in errors:
        print(f"FAIL  requirements: {item}")
    if not errors:
        print(f"ok    requirements: {value}")
    return not errors


SDD_LEDGERS = ".superpowers/sdd/*/progress.md"


def worktrees(root: Path) -> list[Path]:
    """Every checkout of this clone, this one first (they share one git common directory)."""
    listed = git(root, "worktree", "list", "--porcelain") or ""
    others = [Path(line[9:]).resolve() for line in listed.splitlines() if line.startswith("worktree ")]
    return [root] + [path for path in others if path != root and path.is_dir()]


def plan_ledgers(checkout: Path, plan: str) -> list[Path]:
    """Worktree-local SDD ledgers whose plan is this requirements file (marker, else legacy slug)."""
    found = []
    for ledger in sorted(checkout.glob(SDD_LEDGERS)):
        try:
            marker = (ledger.parent / "plan-path").read_text(encoding="utf-8").strip()
        except OSError:
            marker = None
        if marker == plan or (marker is None and ledger.parent.name == Path(plan).stem):
            found.append(ledger)
    return found


def handoff_errors(root: Path, path: Path, expect: str | None = None) -> list[str]:
    """Durable hand-off: committed requirements and no newer state stranded in a worktree-local ledger."""
    root = root.resolve()
    try:
        plan = path.resolve().relative_to(root).as_posix()
    except ValueError:
        return [f"--handoff: {path} is outside this checkout; commit the ledger in its own repository"]
    errors = []
    if git(root, "rev-parse", "--is-inside-work-tree") != "true":
        return [f"--handoff: {root} is not a git checkout; the ledger cannot travel to another worktree"]
    if expect is not None:
        if not re.fullmatch(r"[0-9a-fA-F]{7,40}", expect):
            errors.append("--expect needs a commit SHA (7-40 hexadecimal characters)")
        elif not git(root, "rev-parse", "--verify", f"{expect}^{{commit}}"):
            errors.append(f"--expect: unknown handoff commit {expect}; fetch the predecessor commit first")
        elif subprocess.run(["git", "merge-base", "--is-ancestor", expect, "HEAD"], cwd=root,
                            capture_output=True, check=False).returncode != 0:
            errors.append(f"--expect: HEAD does not contain expected handoff commit {expect}; "
                          "start from the predecessor's committed handoff")
    if git(root, "status", "--porcelain", "--", plan):
        errors.append(f"--handoff: {plan} has uncommitted changes; commit it so the next session's checkout has it")
    if not git(root, "log", "-1", "--format=%h", "--", plan):
        return errors + [f"--handoff: {plan} has never been committed on this branch"]
    for checkout in worktrees(root):
        # Author time survives rebase and amend, so drift errs toward a fixable FAIL, never a silent PASS.
        committed = (git(checkout, "log", "-1", "--format=%at %h", "--", plan) or "0 none").split()
        stamp, sha = int(committed[0]), committed[1]
        branch = git(checkout, "branch", "--show-current") or "detached"
        for ledger in plan_ledgers(checkout, plan):
            relative = ledger.relative_to(checkout).as_posix()
            tracked = git(checkout, "ls-files", "--error-unmatch", "--", relative) is not None
            if tracked:
                newer = bool(git(checkout, "status", "--porcelain", "--", relative))
            else:
                # A future-dated commit cannot prove ordering, so the ledger counts as newer.
                newer = ledger.stat().st_mtime > stamp + 1 or stamp > time.time() + 60
            if not newer:
                print(f"ok    {ledger} ({'tracked' if tracked else 'scratch'}, not newer than {plan}@{sha})")
            elif checkout == root:
                errors.append(f"--handoff: {ledger} holds progress not in committed {plan}@{sha}; fold its completed "
                              "tasks into REQ Evidence/Handoff and commit, then delete the folded scratch or commit "
                              "the ledger itself (git add -f)")
            else:
                print(f"warn  {ledger} on {branch} changed after its {plan}@{sha}; if it is your predecessor's, "
                      "fold it into the requirements file before continuing; never start a second ledger")
    upstream = git(root, "rev-list", "--count", "@{upstream}..HEAD")
    if upstream not in (None, "0"):
        print(f"warn  {upstream} commits are not pushed; a successor in another clone will not see them")
    return errors


def requirements_gate(root: Path, claim: str | None, owner: str | None, done: bool,
                      requested_root: Path | None = None, handoff: bool = False,
                      expect: str | None = None) -> int:
    """Validate the ledger; record coordinator-owned claims only after every check passes."""
    try:
        value = configured_requirements(root, load_config(root))
    except ValueError as exc:
        print(f"requirements: {exc}", file=sys.stderr)
        return 2
    if not value:
        if claim is not None or done or handoff or expect is not None:
            print(f"FAIL  requirements: no requirements ledger resolves for --claim/--done/--handoff; "
                  f"resolved root: {root}; config: {root / 'architrave.config.json'}. "
                  "Configure `requirements` or add a SPEC.md requirements table at the resolved root.")
            if requested_root is not None:
                requested_root = requested_root.resolve()
                if requested_root != root and configured_requirements(requested_root, {}):
                    print(f"FAIL  requirements: {requested_root / DEFAULT_REQUIREMENTS} contains a "
                          "requirements table but is not selected by the parent config; "
                          "add a project config or configure the intended ledger explicitly.")
            print("ARCHITRAVE-REQUIREMENTS: FAIL")
            return 1
        if (root / DEFAULT_REQUIREMENTS).is_file():
            print(f"requirements: {DEFAULT_REQUIREMENTS} has no requirements table "
                  "(| ID | ... | Status |) and `requirements` is not configured - skipping (PASS)")
        else:
            print(f"requirements: no `requirements` configured and no {DEFAULT_REQUIREMENTS} - skipping (PASS)")
        return 0
    path, error = requirements_path(root, value)
    if error:
        print(f"FAIL  requirements: {error}")
        print("ARCHITRAVE-REQUIREMENTS: FAIL")
        return 1
    text = path.read_text(encoding="utf-8-sig")
    reqs, corrections, errors = parse_requirements(text)
    workers = load_config(root).get("workers") or {}
    errors.extend(lane_errors(text, reqs, int(workers.get("maxParallel", 3)) if isinstance(workers, dict) else 3))
    ids = [part.strip() for part in (claim or "").split(",") if part.strip()]
    if expect is not None and not handoff:
        errors.append("--expect requires --handoff")
    if claim is not None:
        if not ids:
            errors.append("--claim needs at least one REQ id")
        if handoff or done:
            errors.append("--claim cannot be combined with --handoff or --done; commit claims before dispatch")
        if not owner or not owner.strip():
            errors.append("--claim needs --owner (the lane/session that will own these REQs)")
        elif any(c in owner for c in "|\r\n"):
            errors.append("--owner must be a single Markdown table cell without pipes or newlines")
        else:
            owner = owner.strip()
        for rid in ids:
            row = reqs.get(rid)
            if row is None:
                errors.append(f"claim {rid}: not in {value}")
                continue
            status = row["status"].lower()
            if status in REQ_CLOSED | {"accepted"}:
                errors.append(f"claim {rid}: status is {status}; do not dispatch it")
            elif row["owner"] and owner and row["owner"] != owner:
                errors.append(f"claim {rid}: already owned by {row['owner']}; do not spawn a duplicate lane")
            else:
                print(f"ok    {rid} [{status}] {row['requirement']}\n        acceptance: {row['acceptance']}")
                for item in corrections:
                    if rid in item["target"]:
                        print(f"        correction {item['id']} ({item['type']}): {item['change']}")
    if handoff:
        errors.extend(handoff_errors(root, path, expect))
    if done:
        pending = [rid for rid, row in reqs.items() if row["status"].lower() in REQ_ACTIVE - {"accepted"}]
        if pending:
            errors.append(f"not done: {len(pending)} active REQs are not accepted: {', '.join(pending[:20])}")
        unacked = [c["id"] for c in corrections
                   if c["type"].lower() == "narrow" and not NARROW_ACK.search(c["change"])]
        if unacked:
            errors.append(f"not done: narrow corrections lack owner acknowledgement: {', '.join(unacked)}")
    if claim is not None and not errors:
        lines = []
        in_requirements = False
        for line in text.splitlines(keepends=True):
            cells = line.strip().split("|")
            if not line.strip().startswith("|"):
                in_requirements = False
            elif [cell.strip().lower() for cell in cells[1:7]] == list(REQ_COLUMNS):
                in_requirements = True
            if in_requirements and len(cells) >= 8 and cells[1].strip() in ids:
                rid = cells[1].strip()
                row = reqs[rid]
                row["owner"] = owner
                if row["status"].lower() == "open":
                    row["status"] = "claimed"
                cells[4], cells[5] = f" {owner} ", f" {row['status']} "
                line = "|".join(cells) + ("\n" if line.endswith("\n") else "")
            lines.append(line)
        try:
            path.write_text("".join(lines), encoding="utf-8")
        except OSError as exc:
            errors.append(f"--claim: cannot write {path}: {exc}")
        else:
            print(f"ok    recorded claims in {value}; commit before dispatch (single coordinator writer)")
    for item in errors:
        print(f"FAIL  requirements: {item}")
    counts: dict[str, int] = {}
    for row in reqs.values():
        counts[row["status"].lower()] = counts.get(row["status"].lower(), 0) + 1
    print("requirements: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    print("ARCHITRAVE-REQUIREMENTS: " + ("FAIL" if errors else "PASS"))
    return 1 if errors else 0


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
    success = check_requirements(root, configured_requirements(root, config), len(items))
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
    spec = configured_requirements(root, config)
    if spec and not check_requirements(root, spec, 0):
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
    parser.add_argument("gate", choices=["checks", "reconcile", "quality-gate", "backend-checks", "message-lint", "components", "requirements"])
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--test", action="store_true", help="components: run service then ui tests")
    parser.add_argument("--hook-json", action="store_true")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--claim", help="requirements: record owner/claimed status for comma-separated REQ ids; commit before dispatch")
    parser.add_argument("--owner", help="requirements: lane/session owner for --claim")
    parser.add_argument("--done", action="store_true", help="requirements: fail unless every active REQ is accepted")
    parser.add_argument("--handoff", action="store_true",
                        help="requirements: fail unless hand-off state is committed and not stranded in a worktree ledger")
    parser.add_argument("--expect", help="requirements --handoff: require this predecessor commit SHA in HEAD history")
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
    if args.gate == "requirements":
        return requirements_gate(root, args.claim, args.owner, args.done, Path(args.repo), args.handoff, args.expect)
    return quality(root, args.hook_json)


if __name__ == "__main__":
    raise SystemExit(main())
