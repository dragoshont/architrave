#!/usr/bin/env python3
"""Source-bound completion checks for declared host work, not a second task ledger.

Local logs/artifacts and reviewer declarations are evidence, not tamper-proof
attestations. Provider-specific meaning remains an independent review obligation.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlparse

import delivery_audit as audit
import gate_runner as gate

SCHEMA = "architrave.delivery.v1"
MAX_JSON = 16 * 1024 * 1024


def session_report_path(session_id: str) -> Path:
    if not isinstance(session_id, str) or not gate.SESSION_UUID.fullmatch(session_id.lower()):
        raise ValueError("a host session UUID is required")
    return gate.session_home() / session_id.lower() / "files" / "architrave-delivery.json"


def file_identity(path: Path) -> dict:
    path = path.expanduser().absolute()
    if path.is_symlink() or any(
        p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction())
        for p in (path, *path.parents)
    ):
        raise ValueError("linked evidence paths are not supported")
    if not path.is_file():
        raise ValueError(f"evidence file missing: {path.name}")
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    return {"path": str(path), "sha256": h.hexdigest()}


def verify_file(value: object) -> None:
    if not isinstance(value, dict) or not isinstance(value.get("path"), str):
        raise ValueError("evidence needs a path and SHA256")
    if not Path(value["path"]).is_absolute():
        raise ValueError("evidence paths must be absolute")
    if not isinstance(value.get("sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", value["sha256"]):
        raise ValueError("evidence SHA256 is missing/invalid")
    if file_identity(Path(value["path"])) != {"path": value["path"], "sha256": value["sha256"]}:
        raise ValueError("evidence identity changed")


def read_json(path: Path) -> dict:
    file_identity(path)
    if path.stat().st_size > MAX_JSON:
        raise ValueError("delivery JSON exceeds the supported size")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("delivery JSON must be an object")
    return value


def events(session_id: str) -> list[dict]:
    path = session_report_path(session_id).parents[1] / "events.jsonl"
    file_identity(path)
    result = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue  # Concurrent trailing log fragments do not become evidence.
            if isinstance(item, dict) and isinstance(item.get("data"), dict):
                result.append(item)
    return result


def timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("observation timestamp is missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("observation timestamp has no timezone")
    return parsed


def host_completed(report: dict, log: list[dict]) -> bool:
    if report.get("schema") != SCHEMA or report.get("state") != "sealed" or not report.get("sealed_at"):
        return False
    sealed = timestamp(report["sealed_at"])
    terminal = any(e.get("type") == "session.task_complete"
                   and timestamp(e.get("timestamp")) > sealed for e in log)
    # Merely backdating an unfinished declaration cannot retire it.
    return terminal and not review_errors(report)


def declared_for(root: Path, session_id: str) -> bool:
    path = session_report_path(session_id)
    if not path.exists():
        return False
    report = read_json(path)
    return Path(report["repo"]).resolve() == repository_root(root)


def repository_root(path: Path) -> Path:
    return Path(audit.git(path.resolve(), "rev-parse", "--show-toplevel").decode().strip()).resolve()


def owner_reference(event_id: str, log: list[dict]) -> dict:
    matches = [e for e in log if e.get("id") == event_id]
    if len(matches) != 1:
        raise ValueError("original owner event is absent or ambiguous")
    event = matches[0]
    data = event["data"]
    content = data.get("content")
    if (event.get("type") != "user.message" or event.get("agentId")
            or data.get("parentToolCallId") or data.get("source") not in (None, "", "user", "human")
            or not isinstance(content, str) or not content.strip()
            or any(marker in (content + str(data.get("transformedContent", ""))).lower()
                   for marker in ("<cross_session_message", "<system_notification", "<system_reminder"))
            or content.startswith("You have not yet marked the task as complete")):
        raise ValueError("event is not an attributable original owner instruction")
    value = {k: event.get(k) for k in ("id", "timestamp", "type")}
    value["data"] = {k: data.get(k) for k in ("content", "source", "attachments")}
    attachments = []
    for item in data.get("attachments") or []:
        if not isinstance(item, dict) or item.get("type") != "file" or not isinstance(item.get("path"), str):
            raise ValueError("owner attachment cannot be bound to a local file")
        attachments.append(file_identity(Path(item["path"])))
    return {"event_id": event_id, "sha256": audit.digest(value), "attachments": attachments}


def tool_evidence(call_id: str, log: list[dict], *, success: bool = True) -> tuple[dict, dict]:
    if not isinstance(call_id, str) or not call_id.strip():
        raise ValueError("tool observation needs a nonempty call identity")
    starts = [e for e in log if e.get("type") == "tool.execution_start"
              and e["data"].get("toolCallId") == call_id]
    ends = [e for e in log if e.get("type") == "tool.execution_complete"
            and e["data"].get("toolCallId") == call_id]
    if len(starts) != 1 or len(ends) != 1 or ends[0]["data"].get("success") is not success:
        raise ValueError("tool observation missing, ambiguous or unsuccessful")
    return starts[0], ends[0]


def strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for child in value.values() for s in strings(child)]
    if isinstance(value, list):
        return [s for child in value for s in strings(child)]
    return []


def child_session(session_id: str, log: list[dict]) -> bool:
    for event in log:
        data = event["data"]
        if (event.get("type") == "tool.execution_start"
                and data.get("toolName") in {"create_session", "open_pr_session", "open_issue_session", "fork_session"}):
            try:
                _, result = tool_evidence(data.get("toolCallId"), log)
            except ValueError:
                continue
            if re.search(r"\b" + re.escape(session_id) + r"\b",
                         " ".join(strings(result["data"].get("result")))):
                return True
    return False


def first_source_edit(root: Path, log: list[dict], after: datetime) -> datetime | None:
    config = gate.load_config(root) if (root / "architrave.config.json").exists() else {}
    ledger = (root / config.get("requirements", "SPEC.md")).resolve()
    edits = []
    for event in log:
        data = event["data"]
        if event.get("type") != "tool.execution_start" or data.get("toolName") not in {"apply_patch", "edit", "create"}:
            continue
        when = timestamp(event.get("timestamp"))
        if when < after:
            continue
        args = data.get("arguments")
        paths = []
        if data["toolName"] == "apply_patch":
            raw = args if isinstance(args, str) else (args or {}).get("patch", "")
            paths = re.findall(r"(?m)^\*\*\* (?:Add|Update|Delete) File: (.+)$", raw)
        elif isinstance(args, dict) and isinstance(args.get("path"), str):
            paths = [args["path"]]
        for value in paths:
            path = (root / value).resolve()
            if path != ledger and path.is_relative_to(root):
                edits.append(when)
    return min(edits) if edits else None

def observation_errors(expected: dict, observed: object) -> list[str]:
    """Relational checks, not a claim that arbitrary adapter prose is authentic."""
    if not isinstance(observed, dict):
        return ["required outcome has no observation"]
    errors = []
    if observed.get("kind") != expected.get("kind") or observed.get("outcome") != "passed":
        errors.append("observed kind/outcome does not satisfy the required outcome")
    kind = expected.get("kind")
    if kind == "integration":
        for key in ("entrypoint", "provider", "target"):
            if not isinstance(expected.get(key), str) or not expected[key].strip():
                errors.append(f"required integration {key} is missing")
            elif observed.get(key) != expected[key]:
                errors.append(f"integration {key} differs from the original expectation")
        if observed.get("enabled") is not True or observed.get("provider_invoked") is not True:
            errors.append("required integration was disabled or not invoked")
        if observed.get("result_mode") != "fresh":
            errors.append("substitute/replayed/readback output is not fresh execution")
        run = observed.get("run_id")
        if not isinstance(run, str) or not run.strip() or any(
            observed.get(key) != run for key in ("provider_run_id", "result_run_id")
        ):
            errors.append("entrypoint, provider and result must join to the same run")
        try:
            verify_file(observed.get("effective_config"))
        except (ValueError, OSError) as exc:
            errors.append(f"effective configuration is not bound: {exc}")
    elif kind == "visual":
        if (not observed.get("consumer") or not isinstance(observed.get("width"), int)
                or isinstance(observed.get("width"), bool) or observed["width"] <= 0):
            errors.append("rendered consumer and actual width are required")
        if observed.get("rendered") is not True or observed.get("reference_compared") is not True:
            errors.append("source/XML/asset counts do not prove rendered-reference acceptance")
        if observed.get("coverage_checked") is not True:
            errors.append("component/content coverage is not established by image counts")
        for key in ("consumer", "width"):
            if key in expected and observed.get(key) != expected[key]:
                errors.append(f"visual {key} differs from the intended reading surface")
    elif kind != "source":
        errors.append("unknown outcome kind; use source, integration or visual")
    return errors


def board_errors(value: object, report: dict, log: list[dict]) -> list[str]:
    if not isinstance(value, dict):
        return ["non-trivial work requires an opened and observed scoped board"]
    try:
        cutoff = max(timestamp(e.get("timestamp")) for e in log
                     if e.get("id") in {r["event_id"] for r in report["owner_requests"]})
        if value.get("unavailable") is True:
            if not isinstance(value.get("reason"), str) or not value["reason"].strip():
                raise ValueError("unavailable board needs its explicit reason")
            if value.get("displayed") is not False:
                raise ValueError("unavailable board cannot claim displayed success")
            if value.get("basis") == "host-tool-absent":
                # Absence cannot be proved by calling a nonexistent tool. This
                # is an explicit limitation covered by the mandatory digest-bound
                # review, not a machine-verified display or a permission grant.
                if not isinstance(value.get("capability_observation"), str) or not value["capability_observation"].strip():
                    raise ValueError("host-tool absence needs its reported capability observation")
                return []
            failed, _ = tool_evidence(value["tool_error_call_id"], log, success=False)
            if failed["data"].get("toolName") not in {"open_canvas", "list_canvas_capabilities"}:
                raise ValueError("board unavailability must be a failed canvas capability/open observation")
            if timestamp(failed.get("timestamp")) < cutoff:
                raise ValueError("board unavailability predates the current owner scope")
            return []
        opened, _ = tool_evidence(value["open_call_id"], log)
        read, result = tool_evidence(value["read_call_id"], log)
        oa, ra = opened["data"].get("arguments"), read["data"].get("arguments")
        if (opened["data"].get("toolName") != "open_canvas"
                or read["data"].get("toolName") != "invoke_canvas_action"
                or not isinstance(oa, dict) or not isinstance(ra, dict)
                or oa.get("canvasId") != "browser" or ra.get("actionName") != "read_page"
                or oa.get("instanceId") != ra.get("instanceId")):
            raise ValueError("board needs matching successful browser open/read calls")
        url = urlparse((oa.get("input") or {}).get("url", ""))
        if url.scheme != "file" or url.netloc not in ("", "localhost"):
            raise ValueError("board observation currently supports local file browser canvases only")
        native = unquote(url.path)
        if os.name == "nt" and re.match(r"^/[A-Za-z]:", native):
            native = native[1:]
        path = Path(native).resolve()
        expected = session_report_path(report["session_id"]).parent / "program-board.html"
        if path != expected.resolve():
            raise ValueError("board path does not belong to this session")
        text = path.read_text(encoding="utf-8")
        observed = json.dumps(result["data"].get("result", {}), ensure_ascii=False)
        if any(not re.search(r"\b" + re.escape(rid) + r"\b", text)
               or not re.search(r"\b" + re.escape(rid) + r"\b", observed) for rid in report["reqs"]):
            raise ValueError("board scope/observation does not cover this task's requirements")
        _, read_end = tool_evidence(value["read_call_id"], log)
        opened_at = timestamp(opened.get("timestamp"))
        read_at = timestamp(read_end.get("timestamp"))
        if opened_at > timestamp(read.get("timestamp")):
            raise ValueError("board read precedes open")
        if opened_at < cutoff:
            raise ValueError("board observation predates the current owner scope")
        first_edit = first_source_edit(Path(report["repo"]), log, cutoff)
        if first_edit is not None and read_at > first_edit:
            raise ValueError("board was not observed before the first recorded source edit")
        if report.get("sealed_at") and read_at > timestamp(report["sealed_at"]):
            raise ValueError("board startup occurred after source was sealed")
    except (ValueError, KeyError, TypeError, OSError) as exc:
        return [f"board: {exc}"]
    return []


def report_digest(report: dict) -> str:
    return audit.digest({k: v for k, v in report.items() if k != "review"})


def review_errors(report: dict) -> list[str]:
    review = report.get("review")
    if not isinstance(review, dict) or not isinstance(review.get("session_id"), str):
        return ["independent delivery review is missing"]
    if review["session_id"] == report["session_id"]:
        return ["delivery reviewer must differ from the implementing session"]
    sha = report_digest(report)
    if review.get("sha256") != sha:
        return ["review binds different delivery bytes"]
    verified, reason = gate.review_session(review["session_id"], "PASS")
    if verified != "verified":
        return [f"review is not verified: {reason or verified}"]
    try:
        log = events(review["session_id"])
    except (ValueError, OSError) as exc:
        return [f"review log unavailable: {exc}"]
    pattern = re.compile(r"(?m)^\s*Delivery digest:\s*" + re.escape(sha) + r"\s*$")
    for event in log:
        data = event["data"]
        if event.get("type") == "session.task_complete":
            text = data.get("summary", "")
        elif event.get("type") == "tool.execution_start" and data.get("toolName") == "send_session_message":
            text = (data.get("arguments") or {}).get("message", "")
        else:
            continue
        if isinstance(text, str) and gate.ruling(text) == "PASS" and pattern.search(text):
            return []
    return ["reviewer's actual report does not bind this delivery digest"]


def check_report(root: Path, report: dict, *, require_review: bool = True) -> list[str]:
    errors = []
    try:
        if report.get("schema") != SCHEMA or Path(report["repo"]).resolve() != root.resolve():
            raise ValueError("delivery schema/repository identity differs")
        session_id = report["session_id"]
        session_report_path(session_id)
        if report.get("state") != "sealed":
            errors.append("delivery is not sealed")
        reqs = report.get("reqs")
        if not isinstance(reqs, list) or not reqs or not all(isinstance(r, str) for r in reqs):
            raise ValueError("explicit delivery requirement scope is missing")
        current = audit.scan(root, base=report["base_sha"], all_files=bool(report.get("all_files")),
                             documents=report.get("document_paths"), reqs=reqs)
        if current["requirements"] != report.get("original_requirements"):
            errors.append("requirements/acceptance changed since owner-bound intake; explicitly re-declare corrections")
        if not isinstance(report.get("audit"), dict) or current["source_sha256"] != report["audit"].get("source_sha256"):
            errors.append("source/config/document inventory changed since delivery capture")
        log = events(session_id)
        owners = report.get("owner_requests")
        if not isinstance(owners, list) or not owners:
            raise ValueError("original owner references are missing")
        for reference in owners:
            if owner_reference(reference["event_id"], log) != reference:
                errors.append("original owner reference or attachment changed")
        owner_times = [timestamp(e.get("timestamp")) for e in log
                       if e.get("id") in {r["event_id"] for r in owners}]
        owner_cutoff = max(owner_times)
        for reference in report.get("references", []):
            verify_file(reference)
        errors.extend(board_errors(report.get("board"), report, log))
        findings = {r["id"]: r for r in current["findings"]}
        dispositions = report.get("dispositions", {})
        if not isinstance(dispositions, dict) or set(dispositions) != set(findings):
            errors.append("every current candidate needs a disposition; unknown/stale candidates are not accepted")
        else:
            for key, row in dispositions.items():
                if (not isinstance(row, dict) or row.get("decision") not in
                        {"existing", "not-substitute", "owner-requested"}
                        or any(not isinstance(row.get(k), str) or not row[k].strip()
                               for k in ("purpose", "reachability", "effective_state", "reason"))):
                    errors.append("candidate has unresolved purpose/reachability/effective state")
                elif row["decision"] == "owner-requested" and row.get("owner_event_id") not in {
                    r["event_id"] for r in owners
                }:
                    errors.append("candidate permission is not bound to an original owner reference")
        expected = report.get("expected", {})
        observations = report.get("observations", {})
        if not isinstance(expected, dict) or set(expected) != set(reqs):
            errors.append("every requirement needs an explicit expected outcome")
        elif not isinstance(observations, dict) or set(observations) != set(reqs):
            errors.append("every requirement needs an outcome observation")
        else:
            for rid in reqs:
                if not isinstance(expected[rid], dict):
                    errors.append(f"{rid}: malformed expected outcome")
                    continue
                errors.extend(f"{rid}: {error}" for error in observation_errors(expected[rid], observations[rid]))
                if expected[rid].get("kind") == "visual" and expected[rid].get("reference_required") is True:
                    if not report.get("references") and not any(r.get("attachments") for r in owners):
                        errors.append(f"{rid}: requested visual reference is not preserved")
                row = observations[rid]
                if not isinstance(row, dict):
                    continue
                try:
                    proof = row.get("proof")
                    verify_file(proof)
                    observed_sid = row.get("session_id", session_id)
                    if observed_sid != session_id and not child_session(observed_sid, log):
                        raise ValueError("observation is neither this session nor a recorded child")
                    observed_log = log if observed_sid == session_id else events(observed_sid)
                    start, end = tool_evidence(row["tool_call_id"], observed_log)
                    if timestamp(start.get("timestamp")) < owner_cutoff:
                        errors.append(f"{rid}: earlier tool results cannot establish this task's fresh acceptance")
                    if timestamp(end.get("timestamp")) < timestamp(start.get("timestamp")):
                        errors.append(f"{rid}: observation ends before its invocation")
                    output = " ".join(strings(end["data"].get("result")))
                    if proof["sha256"].lower() not in output.lower():
                        raise ValueError("proof digest is absent from the cited tool result")
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    errors.append(f"{rid}: proof inspection blocked: {exc}")
                if not isinstance(row.get("meaning"), str) or not row["meaning"].strip():
                    errors.append(f"{rid}: observed proof needs its bounded meaning")
        if require_review:
            errors.extend(review_errors(report))
            config = gate.load_config(root) if (root / "architrave.config.json").exists() else {}
            path, error = gate.requirements_path(root, config.get("requirements", "SPEC.md"))
            if error:
                errors.append(error)
            else:
                rows, _, parse_errors = gate.parse_requirements(path.read_text(encoding="utf-8-sig"))
                errors.extend(parse_errors)
                errors.extend(f"{rid}: requirement is not accepted" for rid in reqs
                              if rows.get(rid, {}).get("status", "").lower() != "accepted")
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
        errors.append(f"delivery inspection blocked: {exc}")
    return errors


def check_session(root: Path, session_id: str, *, allow_withdrawal: bool = True) -> list[str]:
    try:
        report = read_json(session_report_path(session_id))
        if report.get("session_id") != session_id.lower():
            return ["delivery session identity differs"]
        root = repository_root(root)
        if Path(report["repo"]).resolve() != root:
            return ["delivery repository identity differs"]
        if report.get("state") == "withdrawn":
            errors = withdrawal_errors(root, report)
            return errors if allow_withdrawal or errors else ["scope was withdrawn; no delivery acceptance is claimed"]
        # A later real host completion retires this declaration. The next
        # non-trivial task must prepare a new one; no author-written active=false.
        if host_completed(report, events(session_id)):
            errors = check_report(root, report)
            return (["work changed after host completion; prepare a new owner-bound scope", *errors]
                    if errors else [])
        return check_report(root, report)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return [f"delivery inspection blocked: {exc}"]


def newer_requests(report: dict, event_ids: list[str], log: list[dict]) -> list[dict]:
    if not event_ids:
        raise ValueError("a newer original --request event is required")
    known = {r["event_id"] for r in report["owner_requests"]}
    cutoff = max(timestamp(e.get("timestamp")) for e in log if e.get("id") in known)
    additions = [owner_reference(event_id, log) for event_id in event_ids]
    for reference in additions:
        event = next(e for e in log if e.get("id") == reference["event_id"])
        if reference["event_id"] in known or timestamp(event.get("timestamp")) <= cutoff:
            raise ValueError("a newer, distinct owner instruction is required")
    return additions


def withdrawal_errors(root: Path, report: dict, *, fresh: bool = True) -> list[str]:
    try:
        if report.get("schema") != SCHEMA or Path(report["repo"]).resolve() != root.resolve():
            raise ValueError("withdrawal repository/schema mismatch")
        reference = report["withdrawal"]["owner_request"]
        log = events(report["session_id"])
        if owner_reference(reference["event_id"], log) != reference:
            raise ValueError("withdrawal owner reference changed")
        event = next(e for e in log if e.get("id") == reference["event_id"])
        quote = report["withdrawal"]["quote"]
        if not isinstance(quote, str) or not quote.strip() or quote not in event["data"]["content"]:
            raise ValueError("withdrawal quotation is not in the original owner instruction")
        if fresh:
            current = audit.scan(root, base=report["base_sha"], all_files=bool(report.get("all_files")),
                                 documents=report.get("document_paths"), reqs=report["reqs"])
            if current["source_sha256"] != report["withdrawal"]["source_sha256"]:
                raise ValueError("source or requirements changed after withdrawal; prepare a new scope")
    except (ValueError, KeyError, OSError, TypeError, StopIteration) as exc:
        return [f"withdrawal inspection blocked: {exc}"]
    return []


def write_report(path: Path, report: dict, *, create: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        file_identity(path)
    if create:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
            handle.write("\n")
    else:
        temporary = path.with_suffix(f".{os.getpid()}.tmp")
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                json.dump(report, handle, indent=2)
                handle.write("\n")
            temporary.replace(path)
        finally:
            if temporary.exists():
                temporary.unlink()


def session_command(args) -> int:
    try:
        sid = (args.session or os.environ.get("COPILOT_AGENT_SESSION_ID", "")).lower()
        path = session_report_path(sid)
        root = Path(args.repo).resolve()
        if args.prepare:
            reqs = list(dict.fromkeys(r.strip().upper() for r in (args.reqs or "").split(",") if r.strip()))
            if not reqs or not args.request:
                raise ValueError("--prepare requires --reqs and original --request event IDs")
            snapshot = audit.scan(root, base=args.base, all_files=args.all_files,
                                  documents=args.document, reqs=reqs)
            log = events(sid)
            if path.exists():
                prior = read_json(path)
                retired = (not withdrawal_errors(root, prior, fresh=False) if prior.get("state") == "withdrawn"
                           else host_completed(prior, log))
                if not retired:
                    raise ValueError("active declaration exists; use --amend or --withdraw with a newer owner instruction")
                newer_requests(prior, args.request, log)
                archive = path.with_name(f"architrave-delivery-{report_digest(prior)}.json")
                # Preserve the old report before starting the next task.
                with archive.open("xb") as handle:
                    handle.write(path.read_bytes())
                path.unlink()
            report = {
                "schema": SCHEMA, "state": "prepared", "session_id": sid, "repo": str(root),
                "prepared_at": datetime.now(timezone.utc).isoformat(),
                "reqs": reqs, "base_sha": snapshot["base_sha"], "all_files": args.all_files,
                "document_paths": args.document,
                "original_requirements": snapshot["requirements"],
                "owner_requests": [owner_reference(event_id, log) for event_id in args.request],
                "references": [file_identity(Path(name)) for name in args.reference or []],
                "expected": {rid: {"kind": "unclassified"} for rid in reqs},
                "audit": None, "board": None, "dispositions": {}, "observations": {}, "review": None,
            }
            write_report(path, report, create=True)
            print(f"delivery-audit: PREPARED {path}")
            print("Set expected source/integration/visual outcomes from the owner request before implementing; "
                  "open/read the scoped program board. This grants no new operation permission.")
            return 0
        report = read_json(path)
        if (report.get("schema") != SCHEMA or Path(report["repo"]).resolve() != root
                or report["session_id"] != sid):
            raise ValueError("declared delivery belongs to another repository/session")
        if args.withdraw:
            log = events(sid)
            additions = newer_requests(report, args.request or [], log)
            if len(additions) != 1 or not isinstance(args.reason, str) or not args.reason.strip():
                raise ValueError("--withdraw needs one newer --request and a verbatim --reason quotation")
            event = next(e for e in log if e.get("id") == additions[0]["event_id"])
            if args.reason not in event["data"]["content"]:
                raise ValueError("withdrawal reason must quote the original owner instruction")
            current = audit.scan(root, base=report["base_sha"], all_files=bool(report.get("all_files")),
                                 documents=report.get("document_paths"), reqs=report["reqs"])
            prior_digest = report_digest(report)
            prior_bytes = path.read_bytes()
            report["state"] = "withdrawn"
            report["owner_requests"].extend(additions)
            report["withdrawal"] = {
                "owner_request": additions[0], "quote": args.reason,
                "prior_digest": prior_digest, "source_sha256": current["source_sha256"],
            }
            errors = withdrawal_errors(root, report)
            if errors:
                raise ValueError("; ".join(errors))
            archive = path.with_name(f"architrave-delivery-{prior_digest}.json")
            with archive.open("xb") as handle:
                handle.write(prior_bytes)
            write_report(path, report)
            print("delivery-audit: WITHDRAWN by referenced owner instruction; not delivery acceptance")
            return 0
        if args.amend:
            if report.get("state") == "withdrawn":
                raise ValueError("withdrawn work needs a new owner-bound --prepare")
            log = events(sid)
            known = {r["event_id"] for r in report["owner_requests"]}
            additions = newer_requests(report, args.request or [], log)
            reqs = list(dict.fromkeys(r.strip().upper() for r in args.reqs.split(",") if r.strip())) if args.reqs else report["reqs"]
            removed = sorted(set(report["reqs"]) - set(reqs))
            explicit_drop = {r.strip().upper() for r in (args.drop or "").split(",") if r.strip()}
            if set(removed) != explicit_drop:
                raise ValueError("--amend must explicitly name exactly the removed requirements with --drop")
            documents = args.document if args.document is not None else report.get("document_paths")
            current = audit.scan(root, base=report["base_sha"], all_files=bool(report.get("all_files")),
                                 documents=documents, reqs=reqs)
            prior_digest = report_digest(report)
            changed = [rid for rid in reqs if rid in report["original_requirements"]["requirements"]
                       and current["requirements"]["requirements"][rid] != report["original_requirements"]["requirements"][rid]]
            report.setdefault("history", []).append({
                "sha256": prior_digest, "requirements": report["original_requirements"],
                "owner_event_ids": sorted(known),
                "dropped_reqs": removed, "changed_reqs": changed,
            })
            report.update(state="prepared", prepared_at=datetime.now(timezone.utc).isoformat(),
                          reqs=reqs, original_requirements=current["requirements"], document_paths=documents,
                          owner_requests=report["owner_requests"] + additions,
                          expected={rid: {"kind": "unclassified"} for rid in reqs},
                          audit=None, dispositions={}, observations={}, review=None)
            report.pop("sealed_at", None)
            report["references"].extend(file_identity(Path(name)) for name in args.reference or [])
            write_report(path, report)
            print(f"delivery-audit: AMENDED {path}; previous scope retained, acceptance cleared")
            print(f"Scope diff: dropped={removed}; changed={changed}; current={reqs}")
            print(f"Delivery digest: {report_digest(report)}")
            return 0
        if args.seal:
            if report.get("state") == "withdrawn":
                raise ValueError("withdrawn work needs a new owner-bound --prepare")
            current = audit.scan(root, base=report["base_sha"], all_files=bool(report.get("all_files")),
                                 documents=report.get("document_paths"), reqs=report["reqs"])
            if current["requirements"] != report["original_requirements"]:
                raise ValueError("requirements changed; preserve the intake and re-declare against actual owner corrections")
            report["audit"] = current
            report["state"] = "sealed"
            report["sealed_at"] = datetime.now(timezone.utc).isoformat()
            report["review"] = None
            write_report(path, report)
            print(f"delivery-audit: SEALED {path}; {len(current['findings'])} candidates require disposition")
            print("Sealing source does not accept the task. Record observations/dispositions and obtain a digest-bound review.")
            return 0
        errors = (withdrawal_errors(root, report) if report.get("state") == "withdrawn"
                  else check_report(root, report))
        for error in errors:
            print(f"BLOCK delivery: {error}")
        print(f"Delivery digest: {report_digest(report)}")
        label = "WITHDRAWN (not delivery acceptance)" if report.get("state") == "withdrawn" else "PASS (declared scope only)"
        print("delivery-audit: BLOCK" if errors else "delivery-audit: " + label)
        return 2 if errors else 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"delivery-audit: BLOCK - {exc}", file=sys.stderr)
        return 2
