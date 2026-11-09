#!/usr/bin/env python3
"""Copilot startup guidance and advisory loop detection."""
from __future__ import annotations

import argparse
from collections.abc import Callable
from contextlib import contextmanager
import errno
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from uuid import UUID


def bootstrap_context() -> str:
    root = Path(__file__).resolve().parents[1]
    return (
        "For non-trivial development, invoke architrave "
        f"(`{root / 'skills' / 'architrave' / 'SKILL.md'}`); without a skill loader, "
        f"read `{root / 'agents' / 'architrave.agent.md'}` once. "
        "Development loop: one case, acceptance/design, focused checks, authorized commit; "
        "hold unclear specifications for sidebar research; continue independent cases. "
        "Code ready means written implementation; qualification/permission holds block dependent operations. "
        "All code ready before two independent final reviews by default; route accepted findings "
        "as task corrections to fresh implementers; resolve before authorized deployment. "
        "Restore case/phase after resume; stop unchanged rereads and take the next authorized action or state the exact hold. "
        "Track owner requests, corrections and progress in tasks.md, not SPEC.md or delivery declarations. "
        "Open/read tasks board when available; boards are not approval gates. "
        "Report unavailable/denied capability. "
        "Read-only/trivial work needs no board or sidebar; assigned workers/reviewers reuse parent scope. "
        "No unrequested fakes or feature/integration flags. "
        "Never invent prerequisites; respect scoped grants, stops, host permissions and the owner's selected mode."
    )


def _field(payload: dict[str, object], camel: str, snake: str) -> object:
    if camel in payload and snake in payload and payload[camel] != payload[snake]:
        raise ValueError(f"Conflicting {camel}/{snake} fields")
    return payload.get(camel, payload.get(snake))


def _report_path(session: str) -> Path:
    home = Path(os.environ.get("COPILOT_HOME", Path.home() / ".copilot"))
    return home / "session-state" / session / "files" / "architrave-delivery.json"


LOOP_WINDOW = 24
LOOP_REPEATS = 4
LOOP_COOLDOWN = 12
LOOP_CACHE_LIMIT = 16384
READ_TOOLS = {
    "view", "read_file", "glob", "grep", "rg",
    "web_fetch", "web_search", "semantic_code_search",
}


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _loop_failure(error: Exception) -> dict[str, str]:
    return {"additionalContext": (
        f"Architrave loop monitoring unavailable ({type(error).__name__}); "
        "report this limitation without exposing inputs. This is not a tool denial "
        "or a new approval requirement. Respect explicit stops and host permissions."
    )}


@contextmanager
def _loop_lock(path: Path):
    # Keep the lock inode in place so simultaneous hook processes share ownership.
    if path.is_symlink():
        raise ValueError("Loop lock cannot be a symlink")
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "r+b") as handle:
        deadline = time.monotonic() + 2
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as error:
                if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise
                if time.monotonic() >= deadline:
                    raise TimeoutError("Loop cache is busy") from error
                time.sleep(0.02)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _loop_state(path: Path) -> dict:
    if path.is_symlink():
        raise ValueError("Loop cache cannot be a symlink")
    try:
        with path.open("rb") as handle:
            raw = handle.read(LOOP_CACHE_LIMIT + 1)
    except FileNotFoundError:
        return {"schema": "architrave.loop.v1", "history": [], "notified": [], "since_notice": LOOP_COOLDOWN}
    if len(raw) > LOOP_CACHE_LIMIT:
        raise ValueError("Loop cache exceeds its bound")
    state = json.loads(raw)
    if not isinstance(state, dict) or state.get("schema") != "architrave.loop.v1":
        raise ValueError("Invalid loop cache")
    history, notified = state.get("history"), state.get("notified")
    since_notice = state.get("since_notice")
    if (
        not isinstance(history, list) or len(history) > LOOP_WINDOW
        or not isinstance(notified, list) or len(notified) > LOOP_WINDOW
        or type(since_notice) is not int or not 0 <= since_notice <= LOOP_COOLDOWN
    ):
        raise ValueError("Invalid loop cache bounds")
    hashes = list(notified)
    for row in history:
        if not isinstance(row, dict) or set(row) != {"request", "result"}:
            raise ValueError("Invalid loop observation")
        hashes.extend(row.values())
    if any(not isinstance(value, str) or len(value) != 64
           or any(char not in "0123456789abcdef" for char in value) for value in hashes):
        raise ValueError("Invalid loop fingerprint")
    return state


def post_tool_use(payload: dict[str, object]) -> dict[str, str]:
    """Observe successful reads only; never deny a call or change its result."""
    try:
        tool = _field(payload, "toolName", "tool_name")
        if not isinstance(tool, str):
            raise ValueError("Missing tool identity")
        tool = tool.rsplit(".", 1)[-1]
        tool = {"Read": "view", "Grep": "grep", "Glob": "glob",
                "WebFetch": "web_fetch", "WebSearch": "web_search"}.get(tool, tool)
        if tool not in READ_TOOLS:
            return {}
        tool = {"read_file": "view", "rg": "grep"}.get(tool, tool)
        result = _field(payload, "toolResult", "tool_result")
        if not isinstance(result, dict):
            raise ValueError("Missing read result")
        kind = _field(result, "resultType", "result_type")
        if kind == "failure":
            return {}
        text = _field(result, "textResultForLlm", "text_result_for_llm")
        if kind != "success" or not isinstance(text, str):
            raise ValueError("Invalid successful read result")
        session = _field(payload, "sessionId", "session_id")
        if not isinstance(session, str) or str(UUID(session)) != session.lower():
            raise ValueError("Invalid session identity")
        cwd = payload.get("cwd")
        if not isinstance(cwd, str) or not Path(cwd).is_absolute():
            raise ValueError("Missing absolute cwd")
        arguments = _field(payload, "toolArgs", "tool_input")
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        if not isinstance(arguments, dict):
            raise ValueError("Invalid read arguments")
        observation = {
            "request": _digest([os.path.normcase(str(Path(cwd).resolve())),
                                _field(payload, "agentId", "agent_id"), tool, arguments]),
            "result": _digest(text),
        }
        cache = _report_path(session.lower()).with_name("architrave-loop.json")
        cache.parent.mkdir(parents=True, exist_ok=True)
        with _loop_lock(cache.with_suffix(".lock")):
            state = _loop_state(cache)
            # Changed output invalidates the old repetition count for this request.
            history = [
                row for row in state["history"]
                if row["request"] != observation["request"] or row["result"] == observation["result"]
            ]
            history = (history + [observation])[-LOOP_WINDOW:]
            fingerprints = {_digest(row) for row in history}
            notified = [value for value in state["notified"] if value in fingerprints]
            since_notice = min(LOOP_COOLDOWN, state["since_notice"] + 1)
            count = history.count(observation)
            fingerprint = _digest(observation)
            warn = count >= LOOP_REPEATS and fingerprint not in notified and since_notice == LOOP_COOLDOWN
            if warn:
                notified.append(fingerprint)
                since_notice = 0
            state = {"schema": "architrave.loop.v1", "history": history,
                     "notified": notified, "since_notice": since_notice}
            descriptor, temporary = tempfile.mkstemp(prefix="architrave-loop-", suffix=".tmp", dir=cache.parent)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    json.dump(state, handle, separators=(",", ":"))
                os.replace(temporary, cache)
            finally:
                Path(temporary).unlink(missing_ok=True)
        if warn:
            return {"additionalContext": (
                f"Possible investigation loop: {count} identical results for the same read/search "
                f"within the last {len(history)} observed reads/searches. Reuse retained findings; "
                "stop redundant confirmation and take the next authorized action, or name the "
                "exact missing fact or hold. A new question can justify necessary research; "
                "this signal does not prove that no progress occurred. Respect explicit stops, "
                "read-only assignments and host permissions. Do not force edits, add approval "
                "stages, claim completion, or repeat status merely to satisfy this reminder."
            )}
        return {}
    except (OSError, ValueError, TypeError, UnicodeError) as error:
        return _loop_failure(error)


def pre_tool_use(
    payload: dict[str, object],
    *,
    checker: Callable[[Path, str], list[str]] | None = None,
) -> dict[str, str]:
    """Compatibility no-op for sessions retaining the retired completion hook."""
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event", choices=("session-start", "pre-tool-use", "post-tool-use"))
    args = parser.parse_args()
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        raw = sys.stdin.read()
        if args.event == "session-start":
            result = {"additionalContext": bootstrap_context()}
        elif args.event == "pre-tool-use":
            # Retained sessions still invoke this retired SPEC completion hook.
            result = {}
        else:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("Hook input must be an object")
            result = post_tool_use(payload)
    except (ValueError, UnicodeError, OSError) as error:
        if args.event == "session-start":
            result = {"additionalContext": f"Architrave startup input failed ({type(error).__name__}); report this limitation."}
        elif args.event == "post-tool-use":
            result = _loop_failure(error)
        else:
            result = {}
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
