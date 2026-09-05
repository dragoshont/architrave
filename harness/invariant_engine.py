#!/usr/bin/env python3
"""Mechanical repository invariants for Architrave."""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Sequence

from architrave_runtime import RunStore, RuntimeFailure, redact


MAX_SOURCE_BYTES = 2 * 1024 * 1024
IMPORT_PATTERNS = (
    re.compile(r"\bfrom\s+['\"]([^'\"]+)['\"]"),
    re.compile(r"\bimport\s+[^'\";]*?from\s+['\"]([^'\"]+)['\"]"),
    re.compile(r"\brequire\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"),
    re.compile(r"\bimport\s+([A-Za-z_][A-Za-z0-9_.]*)"),
    re.compile(r"ProjectReference\s+Include=['\"]([^'\"]+)['\"]", re.IGNORECASE),
)
CONTROL_PATTERNS = (
    ("placeholder-link", re.compile(r"href\s*=\s*['\"]#['\"]", re.IGNORECASE)),
    ("todo-handler", re.compile(r"\b(?:onClick|onPress|action)\s*=.*\bTODO\b", re.IGNORECASE)),
    ("empty-handler", re.compile(r"\b(?:onClick|onPress)\s*=\s*\{\s*\(.*?\)\s*=>\s*\{\s*\}\s*\}")),
    ("not-implemented-endpoint", re.compile(r"\b(?:501|NotImplementedException|HTTP_501_NOT_IMPLEMENTED)\b")),
)


def load_config(repository: Path) -> dict[str, Any]:
    path = repository / "architrave.config.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeFailure("CONFIG_NOT_FOUND", f"config not found: {path}", exit_code=2) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeFailure("CONFIG_INVALID", f"invalid JSON config: {exc}", exit_code=2) from exc
    if not isinstance(value, dict):
        raise RuntimeFailure("CONFIG_INVALID", "config must be a JSON object", exit_code=2)
    return value


def safe_glob(repository: Path, pattern: str) -> list[Path]:
    candidate = Path(pattern)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise RuntimeFailure("PATH_ESCAPE", f"invariant glob escapes repository: {pattern}")
    return sorted(path for path in repository.glob(pattern) if path.is_file())


def read_source(path: Path) -> str | None:
    if path.stat().st_size > MAX_SOURCE_BYTES:
        return None
    data = path.read_bytes()
    if b"\x00" in data:
        return None
    return data.decode("utf-8", "replace")


def line_number(text: str, start: int) -> int:
    return text.count("\n", 0, start) + 1


def extract_imports(text: str, source: Path | None = None) -> Iterable[tuple[str, int]]:
    if source is not None and source.suffix == ".py":
        try:
            tree = ast.parse(text, filename=str(source))
        except SyntaxError:
            # Keep the existing best-effort behavior for incomplete Python files.
            pass
        else:
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        yield alias.name, node.lineno
                elif isinstance(node, ast.ImportFrom):
                    module = "." * node.level + (node.module or "")
                    yield module, node.lineno
            return
    for pattern in IMPORT_PATTERNS:
        for match in pattern.finditer(text):
            yield match.group(1), line_number(text, match.start())


def resolve_import(source: Path, import_value: str, repository: Path) -> str:
    normalized = import_value.replace("\\", "/")
    if normalized.startswith("."):
        source_parent = source.parent.relative_to(repository).as_posix()
        resolved = os.path.normpath(f"{source_parent}/{normalized}").replace("\\", "/")
        if resolved == ".." or resolved.startswith("../"):
            return normalized
        return resolved
    return normalized


def import_matches(import_value: str, target: str) -> bool:
    normalized_target = target.replace("\\", "/")
    if fnmatch.fnmatch(import_value, normalized_target):
        return True
    prefix = normalized_target.split("*", 1)[0].rstrip("/")
    return bool(prefix and (import_value == prefix or import_value.startswith(prefix + "/")))


def evaluate(repository: Path, config: dict[str, Any]) -> dict[str, Any]:
    invariants = config.get("invariants") or {}
    violations: list[dict[str, Any]] = []
    checked = {"requiredFiles": 0, "forbiddenPatterns": 0, "forbiddenDependencies": 0, "requiredBoundaries": 0, "controls": 0}

    for pattern in invariants.get("requiredFiles") or []:
        checked["requiredFiles"] += 1
        if not safe_glob(repository, pattern):
            violations.append({"code": "REQUIRED_FILE_MISSING", "pattern": pattern})

    for declaration in invariants.get("forbiddenPatterns") or []:
        try:
            pattern = re.compile(declaration["pattern"])
        except re.error as exc:
            raise RuntimeFailure("INVARIANT_INVALID", f"invalid forbidden regex {declaration['pattern']!r}: {exc}") from exc
        for path_glob in declaration["paths"]:
            for path in safe_glob(repository, path_glob):
                text = read_source(path)
                if text is None:
                    continue
                checked["forbiddenPatterns"] += 1
                for match in pattern.finditer(text):
                    violations.append(
                        {
                            "code": "FORBIDDEN_PATTERN",
                            "path": path.relative_to(repository).as_posix(),
                            "line": line_number(text, match.start()),
                            "pattern": declaration["pattern"],
                        }
                    )

    for declaration in invariants.get("forbiddenDependencies") or []:
        for path in safe_glob(repository, declaration["from"]):
            text = read_source(path)
            if text is None:
                continue
            checked["forbiddenDependencies"] += 1
            for imported, line in extract_imports(text, path):
                resolved = resolve_import(path, imported, repository)
                if import_matches(resolved, declaration["to"]):
                    violations.append(
                        {
                            "code": "FORBIDDEN_DEPENDENCY",
                            "path": path.relative_to(repository).as_posix(),
                            "line": line,
                            "dependency": imported,
                            "resolved": resolved,
                            "target": declaration["to"],
                        }
                    )

    for declaration in invariants.get("requiredBoundaries") or []:
        allowed = declaration["allowedImports"]
        for path in safe_glob(repository, declaration["path"]):
            text = read_source(path)
            if text is None:
                continue
            checked["requiredBoundaries"] += 1
            for imported, line in extract_imports(text, path):
                resolved = resolve_import(path, imported, repository)
                if not any(import_matches(resolved, target) for target in allowed):
                    violations.append(
                        {
                            "code": "BOUNDARY_IMPORT_DENIED",
                            "path": path.relative_to(repository).as_posix(),
                            "line": line,
                            "dependency": imported,
                            "resolved": resolved,
                            "allowedImports": allowed,
                        }
                    )

    if (config.get("evaluation") or {}).get("controlAudit"):
        source_globs = config.get("applyTo") or ["**/*"]
        seen: set[Path] = set()
        for path_glob in source_globs:
            for path in safe_glob(repository, path_glob):
                if path in seen:
                    continue
                seen.add(path)
                text = read_source(path)
                if text is None:
                    continue
                checked["controls"] += 1
                for control_name, pattern in CONTROL_PATTERNS:
                    for match in pattern.finditer(text):
                        violations.append(
                            {
                                "code": "DEAD_CONTROL",
                                "kind": control_name,
                                "path": path.relative_to(repository).as_posix(),
                                "line": line_number(text, match.start()),
                            }
                        )

    return {
        "status": "pass" if not violations else "fail",
        "checked": checked,
        "violations": violations,
    }


def cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate Architrave mechanical invariants")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--output")
    parser.add_argument("--run-id")
    parser.add_argument("--task-id")
    args = parser.parse_args(argv)
    repository = Path(args.repo).resolve()
    try:
        result = evaluate(repository, load_config(repository))
        serialized = json.dumps(redact(result), indent=2) + "\n"
        if args.output:
            output = Path(args.output)
            if not output.is_absolute():
                output = repository / output
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(serialized, encoding="utf-8")
        if args.run_id:
            store = RunStore(repository)
            output = store.run_dir(args.run_id) / "deterministic" / "invariants.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(serialized, encoding="utf-8")
            artifact_id = f"invariants-result-{args.run_id}"
            store._record_invariant_result(
                args.run_id,
                artifact_id=artifact_id,
                path=output.relative_to(repository).as_posix(),
                evidence_refs=[f"task:{args.task_id}"] if args.task_id else [],
            )
            store.record_gate(
                args.run_id,
                gate_id=f"invariants-{args.run_id}",
                task_id=args.task_id,
                gate_type="deterministic",
                status="PASS" if result["status"] == "pass" else "FAIL",
                evidence_refs=[f"artifact:{artifact_id}"],
            )
        print(serialized, end="")
        return 0 if result["status"] == "pass" else 1
    except RuntimeFailure as exc:
        print(
            json.dumps({"status": "failed", "error": {"code": exc.code, "message": exc.message}}, indent=2),
            file=sys.stderr,
        )
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(cli())