#!/usr/bin/env python3
"""Read-only Copilot startup context and declared-delivery completion barrier."""
from __future__ import annotations

import argparse
from collections.abc import Callable
import json
import os
from pathlib import Path
import sys
from uuid import UUID


def bootstrap_context() -> str:
    root = Path(__file__).resolve().parents[1]
    return (
        "For non-trivial repository work, invoke architrave "
        f"(`{root / 'skills' / 'architrave' / 'SKILL.md'}`); without a skill loader, "
        f"read `{root / 'agents' / 'architrave.agent.md'}` once. "
        "Before implementation: record REQs against original owner messages/references, "
        "declare this session's scope per docs/program-board.md in that kit, then "
        "open and read ONE scoped program board in the host browser canvas. "
        "Report unavailable/denied host capability; never invent a panel. "
        "Read-only/trivial work needs no declaration or board; assigned workers/reviewers "
        "use their parent's scope without recursive boards. "
        "No unrequested fake results or feature/integration flags, including tests. "
        "Preserve existing scoped grants and host permissions. Load details on demand."
    )


def _deny(reason: str) -> dict[str, str]:
    return {"permissionDecision": "deny", "permissionDecisionReason": reason}


def _failure(step: str, error: Exception) -> dict[str, str]:
    # Exception messages can contain input or credentials; retain operation/type.
    detail = type(error).__name__
    if isinstance(error, OSError) and error.errno is not None:
        detail += f", errno {error.errno}"
    return _deny(f"Architrave {step} failed ({detail}); delivery acceptance is unverified.")


def _field(payload: dict[str, object], camel: str, snake: str) -> object:
    if camel in payload and snake in payload and payload[camel] != payload[snake]:
        raise ValueError(f"Conflicting {camel}/{snake} fields")
    return payload.get(camel, payload.get(snake))


def _report_path(session: str) -> Path:
    # Match gate.session_home() before importing the delivery checker: an import
    # failure must not hide an existing declaration or affect an absent one.
    home = Path(os.environ.get("COPILOT_HOME", Path.home() / ".copilot"))
    return home / "session-state" / session / "files" / "architrave-delivery.json"


def pre_tool_use(
    payload: dict[str, object],
    *,
    checker: Callable[[Path, str], list[str]] | None = None,
) -> dict[str, str]:
    tools = [payload[key] for key in ("toolName", "tool_name") if key in payload]
    if tools and "task_complete" not in tools:
        return {}
    try:
        tool = _field(payload, "toolName", "tool_name")
    except ValueError:
        return _deny("Architrave completion input has conflicting toolName/tool_name fields.")
    if tool != "task_complete":
        return _deny("Architrave completion input is missing toolName/task_complete identity.")
    try:
        session = _field(payload, "sessionId", "session_id")
        if not isinstance(session, str) or str(UUID(session)) != session.lower():
            raise ValueError("Session identity must be a UUID")
        session = session.lower()
    except (ValueError, AttributeError):
        return _deny("Architrave completion input has invalid or conflicting sessionId/session_id fields.")

    try:
        report = _report_path(session)
        report.lstat()
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        return _failure("delivery declaration lookup", error)

    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd or not Path(cwd).is_absolute():
        return _deny("Architrave declared completion requires an absolute cwd for delivery verification.")
    try:
        root = Path(cwd).resolve()
        if checker is None:
            from delivery_check import check_session, session_report_path

            if session_report_path(session) != report:
                return _deny("Architrave delivery checker and hook disagree on the session report path.")
            checker = check_session
        errors = checker(root, session)
        if not isinstance(errors, list) or any(
            not isinstance(error, str) or not error.strip() for error in errors
        ):
            return _deny("Architrave delivery checker returned an invalid error list; acceptance is unverified.")
    except (ImportError, OSError, ValueError, TypeError, RuntimeError, KeyError, AttributeError) as error:
        return _failure("delivery checker", error)
    if errors:
        return _deny("Architrave delivery is not accepted:\n" + "\n".join(errors))
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event", choices=("session-start", "pre-tool-use"))
    args = parser.parse_args()
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        raw = sys.stdin.read()
        if args.event == "session-start":
            result = {"additionalContext": bootstrap_context()}
        else:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("Hook input must be an object")
            result = pre_tool_use(payload)
    except (ValueError, UnicodeError, OSError) as error:
        result = (
            {"additionalContext": f"Architrave startup input failed ({type(error).__name__}); report this limitation."}
            if args.event == "session-start" else _failure("completion input", error)
        )
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
