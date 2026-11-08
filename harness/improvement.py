#!/usr/bin/env python3
"""Repo-local improvement proposals and executable-first lesson promotion."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import signal
import subprocess
import sys
import tempfile

from validate_learning import SECRET_RE

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gates"))
import delivery_check

LEDGER = ".architrave/learning/improvements.jsonl"
ASSUMPTIONS = ".architrave/learning/harness-assumptions.md"
KINDS = {"gate", "test", "lint", "skill", "instruction", "retire"}
STATUSES = {"proposed", "approved", "merged", "rejected"}
TAIL_LIMIT = 2000
HASH_RE = re.compile(r"[0-9a-f]{64}")
ACTION_FIELDS = {
    "operation", "proposal", "lesson_identity", "source_sha256", "target",
    "target_sha256", "content_sha256", "result_sha256", "owner_reference",
    "applied_block", "insertion_offset", "rollback_of", "source_row", "heading",
}


def repo_path(root: Path, value: str, *, reject_symlinks: bool = False) -> Path:
    path = Path(value.replace("\\", "/"))
    windows = PureWindowsPath(value)
    if not value or path.is_absolute() or windows.drive or windows.root or ".." in windows.parts:
        raise ValueError("path must be repo-relative and stay inside the repo")
    root = root.resolve()
    candidate = root
    for component in path.parts:
        candidate /= component
        if reject_symlinks and candidate.is_symlink():
            raise ValueError("symlink paths are not accepted")
    target = candidate.resolve()
    if not target.is_relative_to(root) or target == root:
        raise ValueError("path must be repo-relative and stay inside the repo")
    return target


def global_instruction(root: Path, target: str) -> bool:
    names = {target.replace("\\", "/").casefold(),
             repo_path(root, target).relative_to(root).as_posix().casefold()}
    return any(name in {"agents.md", ".github/copilot-instructions.md"} or (
        name.startswith("agents/") and name.endswith(".agent.md")
    ) for name in names)


PROTECTED_FILES = {"agents.md", "claude.md", "spec.md", "architrave.config.json"}
PROTECTED_DIRS = (".github/", ".architrave/", ".claude/", ".codex/", "agents/", "skills/", "gates/", "harness/")


def protected_target(root: Path, relative: str) -> bool:
    name = relative.casefold()
    configured = set()
    config = root / "architrave.config.json"
    try:
        value = json.loads(config.read_text(encoding="utf-8")).get("requirements") if config.is_file() else None
        if isinstance(value, str):
            configured.add(value.replace("\\", "/").removeprefix("./").casefold())
    except (OSError, ValueError, AttributeError):
        return True
    return (name in PROTECTED_FILES | configured or name.startswith(PROTECTED_DIRS)
            or global_instruction(root, relative))


def target_digest(root: Path, target: str) -> str:
    path = repo_path(root, target, reject_symlinks=True)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "missing"


def nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_proposal(row: object, root: Path) -> None:
    if not isinstance(row, dict):
        raise ValueError("proposal must be an object")
    required = {"id", "source_lessons", "failure_fingerprint", "kind", "target", "summary",
                "before_command", "after_command", "evidence", "status", "approver", "owner_approved"}
    if set(row) not in (required, required | {"learning_actions"}):
        raise ValueError("proposal fields do not match the improvement contract")
    row.setdefault("learning_actions", [])
    if not isinstance(row["id"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", row["id"]):
        raise ValueError("invalid proposal id")
    if row["kind"] not in KINDS or row["status"] not in STATUSES:
        raise ValueError("invalid proposal kind/status")
    sources = row["source_lessons"]
    if not isinstance(sources, list) or any(not nonempty(item) for item in sources):
        raise ValueError("source_lessons must be a list of lesson ids")
    if not isinstance(row["failure_fingerprint"], str) or not (sources or row["failure_fingerprint"].strip()):
        raise ValueError("source lesson or failure fingerprint is required")
    for key in ("target", "summary"):
        if not nonempty(row[key]):
            raise ValueError(f"{key} is required")
    repo_path(root, row["target"], reject_symlinks=True)
    for key in ("before_command", "after_command", "approver"):
        if not isinstance(row[key], str):
            raise ValueError(f"{key} must be text")
    if not isinstance(row["owner_approved"], bool):
        raise ValueError("owner_approved must be boolean")
    evidence = row["evidence"]
    if not isinstance(evidence, dict) or set(evidence) - {"before", "after"}:
        raise ValueError("invalid evidence phases")
    for phase, result in evidence.items():
        if not isinstance(result, dict) or set(result) != {"command", "exit_code", "tail", "target_digest"}:
            raise ValueError("invalid check evidence")
        if not nonempty(result["command"]) or result["command"] != row[f"{phase}_command"]:
            raise ValueError("evidence command does not match proposal")
        if type(result["exit_code"]) is not int or not isinstance(result["tail"], str) or len(result["tail"]) > TAIL_LIMIT:
            raise ValueError("invalid exit code/output tail")
        digest = result["target_digest"]
        if not isinstance(digest, str) or not (digest == "missing" or re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ValueError("invalid target digest")
    if "after" in evidence and "before" not in evidence:
        raise ValueError("after evidence requires before evidence")
    actions = row["learning_actions"]
    if not isinstance(actions, list):
        raise ValueError("learning_actions must be a list")
    for action in actions:
        if not isinstance(action, dict) or set(action) != ACTION_FIELDS:
            raise ValueError("invalid learning application evidence")
        if action["operation"] not in {"apply", "rollback"}:
            raise ValueError("invalid learning operation")
        for key in ("proposal", "lesson_identity", "source_sha256"):
            if not isinstance(action[key], str) or not HASH_RE.fullmatch(action[key]):
                raise ValueError(f"invalid learning evidence hash: {key}")
        for key in ("target_sha256", "content_sha256", "result_sha256"):
            if not isinstance(action[key], str) or not (
                action[key] == "missing" or HASH_RE.fullmatch(action[key])
            ):
                raise ValueError(f"invalid learning evidence hash: {key}")
        repo_path(root, action["target"], reject_symlinks=True)
        if action["content_sha256"] != action["result_sha256"]:
            raise ValueError("learning result must match the approved content hash")
        if not isinstance(action["owner_reference"], dict) or set(action["owner_reference"]) != {
            "event_id", "sha256", "attachments"
        }:
            raise ValueError("invalid original owner event reference")
        owner_ref = action["owner_reference"]
        if (not nonempty(owner_ref["event_id"]) or not isinstance(owner_ref["sha256"], str)
                or not HASH_RE.fullmatch(owner_ref["sha256"]) or not isinstance(owner_ref["attachments"], list)):
            raise ValueError("invalid original owner event identity")
        if not isinstance(action["applied_block"], str) or not action["applied_block"]:
            raise ValueError("learning evidence must retain the exact inverse block")
        source_row = action["source_row"]
        if (not isinstance(source_row, dict) or not source_row
                or any(not isinstance(key, str) or not isinstance(value, str)
                       for key, value in source_row.items())
                or not nonempty(action["heading"])):
            raise ValueError("learning evidence must retain candidate provenance and heading")
        if _lesson_identity(source_row, action["source_sha256"], action["target"],
                            action["heading"], action["applied_block"].encode("utf-8")) != action["lesson_identity"]:
            raise ValueError("learning candidate provenance does not match its identity")
        if (type(action["insertion_offset"]) is not int or action["insertion_offset"] < 0
                or (action["operation"] == "apply" and action["rollback_of"] is not None)
                or (action["operation"] == "rollback" and
                    (not isinstance(action["rollback_of"], str) or not HASH_RE.fullmatch(action["rollback_of"])))):
            raise ValueError("invalid learning inverse evidence")
    if row["status"] in {"approved", "merged"}:
        if not nonempty(row["approver"]):
            raise ValueError("approved/merged proposal requires approver")
        approval_ready(row, root)
    elif row["status"] == "proposed" and (row["approver"] or row["owner_approved"]):
        raise ValueError("proposed improvement cannot claim approval")
    if SECRET_RE.search(json.dumps(row)):
        raise ValueError("possible secret material in proposal")


def approval_ready(row: dict, root: Path, *, check_source: bool = False) -> None:
    evidence = row["evidence"]
    if "before" not in evidence or "after" not in evidence or evidence["after"]["exit_code"] != 0:
        raise ValueError("approval requires recorded before (failure or baseline) and passing after evidence")
    if global_instruction(root, row["target"]) and not row["owner_approved"]:
        raise ValueError("always-loaded global instruction requires --owner-approved")
    if check_source and evidence["after"]["target_digest"] != target_digest(root, row["target"]):
        raise ValueError("target changed since passing after check; rerun the check")


def ledger_digest(root: Path) -> str | None:
    path = repo_path(root, LEDGER, reject_symlinks=True)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def load_proposals(root: Path) -> list[dict]:
    path = repo_path(root, LEDGER, reject_symlinks=True)
    rows: list[dict] = []
    if not path.exists():
        return rows
    if not path.is_file() or not path.read_text(encoding="utf-8").strip():
        raise ValueError("empty improvement ledger")
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            validate_proposal(row, root)
            if any(previous["id"] == row["id"] for previous in rows):
                raise ValueError("duplicate proposal id")
            rows.append(row)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{LEDGER}:{number}: {exc}") from exc
    if not rows:
        raise ValueError("empty improvement ledger")
    return rows


_UNCHECKED = object()


def save_proposals(root: Path, rows: list[dict], expected: str | None | object = _UNCHECKED) -> None:
    for row in rows:
        validate_proposal(row, root)
    path = repo_path(root, LEDGER, reject_symlinks=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = repo_path(root, LEDGER + ".next", reject_symlinks=True)
    try:
        # The exclusive .next file is the write mutex; compare-and-swap rejects stale load-modify-save.
        with pending.open("x", encoding="utf-8") as stream:
            if expected is not _UNCHECKED and ledger_digest(root) != expected:
                raise ValueError("improvement ledger changed concurrently; rerun the command")
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        pending.replace(path)
    finally:
        # Only remove the file created by this writer, not another writer's lock.
        if 'stream' in locals() and pending.exists():
            pending.unlink()


def markdown_rows(path: Path) -> list[dict[str, str]]:
    """Read the single learning table; keep columns explicit and reject broken rows."""
    headers: list[str] = []
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.startswith("|"):
            continue
        if not line.rstrip().endswith("|"):
            raise ValueError(f"malformed table row in {path.name}")
        values = [part.strip() for part in line.strip()[1:-1].split("|")]
        if all(re.fullmatch(r":?-+:?", part) for part in values):
            continue
        if not headers:
            headers = [re.sub(r"[ _]+", "-", value.casefold()) for value in values]
            if len(set(headers)) != len(headers):
                raise ValueError("duplicate table headers")
        else:
            if len(values) != len(headers):
                raise ValueError(f"malformed table row in {path.name}")
            rows.append(dict(zip(headers, values)))
    return rows


def load_assumptions(root: Path) -> list[dict[str, str]]:
    path = repo_path(root, ASSUMPTIONS, reject_symlinks=True)
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if SECRET_RE.search(text):
        raise ValueError("possible secret material in harness assumptions")
    rows = markdown_rows(path)
    required = {"rule", "model-limitation", "last-reviewed-model", "target"}
    if not rows:
        raise ValueError("harness assumptions require a nonempty table")
    seen = set()
    for row in rows:
        if set(row) != required or any(not nonempty(value) for value in row.values()):
            raise ValueError("assumptions need Rule, Model Limitation, Last Reviewed Model, Target")
        repo_path(root, row["target"], reject_symlinks=True)
        identity = (row["rule"], row["target"])
        if identity in seen:
            raise ValueError("duplicate harness assumption")
        seen.add(identity)
    return rows


def new_proposal(identifier: str, kind: str, target: str, summary: str, sources: list[str],
                 fingerprint: str, before: str = "", after: str = "") -> dict:
    return dict(id=identifier, kind=kind, target=target, summary=summary, source_lessons=sources,
                failure_fingerprint=fingerprint, before_command=before, after_command=after,
                evidence={}, status="proposed", approver="", owner_approved=False, learning_actions=[])


def run_check(root: Path, row: dict, phase: str, command: str | None, timeout: float) -> int:
    if row["status"] != "proposed":
        raise ValueError("only proposed improvements can be checked")
    if phase == "after" and "before" not in row["evidence"]:
        raise ValueError("run the before check first")
    key = f"{phase}_command"
    if command and row[key] and command != row[key]:
        raise ValueError("check command is already bound to this proposal")
    row[key] = row[key] or command or ""
    if not nonempty(row[key]) or SECRET_RE.search(row[key]):
        raise ValueError("a non-secret check command is required")
    if not 0 < timeout <= 3600:
        raise ValueError("timeout must be between 0 and 3600 seconds")
    process = subprocess.Popen(row[key], shell=True, cwd=root, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, start_new_session=os.name != "nt")
    try:
        output, _ = process.communicate(timeout=timeout)
        code = process.returncode
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        else:
            # The check owns this session, including any child commands it launched.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        output, _ = process.communicate()
        code, output = 124, output + b"\ncheck timed out"
    # Scan before truncating so a partial token cannot leak through the tail boundary.
    tail = SECRET_RE.sub("[REDACTED]", output.decode("utf-8", errors="replace"))[-TAIL_LIMIT:]
    if phase == "before":
        row["evidence"].pop("after", None)
    row["evidence"][phase] = dict(command=row[key], exit_code=code, tail=tail,
                                  target_digest=target_digest(root, row["target"]))
    return code


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _approval_statement(operation: str, proposal: str, source_hash: str, target: str,
                        target_hash: str, content_hash: str) -> str:
    binding = {
        "content_sha256": content_hash,
        "operation": operation,
        "proposal": proposal,
        "source_sha256": source_hash,
        "target": target,
        "target_sha256": target_hash,
    }
    return "ARCHITRAVE-LEARNING-APPROVAL v1 " + json.dumps(
        binding, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _approved_owner_event(session_id: str | None, event_id: str | None, statement: str) -> dict:
    if not nonempty(session_id) or not nonempty(event_id):
        raise ValueError("AUTHENTICATED_APPROVAL_REQUIRED: --session-id and --owner-event are required")
    log = delivery_check.events(session_id)
    reference = delivery_check.owner_reference(event_id, log)
    event = next(event for event in log if event.get("id") == event_id)
    if event["data"].get("content") != statement:
        raise ValueError("AUTHENTICATED_APPROVAL_REQUIRED: original owner event does not exactly match "
                         "the operation, proposal, source, target, and content hashes")
    return reference


def _result_digest(content: bytes | None) -> str:
    return "missing" if content is None else _sha256(content)


def _atomic_target_write(root: Path, relative: str, expected_hash: str,
                         content: bytes | None) -> None:
    relative_path = Path(relative)
    parent = root.resolve()
    for component in relative_path.parts[:-1]:
        parent /= component
        if parent.is_symlink():
            raise ValueError("symlink paths are not accepted")
        parent.mkdir(exist_ok=True)
        if parent.is_symlink() or not parent.is_dir():
            raise ValueError("target parent is not a safe directory")
    target = repo_path(root, relative, reject_symlinks=True)
    exists = target.is_file()
    actual_hash = _sha256(target.read_bytes()) if exists else "missing"
    if actual_hash != expected_hash:
        raise ValueError("target changed before authorized learning write")
    if target.exists() and not exists:
        raise ValueError("target is not a regular file")
    mode = target.stat().st_mode if exists else 0o644
    if content is None:
        if not exists or _sha256(target.read_bytes()) != expected_hash:
            raise ValueError("target changed before authorized learning removal")
        target.unlink()
        return
    descriptor, temporary = tempfile.mkstemp(prefix=".architrave-learning-", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode & 0o777)
        if repo_path(root, relative, reject_symlinks=True) != target:
            raise ValueError("target path changed before authorized learning write")
        if expected_hash == "missing":
            if target.exists() or target.is_symlink():
                raise ValueError("target appeared during authorized creation")
            os.link(temporary, target)
            os.unlink(temporary)
        else:
            if not target.is_file() or _sha256(target.read_bytes()) != expected_hash:
                raise ValueError("target changed during authorized learning write")
            os.replace(temporary, target)
        if os.name != "nt":
            directory_fd = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _promotion_block(row: dict[str, str], heading: str) -> bytes:
    lesson = row["lesson"]
    evidence = row.get("evidence", "").strip() or "-"
    source = row.get("id", "").strip() or "unidentified candidate"
    if any("\n" in value or "\r" in value for value in (heading, lesson, evidence, source)):
        raise ValueError("promotion heading, lesson, evidence, and source must be single-line text")
    if any(mark in value for value in (lesson, evidence, source) for mark in ("<!--", "-->")):
        raise ValueError("lesson text, evidence, and source cannot contain HTML comment markers")
    return (f"\n## {heading}\n\n- **Lesson:** {lesson}\n"
            f"  **Evidence:** {evidence}\n  **Source lesson:** {source}\n").encode("utf-8")


def _lesson_identity(row: dict[str, str], source_hash: str, target: str,
                     heading: str, block: bytes) -> str:
    return _sha256(json.dumps(
        {"row": row, "source_sha256": source_hash, "target": target,
         "heading": heading, "block_sha256": _sha256(block)},
        sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _learning_record(rows: list[dict], identifier: str, row: dict[str, str],
                     target: str, identity: str, source_hash: str) -> dict:
    source_id = row.get("id", "").strip() or f"candidate-{identity[:16]}"
    summary = f"Approved learning promotion from {source_id}"
    matches = [item for item in rows if item["id"] == identifier]
    if len(matches) > 1:
        raise ValueError("duplicate learning promotion record")
    if matches:
        record = matches[0]
        if (record["kind"], record["target"], record["summary"], record["source_lessons"],
                record["failure_fingerprint"]) != (
                "instruction", target, summary, [source_id], f"learning-promotion:{source_hash}"):
            raise ValueError("learning promotion record identity conflicts with existing provenance")
        return record
    record = new_proposal(identifier, "instruction", target, summary, [source_id],
                          f"learning-promotion:{source_hash}")
    rows.append(record)
    return record


def _latest_action(record: dict, identity: str) -> dict | None:
    return next((action for action in reversed(record["learning_actions"])
                 if action["lesson_identity"] == identity), None)


def _verify_saved_approval(session_id: str, action: dict) -> None:
    expected = _approval_statement(
        action["operation"], action["proposal"], action["source_sha256"], action["target"],
        action["target_sha256"], action["content_sha256"])
    reference = _approved_owner_event(session_id, action["owner_reference"]["event_id"], expected)
    if reference != action["owner_reference"]:
        raise ValueError("stored original owner event reference changed")


def promote(root: Path, args: argparse.Namespace) -> None:
    from validate_learning import validate
    _, errors = validate(root)
    if errors:
        raise ValueError("learning validation failed: " + "; ".join(errors))
    lessons_path = repo_path(root, ".architrave/learning/repo-lessons.md", reject_symlinks=True)
    lessons_bytes = lessons_path.read_bytes()
    rows = markdown_rows(lessons_path)
    if args.action == "promote-lesson-picker":
        if args.index < 1 or args.index > len(rows):
            raise ValueError("candidate index not found")
        row = rows[args.index - 1]
    else:
        matches = [row for row in rows if args.lesson in (row.get("id"), row.get("lesson"))]
        if len(matches) != 1:
            raise ValueError("--lesson must match exactly one candidate lesson id or text")
        row = matches[0]
    if not row.get("lesson") or any("UNVALIDATED:" in value for value in row.values()):
        raise ValueError("lesson is missing or UNVALIDATED")
    checks = ("executable-check", "gate", "test", "lint", "acceptance-command")
    empty = {"", "-", "none", "n/a"}
    if not any(row.get(key, "").casefold() not in empty for key in checks) and row.get("prose-justification", "").casefold() in empty:
        raise ValueError("lesson needs an executable check or explicit prose-justification")
    target = repo_path(root, args.target, reject_symlinks=True)
    if target.suffix.casefold() != ".md":
        raise ValueError("target must be a Markdown file")
    if target.exists() and not target.is_file():
        raise ValueError("target must be a regular Markdown file")
    relative = target.relative_to(root).as_posix()
    if protected_target(root, relative):
        raise ValueError("target is a protected instruction/policy/evidence file; edit it by hand with review")
    heading = getattr(args, "heading", "Promoted Lessons")
    if not heading.strip() or "\n" in heading or "\r" in heading:
        raise ValueError("heading must be one nonempty line")
    block = _promotion_block(row, heading)
    source_hash = _sha256(lessons_bytes)
    identity = _lesson_identity(row, source_hash, relative, heading, block)
    record_id = "learning-" + identity[:32]
    ledger_hash = ledger_digest(root)
    proposal_rows = load_proposals(root)
    record = _learning_record(proposal_rows, record_id, row, relative, identity, source_hash)
    current_bytes = target.read_bytes() if target.is_file() else None
    target_hash = _result_digest(current_bytes)
    operation = "rollback" if args.rollback else "apply"
    rollback_of = None
    insertion_offset = len(current_bytes) if current_bytes is not None else 0
    if operation == "apply":
        latest = _latest_action(record, identity)
        if latest and latest["operation"] == "apply":
            raise ValueError("learning promotion is already applied; request an exact rollback approval first")
        result_bytes = (current_bytes or b"") + block
        applied_block = block.decode("utf-8")
    else:
        latest = _latest_action(record, identity)
        if latest is None or latest["operation"] != "apply":
            raise ValueError("no applied learning promotion with matching source/target provenance to roll back")
        if source_hash != latest["source_sha256"]:
            raise ValueError("source lesson changed since application; rollback is stale")
        if target_hash != latest["result_sha256"]:
            raise ValueError("target changed since application; rollback refuses to overwrite later edits")
        applied_block = latest["applied_block"]
        block_bytes = applied_block.encode("utf-8")
        insertion_offset = latest["insertion_offset"]
        if current_bytes[insertion_offset:insertion_offset + len(block_bytes)] != block_bytes:
            raise ValueError("applied lesson block no longer matches recorded inverse")
        restored_bytes = current_bytes[:insertion_offset] + current_bytes[insertion_offset + len(block_bytes):]
        result_bytes = None if latest["target_sha256"] == "missing" else restored_bytes
        if _result_digest(result_bytes) != latest["target_sha256"]:
            raise ValueError("inverse does not restore the exact pre-application target bytes")
        rollback_of = latest["proposal"]
    content_hash = _result_digest(result_bytes)
    proposal = _sha256(json.dumps(
        {"operation": operation, "lesson_identity": identity, "source_sha256": source_hash,
         "target": relative, "target_sha256": target_hash, "content_sha256": content_hash},
        sort_keys=True, separators=(",", ":")).encode("utf-8"))
    statement = _approval_statement(operation, proposal, source_hash, relative, target_hash, content_hash)
    print(f"DRY RUN: {operation} learning promotion for {relative}")
    print(f"proposal: {proposal}")
    print(f"source_sha256: {source_hash}")
    print(f"target_sha256: {target_hash}")
    print(f"content_sha256: {content_hash}")
    print(f"required original-owner event content:\n{statement}")
    print(f"provenance: {json.dumps(row, sort_keys=True, ensure_ascii=False)}")
    if not args.apply and not args.rollback:
        print("No files changed.")
        return
    if args.approve or args.by:
        raise ValueError("AUTHENTICATED_APPROVAL_REQUIRED: self-supplied --approve/--by values cannot "
                         "authenticate original owner approval")
    if not args.session_id or not args.owner_event:
        raise ValueError("AUTHENTICATED_APPROVAL_REQUIRED: provide --session-id and --owner-event")
    if operation == "rollback":
        _verify_saved_approval(args.session_id, latest)
    owner_ref = _approved_owner_event(args.session_id, args.owner_event, statement)
    action_record = {
        "operation": operation,
        "proposal": proposal,
        "lesson_identity": identity,
        "source_sha256": source_hash,
        "target": relative,
        "target_sha256": target_hash,
        "content_sha256": content_hash,
        "result_sha256": content_hash,
        "owner_reference": owner_ref,
        "applied_block": applied_block,
        "insertion_offset": insertion_offset,
        "rollback_of": rollback_of,
        "source_row": dict(row),
        "heading": heading,
    }
    record["learning_actions"].append(action_record)
    if _sha256(lessons_path.read_bytes()) != source_hash:
        raise ValueError("source lesson changed while confirming the proposal")
    try:
        _atomic_target_write(root, relative, target_hash, result_bytes)
        save_proposals(root, proposal_rows, ledger_hash)
    except (OSError, ValueError) as exc:
        try:
            _atomic_target_write(root, relative, content_hash, current_bytes)
        except (OSError, ValueError) as rollback_exc:
            raise ValueError(f"learning {operation} evidence save failed ({exc}); target reconciliation also failed "
                             f"({rollback_exc})") from rollback_exc
        raise ValueError(f"learning {operation} evidence save failed; target change was reversed: {exc}") from exc
    print(f"{operation} completed; bound owner event and inverse evidence saved in {LEDGER}.")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="action", required=True)
    propose = commands.add_parser("propose")
    propose.add_argument("--id")
    propose.add_argument("--source-lesson", action="append", default=[])
    propose.add_argument("--failure-fingerprint", default="")
    propose.add_argument("--kind", choices=sorted(KINDS), required=True)
    propose.add_argument("--target", required=True)
    propose.add_argument("--summary", required=True)
    propose.add_argument("--before-command", required=True)
    propose.add_argument("--after-command", required=True)
    check = commands.add_parser("check")
    check.add_argument("id")
    check.add_argument("--phase", choices=["before", "after"], required=True)
    check.add_argument("--command", help="fill an empty retire-stub check command")
    check.add_argument("--timeout", type=float, default=60)
    approve = commands.add_parser("approve")
    approve.add_argument("id")
    approve.add_argument("--by", required=True, help="human approver identity; not authentication")
    approve.add_argument("--owner-approved", action="store_true")
    commands.add_parser("list")
    prune = commands.add_parser("prune-review")
    prune.add_argument("--model", required=True)
    for action in ("promote-lesson", "promote-lesson-picker"):
        promotion = commands.add_parser(action)
        if action == "promote-lesson":
            promotion.add_argument("--lesson", required=True)
            promotion.add_argument("--heading", default="Promoted Lessons")
        else:
            promotion.add_argument("--index", type=int, required=True)
        promotion.add_argument("--target", required=True)
        operation = promotion.add_mutually_exclusive_group()
        operation.add_argument("--apply", action="store_true",
                               help="apply only with an exact original-owner approval event")
        operation.add_argument("--rollback", action="store_true",
                               help="rollback only with an exact original-owner approval event")
        promotion.add_argument("--session-id", help="host session containing the original owner event")
        promotion.add_argument("--owner-event", help="exact original owner approval event ID")
        promotion.add_argument("--approve", help="deprecated; cannot authorize application")
        promotion.add_argument("--by", help="deprecated; caller identity is not authentication")
    for subparser in commands.choices.values():
        subparser.add_argument("--repo", default=".")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = Path(args.repo).resolve()
    try:
        if not root.is_dir():
            raise ValueError("repo directory not found")
        if args.action.startswith("promote-lesson"):
            promote(root, args)
            return 0
        expected = ledger_digest(root)
        rows = load_proposals(root)
        if args.action == "list":
            for row in rows:
                print(json.dumps(row, ensure_ascii=False))
            return 0
        if args.action == "propose":
            number = len(rows) + 1
            while any(row["id"] == f"improvement-{number}" for row in rows):
                number += 1
            identifier = args.id or f"improvement-{number}"
            if any(row["id"] == identifier for row in rows):
                raise ValueError("duplicate proposal id")
            if not nonempty(args.before_command) or not nonempty(args.after_command):
                raise ValueError("before/after check commands are required")
            row = new_proposal(identifier, args.kind, args.target, args.summary, args.source_lesson,
                               args.failure_fingerprint, args.before_command, args.after_command)
            rows.append(row)
            print(identifier)
        elif args.action == "prune-review":
            if not nonempty(args.model) or SECRET_RE.search(args.model):
                raise ValueError("a non-secret model name is required")
            added = False
            for assumption in load_assumptions(root):
                if assumption["last-reviewed-model"] == args.model:
                    continue
                fingerprint = "harness-assumption:" + hashlib.sha256(
                    (assumption["target"] + "\n" + assumption["rule"]).encode()).hexdigest()[:16]
                identifier = "retire-" + hashlib.sha256((fingerprint + "\n" + args.model).encode()).hexdigest()[:20]
                print(f"{identifier}: {assumption['rule']} (last reviewed: {assumption['last-reviewed-model']})")
                if any(row["id"] == identifier for row in rows):
                    continue
                rows.append(new_proposal(identifier, "retire", assumption["target"],
                    f"Review for {args.model}: {assumption['rule']}; compensates for {assumption['model-limitation']}. "
                    "Propose retirement only if before/after evaluation supports it.", [], fingerprint))
                added = True
            if not added:
                return 0
        else:
            matches = [row for row in rows if row["id"] == args.id]
            if not matches:
                raise ValueError("proposal id not found")
            row = matches[0]
            if row["status"] != "proposed":
                raise ValueError("only proposed improvements can be changed")
            if args.action == "check":
                code = run_check(root, row, args.phase, args.command, args.timeout)
                save_proposals(root, rows, expected)
                print(f"{row['id']} {args.phase}: exit {code}\n{row['evidence'][args.phase]['tail']}")
                return 0 if code == 0 else 1
            if not nonempty(args.by) or SECRET_RE.search(args.by):
                raise ValueError("a non-secret human approver identity is required")
            row["owner_approved"] = args.owner_approved
            approval_ready(row, root, check_source=True)
            row.update(status="approved", approver=args.by)
            print(f"approved {row['id']} by {args.by}")
        save_proposals(root, rows, expected)
        return 0
    except (ValueError, TypeError, OSError, UnicodeError) as exc:
        print(f"improvement: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
