#!/usr/bin/env python3
"""One invocation's private stdio bridge to the joined Copilot extension.

This is not a daemon or a JSON receipt importer. The installed extension owns
stdin and independently obtains task outcomes from its existing host connection.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from architrave_runtime import (RunStore, RuntimeFailure, find_task, map_effort, primary_criterion_status, redact,
                                requested_effort, state_summary)
from worker_adapters import render_prompt


def receive():
    line = sys.stdin.buffer.readline(65537)
    if not line:
        raise RuntimeFailure(
            "NATIVE_HOST_REQUIRED",
            "No joined native host owns this pipe. Invoke the installed extension in a supported Copilot session; no CLI fallback.",
            exit_code=2,
        )
    if len(line) > 65536:
        raise RuntimeFailure("NATIVE_TRANSPORT_INVALID", "native host message exceeded its bound")
    value = json.loads(line)
    if not isinstance(value, dict):
        raise RuntimeFailure("NATIVE_TRANSPORT_INVALID", "native host message must be an object")
    return value


def emit(value):
    print(json.dumps(redact(value), separators=(",", ":")), flush=True)

def emit_source_inventory(paths):
    chunk = []
    for path in paths:
        candidate = {"status": "source-inventory", "files": [*chunk, path]}
        if len(json.dumps(candidate).encode("utf-8")) > 48000:
            if not chunk:
                raise RuntimeFailure("SEMANTIC_SOURCE_TOO_LARGE", "one tracked path exceeds its transport bound")
            emit({"status": "source-inventory", "files": chunk})
            chunk = [path]
            if len(json.dumps({"status": "source-inventory", "files": chunk}).encode("utf-8")) > 48000:
                raise RuntimeFailure("SEMANTIC_SOURCE_TOO_LARGE", "one tracked path exceeds its transport bound")
        else:
            chunk.append(path)
    if chunk:
        emit({"status": "source-inventory", "files": chunk})


def routing_observation(requested, effective, reused_owner=False):
    fallback = None
    if not effective:
        fallback = "host did not report effective selection"
    elif requested and requested != effective:
        fallback = "host reported a different effective model"
    if requested and reused_owner:
        fallback = "reused owner inherits its configuration; no per-turn model override"
    return {"requestedModel": requested, "effectiveModel": effective, "fallback": fallback}


def main():
    if sys.argv[1:] == ["--help"]:
        print("Architrave native host bridge: owned by the installed Copilot extension's joined tasks RPC.")
        print("This private per-invocation pipe is not a worker CLI or result importer. No host: NATIVE_HOST_REQUIRED.")
        return 0
    ticket = None
    store = None
    try:
        request = receive()
        store = RunStore(request["repo"])
        action = request["action"]
        run_id = request["runId"]
        if action == "status":
            summary = state_summary(store.load(run_id))
            summary["hostWorkers"] = request.get("hostWorkers") or summary["hostWorkers"]
            summary["runtime"]["joinedHostOwner"] = request.get("owner")
            summary["runtime"]["nativeInstallation"] = request.get("nativeInstallation")
            emit({"status": "ok", "result": summary})
            return 0
        if action == "recover":
            if request.get("checkpointId"):
                store.recover_native_checkpoint(run_id, request["checkpointId"], host_owner=request["owner"])
            emit({"status": "ok", "result": state_summary(store.recover_workers(run_id, task_id=request.get("taskId")))})
            return 0
        if action == "gate":
            emit({"status": "ok", "result": store.execute_gate(
                run_id, request["taskId"], recipe=request.get("recipe", "test"), ci_run_id=request.get("ciRunId"))})
            return 0
        if action == "semantic-review":
            if set(request) - {"repo", "action", "runId", "taskId", "owner", "invocationId", "reviewer", "nativeInstallation"}:
                raise RuntimeFailure("NATIVE_TRANSPORT_INVALID", "semantic execution does not accept result/model/producer claims")
            review, prompt = store.prepare_native_semantic_review(
                run_id, request["taskId"], host_owner=request["owner"],
                invocation_id=request["invocationId"], reviewer=request["reviewer"],
            )
            emit({"status": "prepared", "prompt": prompt, "agentType": request["reviewer"],
                  "maxTurns": review.budget.get("maxTurns", 12), "expiresAt": review.binding["expiresAt"],
                  "sourceFileCount": len(review.source_files), "reviewScope": review.binding["reviewScope"]})
            emit_source_inventory(review.source_files)
            admitted = receive()
            if set(admitted) != {"status", "hostTaskId"} or admitted["status"] != "admitted":
                raise RuntimeFailure("NATIVE_ADMISSION_FAILED", "fresh independent reviewer was not admitted")
            store.bind_native_semantic_owner(review, admitted["hostTaskId"])
            emit({"status": "bound"})
            observed = receive()
            if set(observed) != {"hostTaskId", "hostStatus", "text", "completion"}:
                raise RuntimeFailure("NATIVE_TRANSPORT_INVALID", "semantic completion must come from the joined observer")
            reviewed = store.accept_native_semantic_review(review, **{
                "host_task_id": observed["hostTaskId"], "host_status": observed["hostStatus"],
                "text": observed["text"], "completion": observed["completion"],
            })
            emit({"status": "ok" if reviewed["verdict"] == "PASS" else "failed", "result": reviewed})
            return 0 if reviewed["verdict"] == "PASS" else 1
        if action != "dispatch":
            raise RuntimeFailure("NATIVE_TRANSPORT_INVALID", "unknown native host action")
        task_id = request["taskId"]
        ticket = store.begin_native_worker(run_id, task_id, host_owner=request["owner"],
                                          retry_hypothesis=request.get("retryHypothesis"),
                                          owner_handle=request.get("ownerHandle"))
        state = store.load(run_id)
        task = find_task(state, task_id)
        packet = {**task["workPacket"], "budget": ticket.snapshot["budget"]}
        stall = primary_criterion_status(state, store.events(run_id), store.repository)
        effort = map_effort(requested_effort(state, task, bool(stall and stall["stalled"])),
                            request.get("hostEffort") or {})
        emit({
            "status": "prepared", "binding": ticket.binding,
            "prompt": render_prompt(packet) + "\n"
            + f"Use ONLY this isolated workspace, with absolute paths: {task['workspace']}\n"
            + "Do not launch another agent CLI, commit, mutate the source checkout, or change Run state.\n"
            + "Do not call Architrave control-plane extension tools. Return a candidate, never claim gate PASS.",
            "agentType": "general-purpose" if task["mutablePaths"] else "explore",
            "timeoutSeconds": packet["budget"]["timeoutSeconds"],
            "maxTurns": packet["budget"].get("maxTurns", 12),
            "expiresAt": task["lease"]["expiresAt"],
            "effort": effort,
        })
        admitted = receive()
        if admitted.get("status") != "admitted":
            raise RuntimeFailure("NATIVE_ADMISSION_FAILED", admitted.get("error", "host did not admit the worker"))
        store.bind_native_owner(ticket, admitted["hostTaskId"])
        emit({"status": "bound", "binding": ticket.binding})
        observed = receive()
        result = store.accept_native_candidate(
            ticket, host_task_id=observed["hostTaskId"],
            host_status=observed["hostStatus"], text=observed.get("text", ""),
            host_observation={key: observed.get(key) for key in (
                "requestedModel", "effectiveModel", "usageTotal", "totalToolCalls", "turnsObserved", "budgetStop")},
        )
        result["routing"] = routing_observation(observed.get("requestedModel"), observed.get("effectiveModel"),
                                                observed.get("reusedOwner", False))
        emit({"status": "failed" if result["status"] == "failed" else "ok", "result": result})
        return 0 if result["status"] == "candidate" else 1
    except (RuntimeFailure, OSError, ValueError, KeyError) as exc:
        cleanup_error = None
        if ticket is not None and not ticket.consumed and store is not None:
            try:
                store.fail_task(ticket.binding["runId"], ticket.binding["taskId"], f"native bridge failed: {exc}")
            except RuntimeFailure as cleanup:
                cleanup_error = cleanup.code
        emit({"status": "failed", "error": {
            "code": exc.code if isinstance(exc, RuntimeFailure) else "NATIVE_TRANSPORT_INVALID",
            "message": str(exc), "cleanupError": cleanup_error,
        }})
        return exc.exit_code if isinstance(exc, RuntimeFailure) else 1


if __name__ == "__main__":
    raise SystemExit(main())
