#!/usr/bin/env python3
"""Canonical local lifecycle state: restricted YAML 1.2, one locked transaction."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import sys
import uuid

from architrave_runtime import FileLock, RunStore, RuntimeFailure, sha256_value, utc_now

SCHEMA = "architrave.lifecycle.v1"
MAX_BYTES = 4 * 1024 * 1024
MAX_RECEIPTS = 4096
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
COLLECTIONS = ("sources", "goals", "tasks", "constraints", "criteria", "decisions",
               "attempts", "evidence", "operations")
FIELDS = {
    "sources": {"id", "kind", "reference", "excerpt", "available"},
    "goals": {"id", "outcome", "source_refs", "disposition"},
    "tasks": {"id", "goal_id", "title", "source_refs", "depends_on", "criteria",
              "progress", "disposition", "activation", "paths"},
    "constraints": {"id", "statement", "applies_to", "source_refs", "disposition"},
    "criteria": {"id", "task_id", "expected", "source_refs", "kind"},
    "decisions": {"id", "question", "alternatives", "affected", "source_refs",
                  "resolution", "resolution_sources"},
    "attempts": {"id", "task_id", "worker", "host", "inputs", "activity",
                 "stop", "observation", "result", "integrated"},
    "evidence": {"id", "criterion_id", "inputs", "artifact", "method", "result",
                 "observed_at", "limitations"},
    "operations": {"id", "task_id", "attempt_id", "target", "action", "grant_ref", "artifact",
                   "inputs", "outcome", "observation", "reconciled"},
}
OPTIONAL_FIELDS = {
    "sources": {"timestamp"},
    "tasks": {"ready_inputs"},
    "decisions": {"superseded_by"},
    "attempts": {"scope"},
    "evidence": {"identity", "attempt_id"},
    "operations": {"identity"},
}
TERMINAL = {"completed", "failed", "cancelled"}
DISPOSITIONS = {"active", "proposed", "deferred", "cancelled", "retired"}


class StateError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise StateError(code, message)


def text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def identifier(value: object) -> bool:
    return isinstance(value, str) and ID.fullmatch(value) is not None


def keys(value: object, required: set, optional: set = frozenset()) -> None:
    require(isinstance(value, dict) and required <= value.keys()
            and value.keys() <= required | optional, "SHAPE", f"expected fields {sorted(required)}; optional {sorted(optional)}")


def unique(values: object) -> bool:
    return isinstance(values, list) and all(isinstance(v, str) for v in values) and len(values) == len(set(values))


def timestamp(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is not None
    except ValueError:
        return False


def current_decisions(state: dict) -> list:
    return [d for d in state["decisions"].values() if not d.get("superseded_by")]


def parse(raw: bytes) -> dict:
    require(len(raw) <= MAX_BYTES, "SIZE", "state/command exceeds 4 MiB")
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "DUPLICATE_KEY", f"duplicate key {key}")
            result[key] = value
        return result
    def invalid(value):
        raise StateError("SCALAR", f"nonfinite scalar {value}")
    def finite_float(value):
        number = float(value)
        require(math.isfinite(number), "SCALAR", f"nonfinite scalar {value}")
        return number
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid, parse_float=finite_float)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise StateError("YAML_PROFILE", "expected JSON-compatible YAML 1.2 (quoted keys/strings, no aliases/tags)") from exc
    def depth(item, level=0):
        require(level <= 40, "DEPTH", "maximum nesting is 40")
        if isinstance(item, dict):
            for child in item.values():
                depth(child, level + 1)
        elif isinstance(item, list):
            for child in item:
                depth(child, level + 1)
    depth(value)
    require(isinstance(value, dict), "SHAPE", "document must be a mapping")
    return value


def encode(value: dict) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode()


@lru_cache(maxsize=1)
def reported_machine() -> str:
    if sys.platform == "darwin":
        try:
            result = subprocess.run(["/usr/sbin/scutil", "--get", "LocalHostName"],
                                    check=True, capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.SubprocessError) as exc:
            raise StateError("HOST_IDENTITY_UNAVAILABLE", "cannot read the configured macOS host name") from exc
        require(text(result.stdout) and len(result.stdout.strip()) <= 200,
                "HOST_IDENTITY_UNAVAILABLE", "configured macOS host name is unavailable")
        return "macos:" + result.stdout.strip()
    require(text(platform.node()), "HOST_IDENTITY_UNAVAILABLE", "reported host name is unavailable")
    return platform.node()


def location(root: Path) -> dict:
    return {"machine": reported_machine(), "repository": str(root.resolve())}


def seal(state: dict) -> None:
    state["integrity"] = sha256_value({k: v for k, v in state.items() if k != "integrity"})


def refs(state: dict, values: object, collection: str) -> None:
    require(unique(values) and all(v in state[collection] for v in values),
            "REFERENCE", f"expected unique existing {collection} references")


def validate_paths(values: object) -> None:
    require(unique(values), "PATH", "paths must be unique repository-relative directories/files")
    for value in values:
        require(text(value) and "\\" not in value and not value.startswith("/")
                and not re.match(r"^[A-Za-z]:", value) and
                all(p not in {"", ".", ".."} for p in value.split("/"))
                and not any(c in value for c in "*?[]"), "PATH", f"invalid literal scope {value!r}")


def validate_identity(value: object) -> None:
    keys(value, {"candidate", "source", "base", "check_inputs"})
    require(all(text(v) for v in value.values()), "IDENTITY", "candidate/source/base/check-input identity is required")


def validate(state: dict) -> None:
    keys(state, {"schema", "project_id", "revision", "location", "created_at", "updated_at",
                 "phase", "corrections", "receipts", "imports", "conflicts", "integrity", *COLLECTIONS})
    require(state["schema"] == SCHEMA, "SCHEMA", "unsupported lifecycle schema")
    require(identifier(state["project_id"]) and type(state["revision"]) is int and state["revision"] >= 0,
            "IDENTITY", "invalid project/revision")
    keys(state["location"], {"machine", "repository"})
    require(all(text(v) for v in state["location"].values()), "LOCATION", "invalid location binding")
    require(state["phase"] in {"implementation", "review", "delivery", "held"}, "PHASE", "invalid phase")
    for collection in COLLECTIONS:
        require(isinstance(state[collection], dict), "SHAPE", f"{collection} must be a mapping")
        for key, row in state[collection].items():
            keys(row, FIELDS[collection], OPTIONAL_FIELDS.get(collection, set()))
            require(identifier(key) and row["id"] == key, "IDENTITY", f"invalid {collection} identity")
    for row in state["sources"].values():
        require(row["kind"] in {"owner", "observation", "document", "assistant", "worker"}
                and text(row["reference"]) and isinstance(row["excerpt"], str)
                and type(row["available"]) is bool, "SOURCE", "invalid source; kind is reported provenance, not authentication")
        require(row.get("timestamp") is None or timestamp(row["timestamp"]), "SOURCE", "invalid source timestamp")
    for collection in ("goals", "tasks", "constraints", "criteria", "decisions"):
        for row in state[collection].values():
            refs(state, row["source_refs"], "sources")
            require(bool(row["source_refs"]), "SOURCE", f"{row['id']} needs sources")
    for collection in ("goals", "tasks", "constraints"):
        for row in state[collection].values():
            require(row["disposition"] in DISPOSITIONS, "DISPOSITION", "invalid disposition")
    for row in state["goals"].values():
        require(text(row["outcome"]), "GOAL", "outcome is required")
    for row in state["constraints"].values():
        require(text(row["statement"]) and unique(row["applies_to"]) and bool(row["applies_to"])
                and all(v in state["tasks"] or v in state["goals"] for v in row["applies_to"]),
                "CONSTRAINT", "constraint needs bounded targets")
    for row in state["tasks"].values():
        require(row["goal_id"] in state["goals"] and text(row["title"]), "TASK", "task needs goal and title")
        refs(state, row["depends_on"], "tasks")
        refs(state, row["criteria"], "criteria")
        require(all(state["criteria"][c]["task_id"] == row["id"] for c in row["criteria"]),
                "CRITERION", "criterion belongs to another task")
        require(row["progress"] in {"", "In progress", "Code ready"}, "PROGRESS", "invalid progress")
        require(row["activation"] in {"automatic", "explicit_owner_direction"}, "ACTIVATION", "invalid activation")
        validate_paths(row["paths"])
        if "ready_inputs" in row:
            require(text(row["ready_inputs"]), "PROGRESS", "readiness needs its reported semantic input binding")
    visiting, visited = set(), set()
    def visit(tid):
        require(tid not in visiting, "DEPENDENCY_CYCLE", tid)
        if tid in visited:
            return
        visiting.add(tid)
        for dep in state["tasks"][tid]["depends_on"]:
            visit(dep)
        visiting.remove(tid)
        visited.add(tid)
    for tid in state["tasks"]:
        visit(tid)
    for row in state["criteria"].values():
        require(row["task_id"] in state["tasks"] and row["id"] in state["tasks"][row["task_id"]]["criteria"]
                and text(row["expected"]) and row["kind"] in {"implementation", "review", "integration", "runtime"},
                "CRITERION", "invalid criterion binding/kind")
    for row in state["decisions"].values():
        refs(state, row["affected"], "tasks")
        refs(state, row["resolution_sources"], "sources")
        require(text(row["question"]) and unique(row["alternatives"]) and len(row["alternatives"]) >= 2
                and (row["resolution"] is None or text(row["resolution"]) and bool(row["resolution_sources"])),
                "DECISION", "decision needs alternatives and source-backed resolution")
        if row.get("superseded_by"):
            require(row["superseded_by"] in state["decisions"]
                    and row["affected"] == state["decisions"][row["superseded_by"]]["affected"],
                    "DECISION", "supersession needs the same scoped decisions")
    owners = []
    for row in state["attempts"].values():
        require(row["task_id"] in state["tasks"] and text(row["worker"]) and text(row["host"])
                and text(row["inputs"]) and row["activity"] in TERMINAL | {"unknown", "running", "dispatched"}
                and row["stop"] in {"none", "requested", "acknowledged"}
                and type(row["integrated"]) is bool, "ATTEMPT", "invalid attempt")
        scope = row.get("scope")
        if "scope" in row:
            keys(scope, {"mode", "paths"})
            validate_paths(scope["paths"])
            require(scope["mode"] in {"mutable", "read_only"}
                    and (scope["mode"] == "read_only" or bool(scope["paths"])),
                    "SCOPE", "mutable attempts need a nonempty frozen assigned scope")
        if row["result"] is not None:
            keys(row["result"], {"artifact", "summary"}, {"identity"})
            require(text(row["result"]["artifact"]) and text(row["result"]["summary"]), "RESULT", "invalid result")
            if "identity" in row["result"]:
                validate_identity(row["result"]["identity"])
                require(row["result"]["identity"]["candidate"] == row["result"]["artifact"],
                        "IDENTITY", "result candidate must match its artifact")
        if row["activity"] not in TERMINAL:
            for other in owners:
                other_scope = other.get("scope")
                require(other["task_id"] != row["task_id"]
                        and not (scope and other_scope and scope["mode"] == other_scope["mode"] == "mutable"
                                 and overlaps(scope["paths"], other_scope["paths"])),
                        "OWNERSHIP", "live attempts overlap; unknown owners remain live")
            owners.append(row)
    for row in state["evidence"].values():
        require(row["criterion_id"] in state["criteria"] and row["result"] in {"pass", "fail", "unknown"}
                and all(text(row[k]) for k in ("inputs", "artifact", "method", "limitations"))
                and timestamp(row["observed_at"]),
                "EVIDENCE", "evidence requires identity, method, observed time and limitations")
        if "identity" in row:
            validate_identity(row["identity"])
        if "attempt_id" in row:
            require(row["attempt_id"] in state["attempts"]
                    and state["attempts"][row["attempt_id"]]["task_id"] == state["criteria"][row["criterion_id"]]["task_id"],
                    "EVIDENCE", "checked attempt must belong to the criterion task")
    for row in state["operations"].values():
        require(row["task_id"] in state["tasks"] and row["attempt_id"] in state["attempts"]
                and state["attempts"][row["attempt_id"]]["task_id"] == row["task_id"]
                and row["outcome"] in {"intended", "unknown", "succeeded", "failed"}
                and type(row["reconciled"]) is bool
                and all(text(row[k]) for k in ("target", "action", "grant_ref", "inputs", "artifact")),
                "OPERATION", "invalid external-operation record")
        if "identity" in row:
            validate_identity(row["identity"])
            require(row["identity"]["candidate"] == row["artifact"], "IDENTITY", "operation candidate differs from artifact")
        if row["observation"] is not None:
            keys(row["observation"], {"reference", "observed_at"}, {"identity"})
            require(text(row["observation"]["reference"]) and timestamp(row["observation"]["observed_at"]),
                    "OBSERVATION", "operation observation needs identity and time")
            if "identity" in row["observation"]:
                validate_identity(row["observation"]["identity"])
    require(isinstance(state["receipts"], dict) and len(state["receipts"]) <= MAX_RECEIPTS,
            "HISTORY_FULL", "receipt bound reached; archive whole project at a reconciled boundary")
    require(isinstance(state["corrections"], list) and isinstance(state["imports"], list)
            and isinstance(state["conflicts"], list), "HISTORY", "invalid history")
    require(state["integrity"] == sha256_value({k: v for k, v in state.items() if k != "integrity"}),
            "UNSUPPORTED_EDIT", "snapshot integrity mismatch; do not silently repair or fall back")


def overlaps(left: list, right: list) -> bool:
    return any(a == b or a.startswith(b + "/") or b.startswith(a + "/") for a in left for b in right)


def applicable_constraints(state: dict, tid: str) -> list:
    task = state["tasks"][tid]
    return [c for _, c in sorted(state["constraints"].items())
            if c["disposition"] == "active" and {tid, task["goal_id"]} & set(c["applies_to"])]


def inputs(state: dict, tid: str, criterion: str | None = None, *, _memo: dict | None = None) -> str:
    memo = {} if _memo is None else _memo
    key = (tid, criterion)
    if key in memo:
        return memo[key]
    task = state["tasks"][tid]
    goal = state["goals"][task["goal_id"]]
    # Bind declared meaning, not display labels, provenance additions or list order.
    # Equality does not prove that the interpretation entails the owner's request.
    relevant = {"task": {k: task[k] for k in ("id", "goal_id", "disposition", "activation")},
                "goal": {k: goal[k] for k in ("id", "outcome", "disposition")},
                "paths": sorted(task["paths"]),
                "constraints": [{k: c[k] for k in ("id", "statement")} for c in applicable_constraints(state, tid)],
                "criteria": [{k: state["criteria"][cid][k] for k in ("id", "task_id", "expected", "kind")}
                             for cid in sorted([criterion] if criterion else task["criteria"])],
                "decisions": [dict(id=d["id"], question=d["question"], alternatives=sorted(d["alternatives"]),
                                   resolution=d["resolution"])
                              for d in sorted(current_decisions(state), key=lambda d: d["id"]) if tid in d["affected"]],
                "dependencies": {dep: inputs(state, dep, _memo=memo) for dep in sorted(task["depends_on"])}}
    memo[key] = sha256_value(relevant)
    return memo[key]


def readiness(state: dict, tid: str) -> str:
    task = state["tasks"][tid]
    if task["progress"] != "Code ready":
        return "not_ready"
    if "ready_inputs" not in task:
        return "unavailable"
    return "current" if task["ready_inputs"] == inputs(state, tid) else "stale"


def scope_conflicts(attempt: dict, tid: str, paths: list, *, read_only: bool = False) -> bool:
    if attempt["task_id"] == tid:
        return True
    scope = attempt.get("scope")
    # Missing legacy scope is unknown, never reconstructed from a corrected task.
    return not read_only and (scope is None or scope["mode"] == "mutable" and overlaps(paths, scope["paths"]))


def evidence_applicability(state: dict, evidence: dict) -> str:
    if "identity" not in evidence:
        return "unavailable"
    criterion = state["criteria"][evidence["criterion_id"]]
    if evidence["inputs"] != inputs(state, criterion["task_id"], criterion["id"]):
        return "stale"
    if "attempt_id" in evidence:
        result = state["attempts"][evidence["attempt_id"]]["result"]
        if result is None or "identity" not in result:
            return "unavailable"
        if evidence["identity"] != result["identity"]:
            return "stale"
    return "current"


def holds(state: dict, tid: str, *, ignore_attempt: str | None = None, read_only: bool = False) -> list[str]:
    task = state["tasks"][tid]
    result = []
    if task["disposition"] != "active":
        result.append(f"task {task['disposition']}")
    if state["goals"][task["goal_id"]]["disposition"] != "active":
        result.append("goal not active")
    if task["activation"] != "automatic":
        result.append("explicit owner activation required")
    result += [f"decision {d['id']}" for d in current_decisions(state)
               if tid in d["affected"] and d["resolution"] is None]
    result += [f"dependency {dep}" for dep in task["depends_on"]
               if readiness(state, dep) != "current"
               or state["tasks"][dep]["disposition"] != "active"]
    result += [f"attempt {a['id']} ({a['activity']}, stop {a['stop']})"
               for a in state["attempts"].values() if a["activity"] not in TERMINAL and a["id"] != ignore_attempt
               and scope_conflicts(a, tid, task["paths"], read_only=read_only)]
    result += [f"operation {op['id']} requires reconciliation" for op in state["operations"].values()
               if scope_conflicts(state["attempts"][op["attempt_id"]], tid, task["paths"], read_only=read_only)
               and op["outcome"] in {"intended", "unknown"}]
    result += [f"migration conflict: {c['id']}" for c in state["conflicts"] if c["resolution"] is None
               and (not c["affected"] or tid in c["affected"])]
    relevant = list(task["source_refs"]) + state["goals"][task["goal_id"]]["source_refs"]
    for row in applicable_constraints(state, tid) + [state["criteria"][c] for c in task["criteria"]]:
        relevant += row["source_refs"]
    for row in current_decisions(state):
        if tid in row["affected"]:
            relevant += row["source_refs"] + row["resolution_sources"]
    result += [f"source unavailable: {sid}" for sid in sorted(set(relevant)) if not state["sources"][sid]["available"]]
    return result


def snapshot(state: dict, *, now: str, task_ids: list[str] | None = None) -> dict:
    require(timestamp(now), "CLOCK", "snapshot clock must be an offset-aware ISO timestamp")
    selected = list(state["tasks"]) if task_ids is None else task_ids
    require(all(tid in state["tasks"] for tid in selected), "REFERENCE", "unknown context task")
    tasks = []
    for tid in selected:
        task = copy.deepcopy(state["tasks"][tid])
        task["readiness"] = readiness(state, tid)
        task["holds"] = holds(state, tid)
        task["owners"] = [copy.deepcopy(a) for a in state["attempts"].values()
                          if a["task_id"] == tid and a["activity"] not in TERMINAL]
        task["acceptance"] = []
        for cid in task["criteria"]:
            criterion = copy.deepcopy(state["criteria"][cid])
            criterion["inputs"] = inputs(state, tid, cid)
            criterion["evidence"] = [copy.deepcopy(dict(e, applicability=evidence_applicability(state, e)))
                                     for e in state["evidence"].values() if e["criterion_id"] == cid]
            task["acceptance"].append(criterion)
        task["constraints"] = copy.deepcopy(applicable_constraints(state, tid))
        tasks.append(task)
    eligible = [t for t in tasks if not t["holds"] and t["readiness"] != "current"]
    relevant_goals = {t["goal_id"] for t in tasks}
    relevant_criteria = {c for t in tasks for c in t["criteria"]}
    scope_ids = set(selected) | relevant_goals
    constraint_ids = {c["id"] for c in state["constraints"].values() if scope_ids & set(c["applies_to"])}
    for correction in state["corrections"]:
        if correction["collection"] == "constraints" and any(
                isinstance(row, dict) and scope_ids & set(row["applies_to"])
                for row in (correction["before"], correction["after"])):
            constraint_ids.add(correction["target"])
    decisions = [d for d in state["decisions"].values() if set(d["affected"]) & set(selected)]
    targets = {"tasks": set(selected), "goals": relevant_goals, "criteria": relevant_criteria,
               "constraints": constraint_ids, "decisions": {d["id"] for d in decisions}}
    corrections = [c for c in state["corrections"]
                   if c["target"] in targets.get(c["collection"], set()) or c["collection"] == "location"]
    source_ids = set()
    scoped_rows = ([state["goals"][gid] for gid in relevant_goals] + tasks
                   + [state["constraints"][cid] for cid in sorted(constraint_ids)]
                   + [state["criteria"][cid] for cid in relevant_criteria]
                   + decisions)
    for correction in corrections:
        if correction["collection"] != "location":
            source_ids.update(correction["source_refs"])
            scoped_rows.extend(row for row in (correction["before"], correction["after"]) if isinstance(row, dict))
    for row in scoped_rows:
        source_ids.update(row["source_refs"])
        source_ids.update(row.get("resolution_sources", []))
    return {"schema": state["schema"], "project_id": state["project_id"], "revision": state["revision"],
            "source_identity": state["integrity"], "generated_at": now, "updated_at": state["updated_at"],
            "phase": state["phase"], "goals": copy.deepcopy([g for g in state["goals"].values() if g["id"] in relevant_goals]),
            "tasks": tasks, "decisions": copy.deepcopy(decisions),
            "constraints": copy.deepcopy([state["constraints"][cid] for cid in sorted(constraint_ids)]),
            "corrections": copy.deepcopy(corrections),
            "sources": {sid: dict({k: v for k, v in state["sources"][sid].items() if k != "excerpt"},
                                 timestamp=state["sources"][sid].get("timestamp"))
                        for sid in sorted(source_ids)},
            "attempts": [copy.deepcopy(dict(a, scope_status="available" if "scope" in a else "unavailable",
                                           applicability="current" if a["inputs"] == inputs(state, a["task_id"]) else "stale"))
                         for a in state["attempts"].values() if a["task_id"] in selected],
            "operations": copy.deepcopy([o for o in state["operations"].values() if o["task_id"] in selected]),
            "next_action": {"kind": "reevaluate" if eligible[0]["progress"] == "Code ready" else "work",
                            "task_id": eligible[0]["id"]} if eligible else
                           {"kind": "hold" if any(t["holds"] for t in tasks) else "review",
                            "reason": "No eligible implementation; inspect holds and acceptance separately"},
            "authority": "Reported sources are not authenticated grants; host permissions remain authoritative"}


def task_projection(state: dict) -> str:
    def cell(value):
        return value.replace("\n", " ").replace("\r", " ").replace("|", "\\|")
    rows = ["<!-- Generated from .architrave/state.yaml; read-only compatibility view. -->",
            "# Tasks", "", "| Task | Status |", "| --- | --- |"]
    for task in state["tasks"].values():
        rows.append(f"| {cell(task['title'])} ({task['id']}; {task['disposition']}) | {task['progress']} |")
    return "\n".join(rows) + "\n"


class StateStore:
    def __init__(self, repository: Path | str):
        self.root = Path(repository).resolve()
        self.path = self.root / ".architrave" / "state.yaml"
        self.lock = self.path.with_suffix(".lock")

    def _safe(self) -> None:
        for path in (self.path.parent, self.path, self.lock):
            if path.exists() or path.is_symlink():
                info = path.lstat()
                require(not path.is_symlink() and not getattr(info, "st_file_attributes", 0) & 0x400,
                        "PATH", "state directory/files cannot be links or reparse points")
                require(stat.S_ISDIR(info.st_mode) if path == self.path.parent else stat.S_ISREG(info.st_mode),
                        "PATH", "state paths must be regular files/directories")

    def selected(self) -> bool:
        return self.path.exists() or self.path.is_symlink()

    def _read(self) -> dict:
        self._safe()
        with self.path.open("rb") as handle:
            state = parse(handle.read(MAX_BYTES + 1))
        try:
            validate(state)
        except (KeyError, TypeError) as exc:
            raise StateError("SHAPE", "invalid nested lifecycle value") from exc
        for record in state["imports"]:
            if record["kind"] == "tasks":
                path = self.root / "tasks.md"
                raw = path.read_bytes()
                require(sha256_value(raw.decode("utf-8-sig")) in {record["digest"], *record["projections"]}
                        or raw == task_projection(state).encode(), "DUAL_WRITE",
                        "tasks.md changed outside the canonical store; reconcile explicitly, never import over state")
        return state

    def read(self) -> dict:
        self._safe()
        with FileLock(self.lock):
            return copy.deepcopy(self._read())

    def _write(self, state: dict) -> None:
        seal(state)
        validate(state)
        require(len(encode(state)) <= MAX_BYTES, "HISTORY_FULL", "snapshot bound reached; archive, do not prune live history")
        # Reuse the existing flushed same-filesystem replace, not RunStore's multi-file journal.
        RunStore(self.root)._atomic_write(self.path, state)

    def initialize(self, project_id: str, *, import_tasks: bool = False,
                   legacy_runs: list[str] = ()) -> dict:
        require(identifier(project_id), "IDENTITY", "invalid project ID")
        self._safe()
        with FileLock(self.lock):
            require(not self.selected(), "ALREADY_SELECTED", "state.yaml already selects the store")
            now = utc_now()
            state = dict(schema=SCHEMA, project_id=project_id, revision=0, location=location(self.root),
                         created_at=now, updated_at=now, phase="implementation", corrections=[],
                         receipts={}, imports=[], conflicts=[], integrity="")
            state.update({name: {} for name in COLLECTIONS})
            if import_tasks:
                from program_board import task_rows
                raw = (self.root / "tasks.md").read_text(encoding="utf-8-sig")
                rows = task_rows(raw)
                sid = "source-tasks-import"
                state["sources"][sid] = dict(id=sid, kind="document", reference="tasks.md",
                                             excerpt=raw, available=True)
                gid = "goal-imported"
                state["goals"][gid] = dict(id=gid, outcome="Imported task outcomes; acceptance not inferred",
                                           source_refs=[sid], disposition="active")
                mapping = {}
                for position, row in rows.items():
                    tid = "task-" + uuid.uuid5(uuid.NAMESPACE_URL, project_id + ":" + position + ":" + row["requirement"]).hex
                    mapping[position] = tid
                    state["tasks"][tid] = dict(id=tid, goal_id=gid, title=row["requirement"], source_refs=[sid],
                                               depends_on=[], criteria=[], progress={"not started": "", "started": "In progress",
                                               "code ready": "Code ready"}[row["status"]], disposition="active",
                                               activation="automatic", paths=[])
                    if row["status"] == "started":
                        state["conflicts"].append(dict(id=f"ownership-{tid}", affected=[tid],
                                                       reason="Imported In progress task has unknown host ownership",
                                                       resolution=None, source_refs=[]))
                state["imports"].append(dict(kind="tasks", digest=sha256_value(raw), mapping=mapping, projections=[]))
            for relative in legacy_runs:
                require(relative.startswith(".architrave/runs/") and ".." not in Path(relative).parts,
                        "PATH", "legacy import must name .architrave/runs/<id>")
                path = (self.root / relative).resolve()
                require(path.is_relative_to(self.root / ".architrave" / "runs"), "PATH", "legacy path escapes")
                legacy = RunStore(self.root).load(path.name)
                require(not any(t.get("lease") or t["status"] == "RUNNING" for t in legacy["tasks"])
                        and not any(w["status"] == "RUNNING" for w in legacy["workers"]),
                        "LIVE_MIGRATION", "reconcile active legacy workers before migration")
                cid = f"conflict-{len(state['conflicts']) + 1}"
                state["imports"].append(dict(kind="legacy", path=relative, state=legacy))
                state["conflicts"].append(dict(id=cid, affected=[], reason="Selected legacy state requires explicit authority reconciliation",
                                               resolution=None, source_refs=[]))
            self._write(state)
            return copy.deepcopy(state)

    def apply(self, command: dict, *, worker: str | None = None) -> dict:
        keys(command, {"project_id", "command_id", "expected_revision", "operation", "payload"})
        require(identifier(command["command_id"]) and type(command["expected_revision"]) is int,
                "COMMAND", "command needs stable ID and integer expected revision")
        digest = sha256_value(command)
        self._safe()
        with FileLock(self.lock):
            state = self._read()
            require(command["project_id"] == state["project_id"], "PROJECT", "wrong project")
            old = state["receipts"].get(command["command_id"])
            if old:
                require(old["digest"] == digest and old["worker"] == worker, "IDEMPOTENCY_CONFLICT",
                        "command ID reused with another payload or caller")
                return copy.deepcopy(old)
            require(command["expected_revision"] == state["revision"], "STALE_REVISION",
                    f"expected {command['expected_revision']}, current {state['revision']}")
            require(len(state["receipts"]) < MAX_RECEIPTS, "HISTORY_FULL", "archive whole reconciled project; receipts are never silently pruned")
            require(state["location"] == location(self.root) or command["operation"] == "reconcile_location",
                    "LOCATION_RECONCILIATION", "state moved; reconcile ownership before writing")
            try:
                for record in state["imports"]:
                    if record["kind"] == "tasks":
                        digest_projection = sha256_value(task_projection(state))
                        if digest_projection not in record["projections"]:
                            record["projections"].append(digest_projection)
                result = self._transition(state, command["operation"], command["payload"], worker)
                state["revision"] += 1
                state["updated_at"] = utc_now()
                receipt = dict(digest=digest, revision=state["revision"], result=result, worker=worker)
                state["receipts"][command["command_id"]] = receipt
                self._write(state)
            except (KeyError, TypeError) as exc:
                raise StateError("SHAPE", "invalid command field type or nested value; no replacement performed") from exc
            return copy.deepcopy(receipt)

    def _transition(self, s: dict, op: str, p: dict, worker: str | None) -> dict:
        require(isinstance(p, dict), "COMMAND", "payload must be a mapping")
        if worker is not None:
            require(op in {"observe_attempt", "record_result", "record_evidence"}, "ROLE", "worker cannot revise intent or grant authority")
        def source_refs(values):
            refs(s, values, "sources")
            require(bool(values), "SOURCE", "source references required")
        def owner_sources(values):
            source_refs(values)
            require(any(s["sources"][v]["kind"] == "owner" and s["sources"][v]["available"] for v in values),
                    "OWNER_SOURCE", "scope removal/activation needs available original owner direction")
        def attempt(aid):
            require(aid in s["attempts"], "REFERENCE", "unknown attempt")
            row = s["attempts"][aid]
            require(worker is None or row["worker"] == worker, "ROLE", "attempt belongs to another worker")
            return row
        if op == "record_source":
            keys(p, FIELDS["sources"], {"timestamp"})
            require(p["id"] not in s["sources"], "IMMUTABLE_SOURCE", "retain original; add a new source for corrections")
            s["sources"][p["id"]] = copy.deepcopy(p)
        elif op == "observe_source":
            keys(p, {"id", "available"})
            require(p["id"] in s["sources"] and type(p["available"]) is bool, "SOURCE", "invalid source observation")
            s["sources"][p["id"]]["available"] = p["available"]
        elif op == "record_request":
            keys(p, {"goal", "tasks", "criteria", "constraints"})
            for collection, rows in (("goals", [p["goal"]]), ("tasks", p["tasks"]),
                                     ("criteria", p["criteria"]), ("constraints", p["constraints"])):
                require(isinstance(rows, list), "SHAPE", "request collections must be lists")
                for row in rows:
                    keys(row, FIELDS[collection])
                    if collection == "goals" and row["id"] in s["goals"]:
                        require(row == s["goals"][row["id"]], "IDENTITY", "use a sourced correction to revise existing goal")
                        continue
                    require(identifier(row["id"]) and row["id"] not in s[collection], "IDENTITY", "entity already exists")
                    source_refs(row["source_refs"])
                    if row.get("disposition") == "active":
                        owner_sources(row["source_refs"])
                    s[collection][row["id"]] = copy.deepcopy(row)
        elif op == "add_criterion":
            keys(p, FIELDS["criteria"])
            require(p["id"] not in s["criteria"] and p["task_id"] in s["tasks"], "REFERENCE", "invalid criterion/task")
            source_refs(p["source_refs"])
            s["criteria"][p["id"]] = copy.deepcopy(p)
            s["tasks"][p["task_id"]]["criteria"].append(p["id"])
        elif op == "apply_correction":
            keys(p, {"collection", "target", "changes", "source_refs", "kind"})
            collection = p["collection"]
            require(collection in {"goals", "tasks", "constraints", "criteria"}, "CORRECTION", "invalid correction target")
            require(p["target"] in s[collection], "REFERENCE", "unknown correction target")
            source_refs(p["source_refs"])
            require(p["kind"] in {"revise", "defer", "cancel", "retire", "activate", "reorder"}, "CORRECTION", "invalid change kind")
            row = s[collection][p["target"]]
            allowed = FIELDS[collection] - {"id", "goal_id", "task_id", "progress"}
            require(isinstance(p["changes"], dict) and bool(p["changes"]) and p["changes"].keys() <= allowed,
                    "CORRECTION", "unsupported correction fields")
            owner_sources(p["source_refs"])
            before = copy.deepcopy(row)
            row.update(copy.deepcopy(p["changes"]))
            row["source_refs"] = list(dict.fromkeys(row["source_refs"] + p["source_refs"]))
            s["corrections"].append(dict(collection=collection, target=p["target"], kind=p["kind"],
                                         before=before, after=copy.deepcopy(row), source_refs=p["source_refs"],
                                         revision=s["revision"] + 1))
        elif op == "record_question":
            keys(p, FIELDS["decisions"])
            require(p["id"] not in s["decisions"] and p["resolution"] is None and not p["resolution_sources"],
                    "DECISION", "new decision must be unresolved")
            s["decisions"][p["id"]] = copy.deepcopy(p)
        elif op == "resolve_decision":
            keys(p, {"id", "resolution", "source_refs"})
            require(p["id"] in s["decisions"] and text(p["resolution"]), "DECISION", "unknown decision or empty answer")
            owner_sources(p["source_refs"])
            row = s["decisions"][p["id"]]
            require(row["resolution"] is None and not row.get("superseded_by"),
                    "DECISION", "resolved/superseded decisions are immutable; record a superseding decision")
            before = copy.deepcopy(row)
            row.update(resolution=p["resolution"], resolution_sources=p["source_refs"])
            s["corrections"].append(dict(collection="decisions", target=row["id"], kind="resolve",
                                         before=before, after=copy.deepcopy(row), source_refs=p["source_refs"],
                                         revision=s["revision"] + 1))
        elif op == "supersede_decision":
            keys(p, {"id", "replacement", "source_refs"})
            owner_sources(p["source_refs"])
            require(p["id"] in s["decisions"] and p["replacement"] in s["decisions"]
                    and p["id"] != p["replacement"], "DECISION", "unknown supersession target")
            old, new = s["decisions"][p["id"]], s["decisions"][p["replacement"]]
            require(not old.get("superseded_by") and not new.get("superseded_by")
                    and old["affected"] == new["affected"], "DECISION", "supersession must preserve affected scope")
            before = copy.deepcopy(old)
            old["superseded_by"] = new["id"]
            s["corrections"].append(dict(collection="decisions", target=old["id"], kind="supersede",
                                         before=before, after=copy.deepcopy(new), source_refs=p["source_refs"],
                                         revision=s["revision"] + 1))
        elif op == "record_progress":
            keys(p, {"task_id", "progress"})
            require(p["task_id"] in s["tasks"], "REFERENCE", "unknown task")
            require(not any(a["task_id"] == p["task_id"] and a["activity"] not in TERMINAL
                            for a in s["attempts"].values()), "OWNERSHIP", "progress belongs to live attempt")
            s["tasks"][p["task_id"]]["progress"] = p["progress"]
            if p["progress"] == "Code ready":
                s["tasks"][p["task_id"]]["ready_inputs"] = inputs(s, p["task_id"])
        elif op == "claim_task":
            keys(p, {"id", "task_id", "worker", "host"}, {"read_only"})
            require(p["id"] not in s["attempts"] and p["task_id"] in s["tasks"], "REFERENCE", "invalid attempt/task")
            read_only = p.get("read_only", False)
            require(type(read_only) is bool, "SCOPE", "read_only must be explicit boolean")
            paths = copy.deepcopy(s["tasks"][p["task_id"]]["paths"])
            require(read_only or bool(paths), "SCOPE", "mutable claim needs known nonempty paths; use read_only for reviews")
            blockers = holds(s, p["task_id"], read_only=read_only)
            require(not blockers, "HELD", "; ".join(blockers))
            s["attempts"][p["id"]] = dict(id=p["id"], task_id=p["task_id"], worker=p["worker"], host=p["host"],
                                          scope=dict(mode="read_only" if read_only else "mutable", paths=paths),
                                          inputs=inputs(s, p["task_id"]), activity="unknown",
                                          stop="none", observation=None, result=None, integrated=False)
            if not read_only:
                s["tasks"][p["task_id"]]["progress"] = "In progress"
        elif op == "request_stop":
            keys(p, {"attempt_id"})
            row = attempt(p["attempt_id"])
            require(row["activity"] not in TERMINAL, "TERMINAL", "attempt already terminal")
            row["stop"] = "requested"
        elif op == "observe_attempt":
            keys(p, {"attempt_id", "activity", "stop_acknowledged", "reference", "observed_at"})
            row = attempt(p["attempt_id"])
            require(text(p["reference"]) and timestamp(p["observed_at"]) and type(p["stop_acknowledged"]) is bool,
                    "OBSERVATION", "host observation requires identity and time")
            require(row["activity"] not in TERMINAL or row["activity"] == p["activity"],
                    "TERMINAL", "terminal observation cannot be undone")
            if p["stop_acknowledged"]:
                require(row["stop"] != "none", "STOP", "stop was not requested")
                row["stop"] = "acknowledged"
            row["activity"] = p["activity"]
            row["observation"] = dict(reference=p["reference"], observed_at=p["observed_at"])
        elif op == "record_result":
            keys(p, {"attempt_id", "artifact", "summary", "identity"})
            row = attempt(p["attempt_id"])
            require(text(p["artifact"]) and text(p["summary"]), "RESULT", "result needs artifact and summary")
            validate_identity(p["identity"])
            require(p["identity"]["candidate"] == p["artifact"], "IDENTITY", "reported candidate differs from result artifact")
            result = dict(artifact=p["artifact"], summary=p["summary"], identity=copy.deepcopy(p["identity"]))
            require(row["result"] is None or row["result"] == result, "RESULT_CONFLICT", "attempt result is immutable")
            row["result"] = result
        elif op == "integrate_candidate":
            keys(p, {"attempt_id", "operation_id", "checks"})
            row = attempt(p["attempt_id"])
            require(row["activity"] == "completed" and row["result"] is not None and not row["integrated"],
                    "RESULT", "requires completed, unintegrated result")
            require("identity" in row["result"], "IDENTITY_UNAVAILABLE", "legacy result has no checked candidate identity")
            require(row["inputs"] == inputs(s, row["task_id"]), "STALE_INPUTS", "candidate retained but no longer applicable")
            require(not holds(s, row["task_id"]), "HELD", "; ".join(holds(s, row["task_id"])))
            refs(s, p["checks"], "evidence")
            require(bool(p["checks"]) and all(s["evidence"][eid]["result"] == "pass"
                    and s["criteria"][s["evidence"][eid]["criterion_id"]]["task_id"] == row["task_id"]
                    and evidence_applicability(s, s["evidence"][eid]) == "current"
                    and s["evidence"][eid].get("attempt_id") == row["id"]
                    and s["evidence"][eid].get("identity") == row["result"]["identity"]
                    for eid in p["checks"]), "CHECKS", "integration needs current passing checks for this exact attempt/candidate")
            operation = s["operations"].get(p["operation_id"])
            require(operation is not None and operation["attempt_id"] == row["id"]
                    and operation["outcome"] == "succeeded" and operation["action"] == "integrate"
                    and operation["inputs"] == row["inputs"] and operation["artifact"] == row["result"]["artifact"]
                    and operation.get("identity") == row["result"]["identity"]
                    and isinstance(operation["observation"], dict)
                    and operation["observation"].get("identity") == row["result"]["identity"],
                    "OPERATION", "record observed integration separately; this command never mutates git")
            row["integrated"] = True
            s["tasks"][row["task_id"]]["progress"] = "Code ready"
            s["tasks"][row["task_id"]]["ready_inputs"] = inputs(s, row["task_id"])
        elif op == "record_evidence":
            keys(p, FIELDS["evidence"] | {"identity"}, {"attempt_id"})
            require(p["criterion_id"] in s["criteria"] and p["id"] not in s["evidence"], "REFERENCE", "invalid criterion/evidence")
            validate_identity(p["identity"])
            if "attempt_id" in p:
                attempt(p["attempt_id"])
            if worker is not None:
                tid = s["criteria"][p["criterion_id"]]["task_id"]
                require(any(a["worker"] == worker and a["task_id"] == tid for a in s["attempts"].values()),
                        "ROLE", "evidence not assigned to worker")
            s["evidence"][p["id"]] = copy.deepcopy(p)
        elif op == "record_operation":
            keys(p, {"id", "attempt_id", "target", "action", "grant_ref", "artifact"}, {"identity"})
            row = attempt(p["attempt_id"])
            require(p["id"] not in s["operations"], "IDENTITY", "operation identity already exists")
            require(row["inputs"] == inputs(s, row["task_id"]), "STALE_INPUTS", "operation inputs changed")
            require(row["stop"] == "none", "STOP", "stop requested; no new external operation")
            require(row.get("scope") is not None, "SCOPE_UNAVAILABLE", "legacy assigned scope is unknown; reconcile before mutation")
            require(row["scope"]["mode"] == "mutable", "READ_ONLY", "read-only attempts cannot record external mutation")
            if "identity" in p:
                validate_identity(p["identity"])
            if p["action"] == "integrate":
                require(row["activity"] == "completed" and row["result"] is not None
                        and row["result"]["artifact"] == p["artifact"]
                        and "identity" in row["result"] and p.get("identity") == row["result"]["identity"], "RESULT",
                        "integration intention must bind the actual completed candidate")
            require(not any(o["target"] == p["target"]
                            and o["outcome"] in {"intended", "unknown"} for o in s["operations"].values()),
                    "RECONCILE_FIRST", "uncertain target operation exists; inspect target before retry")
            blockers = holds(s, row["task_id"], ignore_attempt=row["id"])
            require(not blockers, "HELD", "; ".join(blockers))
            s["operations"][p["id"]] = dict(**p, task_id=row["task_id"], inputs=row["inputs"],
                                             outcome="intended", observation=None, reconciled=False)
        elif op == "observe_operation":
            keys(p, {"id", "outcome", "reference", "observed_at", "reconciliation"}, {"identity"})
            require(p["id"] in s["operations"] and p["outcome"] in {"unknown", "succeeded", "failed"}
                    and text(p["reference"]) and timestamp(p["observed_at"]) and type(p["reconciliation"]) is bool,
                    "OPERATION", "invalid observation")
            row = s["operations"][p["id"]]
            if "identity" in p:
                validate_identity(p["identity"])
            if row["action"] == "integrate" and p["outcome"] == "succeeded":
                require("identity" in p, "IDENTITY_UNAVAILABLE", "successful integration must report the observed candidate identity")
            require(row["outcome"] not in {"succeeded", "failed"}, "TERMINAL", "operation already terminal")
            require(row["outcome"] != "unknown" or p["outcome"] == "unknown" or p["reconciliation"],
                    "RECONCILE_FIRST", "unknown outcome requires target reconciliation")
            row.update(outcome=p["outcome"], reconciled=p["reconciliation"],
                       observation=dict(reference=p["reference"], observed_at=p["observed_at"]))
            if "identity" in p:
                row["observation"]["identity"] = copy.deepcopy(p["identity"])
        elif op == "resolve_import":
            keys(p, {"id", "resolution", "source_refs"})
            owner_sources(p["source_refs"])
            require(text(p["resolution"]), "IMPORT", "resolution required")
            matches = [c for c in s["conflicts"] if c["id"] == p["id"] and c["resolution"] is None]
            require(len(matches) == 1, "IMPORT", "unknown/resolved conflict")
            matches[0].update(resolution=p["resolution"], source_refs=p["source_refs"])
        elif op == "set_phase":
            keys(p, {"phase"})
            s["phase"] = p["phase"]
        elif op == "reconcile_location":
            keys(p, {"reference"}, {"read_only_observations"})
            observations = p.get("read_only_observations", [])
            require(isinstance(observations, list) and len(observations) <= len(s["attempts"]),
                    "OBSERVATION", "invalid read-only reconciliation observations")
            seen = set()
            for observation in observations:
                keys(observation, {"attempt_id", "activity", "reference", "observed_at"})
                aid = observation["attempt_id"]
                require(aid in s["attempts"] and aid not in seen, "REFERENCE", "unknown/duplicate recovery attempt")
                seen.add(aid)
                row = s["attempts"][aid]
                require(row.get("scope", {}).get("mode") == "read_only"
                        and observation["activity"] in TERMINAL and text(observation["reference"])
                        and timestamp(observation["observed_at"])
                        and (row["activity"] not in TERMINAL or row["activity"] == observation["activity"]),
                        "OWNERSHIP", "only source-backed terminal read-only observations can accompany a handoff")
                row["activity"] = observation["activity"]
                row["observation"] = dict(reference=observation["reference"], observed_at=observation["observed_at"])
            require(text(p["reference"]) and all(a["activity"] in TERMINAL for a in s["attempts"].values())
                    and all(o["outcome"] not in {"intended", "unknown"} for o in s["operations"].values()),
                    "OWNERSHIP", "reconcile live owners/uncertain operations on original host before handoff")
            s["corrections"].append(dict(collection="location", target=s["project_id"], kind="handoff",
                                         before=s["location"], after=location(self.root), source_refs=[p["reference"]],
                                         revision=s["revision"] + 1))
            s["location"] = location(self.root)
        else:
            raise StateError("OPERATION", f"unknown operation {op}")
        return {"operation": op}


def cli(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    sub = parser.add_subparsers(dest="action", required=True)
    init = sub.add_parser("init")
    init.add_argument("--project", required=True)
    init.add_argument("--import-tasks", action="store_true")
    init.add_argument("--legacy-run", action="append", default=[])
    apply = sub.add_parser("apply")
    apply.add_argument("--command", required=True, help="restricted YAML/JSON command file, or - for stdin")
    apply.add_argument("--worker", help="restrict operations to this worker; not an authentication boundary")
    for name in ("snapshot", "context"):
        read = sub.add_parser(name)
        read.add_argument("--tasks", help="comma-separated stable task IDs")
        read.add_argument("--now", help="injected UTC clock for reproducibility")
    source = sub.add_parser("source", help="retrieve an original only when needed")
    source.add_argument("--id", required=True)
    sub.add_parser("export-tasks")
    args = parser.parse_args(argv)
    try:
        store = StateStore(args.repo)
        if args.action == "init":
            result = store.initialize(args.project, import_tasks=args.import_tasks, legacy_runs=args.legacy_run)
        elif args.action == "apply":
            raw = sys.stdin.buffer.read(MAX_BYTES + 1) if args.command == "-" else Path(args.command).read_bytes()
            result = store.apply(parse(raw), worker=args.worker)
        elif args.action == "export-tasks":
            print(task_projection(store.read()), end="")
            return 0
        elif args.action == "source":
            state = store.read()
            require(args.id in state["sources"], "REFERENCE", "unknown source")
            result = state["sources"][args.id]
        else:
            result = snapshot(store.read(), now=args.now or utc_now(),
                              task_ids=args.tasks.split(",") if args.tasks else None)
        print(encode(result).decode(), end="")
        return 0
    except (OSError, ValueError, RuntimeFailure) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli())
