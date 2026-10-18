#!/usr/bin/env python3
"""Dispatch one native WorkPacket to an already-running local `opencode serve`.

Uses OpenCode's own session HTTP API; it never launches the opencode CLI. The
server, its permissions and model selection stay user/host-owned. The returned
text is only a candidate: the coordinator still runs gates and completes tasks.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from architrave_runtime import RunStore, RuntimeFailure, find_task, redact
from worker_adapters import render_prompt

LOOPBACK = {"127.0.0.1", "localhost", "::1"}
OUTCOME_STATUS = {"succeeded": "completed", "failed": "failed", "interrupted": "cancelled"}


class OpenCodeServer:
    def __init__(self, url: str, username: str, password: str | None):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "http" or parsed.hostname not in LOOPBACK:
            raise RuntimeFailure("OPENCODE_SERVER_DENIED", "only a loopback http opencode server is supported", exit_code=2)
        self.base = url.rstrip("/")
        self.headers = {"content-type": "application/json"}
        if password:
            token = base64.b64encode(f"{username}:{password}".encode()).decode()
            self.headers["authorization"] = f"Basic {token}"

    def call(self, method: str, path: str, body: dict | None = None, timeout: float = 30) -> dict | None:
        request = urllib.request.Request(
            self.base + path, method=method, headers=self.headers,
            data=None if body is None else json.dumps(body).encode())
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            exc.close()
            raise RuntimeFailure("OPENCODE_HTTP", f"{method} {path} returned {exc.code}") from exc
        except TimeoutError as exc:
            raise RuntimeFailure("OPENCODE_TIMEOUT", f"{method} {path} exceeded {timeout}s") from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise RuntimeFailure("OPENCODE_TIMEOUT", f"{method} {path} exceeded {timeout}s") from exc
            raise RuntimeFailure("OPENCODE_UNAVAILABLE", f"opencode server unreachable: {exc.reason}", exit_code=2) from exc
        if not raw:
            return None
        if not raw.lstrip().startswith(b"{"):
            raise RuntimeFailure("OPENCODE_API_UNSUPPORTED", f"{path} did not return the OpenCode JSON API", exit_code=2)
        return json.loads(raw)


def session_reply(server: OpenCodeServer, session_id: str) -> tuple[str, int, dict]:
    messages = server.call("GET", f"/api/session/{session_id}/message?order=asc&limit=200")["data"]
    replies = [message for message in messages if message.get("type") == "assistant"]
    text = "\n".join(part["text"] for message in replies[-1:] for part in message.get("content", [])
                     if part.get("type") == "text")
    return text, len(replies), (replies[-1].get("model") or {}) if replies else {}


def wait_until_idle(server: OpenCodeServer, session_id: str, timeout: float, interval: float = 2) -> str | None:
    """Poll until the session is idle. Permission prompts stay host-owned: report, never answer."""
    deadline = time.monotonic() + timeout
    reported: set[str] = set()
    pending: list[dict] = []
    while time.monotonic() < deadline:
        if session_id not in ((server.call("GET", "/api/session/active") or {}).get("data") or {}):
            return None
        pending = (server.call("GET", f"/api/session/{session_id}/permission") or {}).get("data") or []
        for request in pending:
            if request.get("id") not in reported:
                reported.add(request.get("id"))
                print(f"OpenCode is waiting for permission: {request.get('action')} {request.get('resources')}; "
                      "answer it in OpenCode (Architrave never answers host permissions).", file=sys.stderr)
        time.sleep(min(interval, max(0.0, deadline - time.monotonic())))
    if pending:
        return f"timeout with pending OpenCode permission: {pending[0].get('action')}"
    return "timeout"


def dispatch(store: RunStore, server: OpenCodeServer, run_id: str, task_id: str, agent: str | None) -> dict:
    info = server.call("GET", "/api/info") or {}
    owner = f"opencode:{info.get('pid', '?')}@{server.base}"[:256]
    ticket = store.begin_native_worker(run_id, task_id, host_owner=owner)
    session_id = None
    try:
        task = find_task(store.load(run_id), task_id)
        workspace = Path(task["workspace"]).resolve()
        packet = {**task["workPacket"], "budget": ticket.snapshot["budget"]}
        agent = agent or ("general" if task["mutablePaths"] else "explore")
        server.call("GET", f"/api/agent/{urllib.parse.quote(agent)}")
        created = server.call("POST", "/api/session", {
            "title": f"architrave {run_id}/{task_id}", "agent": agent,
            "location": {"directory": str(workspace)},
        })["data"]
        session_id = created["id"]
        if Path(created["location"]["directory"]).resolve() != workspace:
            raise RuntimeFailure("WORKSPACE_MISMATCH", "opencode session is not bound to the isolated worktree")
        store.bind_native_owner(ticket, session_id)
        server.call("POST", f"/api/session/{session_id}/prompt", {"text": render_prompt(packet) + "\n"
            + f"Use ONLY this isolated workspace: {workspace}\n"
            + "Do not commit, mutate the source checkout, or change Run state. Return a candidate, never claim gate PASS."})
        budget_stop = wait_until_idle(server, session_id, packet["budget"]["timeoutSeconds"])
        if budget_stop:
            server.call("POST", f"/api/session/{session_id}/interrupt")
            if wait_until_idle(server, session_id, 10, 0.5):
                budget_stop += "; termination unconfirmed"
        session = server.call("GET", f"/api/session/{session_id}")["data"]
        status = "cancelled" if budget_stop else OUTCOME_STATUS.get(session.get("outcome"), "failed")
        text, turns, model = session_reply(server, session_id)
        tokens = session.get("tokens") or {}
        model = session.get("model") or model
        result = store.accept_native_candidate(ticket, host_task_id=session_id, host_status=status, text=text, host_observation={
            "requestedModel": None,
            "effectiveModel": "/".join(str(model[key]) for key in ("providerID", "id") if model.get(key)) or None,
            "usageTotal": (tokens.get("input") or 0) + (tokens.get("output") or 0) or None,
            "totalToolCalls": None, "turnsObserved": turns, "budgetStop": budget_stop,
        })
        return {**result, "host": "opencode", "sessionId": session_id}
    except BaseException as exc:
        if session_id:
            try:
                server.call("POST", f"/api/session/{session_id}/interrupt")
            except RuntimeFailure:
                pass
        if not ticket.consumed:
            try:
                store.fail_task(run_id, task_id, f"opencode bridge failed: {exc}")
            except RuntimeFailure:
                pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=".")
    parser.add_argument("--server", default=os.environ.get("OPENCODE_SERVER_URL", "http://127.0.0.1:4096"))
    parser.add_argument("--agent", help="existing OpenCode agent; default general (mutable) or explore (read-only)")
    parser.add_argument("run_id")
    parser.add_argument("task_id")
    args = parser.parse_args(argv)
    try:
        server = OpenCodeServer(args.server, os.environ.get("OPENCODE_SERVER_USERNAME", "opencode"),
                                os.environ.get("OPENCODE_SERVER_PASSWORD"))
        result = dispatch(RunStore(args.repo), server, args.run_id, args.task_id, args.agent)
    except RuntimeFailure as exc:
        print(json.dumps({"status": "failed", "error": {"code": exc.code, "message": str(exc)}}), file=sys.stderr)
        return exc.exit_code
    print(json.dumps(redact(result), indent=2))
    return 0 if result["status"] == "candidate" else 1


if __name__ == "__main__":
    raise SystemExit(main())
