#!/usr/bin/env python3
"""Validate tracked Architrave learning artifacts."""

from __future__ import annotations

from pathlib import Path
import re


LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
SECRET_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY|gh[pousr]_[A-Za-z0-9_]{20,}|"
    r"sk-[A-Za-z0-9]{20,}|(?:api[_-]?key|token|password)\s*[:=]\s*\S{12,}",
    re.IGNORECASE,
)


def validate(root: Path) -> tuple[list[str], list[str]]:
    root = root.resolve()
    learning = root / ".architrave" / "learning"
    files = [learning / "repo-profile.md", learning / "repo-lessons.md"]
    passed: list[str] = []
    errors: list[str] = []
    for path in files:
        relative = path.relative_to(root).as_posix()
        if not path.is_file() or path.stat().st_size == 0:
            errors.append(f"missing/empty {relative}")
            continue
        passed.append(relative)
        text = path.read_text(encoding="utf-8", errors="replace")
        if SECRET_RE.search(text):
            errors.append(f"possible secret material in {relative}")
        for target in LINK_RE.findall(text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            raw_path, _, anchor = target.partition("#")
            decoded = raw_path.replace("%20", " ")
            candidate = Path(decoded)
            if candidate.is_absolute() or ".." in candidate.parts:
                errors.append(f"{relative} link escapes repo: {target}")
                continue
            destination = (root / candidate).resolve()
            try:
                destination.relative_to(root)
            except ValueError:
                errors.append(f"{relative} link escapes repo: {target}")
                continue
            if decoded and not destination.exists():
                errors.append(f"{relative} missing link target: {target}")
            elif anchor and decoded and destination.is_file():
                destination_text = destination.read_text(encoding="utf-8", errors="replace")
                if not re.search(r"^#+\s+.+", destination_text, re.MULTILINE):
                    errors.append(f"{relative} anchor references file without headings: {target}")
    return passed, errors
