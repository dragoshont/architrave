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


REVIEW_NOTE = re.compile(r"(?:^|[;,])\s*review:\s*([^;|,]*)")


REVIEWER_ROLE = re.compile(r"(?:architrave:)?(?:adversarial-judge|code-review|rubber-duck|security-review|architrave-review)", re.I)
SESSION_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
SESSION_FACTS: dict[tuple[str, int, float], dict[str, str | None]] = {}
RULING_START = r"^[^\w>|]*(?:\(?[a-z0-9]\)\s*)?"
LABELLED_RULING = re.compile(RULING_START + r"(?i:(?:final\s+)?(?:verdict|outcome|result|ruling|(?:re-?)?review(?:\s+of\s+\S+)?)"
                             r"\W{0,6}(PASS|REVISE|FAIL))\b")
BARE_RULING = re.compile(RULING_START + r"(PASS|REVISE|FAIL)\b")
QUOTED = re.compile(r"```.*?```|`[^`\n]*`|\"[^\"\n]*\"|\u201c[^\u201d\n]*\u201d|(?<!\w)'[^'\n]*'(?!\w)", re.S)


def ruling(text: str) -> str | None:
    """A report's ruling: the first labelled line (`Verdict: REVISE`, `Re-review of X: PASS`), else the first line
    opening with an upper-case verdict (`**PASS** on ...`).

    Quoted, backticked, fenced, `>` and table lines are ignored, and a verdict word mid-sentence is never a ruling.
    """
    lines = QUOTED.sub("", text).splitlines()
    for pattern in (LABELLED_RULING, BARE_RULING):
        for line in lines:
            found = pattern.match(line)
            if found:
                return found.group(1).upper()
    return None


def session_home() -> Path:
    return Path(os.environ.get("COPILOT_HOME", Path.home() / ".copilot")) / "session-state"


def session_facts(session: str) -> dict[str, str | None] | None:
    """Kickoff role, model and final verdict of a local session log, or None when it is not logged here."""
    log = session_home() / session.lower() / "events.jsonl"
    if not SESSION_UUID.fullmatch(session.lower()) or not log.is_file():
        return None
    stat = log.stat()
    key = (session.lower(), stat.st_size, stat.st_mtime)
    if key not in SESSION_FACTS:
        role = model = None
        messages: list[str] = []
        reports: list[str] = []
        models: list[str] = []
        started = False
        with log.open(encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(event, dict):
                    continue
                data = event.get("data") if isinstance(event.get("data"), dict) else {}
                kind = event.get("type")
                if kind == "session.start" and isinstance(data.get("selectedModel"), str):
                    model = data["selectedModel"]
                    models.append(model)
                elif kind == "session.model_change" and isinstance(data.get("newModel"), str):
                    models.append(data["newModel"])
                elif kind == "subagent.selected" and not started and role is None:
                    role = str(data.get("agentName") or "")
                elif kind == "assistant.turn_start":
                    started = True
                elif kind == "assistant.message" and isinstance(data.get("content"), str):
                    messages.append(data["content"])
                elif kind == "session.task_complete" and isinstance(data.get("summary"), str):
                    reports.append(data["summary"])
                elif kind == "tool.execution_start" and data.get("toolName") == "send_session_message":
                    arguments = data.get("arguments") if isinstance(data.get("arguments"), dict) else {}
                    reports.append(str(arguments.get("message") or ""))
        said = None
        said_all = []
        # The verdict is the ruling of the reviewer's last report (task_complete or a message to another session);
        # narration counts only when the session sent no report.
        for text in reports or messages:
            found = ruling(text)
            if found:
                said = found
                said_all.append(found)
        SESSION_FACTS.clear() if len(SESSION_FACTS) > 512 else None
        SESSION_FACTS[key] = {"role": role, "model": model, "models": " ".join(models), "verdict": said,
                              "verdicts": " ".join(said_all)}
    return SESSION_FACTS[key]


def review_session(reviewer: str, verdict: str, final: bool = True) -> tuple[str, str | None]:
    """Check a `review: <session-id> <verdict>` note against the reviewer session's local log.

    ("verified", None); ("unknown", None) when the reviewer is not a session logged on this machine;
    ("contradicted", reason) when the log shows a different role or verdict. A final note (the latest naming
    this session) must match the session's last report; an earlier one only one of its reports (a re-review).
    """
    facts = session_facts(reviewer)
    if facts is None:
        return "unknown", None
    role = facts["role"] or ""
    if not REVIEWER_ROLE.fullmatch(role):
        return "contradicted", f"session {reviewer[:8]} ran {role or 'no agent role'}, not a reviewer role"
    if final and facts["verdict"] != verdict:
        return "contradicted", (f"session {reviewer[:8]} last reported {facts['verdict'] or 'no ruling'}, not {verdict}; record "
                                "its latest verdict, and use a fresh reviewer session for each delivery")
    if not final and verdict not in (facts["verdicts"] or "").split():
        return "contradicted", f"session {reviewer[:8]} never reported {verdict}"
    return "verified", None


BOARD_POINTER = "program-board.watch"


def pid_alive(pid: int) -> bool:
    """True when a process with this pid exists. Never signals on Windows, where signal 0 is CTRL_C_EVENT."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def board_watcher(session: str) -> dict[str, object] | None:
    """The live program-board watcher a coordinator session registered (files/program-board.watch), if any."""
    try:
        pointer = json.loads((session_home() / session / "files" / BOARD_POINTER).read_text(encoding="utf-8"))
        return pointer if pid_alive(int(pointer["pid"])) else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def board_note(lanes: list[dict[str, str]]) -> str | None:
    """A reminder when a coordinator with running lanes has no live board; lane sessions are never reminded."""
    session = os.environ.get("COPILOT_AGENT_SESSION_ID", "").lower()
    running = [lane for lane in lanes if lane["state"].lower() == "running"]
    if not running or not SESSION_UUID.fullmatch(session) or not session_home().is_dir():
        return None
    if any(lane["session id"].lower() == session for lane in running) or board_watcher(session):
        return None
    return (f"{len(running)} lanes running and no program board for this coordinator; start "
            "`python harness/program_board.py --watch 120` and open it in the browser canvas")


def strict_reviews() -> bool:
    """On a host that keeps local session logs, completion requires session-verified reviews."""
    return session_home().is_dir()


def review_passed(evidence: str, strict: bool = False) -> bool:
    """True when the latest well-formed review note is PASS (and, when strict, verified in its session log)."""
    notes = [(who_, v) for who_, v in review_notes(evidence) if v]
    if not notes or notes[-1][1] != "PASS":
        return False
    return not strict or review_session(notes[-1][0], "PASS")[0] == "verified"


def model_family(model: str | None) -> str:
    """Leading vendor/family token of a model id; "" when unknown or host-routed (`auto`)."""
    family = re.split(r"[-:/]", (model or "").lower())[0]
    return "" if family == "auto" else family


def model_families(session: str) -> set[str] | None:
    """Families of every model a logged session used; None when any is unknown or the session is not logged here."""
    facts = session_facts(session)
    models = (facts or {}).get("models") or ""
    families = {model_family(m) for m in models.split()}
    return families if families and all(families) else None


def lane_review_gaps(lane: dict[str, str], reqs: dict[str, dict[str, str]], strict: bool = False,
                     cross_family: bool = False) -> list[str]:
    """REQs in a lane still needing a PASS review: all open ones in a done lane, accepted ones anywhere.

    Strict (local session logs present): the latest PASS must be verified in its reviewer session log, and with
    `review.crossFamily` no model family the reviewer used may match one the lane session used.
    """
    gaps = []
    lane_families = model_families(lane.get("session id", "")) if cross_family and strict else None
    for rid in dict.fromkeys(r.upper() for r in re.findall(r"REQ-[A-Za-z0-9_.-]+", lane["req ids"], re.I)):
        row = reqs.get(rid)
        if not row or row["status"].lower() in REQ_CLOSED:
            continue
        if lane["state"].lower() != "done" and row["status"].lower() != "accepted":
            continue
        if not review_passed(row["evidence"], strict):
            gaps.append(rid)
        elif cross_family and strict:
            reviewer = [w for w, v in review_notes(row["evidence"]) if v][-1]
            reviewer_families = model_families(reviewer)
            if lane_families is None or reviewer_families is None:
                gaps.append(f"{rid} (cross-family unverifiable: a lane or reviewer model is auto or not logged here)")
            elif lane_families & reviewer_families:
                gaps.append(f"{rid} (same model family)")
    return gaps


def parallel_cap(config: dict[str, object]) -> tuple[int, str | None]:
    """workers.maxParallel clamped to 1..20 (default 3); an error string when it is not a positive integer."""
    workers = config.get("workers") or {}
    value = workers.get("maxParallel", 3) if isinstance(workers, dict) else 3
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return 3, f"workers.maxParallel {value!r} is not a positive integer"
    return min(value, 20), None


def review_notes(evidence: str) -> list[tuple[str, str | None]]:
    """Every `review: <reviewer> <verdict>` note in order; verdict None when malformed."""
    notes = []
    for note in REVIEW_NOTE.finditer(evidence):
        match = re.fullmatch(r"([A-Za-z][\w:.@/-]*|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
                             r"\s+(PASS|REVISE|FAIL)\b.*", note.group(1).strip(), re.I)
        notes.append((match.group(1), match.group(2).upper()) if match else (note.group(1).strip(), None))
    return notes


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
        notes = review_notes(row["evidence"])
        for index, (reviewer, verdict) in enumerate(notes):
            if verdict is None:
                errors.append(f"{rid} review note must read 'review: <reviewer> <PASS|REVISE|FAIL>'")
                continue
            final = all(later.lower() != reviewer.lower() for later, _v in notes[index + 1:])
            check, reason = review_session(reviewer, verdict, final)
            if check == "contradicted":
                errors.append(f"{rid} review note contradicts the session log: {reason}")
            elif who(reviewer) and who(reviewer) == who(row["owner"]):
                errors.append(f"{rid} review by {reviewer} is not independent of the owner")
        verdicts = [v for _r, v in notes if v]
        if status == "accepted" and verdicts and verdicts[-1] != "PASS":
            errors.append(f"{rid} is accepted on a {verdicts[-1]} review; record the PASS re-review")
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
OWNER_ACK = re.compile(r"owner acknowledged:\s*[\"\u201c]\S", re.I)


def lane_reqs(lane: dict[str, str]) -> list[str]:
    return [rid.upper() for rid in re.findall(r"REQ-[A-Za-z0-9_.-]+", lane["req ids"], re.I)]


def lane_errors(text: str, reqs: dict[str, dict[str, str]], max_parallel: int) -> list[str]:
    """Enforce the committed GHC lane table: one live owner per REQ and path, caps and terminal supersede."""
    errors: list[str] = []
    lanes = [dict(zip(LANE_COLUMNS, cells + [""] * len(LANE_COLUMNS)))
             for table in markdown_tables(text) if [c.lower() for c in table[0]][:3] == ["lane", "repo", "project id"]
             for cells in table[1:]]
    live = [lane for lane in lanes if lane["state"].lower() not in {"stopped", "done"}]
    names = [lane["lane"] for lane in lanes]
    for name in sorted({n for n in names if names.count(n) > 1}):
        errors.append(f"lane {name} is listed more than once")
    req_owner: dict[str, str] = {}
    paths: list[tuple[str, str, str]] = []
    for lane in lanes:
        name, state = lane["lane"], lane["state"].lower()
        if state not in LANE_STATES:
            errors.append(f"lane {name} state {lane['state']!r} is not one of {', '.join(sorted(LANE_STATES))}")
        if state == "superseded" and lane["superseded by"] in {"", "-"}:
            errors.append(f"lane {name} is superseded without 'Superseded by'")
        elif state == "superseded" and lane["superseded by"] not in names:
            errors.append(f"lane {name} is superseded by unknown lane {lane['superseded by']}")
        if state == "running" and lane["session id"] in {"", "-"}:
            errors.append(f"lane {name} is running without a session ID")
        try:
            if not isinstance(json.loads(lane["owner-only decisions"] or "[]"), list):
                raise ValueError
        except ValueError:
            errors.append(f"lane {name} 'Owner-only decisions' is not a JSON array")
        if lane["session id"] not in {"", "-"} and not re.fullmatch(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}", lane["session id"]):
            errors.append(f"lane {name} session ID {lane['session id']!r} is not a full host session UUID")
        for rid in lane_reqs(lane):
            if rid not in reqs:
                errors.append(f"lane {name} references unknown {rid}")
    for lane in live:
        for rid in lane_reqs(lane):
            if rid in req_owner:
                errors.append(f"{rid} is owned by live lanes {req_owner[rid]} and {lane['lane']}")
            req_owner[rid] = lane["lane"]
        for raw in lane["mutable paths"].split(","):
            path = re.sub(r"^(\./)+", "", raw.strip()).strip("/").rstrip("*").rstrip("/")
            if path in {"", "-"}:
                continue
            for repo, other, owner in paths:
                if repo == lane["repo"].lower() and (path == other or path.startswith(other + "/") or other.startswith(path + "/")):
                    errors.append(f"lanes {owner} and {lane['lane']} both own {lane['repo']}:{path}")
            paths.append((lane["repo"].lower(), path, lane["lane"]))
    states = {lane["lane"]: lane["state"].lower() for lane in lanes}
    for lane in lanes:
        if lane["state"].lower() != "running":
            continue
        for dep in (d.strip() for d in lane["depends on"].split(",")):
            if dep not in {"", "-"} and states.get(dep) != "done":
                errors.append(f"lane {lane['lane']} is running before dependency {dep} is done ({states.get(dep, 'missing')})")
    running = [lane for lane in live if lane["state"].lower() == "running"]
    if len(running) > max_parallel:
        errors.append(f"{len(running)} running lanes exceed workers.maxParallel={max_parallel}")
    heavy = [lane["lane"] for lane in running if lane["heavy build"].strip().lower() in {"yes", "y", "true", "1"}]
    if len(heavy) > 1:
        errors.append(f"heavy-build slot held by several running lanes: {', '.join(heavy)}")
    return errors


EVIDENCE_STATES = {"unverified", "supported", "contradicted", "stale", "superseded"}
DECISION_STATES = {"proposed", "active", "reconsider", "superseded"}
FINDING_SEVERITIES = {"low", "medium", "high", "critical", "nit", "minor", "major", "blocker"}
SERIOUS = {"high", "critical", "major", "blocker"}
CHAIN_HEADERS = {
    "evidence": ("id", "question", "source", "claim", "author", "status", "reviewed by"),
    "decision": ("id", "decision", "rejected", "evidence", "status"),
    "finding": ("id", "severity", "target", "finding", "raised by", "disposition", "verified by", "evidence"),
}
FINDING_DISPOSITIONS = {"open", "fixed", "rejected", "accepted-risk", "deferred"}
GIT_SOURCE = re.compile(r"\b([A-Za-z0-9_.-]+)@([0-9a-fA-F]{7,40}):([^\s|,;`]+)")


def who(value: str) -> str:
    """Normalize a person/lane label so 'L1 (lane)' and 'l1' compare equal."""
    return re.sub(r"\s+", " ", re.sub(r"\(.*?\)", "", value)).strip(" -_.`").lower()


def header_errors(text: str) -> list[str]:
    """A table that looks like an evidence/decision/finding/lane table must use the exact header, or it is not checked."""
    errors = []
    for table in markdown_tables(text):
        head = tuple(c.lower() for c in table[0])
        first = head[:1] == ("id",)
        kind = ("finding" if first and any(c.startswith("sev") for c in head) and any("finding" in c for c in head) else
                "evidence" if first and any(c.startswith("source") for c in head) and any(c.startswith("claim") for c in head) else
                "decision" if head[:1] == ("id",) and len(head) > 1 and "decision" in head[1] else
                "lane" if head[:1] == ("lane",) and any("repo" in c for c in head) else None)
        expected = LANE_COLUMNS if kind == "lane" else CHAIN_HEADERS.get(kind or "")
        if expected and head != expected:
            errors.append(f"{kind} table header must be exactly | {' | '.join(expected)} | (got | {' | '.join(head)} |)")
    return errors


def ledger_table(text: str, prefix: tuple[str, ...], columns: tuple[str, ...]) -> list[dict[str, str]]:
    return [dict(zip(columns, cells + [""] * len(columns)))
            for table in markdown_tables(text) if tuple(c.lower() for c in table[0][:len(prefix)]) == prefix
            for cells in table[1:]]


def ref_ids(text: str, kind: str) -> list[str]:
    return re.findall(rf"\b{kind}-[A-Za-z0-9_.]+(?:-[A-Za-z0-9_.]+)*\b", text)


def git_source_errors(root: Path, sid: str, source: str, status: str, repos: dict[str, Path]) -> tuple[list[str], list[str]]:
    """Resolve `<repo>@<commit>:<path>` sources; a changed file at the repo's HEAD makes the claim stale."""
    errors: list[str] = []
    notes: list[str] = []
    for name, commit, rel in GIT_SOURCE.findall(source):
        repo = repos.get(name)
        if repo is None or git(repo, "rev-parse", "--git-dir") is None:
            notes.append(f"{sid}: {name} checkout not configured here; source {name}@{commit}:{rel} unverified")
            continue
        if git(repo, "cat-file", "-e", f"{commit}^{{commit}}") is None:
            errors.append(f"{sid} source commit {name}@{commit} does not resolve")
            continue
        cited = git(repo, "rev-parse", f"{commit}:{rel}")
        if cited is None:
            errors.append(f"{sid} source {rel} is absent at {name}@{commit}")
            continue
        if subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", commit, "HEAD"],
                          capture_output=True, check=False).returncode:
            notes.append(f"{sid}: {name} HEAD does not contain {commit}; freshness of {rel} unverified here")
            continue
        current = git(repo, "rev-parse", f"HEAD:{rel}")
        if current != cited and status not in {"stale", "superseded", "contradicted"}:
            errors.append(f"{sid} source {name}:{rel} changed since {commit}; mark it stale and reconsider dependent decisions")
    return errors, notes


def chain_errors(root: Path, text: str, reqs: dict[str, dict[str, str]],
                 config: dict[str, object]) -> tuple[list[str], list[str], list[str]]:
    """Research -> decision -> requirement -> finding links: (errors, done-blockers, notes)."""
    evidence = {row["id"]: row for row in ledger_table(
        text, ("id", "question", "source"), ("id", "question", "source", "claim", "author", "status", "reviewed by"))}
    decisions = {row["id"]: row for row in ledger_table(
        text, ("id", "decision", "rejected"), ("id", "decision", "rejected", "evidence", "status"))}
    findings = ledger_table(text, ("id", "severity", "target", "finding"),
                            ("id", "severity", "target", "finding", "raised by", "disposition", "verified by", "evidence"))
    errors: list[str] = []
    blockers: list[str] = []
    notes: list[str] = []
    repos = {"self": root}
    for item in config.get("components") or []:
        if isinstance(item, dict) and isinstance(item.get("name"), str) and isinstance(item.get("path"), str):
            repos[item["name"]] = component_path(root, item["path"])
    known = set(reqs) | set(evidence) | set(decisions)
    local = [repo for repo in repos.values() if git(repo, "rev-parse", "--git-dir") is not None]

    def verifiable(value: str) -> bool:
        if any(i in known for i in ref_ids(value, "E") + ref_ids(value, "D")):
            return True
        shas = re.findall(r"\b[0-9a-fA-F]{7,40}\b", value)
        if not local:
            return bool(shas)
        return any(git(repo, "cat-file", "-e", f"{sha}^{{commit}}") is not None for sha in shas for repo in local)

    for eid, row in evidence.items():
        status = row["status"].lower()
        if status not in EVIDENCE_STATES:
            errors.append(f"{eid} status {row['status']!r} is not one of {', '.join(sorted(EVIDENCE_STATES))}")
        if not row["source"] or not row["claim"]:
            errors.append(f"{eid} needs a source and the claim it supports")
        if status == "supported":
            reviewer = row["reviewed by"].strip()
            if reviewer in {"", "-"} or who(reviewer) == who(row["author"]):
                errors.append(f"{eid} is supported without an independent reviewer (not the author)")
        if re.search(r"https?://", row["source"]) and not re.search(r"\d{4}-\d{2}-\d{2}", row["source"]):
            errors.append(f"{eid} web source needs a retrieval date (YYYY-MM-DD)")
        more, info = git_source_errors(root, eid, row["source"], status, repos)
        errors += more
        notes += info
    for did, row in decisions.items():
        status = row["status"].lower()
        if status not in DECISION_STATES:
            errors.append(f"{did} status {row['status']!r} is not one of {', '.join(sorted(DECISION_STATES))}")
        if row["rejected"].strip() in {"", "-"}:
            errors.append(f"{did} records no rejected alternatives")
        cited = ref_ids(row["evidence"], "E")
        for eid in cited:
            if eid not in evidence:
                errors.append(f"{did} cites unknown {eid}")
        if status == "active":
            if not cited:
                errors.append(f"{did} is active without evidence")
            weak = [e for e in cited if e in evidence and evidence[e]["status"].lower() != "supported"]
            if weak:
                errors.append(f"{did} is active but rests on {', '.join(f'{e} ({evidence[e]['status']})' for e in weak)}; set it to reconsider")
    for rid, row in reqs.items():
        for did in ref_ids(" ".join((row["requirement"], row["acceptance"], row["evidence"])), "D"):
            if did not in decisions:
                errors.append(f"{rid} cites unknown {did}")
            elif row["status"].lower() == "accepted" and decisions[did]["status"].lower() in {"reconsider", "proposed"}:
                errors.append(f"{rid} is accepted on {did}, which is {decisions[did]['status']}")
    for row in findings:
        fid, severity, disposition = row["id"], row["severity"].lower(), row["disposition"].lower()
        if severity not in FINDING_SEVERITIES:
            errors.append(f"{fid} severity {row['severity']!r} is not one of {', '.join(sorted(FINDING_SEVERITIES))}")
        if disposition not in FINDING_DISPOSITIONS:
            errors.append(f"{fid} disposition {row['disposition']!r} is not one of {', '.join(sorted(FINDING_DISPOSITIONS))}")
        targets = ref_ids(row["target"], "REQ") + ref_ids(row["target"], "D") + ref_ids(row["target"], "E")
        for target in targets:
            if target not in known:
                errors.append(f"{fid} targets unknown {target}")
        serious = severity in SERIOUS
        if disposition in {"fixed", "rejected"} and not verifiable(row["evidence"]):
            errors.append(f"{fid} is {disposition} without verifiable evidence (a commit that resolves in a configured repo, or an existing E-/D- id); agreement is not evidence")
        if serious and disposition in {"fixed", "rejected"}:
            verifier = who(row["verified by"])
            owners = {who(reqs[t]["owner"]) for t in targets if t in reqs}
            owners |= {who(evidence[t]["author"]) for t in targets if t in evidence}
            if verifier in {"", "-"} or verifier in owners:
                errors.append(f"{fid} {severity} finding needs verification by someone other than the target's owner")
        if serious and disposition in {"accepted-risk", "deferred"} and not OWNER_ACK.search(row["evidence"]):
            errors.append(f"{fid} {severity} finding is {disposition} without a quoted owner acknowledgement")
        if serious and disposition == "open":
            blockers.append(fid)
            for target in targets:
                if target in reqs and reqs[target]["status"].lower() == "accepted":
                    errors.append(f"{target} is accepted while {severity} finding {fid} is open")
    return errors, blockers, notes


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
    config = load_config(root)
    more, blockers, notes = chain_errors(root, text, reqs, config)
    errors.extend(more)
    for note in notes:
        print(f"note  {note}")
    errors.extend(header_errors(text))
    max_parallel, cap_error = parallel_cap(config)
    errors.extend([cap_error] if cap_error else [])
    errors.extend(lane_errors(text, reqs, max_parallel))
    lanes = ledger_table(text, ("lane", "repo", "project id"), LANE_COLUMNS)
    reminder = board_note(lanes)
    if reminder:
        print(f"note  {reminder}")
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
                   if c["type"].lower() == "narrow" and not OWNER_ACK.search(c["change"])]
        if unacked:
            errors.append(f"not done: narrow corrections lack owner acknowledgement: {', '.join(unacked)}")
        if blockers:
            errors.append(f"not done: open serious findings: {', '.join(blockers)}")
        strict = strict_reviews()
        for lane in lanes:
            if lane["state"].lower() == "done" and lane["session id"] in {"", "-"}:
                errors.append(f"not done: lane {lane['lane']} is done without the session that did the work")
            elif lane["state"].lower() == "done" and strict and session_facts(lane["session id"]) is None:
                errors.append(f"not done: lane {lane['lane']} session {lane['session id'][:8]} is not logged on this machine; "
                              "record the visible session that did the work")
            unreviewed = lane_review_gaps(lane, reqs, strict, bool((config.get("review") or {}).get("crossFamily"))
                                          if isinstance(config.get("review"), dict) else False)
            if unreviewed:
                errors.append(f"not done: lane {lane['lane']} ({lane['state']}) lacks a PASS review on {', '.join(unreviewed)}")
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
