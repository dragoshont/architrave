"""Bounded, read-only canvas projection of authenticated Run state and events."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from architrave_runtime import RunStore, RuntimeFailure, feasibility_status, redact, state_summary


def compact(value: Any) -> str:
    return redact(str(value))[:1200]


def ribbon_snapshot(store: RunStore, run_id: str | None = None) -> dict[str, Any]:
    state = store.load(run_id)
    events = store.events(state["runId"])
    if not events:
        raise RuntimeFailure("RIBBON_HISTORY_EMPTY", "Run projection requires authenticated event history")
    if events[-1]["sequence"] != state["eventCursor"]["sequence"]:
        raise RuntimeFailure("RIBBON_SNAPSHOT_RACE", "Run changed during projection; request a fresh snapshot")
    summary = state_summary(state)
    source = summary["source"]
    tasks = {task["id"]: task for task in state["tasks"]}
    if len(tasks) > 80:
        raise RuntimeFailure("RIBBON_SNAPSHOT_LIMIT", "Ribbon supports at most 80 steps; no history is silently dropped")
    criteria = {item["id"]: item for item in state["acceptanceCriteria"]}
    artifacts = {f"artifact:{item['id']}": item for item in state["artifacts"]}
    steps = []
    streams = {}
    known_lanes = {lane["id"] for lane in [*state["lanes"]["active"], *state["lanes"]["deferred"]]}
    deadlines = []
    reasons = {event["taskId"]: event["payload"]["reason"] for event in events
               if event.get("taskId") and event["payload"].get("reason")
               and event["type"] in {"task.failed", "task.skipped", "task.deferred"}}
    completions = {event["taskId"]: event["evidenceRefs"] for event in events
                   if event.get("taskId") and event["type"] == "task.completed"}
    failed_tasks = set()
    for task in tasks.values():
        work_kind = task.get("workKind") or "unassigned"
        category = ("delivery" if work_kind == "product" else
                    "reference" if task.get("reference") and work_kind != "product" else
                    "exploratory" if work_kind in {"research", "diagnostic"} else
                    "review" if work_kind == "review" else
                    "operations" if work_kind in {"communications", "infrastructure"} else "unassigned")
        lane = task.get("lane")
        stream_id = "stream-" + hashlib.sha256(f"{lane}:{category}".encode()).hexdigest()[:16]
        label = f"{lane} / {category}" if lane in known_lanes else f"Unassigned lane ({lane or 'unknown'}) / {category}"
        streams.setdefault(stream_id, {"id": stream_id, "label": label, "kind": category,
                                      "outcome": ("Scoped investigation/reference findings; not product shipped or verified."
                                                  if category in {"exploratory", "reference"}
                                                  else "Independent scoped work; acceptance remains source-bound.")})
        current = task["objectiveVersion"] == state["objective"]["version"]
        status = task["status"]
        display = {
            "COMPLETED": "done", "RUNNING": "active", "WAITING_WORKER": "active",
            "WAITING_EXTERNAL": "blocked", "WAITING_RESOURCE": "blocked", "NOT_READY": "blocked",
            "DEFERRED": "deferred", "SKIPPED": "bypassed", "FAILED": "stopped",
            "CANCELLED": "stopped", "READY": "planned",
        }.get(status, "planned")
        reason = task.get("deferredReason") or reasons.get(task["id"]) or f"Canonical task state: {status}. Not a product acceptance claim."
        blocker = {"WAITING_EXTERNAL": "human", "WAITING_RESOURCE": "resource", "NOT_READY": "dependency"}.get(status)
        holds = [item for item in state["externalCheckpoints"]
                 if item["taskId"] == task["id"] and item["status"] == "PENDING"]
        if current and holds:
            if display not in {"stopped", "deferred", "bypassed", "done", "verified"}:
                display = "blocked"
            blocker = "human"
            reason = "Pending human checkpoint: " + ", ".join(item["type"] for item in holds)
        if not current:
            display = display if display in {"done", "bypassed", "stopped"} else "deferred"
            blocker = None
            reason = f"Historical objective {task['objectiveVersion']}; not a current blocker. {reason}"
        evidence = list(dict.fromkeys([*(task.get("evidenceRefs") or []),
                                      *completions.get(task["id"], [])]))
        failures = [gate for gate in state["gateResults"] if current
                    and gate["objectiveVersion"] == state["objective"]["version"]
                    and gate["status"] == "FAIL"
                    and gate["type"] in {"deterministic", "reality", "e2e", "policy", "security"}
                    and (gate["taskId"] == task["id"]
                         or set(gate["criteria"]).intersection(task["acceptanceCriteria"]))]
        if failures:
            failed_tasks.add(task["id"])
            display = "stopped"
            reason = "Governing verification failed: " + ", ".join(gate["id"] for gate in failures) + (
                ". Earlier scoped completion/observations are history, not current product verification.")
            evidence.extend(f"gate:{gate['id']}" for gate in failures)
        if display == "done" and not evidence:
            evidence = [f"task:{task['id']} (canonical scoped completion; not product verification)"]
        if current and display == "done" and source["baselineFresh"] and category == "delivery":
            product = []
            for criterion_id in task["acceptanceCriteria"]:
                criterion = criteria[criterion_id]
                if criterion["status"] != "PASS" or criterion["verificationType"] not in {"reality", "e2e"}:
                    break
                matches = []
                for gate in state["gateResults"]:
                    if (gate["status"] != "PASS" or gate["type"] not in {"reality", "e2e"}
                            or gate["taskId"] != task["id"] or gate["objectiveVersion"] != state["objective"]["version"]
                            or criterion_id not in gate["criteria"] or f"gate:{gate['id']}" not in criterion["evidenceRefs"]):
                        continue
                    for ref in gate["evidenceRefs"]:
                        artifact = artifacts.get(ref)
                        if not artifact or artifact["producer"] != "legibility":
                            continue
                        receipt = json.loads((store.repository / artifact["path"]).read_text(encoding="utf-8"))
                        binding = receipt.get("binding") or {}
                        observed = receipt.get("source") or {}
                        if (binding.get("runId") == state["runId"] and binding.get("taskId") == task["id"]
                                and binding.get("objectiveVersion") == state["objective"]["version"]
                                and criterion_id in binding.get("criteria", [])
                                and observed.get("commit") == source["observedCommit"]
                                and observed.get("sha256") == source["sha256"]):
                            matches.append(f"gate:{gate['id']} / {ref} / sha256:{artifact['sha256']}")
                if not matches:
                    break
                product.extend(matches)
            else:
                if product:
                    display, evidence = "verified", product
                    reason = "Current task criteria have source-bound observed product PASS; not universal product acceptance."
        loop = task.get("loop")
        retry = None
        if loop:
            retry = {"fingerprint": loop["fingerprint"], "evidenceFingerprint": loop["evidence"],
                     "repeated": loop["count"], "stopped": loop["stopped"],
                     "reason": compact(loop.get("hypothesis") or (
                         "Same failure and evidence fingerprints repeated; lane stopped." if loop["stopped"]
                         else "Recorded failure; another attempt requires a new hypothesis or evidence."))}
            if loop["stopped"]:
                display = "stopped"
        feasibility = task.get("feasibility")
        if current and feasibility:
            deadlines.append(feasibility["expiresAt"])
            reason += f" Lane deadline: {feasibility['expiresAt']}; decision: {feasibility['decision']}."
            reset = feasibility_status(state, task)
            if display not in {"done", "verified", "bypassed"} and reset and (
                    reset["expired"] or reset["decision"] == "PARK"):
                display = "stopped"
                reason += " Explicit parked/expired feasibility window; not product verification."
        owners = [worker for worker in state["workers"] if worker.get("taskId") == task["id"]]
        owner = next((worker for worker in owners if worker["id"] == (task.get("lease") or {}).get("owner")),
                     owners[-1] if owners else None)
        host = (owner or {}).get("nativeBinding") or {}
        steps.append({
            "id": task["id"], "title": compact(task["title"]), "state": display, "current": current,
            "reason": compact(reason), "evidence": [compact(item) for item in evidence],
            "dependencies": task["dependencies"], "blocker": blocker, "attempts": task["attempts"],
            "retry": retry, "weightEstimate": 1,
            "streamId": stream_id, "workKind": work_kind,
            "owner": owner["id"] if owner else None, "hostOwner": host.get("owner"),
            "hostTaskId": host.get("hostTaskId"), "startedAt": (owner or {}).get("startedAt"),
            "finishedAt": (owner or {}).get("finishedAt"),
        })
    milestone = None
    milestone_criterion = None
    for event in events:
        if event["type"] == "objective.replaced":
            milestone = None
        payload = event["payload"]
        if (event["type"] == "acceptance.updated" and payload.get("criterionId") == milestone_criterion
                and payload.get("status") != "PASS"):
            milestone = None
        if (event["type"] == "product.milestone" and payload.get("taskId") in tasks
                and tasks[payload["taskId"]]["objectiveVersion"] == state["objective"]["version"]
                and tasks[payload["taskId"]].get("workKind") == "product"
                and payload["taskId"] not in failed_tasks
                and criteria[payload["criterionId"]]["status"] != "FAIL"
                and payload.get("source") == {"commit": source["observedCommit"], "sha256": source["sha256"]}):
            milestone = compact(f"{payload['milestone']} / criterion:{payload['criterionId']} / "
                                f"task:{payload['taskId']} / event:{event['sequence']} / "
                                f"source:{source['sha256']}")
            milestone_criterion = payload["criterionId"]
    domain = hashlib.sha256(str(store.repository.resolve()).encode("utf-8")).hexdigest()[:24]
    result = {
        "schema": "architrave.ribbon.v1", "domainKey": f"{domain}:{state['runId']}", "runId": state["runId"],
        "revision": state["revision"], "objectiveVersion": state["objective"]["version"],
        "title": compact(state["goal"]), "objective": compact(state["objective"]["description"]),
        "capturedAt": summary["observedAt"], "startedAt": state["createdAt"],
        "deadline": min(deadlines) if deadlines else None,
        "source": {"commit": source["observedCommit"], "sha256": source["sha256"],
                   "freshness": "current" if source["baselineFresh"] else "stale",
                   "provenance": "Python authenticated Run/event projection, agent-fed; canvas does not attest claims. "
                                 "Freshness is capture-time only. Direct host workers and usage telemetry are unknown."},
        "next": compact(summary["nextCheapestTest"]) if summary["nextCheapestTest"] else None,
        "milestone": milestone, "steps": steps,
    }
    for stream in streams.values():
        stream["sourceRef"] = {
            "domainKey": result["domainKey"], "runId": state["runId"], "revision": state["revision"],
            "objectiveVersion": state["objective"]["version"], "capturedAt": summary["observedAt"],
            "commit": source["observedCommit"], "sha256": source["sha256"],
            "freshness": result["source"]["freshness"],
        }
    result["streams"] = list(streams.values())
    indexed = {step["id"]: step for step in steps}
    result["relations"] = [
        {"fromStep": parent, "toStep": step["id"], "type": "blocks",
         "reason": ("Canonical prerequisite; not a non-blocking research annotation."
                    if step["current"] and indexed[parent]["current"]
                    else "Historical prerequisite from a superseded objective; not a current blocker."),
         "provenance": "canonical dependency"}
        for step in steps for parent in step["dependencies"]
        if indexed[parent]["streamId"] != step["streamId"]
    ]
    if (len(json.dumps(result).encode("utf-8")) > 65536 or len(result["relations"]) > 160
            or any(len(step["evidence"]) > 12 for step in steps)):
        raise RuntimeFailure("RIBBON_SNAPSHOT_LIMIT", "Projection exceeds canvas bounds; no evidence is silently dropped")
    return result
