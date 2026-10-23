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

from validate_learning import SECRET_RE

LEDGER = ".architrave/learning/improvements.jsonl"
ASSUMPTIONS = ".architrave/learning/harness-assumptions.md"
KINDS = {"gate", "test", "lint", "skill", "instruction", "retire"}
STATUSES = {"proposed", "approved", "merged", "rejected"}
TAIL_LIMIT = 2000


def repo_path(root: Path, value: str) -> Path:
    path = Path(value.replace("\\", "/"))
    windows = PureWindowsPath(value)
    if not value or path.is_absolute() or windows.drive or windows.root or ".." in windows.parts:
        raise ValueError("path must be repo-relative and stay inside the repo")
    target = (root / path).resolve()
    if not target.is_relative_to(root) or target == root:
        raise ValueError("path must be repo-relative and stay inside the repo")
    return target


def global_instruction(root: Path, target: str) -> bool:
    names = {target.replace("\\", "/").casefold(),
             repo_path(root, target).relative_to(root).as_posix().casefold()}
    return any(name in {"agents.md", ".github/copilot-instructions.md"} or (
        name.startswith("agents/") and name.endswith(".agent.md")
    ) for name in names)


def target_digest(root: Path, target: str) -> str:
    path = repo_path(root, target)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "missing"


def nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_proposal(row: object, root: Path) -> None:
    if not isinstance(row, dict):
        raise ValueError("proposal must be an object")
    required = {"id", "source_lessons", "failure_fingerprint", "kind", "target", "summary",
                "before_command", "after_command", "evidence", "status", "approver", "owner_approved"}
    if set(row) != required:
        raise ValueError("proposal fields do not match the improvement contract")
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
    repo_path(root, row["target"])
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
    if row["kind"] == "instruction" and global_instruction(root, row["target"]) and not row["owner_approved"]:
        raise ValueError("always-loaded global instruction requires --owner-approved")
    if check_source and evidence["after"]["target_digest"] != target_digest(root, row["target"]):
        raise ValueError("target changed since passing after check; rerun the check")


def load_proposals(root: Path) -> list[dict]:
    path = repo_path(root, LEDGER)
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


def save_proposals(root: Path, rows: list[dict]) -> None:
    for row in rows:
        validate_proposal(row, root)
    path = repo_path(root, LEDGER)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = repo_path(root, LEDGER + ".next")
    try:
        with pending.open("x", encoding="utf-8") as stream:
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
    path = repo_path(root, ASSUMPTIONS)
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
        repo_path(root, row["target"])
        identity = (row["rule"], row["target"])
        if identity in seen:
            raise ValueError("duplicate harness assumption")
        seen.add(identity)
    return rows


def new_proposal(identifier: str, kind: str, target: str, summary: str, sources: list[str],
                 fingerprint: str, before: str = "", after: str = "") -> dict:
    return dict(id=identifier, kind=kind, target=target, summary=summary, source_lessons=sources,
                failure_fingerprint=fingerprint, before_command=before, after_command=after,
                evidence={}, status="proposed", approver="", owner_approved=False)


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


def promote(root: Path, args: argparse.Namespace) -> None:
    from validate_learning import validate
    _, errors = validate(root)
    if errors:
        raise ValueError("learning validation failed: " + "; ".join(errors))
    rows = markdown_rows(repo_path(root, ".architrave/learning/repo-lessons.md"))
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
    target = repo_path(root, args.target)
    if target.suffix.casefold() != ".md":
        raise ValueError("target must be a Markdown file")
    heading = getattr(args, "heading", "Promoted Lessons")
    if not heading.strip() or "\n" in heading or "\r" in heading:
        raise ValueError("heading must be one nonempty line")
    entry = "- " + row["lesson"]
    if not args.apply:
        print(f"DRY RUN: would append to {args.target} under heading '{heading}':\n{entry}")
        return
    text = target.read_text(encoding="utf-8") if target.exists() else ""
    if not re.search(r"^##\s+" + re.escape(heading) + r"$", text, re.MULTILINE):
        text += ("\n" if text else "") + f"## {heading}\n\n"
    elif text and not text.endswith("\n"):
        text += "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text + entry + "\n", encoding="utf-8")
    print(f"promoted lesson to {args.target}")


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
            promotion.add_argument("--lesson", "-Lesson", required=True)
            promotion.add_argument("--heading", "-Heading", default="Promoted Lessons")
        else:
            promotion.add_argument("--index", "-Index", type=int, required=True)
        promotion.add_argument("--target", "-Target", required=True)
        promotion.add_argument("--apply", "-Apply", action="store_true")
    for subparser in commands.choices.values():
        subparser.add_argument("--repo", "-Repo", default=".")
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
                save_proposals(root, rows)
                print(f"{row['id']} {args.phase}: exit {code}\n{row['evidence'][args.phase]['tail']}")
                return 0 if code == 0 else 1
            if not nonempty(args.by) or SECRET_RE.search(args.by):
                raise ValueError("a non-secret human approver identity is required")
            row["owner_approved"] = args.owner_approved
            approval_ready(row, root, check_source=True)
            row.update(status="approved", approver=args.by)
            print(f"approved {row['id']} by {args.by}")
        save_proposals(root, rows)
        return 0
    except (ValueError, TypeError, OSError, UnicodeError) as exc:
        print(f"improvement: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
