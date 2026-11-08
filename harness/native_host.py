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
    """Only permission-checked public filenames, never report or file contents."""
    chunk = []
    for path in paths:
        candidate = {"status": "source-inventory", "files": [*chunk, path]}
        if len(json.dumps(candidate).encode("utf-8")) > 48000:
            if not chunk:
                raise RuntimeFailure("SEMANTIC_SOURCE_TOO_LARGE", "one tracked path exceeds its transport bound")
            print(json.dumps({"status": "source-inventory", "files": chunk}, separators=(",", ":")), flush=True)
            chunk = [path]
            if len(json.dumps({"status": "source-inventory", "files": chunk}).encode("utf-8")) > 48000:
                raise RuntimeFailure("SEMANTIC_SOURCE_TOO_LARGE", "one tracked path exceeds its transport bound")
        else:
            chunk.append(path)
    if chunk:
        print(json.dumps({"status": "source-inventory", "files": chunk}, separators=(",", ":")), flush=True)


def requirements_kickoff(store: RunStore, task: dict, reqs: object) -> str:
    """Validate the tool's explicit binding against canonical state before host admission."""
    if store.requirements_document() is not None:
        selected = store.validate_requirement_binding(reqs)
        if selected != task.get("reqs", []):
            raise RuntimeFailure("REQ_BINDING_MISMATCH", "dispatch reqs must match the canonical task/WorkPacket")
    return store.requirements_context(task)


def host_task_inventory(value: object) -> list[dict]:
    if not isinstance(value, list):
        raise RuntimeFailure("NATIVE_TRANSPORT_INVALID", "native recovery requires an observed host task listing")
    tasks = []
    for task in value:
        if (not isinstance(task, dict) or not isinstance(task.get("id"), str) or not task["id"]
                or task.get("type") != "agent" or not isinstance(task.get("status"), str)):
            raise RuntimeFailure("NATIVE_TRANSPORT_INVALID", "host task listing contains an invalid identity")
        tasks.append({"id": task["id"], "type": task["type"], "status": task["status"],
                      "description": task.get("description") if isinstance(task.get("description"), str) else ""})
    return tasks


def native_workers(store: RunStore, run_id: str | None = None):
    states = []
    if run_id is not None:
        states.append(store.load(run_id))
    elif store.runs_root.is_dir():
        for directory in sorted(store.runs_root.iterdir()):
            if directory.is_dir() and (directory / "run.json").is_file():
                states.append(store.load(directory.name))
    for state in states:
        tasks = {task["id"]: task for task in state["tasks"]}
        for worker in state["workers"]:
            if worker.get("status") != "RUNNING" or worker.get("adapter") != "native":
                continue
            task = tasks.get(worker.get("taskId"))
            if (task is None or task.get("status") != "RUNNING"
                    or (task.get("lease") or {}).get("owner") != worker.get("id")):
                raise RuntimeFailure(
                    "NATIVE_RECOVERY_PENDING", "native worker and task lease identities do not agree",
                    details={"runId": state["runId"], "taskId": worker.get("taskId"),
                             "attemptId": worker.get("id"), "hostDisposition": "unconfirmed"},
                )
            yield state, task, worker


def unresolved_native_reservations(store: RunStore, host_tasks: list[dict]) -> list[str]:
    """Keep canonical attempts counted when the current host listing cannot account for them."""
    reservations = []
    for _, _, worker in native_workers(store):
        binding = worker.get("nativeBinding") or {}
        host_id = binding.get("hostTaskId")
        if host_id:
            accounted = any(task["id"] == host_id and task["status"] == "running" for task in host_tasks)
        else:
            marker = f"Architrave native attempt:{worker['id']}"
            accounted = any(task["description"] == marker and task["status"] == "running" for task in host_tasks)
        if not accounted:
            reservations.append(worker["id"])
    return reservations


def refuse_unreconciled_native_workers(store: RunStore, run_id: str) -> None:
    """Keep the read-only refusal seam for callers without joined-host cleanup proof."""
    for _, task, worker in native_workers(store, run_id):
        raise RuntimeFailure(
            "NATIVE_RECOVERY_PENDING",
            "native host ownership is live or unknown; recovery cannot close this Run lease",
            details={"taskId": task["id"], "attemptId": worker["id"],
                     "hostTaskId": (worker.get("nativeBinding") or {}).get("hostTaskId"),
                     "hostDisposition": "unconfirmed"},
        )


def native_recovery_targets(store: RunStore, run_id: str, host_owner: str,
                            host_tasks: list[dict], task_id: str | None = None) -> list[dict]:
    targets = []
    for state, task, worker in native_workers(store, run_id):
        if task_id is not None and task["id"] != task_id:
            continue
        binding = worker.get("nativeBinding") or {}
        if binding and binding.get("owner") != host_owner:
            raise RuntimeFailure(
                "NATIVE_RECOVERY_PENDING", "native attempt belongs to a different joined host owner",
                details={"taskId": task["id"], "attemptId": worker["id"],
                         "hostTaskId": binding.get("hostTaskId"), "hostDisposition": "unconfirmed"},
            )
        host_id = binding.get("hostTaskId")
        if not host_id:
            marker = f"Architrave native attempt:{worker['id']}"
            matches = [item for item in host_tasks if item["description"] == marker]
            if len(matches) != 1:
                raise RuntimeFailure(
                    "NATIVE_RECOVERY_PENDING",
                    "unbound native start has no unique attempt-matched host owner; absence is unconfirmed",
                    details={"taskId": task["id"], "attemptId": worker["id"],
                             "candidateCount": len(matches), "hostDisposition": "unconfirmed"},
                )
            host_id = matches[0]["id"]
            store.bind_recovered_native_owner(
                state["runId"], task["id"], attempt_id=worker["id"],
                host_owner=host_owner, host_task_id=host_id,
            )
        retained = any(
            previous["id"] != worker["id"]
            and previous["taskId"] == task["id"]
            and (previous.get("nativeBinding") or {}).get("hostTaskId") == host_id
            for previous in state["workers"]
        )
        targets.append({"attemptId": worker["id"], "taskId": task["id"], "hostTaskId": host_id,
                        "removeRequired": not retained})
    if len({item["hostTaskId"] for item in targets}) != len(targets):
        raise RuntimeFailure("NATIVE_RECOVERY_PENDING", "multiple Run attempts claim the same host owner")
    return targets


def confirm_native_recovery(store: RunStore, run_id: str, host_owner: str,
                            targets: list[dict], proof: object) -> list[dict]:
    if not isinstance(proof, dict) or set(proof) != {"status", "owners"} or proof["status"] != "reconciled":
        raise RuntimeFailure("NATIVE_RECOVERY_PENDING", "host cancellation/removal proof was not supplied")
    owners = proof["owners"]
    if not isinstance(owners, list) or len(owners) != len(targets):
        raise RuntimeFailure("NATIVE_RECOVERY_PENDING", "host cleanup proof does not cover every native attempt")
    supplied = {}
    for item in owners:
        if (not isinstance(item, dict) or set(item) - {
                "attemptId", "hostTaskId", "cancellationConfirmed", "removalConfirmed", "error"}
                or not {"attemptId", "hostTaskId", "cancellationConfirmed", "removalConfirmed"}.issubset(item)
                or item.get("error") is not None and not isinstance(item.get("error"), str)):
            raise RuntimeFailure("NATIVE_RECOVERY_PENDING", "host cleanup proof has an invalid shape")
        supplied[item["attemptId"]] = item
    expected = {target["attemptId"] for target in targets}
    if set(supplied) != expected:
        raise RuntimeFailure("NATIVE_RECOVERY_PENDING", "host cleanup proof does not match the Run attempts")
    recovered = []
    for target in targets:
        result = supplied[target["attemptId"]]
        if (result["hostTaskId"] != target["hostTaskId"] or result["cancellationConfirmed"] is not True
                or result["removalConfirmed"] is not target["removeRequired"]):
            raise RuntimeFailure(
                "NATIVE_RECOVERY_PENDING", result.get("error") or
                "host did not confirm required cancellation and removal",
                details={"taskId": target["taskId"], "attemptId": target["attemptId"],
                         "hostTaskId": target["hostTaskId"], "hostDisposition": "unconfirmed"},
            )
        state = store.load(run_id)
        task = find_task(state, target["taskId"])
        worker = next((item for item in state["workers"] if item["id"] == target["attemptId"]), None)
        if worker is None:
            raise RuntimeFailure("NATIVE_RECOVERY_PENDING", "native attempt disappeared during host cleanup")
        if worker["status"] != "RUNNING" or task["status"] != "RUNNING":
            recovered.append({"taskId": task["id"], "attemptId": worker["id"],
                              "hostRemovalConfirmed": target["removeRequired"], "alreadySettled": True})
            continue
        binding = worker.get("nativeBinding") or {}
        if ((task.get("lease") or {}).get("owner") != worker["id"]
                or binding.get("hostTaskId") != target["hostTaskId"]
                or binding.get("owner") != host_owner):
            raise RuntimeFailure("NATIVE_RECOVERY_PENDING", "Run ownership changed during host cleanup")
        store.fail_task(
            run_id, task["id"],
            f"native attempt {worker['id']} host owner {target['hostTaskId']} cancelled and removed during recovery",
            actor="native-host-recovery",
        )
        recovered.append({"taskId": task["id"], "attemptId": worker["id"],
                          "hostRemovalConfirmed": target["removeRequired"], "alreadySettled": False})
    return recovered


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
    admission_started = False
    try:
        request = receive()
        store = RunStore(request["repo"])
        action = request["action"]
        run_id = request["runId"]
        if not isinstance(run_id, str) or not run_id.strip():
            raise RuntimeFailure("NATIVE_RUN_REQUIRED", "native work requires an explicit Run id; latest history is not current context")
        if action == "status":
            summary = state_summary(store.load(run_id))
            summary["hostWorkers"] = request.get("hostWorkers") or summary["hostWorkers"]
            summary["runtime"]["joinedHostOwner"] = request.get("owner")
            summary["runtime"]["nativeInstallation"] = request.get("nativeInstallation")
            emit({"status": "ok", "result": summary})
            return 0
        if action == "capacity":
            tasks = host_task_inventory(request.get("hostTasks"))
            emit({"status": "ok", "result": {
                "unresolvedAttemptIds": unresolved_native_reservations(store, tasks),
            }})
            return 0
        if action in {"native-cancel", "recover"}:
            tasks = host_task_inventory(request.get("hostTasks"))
            targets = native_recovery_targets(
                store, run_id, request["owner"], tasks,
                task_id=request.get("taskId") if action == "native-cancel" else None,
            )
            if action == "native-cancel" and not targets:
                raise RuntimeFailure("NATIVE_RECOVERY_PENDING", "no live native Run attempt is available to reconcile")
            recovered = []
            if targets:
                emit({"status": "recovery-required", "targets": targets})
                recovered = confirm_native_recovery(
                    store, run_id, request["owner"], targets, receive(),
                )
            if action == "native-cancel":
                emit({"status": "ok", "result": {
                    "cancelled": True, "recovered": recovered,
                    "hostCancellationConfirmed": True,
                    "hostRemovalConfirmed": all(item["hostRemovalConfirmed"] for item in recovered),
                }})
                return 0
            if request.get("checkpointId"):
                store.recover_native_checkpoint(run_id, request["checkpointId"], host_owner=request["owner"])
            emit({"status": "ok", "result": state_summary(
                store.recover_workers(run_id, task_id=request.get("taskId")))})
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
        requirements_kickoff(store, find_task(store.load(run_id), task_id), request.get("reqs"))
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
            "prompt": requirements_kickoff(store, task, request.get("reqs")) + render_prompt(packet) + "\n"
            + f"Current Run: {run_id}. Use declared context, not another Run's scratch, receipts or latest-history discovery. "
            + "Explicit same-run reuse still requires current source and authority bindings.\n"
            + f"Use ONLY this isolated workspace, with absolute paths: {task['workspace']}\n"
            + "Do not launch another agent CLI, commit, mutate the source checkout, or change Run state.\n"
            + "Do not call Architrave control-plane extension tools. Return a candidate, never claim gate PASS.",
            "agentType": "general-purpose" if task["mutablePaths"] else "explore",
            "timeoutSeconds": packet["budget"]["timeoutSeconds"],
            "maxTurns": packet["budget"].get("maxTurns", 12),
            "expiresAt": task["lease"]["expiresAt"],
            "effort": effort,
        })
        admission = receive()
        if admission.get("status") == "starting":
            if admission.get("attemptId") != ticket.binding["workerId"]:
                raise RuntimeFailure("NATIVE_ATTEMPT_MISMATCH", "start request does not match the persisted Run worker attempt")
            admission_started = True
            admitted = receive()
        else:
            admitted = admission
        if admitted.get("status") != "admitted":
            raise RuntimeFailure("NATIVE_ADMISSION_FAILED", admitted.get("error", "host did not admit the worker"))
        admission_started = True
        store.bind_native_owner(ticket, admitted["hostTaskId"])
        emit({"status": "bound", "binding": ticket.binding})
        observed = receive()
        required_observation = {"hostTaskId", "hostStatus", "text"}
        optional_observation = {"reusedOwner", "requestedModel", "effectiveModel", "usageTotal",
                                "totalToolCalls", "turnsObserved", "budgetStop",
                                "cancellationConfirmed", "removalConfirmed"}
        if not required_observation.issubset(observed) or set(observed) - required_observation - optional_observation:
            raise RuntimeFailure("NATIVE_TRANSPORT_INVALID", "native completion frame has an invalid shape")
        reused_owner = observed.get("reusedOwner", False)
        if not isinstance(reused_owner, bool):
            raise RuntimeFailure("NATIVE_TRANSPORT_INVALID", "native completion owner-reuse claim must be boolean")
        if reused_owner != bool(request.get("ownerHandle")):
            raise RuntimeFailure("NATIVE_TRANSPORT_INVALID", "native completion owner reuse does not match admission")
        if reused_owner:
            if (observed.get("removalConfirmed") is not False
                    or not isinstance(observed.get("cancellationConfirmed"), bool)):
                raise RuntimeFailure("NATIVE_TRANSPORT_INVALID", "retained owners require cancellation proof and cannot be removed")
            if observed["hostStatus"] == "cancelled" and observed["cancellationConfirmed"] is not True:
                raise RuntimeFailure("NATIVE_RECOVERY_PENDING", "retained owner cancellation was not confirmed")
        elif observed.get("cancellationConfirmed") is not True or observed.get("removalConfirmed") is not True:
            raise RuntimeFailure("NATIVE_RECOVERY_PENDING", "candidate persistence requires confirmed host cancellation and removal")
        result = store.accept_native_candidate(
            ticket, host_task_id=observed["hostTaskId"],
            host_status=observed["hostStatus"], text=observed.get("text", ""),
            host_observation={key: observed.get(key) for key in (
                "requestedModel", "effectiveModel", "usageTotal", "totalToolCalls", "turnsObserved", "budgetStop",
                "cancellationConfirmed", "removalConfirmed")},
        )
        result["routing"] = routing_observation(observed.get("requestedModel"), observed.get("effectiveModel"),
                                                reused_owner)
        emit({"status": "failed" if result["status"] == "failed" else "ok", "result": result})
        return 0 if result["status"] == "candidate" else 1
    except (RuntimeFailure, OSError, ValueError, KeyError) as exc:
        cleanup_error = None
        if ticket is not None and not ticket.consumed and store is not None and not admission_started:
            try:
                store.fail_task(ticket.binding["runId"], ticket.binding["taskId"], f"native bridge failed: {exc}")
            except RuntimeFailure as cleanup:
                cleanup_error = cleanup.code
        emit({"status": "failed", "error": {
            "code": exc.code if isinstance(exc, RuntimeFailure) else "NATIVE_TRANSPORT_INVALID",
            "message": str(exc), "cleanupError": cleanup_error,
            **({"ownership": "unknown", "attemptId": ticket.binding["workerId"],
                "hostTaskId": ticket.binding.get("hostTaskId")} if admission_started and ticket is not None else {}),
            **({"details": exc.details} if isinstance(exc, RuntimeFailure) and exc.details else {}),
        }})
        return exc.exit_code if isinstance(exc, RuntimeFailure) else 1


if __name__ == "__main__":
    raise SystemExit(main())
