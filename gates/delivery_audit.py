#!/usr/bin/env python3
"""Read-only substitute/flag candidate inventory; not proof of authorization or delivery."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


SOURCE_SUFFIXES = {
    ".cs", ".fs", ".vb", ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".go", ".rs", ".java", ".kt", ".swift", ".cpp", ".h", ".rb", ".php",
    ".json", ".yaml", ".yml", ".toml", ".xml", ".config", ".props", ".targets", ".ini",
    ".ps1", ".sh", ".bash", ".cmd", ".bat", ".html", ".vue", ".svelte",
}
# Signals require semantic review. Names alone cannot establish runtime reachability.
RULES = (
    ("substitute", re.compile(
        r"\b\w*(?:mock|fake|fixture|stub|canned|synthetic)\w*\b", re.I)),
    ("test-provider", re.compile(
        r"deterministic[-_ ]test|fixture://|test[-_ ]only|regression[-_ ]provider", re.I)),
    ("flag-or-selector", re.compile(
        r"(?i:\b\w*(?:enabled|eligible|featureflag|feature_flag|testmode|test_mode|"
        r"dryrun|dry_run)\w*\b|\b(?:isdev|executionmode|providermode|runtimemode)\b)"
        r"|\b(?:[Ee]nable|[Dd]isable|[Aa]llow|[Uu]se)[A-Z_]\w*"
        r"|(?i:\b(?:enable|disable|allow|use)_[a-z0-9_]+\b)")),
    ("environment-selector", re.compile(
        r"getenv|GetEnvironmentVariable|process\.env\b|os\.environ|"
        r"\$env:|\$\{?[A-Z][A-Z0-9_]*(?:ENABLE|DISABLE|MODE|PROVIDER|ELIGIBLE|LIVE)"
        r"[A-Z0-9_]*", re.I)),
    ("interception", re.compile(
        r"\b(?:route\.fulfill|page\.route|context\.route|browserContext\.route|"
        r"responses\.add|requests_mock|HttpMessageHandler)\b|\bnock\s*\(", re.I)),
)


def git(root: Path, *args: str) -> bytes:
    process = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(root), *args],
        capture_output=True, check=False,
    )
    if process.returncode:
        raise ValueError(f"git {args[0]} failed: "
                         + process.stderr.decode("utf-8", errors="replace").strip())
    return process.stdout


def local_file(root: Path, name: str) -> Path:
    path = Path(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"path must be repository-relative: {name}")
    path = root / path
    if not path.resolve().is_relative_to(root) or path.is_symlink():
        raise ValueError(f"unsafe or external path: {name}")
    # Refuse symlink/junction traversal, even when it happens to point inside root.
    for parent in (path, *path.parents):
        if parent == root:
            break
        if parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction()):
            raise ValueError(f"linked path cannot be inspected: {name}")
    return path


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot inspect {path.name}: {exc}") from exc


def inventory(root: Path, base: str | None, all_files: bool) -> list[str]:
    if all_files:
        raw = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    else:
        # Resolve as a commit first; a supplied ref must never become a Git option.
        commit = git(root, "rev-parse", "--verify", "--end-of-options",
                     (base or "HEAD") + "^{commit}").decode().strip()
        # Whole changed files, not added lines: unchanged defaults can control new code.
        raw = git(root, "diff", "--no-ext-diff", "--name-only", "-z",
                  "--diff-filter=ACMRT", commit, "--")
        raw += git(root, "ls-files", "-z", "--others", "--exclude-standard")
    return sorted({item.decode("utf-8") for item in raw.split(b"\0") if item})


def scope(name: str) -> str:
    parts = {p.lower() for p in Path(name).parts}
    stem = Path(name).stem.lower()
    if parts.intersection({"test", "tests", "__tests__", "fixtures", "mocks"}) or (
        stem.startswith(("test_", "test-")) or stem.endswith((".test", ".spec", "_test"))
    ):
        return "test-location-unverified"
    return "runtime-or-tooling-unverified"


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=True).encode()).hexdigest()


def requirement_contract(text: str, selected: list[str] | None = None) -> dict:
    from gate_runner import parse_requirements

    rows, corrections, errors = parse_requirements(text)
    if errors:
        raise ValueError("invalid requirements: " + "; ".join(errors))
    ids = sorted(set(selected if selected is not None else rows))
    if not ids or any(rid not in rows for rid in ids):
        raise ValueError("requirements scope is empty or contains unknown IDs")
    # Acceptance status/evidence evolve; the original requirement cannot silently shrink.
    return {
        "requirements": {rid: {k: rows[rid][k] for k in ("requirement", "acceptance")} for rid in ids},
        "corrections": [c for c in corrections if any(
            rid in re.findall(r"REQ-[A-Za-z0-9_.-]+", c["target"]) for rid in ids)
            or c["target"].strip().lower() == "all"],
    }


def source_snapshot(root: Path, excluded: set[str]) -> list[dict]:
    result = []
    for name in inventory(root, None, True):
        if name in excluded:
            continue
        path = local_file(root, name)
        if path.is_dir():
            raise ValueError(f"uninspected Git submodule/directory: {name}")
        result.append({"path": name,
                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None})
    return result


def scan(root: Path, *, base: str | None = None, all_files: bool = False,
         documents: list[str] | None = None, reqs: list[str] | None = None) -> dict:
    root = root.resolve()
    actual = Path(git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    if root != actual:
        raise ValueError("--repo must name the Git repository root")
    config_path = root / "architrave.config.json"
    config = json.loads(read_text(local_file(root, "architrave.config.json"))) if config_path.exists() else {}
    if not isinstance(config, dict):
        raise ValueError("architrave.config.json must be an object")
    requirement = config.get("requirements", "SPEC.md")
    if not isinstance(requirement, str) or not requirement.strip():
        raise ValueError("requirements must name a repository-relative document")
    base_sha = git(root, "rev-parse", "--verify", "--end-of-options",
                   (base or "HEAD") + "^{commit}").decode().strip()
    git(root, "merge-base", "--is-ancestor", base_sha, "HEAD")
    names = list(dict.fromkeys([requirement, *(documents or (["README.md"] if (root / "README.md").exists() else []))]))
    contracts = []
    contract_lines: list[tuple[str, int, str]] = []
    selected_contract = None
    ledger_contract = None
    for name in names:
        path = local_file(root, name)
        text = read_text(path)
        if not text.strip():
            raise ValueError(f"empty contract document: {name}")
        contracts.append({"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        contract_lines.extend((name, n, line) for n, line in enumerate(text.splitlines(), 1))
        if name == requirement and reqs is not None:
            selected_contract = requirement_contract(text, reqs)
            ledger_contract = requirement_contract(text)
    sources = source_snapshot(root, {requirement}) if reqs is not None else source_snapshot(root, set())
    source_hashes = {r["path"]: r["sha256"] for r in sources}
    findings = []
    inspected = []
    for name in inventory(root, base_sha, all_files):
        path = local_file(root, name)
        if not path.exists():
            # Deletions are not replacement implementations.
            continue
        if (path.suffix.lower() not in SOURCE_SUFFIXES
                and path.name not in {"Dockerfile", "Makefile", ".env"}
                and not path.name.startswith(".env.")):
            continue
        text = read_text(path)
        if name in source_hashes and hashlib.sha256(path.read_bytes()).hexdigest() != source_hashes[name]:
            raise ValueError(f"source changed during inspection: {name}")
        inspected.append(name)
        for number, line in enumerate(text.splitlines(), 1):
            for category, pattern in RULES:
                if not pattern.search(line):
                    continue
                # Never echo matched lexemes: they can be credential/config values.
                refs = [
                    {"path": doc, "line": n} for doc, n, content in contract_lines
                    if pattern.search(content)
                ]
                findings.append({
                    "path": name, "line": number, "category": category,
                    "scope": scope(name),
                    "contract_mentions": refs,
                    "id": digest({"path": name, "line": number, "category": category,
                                  "sha256": source_hashes.get(name)}),
                })
    identity = {
        "base_sha": base_sha, "source_files": sources,
        "documents": [c for c in contracts if selected_contract is None or c["path"] != requirement],
        "requirements": selected_contract,
        "ledger_contract": ledger_contract,
        "selection": "all-nonignored-files" if all_files else "changed-files",
    }
    return {
        "schema": "architrave.delivery-audit.v1",
        "status": "REVIEW_REQUIRED" if findings else "NO_CANDIDATES",
        "selection": identity["selection"],
        "base_sha": base_sha, "source_files": sources, "source_sha256": digest(identity),
        "requirements": selected_contract,
        "documents": contracts, "inspected_files": inspected, "findings": findings,
        "limitations": [
            "Lexical candidates only: renaming, indirect selection and semantic substitutes may evade detection.",
            "A test path is not proof of isolation; a document mention is not owner authorization.",
            "NO_CANDIDATES is not real-integration, requirements-conformance or completion evidence.",
            "Review must join owner request, requirements/docs, runtime wiring, effective flags and provider observations.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--base", help="compare working tree with this reviewed Git ref")
    selection.add_argument("--all", action="store_true", dest="all_files")
    parser.add_argument("--document", action="append", default=None,
                        help="repository-relative design/demo/runbook to compare (repeatable)")
    parser.add_argument("--json", action="store_true", dest="as_json")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--prepare", action="store_true", help="declare non-trivial work in this host session")
    action.add_argument("--amend", action="store_true", help="rebind changed scope to a newer original owner event")
    action.add_argument("--withdraw", action="store_true", help="retain an owner-directed withdrawal, not delivery acceptance")
    action.add_argument("--seal", action="store_true", help="freeze current source inventory for review")
    action.add_argument("--check", action="store_true", help="verify the session's declared delivery")
    parser.add_argument("--session", help="host session UUID; defaults to COPILOT_AGENT_SESSION_ID")
    parser.add_argument("--reqs", help="explicit comma-separated requirement scope")
    parser.add_argument("--request", action="append", help="original owner event ID in this session (repeatable)")
    parser.add_argument("--reference", action="append", help="original visual/design reference path (repeatable)")
    parser.add_argument("--drop", help="--amend: explicitly acknowledge removed REQ IDs")
    parser.add_argument("--reason", help="--withdraw: verbatim owner withdrawal quotation")
    args = parser.parse_args(argv)
    if args.drop and not args.amend:
        parser.error("--drop requires --amend")
    if args.reason and not args.withdraw:
        parser.error("--reason requires --withdraw")
    if args.prepare or args.amend or args.withdraw or args.seal or args.check:
        from delivery_check import session_command

        return session_command(args)
    try:
        report = scan(Path(args.repo), base=args.base, all_files=args.all_files,
                      documents=args.document)
    except (ValueError, OSError, UnicodeError) as exc:
        if args.as_json:
            print(json.dumps({"status": "BLOCK", "error": str(exc)}))
        else:
            print(f"delivery-audit: BLOCK - {exc}", file=sys.stderr)
        return 2
    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        print(f"delivery-audit: {report['status']} ({len(report['findings'])} candidates)")
        for finding in report["findings"]:
            refs = ", ".join(f"{r['path']}:{r['line']}" for r in finding["contract_mentions"])
            print(f"REVIEW {finding['path']}:{finding['line']} [{finding['category']}; "
                  f"{finding['scope']}] | category mentions in contracts: {refs or 'none'}")
        for limitation in report["limitations"]:
            print(f"LIMIT {limitation}")
    return 2 if report["findings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
