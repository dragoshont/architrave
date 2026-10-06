#!/usr/bin/env python3
"""Frozen one-run host experiment; this script never launches an agent."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


STARTUP_PATHS = (
    "templates/AGENTS.stanza.md", "agents/architrave.agent.md",
    "skills/architrave/SKILL.md",
)
BASELINE_LOADS = (
    "skills/architrave-cto/SKILL.md", "knowledge/runtime-v2.md",
    "knowledge/execution-policy.md", "knowledge/yagni.md",
    "knowledge/learning-loop.md",
)
FILES = {
    "slug.py": 'def slug(value):\n    return value.lower().replace(" ", "-")\n',
    "validate.py": "def validate(records):\n    return records\n",
    "summary.py": "def summarize(records):\n    return {}\n",
    "verify.py": '''import sys
from slug import slug
from validate import validate
from summary import summarize
lane = sys.argv[1] if len(sys.argv) > 1 else "all"
if lane in ("a", "all"):
    assert slug("  Hello   WORLD  ") == "hello-world"
    assert slug("\\tA\\nB ") == "a-b"
    assert slug("") == ""
if lane in ("validate", "b", "all"):
    source = [{"name": " alpha ", "state": "ready"}, {"name": "b", "state": "blocked"}]
    result = validate(source)
    assert result == [{"name": "alpha", "state": "ready"}, {"name": "b", "state": "blocked"}]
    assert source[0]["name"] == " alpha " and result is not source
    for bad in ([{"name": "", "state": "ready"}], [{"name": "a", "state": "bad"}],
                [{"name": "a", "state": "ready"}, {"name": "a", "state": "blocked"}]):
        try:
            validate(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid record accepted")
if lane in ("summary", "b", "all"):
    source = [{"name": "b", "state": "blocked"}, {"name": "a", "state": "ready"}]
    assert summarize(source) == {"total": 2, "ready": 1, "blocked": 1, "names": ["a", "b"]}
    assert source[0]["name"] == "b"
    assert summarize([]) == {"total": 0, "ready": 0, "blocked": 0, "names": []}
print(lane + " acceptance PASS")
''',
}
OBJECTIVES = {
    "validate": "Implement validate(records): return a fresh list of fresh dicts; trim names; reject empty or duplicate trimmed names and states other than ready/blocked with ValueError. Preserve caller input. Only edit validate.py.",
    "summary": "Implement summarize(records): return total/ready/blocked integer counts and sorted names for normalized valid records, including empty input. Preserve caller input. Only edit summary.py.",
}


def command(argv, cwd):
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def footprint(source, paths):
    rows = [{"path": path, "bytes": len((source / path).read_bytes()),
             "sha256": hashlib.sha256((source / path).read_bytes()).hexdigest()} for path in paths]
    return {"files": rows, "bytes": sum(row["bytes"] for row in rows),
            "tokenEstimate": sum(row["bytes"] for row in rows) / 4,
            "tokenMethod": "UTF-8 bytes / 4 proxy; not host token telemetry"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "finish", "measure", "report"])
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--arm", choices=["baseline", "candidate"], required=True)
    parser.add_argument("--baseline-source", type=Path)
    parser.add_argument("--record", type=Path)
    parser.add_argument("--candidate-measurement", type=Path)
    parser.add_argument("--host-observations", type=Path, help="Explicit install/test/review observations; absent stays unavailable")
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    sys.path.insert(0, str(source / "harness"))
    from architrave_runtime import RunStore
    from workspaces import WorkspaceManager
    directory = output / args.arm
    metadata_path = directory / "measurement.json"
    if args.action == "report":
        if not args.baseline_source or not args.record:
            raise SystemExit("report needs --baseline-source and --record")
        baseline = json.loads((output / "baseline/measurement.json").read_text(encoding="utf-8"))
        candidate = json.loads((args.candidate_measurement or output / "candidate/measurement.json").read_text(encoding="utf-8"))
        if baseline["frozenFixtureSha256"] != candidate["frozenFixtureSha256"]:
            raise SystemExit("Arms do not share a frozen fixture")
        for measurement in (baseline, candidate):
            for row in measurement["tasks"].values():
                row.pop("stderrPreview", None)
        startup = {}
        for label, kit in (("baseline", args.baseline_source.resolve()), ("candidate", source)):
            startup[label] = {
                "entry": footprint(kit, STARTUP_PATHS),
                "startupIncludingInlineCTO": footprint(kit, STARTUP_PATHS + ("skills/architrave-cto/SKILL.md",)),
                "allEnumeratedSurfaces": footprint(kit, STARTUP_PATHS + BASELINE_LOADS),
                "forcedDurableB": footprint(kit, STARTUP_PATHS + BASELINE_LOADS if label == "baseline" else
                                           STARTUP_PATHS + ("skills/architrave-cto/SKILL.md",
                                                            "knowledge/runtime-v2.md", "knowledge/execution-policy.md")),
            }
        reductions = {key: round(100 * (1 - startup["candidate"][key]["bytes"] /
                                        startup["baseline"][key]["bytes"]), 2)
                      for key in startup["baseline"]}
        observations = json.loads(args.host_observations.read_text(encoding="utf-8")) if args.host_observations else {}
        a = candidate["tasks"].get("A", {})
        b = candidate["tasks"].get("B", {})
        native_b_pass = (b.get("acceptance") == "PASS" and b.get("execution") == "OBSERVED"
                         and b.get("nativeOwnersObserved", 0) in (2, 3)
                         and b.get("maxConcurrency", 0) in (2, 3)
                         and bool(b.get("workerStatuses"))
                         and all(status == "FINISHED" for status in b["workerStatuses"]))
        direct_a_pass = a.get("acceptance") == "PASS" and a.get("childCount") == 0
        verification = observations.get("verification", {})
        review = observations.get("review", {"status": "UNOBSERVED", "kind": "host-native"})
        host_matrix = {
            "windowsCopilotApp": {**observations.get("windowsCopilotApp", {}),
                                 "A": a.get("acceptance", "UNOBSERVED"),
                                 "B": ("UNVERIFIED_NATIVE_EXECUTION" if b.get("acceptance") == "PASS" and not native_b_pass
                                       else b.get("acceptance", "UNOBSERVED")),
                                 "nativeParallelBVerified": native_b_pass},
            "macOfficialCopilotCLI": observations.get("macOfficialCopilotCLI", {"A": "UNOBSERVED", "B": "UNOBSERVED"}),
            "macCopilotApp": observations.get("macCopilotApp", {"discovery": "UNOBSERVED", "A": "UNOBSERVED", "B": "UNOBSERVED"}),
            "macCodex": observations.get("macCodex", {"discovery": "UNOBSERVED", "desktopA": "UNOBSERVED", "desktopB": "UNOBSERVED"}),
        }
        record = {
            "schema": "architrave.thin-supervisor-experiment.v1", "version": "0.13.0",
            "baselineCommit": baseline["sourceCommit"], "candidateCommit": None,
            "frozenFixtureSha256": baseline["frozenFixtureSha256"],
            "startup": startup, "byteReductionPercent": reductions,
            "method": "One controlled comparison plus bounded final-source revalidation after transport changes, same frozen tasks and Windows app host, fresh git fixtures. Baseline has only an invocation-only batch helper; Python/ticket logic is untouched. Earlier serial diagnostics are excluded.",
            "limitations": [
                "Source byte/4 estimates are not tokenizer or complete host-injected context measurements.",
                "Parent context start/peak/end/growth and cost are unavailable for the Windows comparison.",
                "A is actual direct builder work, not a scripted native-worker fixture. A wall time is unavailable.",
                "B wall time is authenticated task-start to last native finish/failure, excluding later integration.",
                "Successful B has more evidence artifacts than failed baseline B; this is not an artifact-regression comparison.",
                "SDK contract tests are deterministic fixtures, not host-native execution evidence.",
            ],
            "windowsCopilotApp": {
                "baseline": baseline["tasks"], "candidate": candidate["tasks"],
                "unavailableExactTelemetry": candidate.get("exactTelemetry", {}),
                "candidateNativeOwnerCountObserved": b.get("nativeOwnersObserved"),
                "installedVersion": observations.get("windowsCopilotApp", {}).get("installedVersion"),
                "payloadMatchesCandidate": observations.get("windowsCopilotApp", {}).get("payloadMatchesCandidate"),
            },
            "hostMatrix": host_matrix,
            "suppliedVerificationObservations": verification,
            "acceptance": {
                "1": "Documented source audit; host observations supplied separately",
                "2": "Source implementation; no claim of unobserved execution",
                "3": "Windows native B verified; other transports unobserved" if native_b_pass else "Windows native B not verified",
                "4": "PASS: direct A, zero children" if direct_a_pass else "UNVERIFIED",
                "5": "Windows bounded parallel B verified; Mac app B unobserved" if native_b_pass else "UNVERIFIED",
                "6": "SDK/runtime guards require supplied test observations; descendant telemetry not separately captured",
                "7": "PASS: supplied native/loop regressions" if verification.get("nativeTestsExitCode") == 0 else "UNOBSERVED",
                "8": "PASS for measured startup bytes; actual context unavailable" if reductions["startupIncludingInlineCTO"] >= 35 else "FAIL startup byte target",
                "9": "Measured compact candidate returns" if native_b_pass and b.get("compactResultBytes") else "UNOBSERVED",
                "10": "Reported inheritance in host observations; concrete pin execution not observed",
                "11": "Source design only; local-model execution unobserved",
                "12": "Source implementation; Python plus required SDK glue",
                "13": "See supplied per-host install and execution observations; unobserved is not PASS",
                "14": "See supplied Codex install/discovery observations; desktop execution not inferred",
                "15": "PASS supplied full suite" if verification.get("fullSuiteExitCode") == 0 else "UNOBSERVED_OR_FAILED",
                "16": "Measured artifacts; aborted baseline is not a regression comparator",
                "17": "Candidate manifest version recorded; publication not inferred",
                "18": "Source documentation; final host limits recorded separately",
                "19": "Paired fixture digest checked; one reproducible measurement record",
                "20": review.get("status", "UNOBSERVED"),
            },
            "review": review,
        }
        args.record.parent.mkdir(parents=True, exist_ok=True)
        args.record.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"record": str(args.record), "byteReductionPercent": reductions}, indent=2))
        return
    if args.action == "measure":
        print(json.dumps(footprint(source, STARTUP_PATHS), indent=2))
        return
    if args.action == "prepare":
        if directory.exists():
            raise SystemExit("Refusing to overwrite an experiment arm")
        directory.mkdir(parents=True)
        frozen = hashlib.sha256(json.dumps(FILES, sort_keys=True).encode()).hexdigest()
        metadata = {
            "arm": args.arm, "frozenFixtureSha256": frozen,
            "startup": footprint(source, STARTUP_PATHS),
            "enumeratedDisclosureSurfaces": footprint(source, STARTUP_PATHS + BASELINE_LOADS),
            "forcedLoads": list(STARTUP_PATHS + BASELINE_LOADS) if args.arm == "baseline" else list(
                STARTUP_PATHS + ("skills/architrave-cto/SKILL.md",)),
            "durableTaskBLoads": list(STARTUP_PATHS + BASELINE_LOADS) if args.arm == "baseline" else list(
                STARTUP_PATHS + ("skills/architrave-cto/SKILL.md", "knowledge/runtime-v2.md",
                                 "knowledge/execution-policy.md")),
            "sourceCommit": command(["git", "rev-parse", "HEAD"], source) if (source / ".git").exists() else "c7229b1",
            "startedAtEpoch": time.time(), "host": "GitHub Copilot app, joined native tasks RPC",
            "exactTelemetry": {key: None for key in (
                "inputTokens", "outputTokens", "cost", "parentContextStart", "parentContextPeak",
                "parentContextEnd", "childContext", "parentTurns", "repeatedReads", "rawToolOutputBytes")},
            "telemetryLimitation": "Unavailable to this bounded experiment. Startup bytes and compact return bytes are proxies, not parent context usage. Same foreground supervisor, fresh independent git fixtures; no statistical claim.",
        }
        for lane in ("a", "b"):
            repo = directory / lane
            repo.mkdir()
            for name, content in FILES.items():
                (repo / name).write_text(content, encoding="utf-8")
            (repo / ".gitignore").write_text(".architrave/\n__pycache__/\n", encoding="utf-8")
            (repo / "architrave.config.json").write_text(json.dumps({
                "kind": "knowledge", "build": f'{"& " if sys.platform == "win32" else ""}"{sys.executable}" -B verify.py {lane}',
                "test": f'{"& " if sys.platform == "win32" else ""}"{sys.executable}" -B verify.py {lane}',
                "workers": {"defaultAdapter": "native", "enabledAdapters": ["native", "shell"]},
            }), encoding="utf-8")
            command(["git", "init", "-q"], repo)
            command(["git", "config", "user.name", "Architrave Benchmark"], repo)
            command(["git", "config", "user.email", "benchmark@example.invalid"], repo)
            command([sys.executable, str(source / "tools/install_update.py"), "install", "--profile", "knowledge", str(repo)], repo)
            command(["git", "add", "."], repo)
            command(["git", "commit", "-qm", "Frozen thin-supervisor fixture"], repo)
            result = subprocess.run([sys.executable, "-B", "verify.py", lane], cwd=repo, capture_output=True)
            if result.returncode == 0:
                raise SystemExit("Frozen baseline unexpectedly passes")
        store = RunStore(directory / "b")
        store.create(goal="Frozen B", outcome="Validated records and deterministic status summary",
                     run_id="frozen-b", autonomy_scope="approved-program",
                     policy_allow=[{"scope": "repository", "operations": ["edit"]}],
                     criteria=[{"id": "B", "description": "verify.py b passes", "scope": "product",
                                "risk": "R0", "verificationType": "deterministic", "blocking": True}])
        for task_id, objective in OBJECTIVES.items():
            store.add_task("frozen-b", {
                "id": task_id, "objective": objective + " Read verify.py for exact acceptance. Run only python -B verify.py " + task_id +
                ". Do not spawn agents. Do not write reports. Return status, changedPaths, findings, validation, blocker, nextAction in <=1500 bytes.",
                "acceptanceCriteria": ["B"], "workerProfile": "native", "risk": "R0",
                "mutablePaths": [task_id + ".py"], "pushback": "KEEP:independent frozen feature slice",
                "tools": ["read", "edit", "execute"],
                "workPacket": {"contextBundle": ["verify.py", task_id + ".py"],
                               "budget": {"timeoutSeconds": 240, "maxOutputBytes": 2000}},
            })
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"prepared": str(directory), "run": "frozen-b", "tasks": list(OBJECTIVES)}))
        return
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    store = RunStore(directory / "b")
    state = store.load("frozen-b")
    manager = WorkspaceManager(directory / "b")
    candidate_tasks = [task for task in state["tasks"] if task["status"] == "WAITING_RESOURCE"]
    for task in candidate_tasks:
        manager.collect("frozen-b", task["id"])
        manager.integrate("frozen-b", task["id"])
    if candidate_tasks:
        config_path = directory / "b" / "architrave.config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if sys.platform == "win32" and not config["test"].startswith("& "):
            config["test"] = "& " + config["test"]
            config["build"] = "& " + config["build"]
            config_path.write_text(json.dumps(config), encoding="utf-8")
        for task in candidate_tasks:
            gate = store.execute_gate("frozen-b", task["id"])
            if gate["status"] != "PASS":
                raise SystemExit("Independent configured gate failed: " + json.dumps(gate))
            store.complete_task("frozen-b", task["id"], evidence_refs=[gate["gateRef"]])
        store.set_criterion("frozen-b", "B", "PASS", [gate["gateRef"]])
        store.verify("frozen-b")
    state = store.load("frozen-b")
    workers = state["workers"]
    if not workers:
        native_execution = "NOT_DISPATCHED"
    elif any(worker["status"] == "FAILED" for worker in workers):
        native_execution = "FAILED"
    else:
        native_execution = "OBSERVED"
    metadata["tasks"] = {}
    for lane in ("a", "b"):
        repo = directory / lane
        check = subprocess.run([sys.executable, "-B", "verify.py", lane], cwd=repo, capture_output=True, text=True)
        paths = list((repo / ".architrave" / "runs").rglob("*")) if (repo / ".architrave" / "runs").exists() else []
        files = [path for path in paths if path.is_file()]
        row = {"acceptance": "UNOBSERVED" if lane == "b" and not workers else "PASS" if check.returncode == 0 else "FAIL",
               "testExit": check.returncode, "stdout": check.stdout.strip(),
               "stderrPreview": check.stderr[-1000:], "childCount": 0 if lane == "a" else len(workers),
               "maxDepth": 0 if lane == "a" else 1,
               "retries": 0 if lane == "a" else sum(max(0, task["attempts"] - 1) for task in state["tasks"]),
               "generatedFiles": len(files), "generatedBytes": sum(path.stat().st_size for path in files),
               "reviewReopens": 0, "conflictingWrites": 0,
               "modelRequested": None, "effectiveModel": None,
               "routing": "host inheritance; effective model not reported by task transport",
               "testExecutions": None,
               "testExecutionLimit": "Preparation and final acceptance observed; child test calls available only when reported",
               "wallSeconds": None}
        if lane == "b":
            row["execution"] = native_execution
            if not workers:
                row["maxDepth"] = None
            events = store.events("frozen-b")
            active = peak = 0
            for event in events:
                if event["type"] == "task.started":
                    active += 1
                    peak = max(peak, active)
                if event["type"] in {"worker.finished", "task.failed"}:
                    active = max(0, active - 1)
            row["maxConcurrency"] = peak
            row["nativeOwnersObserved"] = sum(bool(worker.get("nativeBinding", {}).get("hostTaskId")) for worker in workers)
            row["compactResultBytes"] = sum((store.repository / artifact["path"]).stat().st_size
                                            for artifact in state["artifacts"] if artifact["producer"] == "worker")
            row["workerStatuses"] = [worker["status"] for worker in workers]
            row["failureReasons"] = [worker.get("reason") for worker in workers if worker["status"] == "FAILED"]
            starts = [event["timestamp"] for event in events if event["type"] == "task.started"]
            ends = [event["timestamp"] for event in events if event["type"] in {"worker.finished", "task.failed"}]
            if starts and ends:
                from datetime import datetime
                row["wallSeconds"] = (datetime.fromisoformat(max(ends).replace("Z", "+00:00")) -
                                      datetime.fromisoformat(min(starts).replace("Z", "+00:00"))).total_seconds()
            row["wallMethod"] = "Run task-start through last native worker finish/failure; second-resolution authenticated events"
            row["hostObservations"] = [
                json.loads((store.repository / artifact["path"]).read_text(encoding="utf-8")).get("hostObservation")
                for artifact in state["artifacts"] if artifact["producer"] == "worker"]
            reported_models = sorted({observation["effectiveModel"] for observation in row["hostObservations"]
                                      if observation and observation.get("effectiveModel")})
            row["effectiveModel"] = reported_models or None
            row["routing"] = "host inheritance; effective selection reported" if reported_models else row["routing"]
            row["hostReportedCombinedUsage"] = sum(observation["usageTotal"] for observation in row["hostObservations"]
                                                   if observation and isinstance(observation.get("usageTotal"), int)) or None
            row["maxDepthMethod"] = "one-level canonical dispatch; descendant telemetry not separately captured; depth denial covered by SDK contract fixture"
        else:
            row["maxConcurrency"] = 0
        metadata["tasks"][lane.upper()] = row
    metadata["elapsedSecondsIncludingSupervisorTooling"] = round(time.time() - metadata["startedAtEpoch"], 3)
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
