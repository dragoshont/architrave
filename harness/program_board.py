#!/usr/bin/env python3
"""Program board: one standalone HTML view of a coordinated program.

Usage: python harness/program_board.py --ledger <dir with SPEC.md> --reqs REQ-1,REQ-2 --session <coordinator-session-id> --output <file.html>

Reads working-tree ledger tables (REQs, lanes) and the host's local session logs
(~/.copilot/session-state/<id>/events.jsonl) for the coordinator and the child
sessions it created. Writes one HTML file with no network requests; open it in
the browser canvas. It never changes a ledger, session or repository.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gate_runner", ROOT / "gates" / "gate_runner.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

STATE_HOME = Path(os.environ.get("COPILOT_HOME", Path.home() / ".copilot")) / "session-state"
REQ_TONE = {"accepted": "done", "claimed": "active", "in-progress": "active", "blocked": "blocked", "open": "open"}
LANE_TONE = {"done": "done", "running": "active", "blocked": "blocked", "idle": "open", "ready": "open",
             "superseded": "gone", "stopped": "gone"}


def when(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
    except ValueError:
        return None


SPAWN_TOOLS = {"create_session", "open_pr_session", "open_issue_session", "fork_session"}
REVIEWER = gate.REVIEWER_ROLE
SESSION_ID = re.compile(r"\b([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\b")


def as_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


STATE: dict[tuple[str, datetime | None], dict] = {}


def fresh_state(sid: str) -> dict:
    return {"offset": 0, "pending": {}, "turn_open": None, "info": {
        "id": sid, "start": None, "end": None, "turns": [], "calls": 0, "input": 0, "cached": 0, "output": 0,
        "max_context": 0, "context_limit": 0, "context": 0, "context_at": None, "baseline": 0, "model": None,
        "agent": None, "children": [], "reviews": set(), "completed": None, "turn_after_complete": False}}


def read_session(sid: str, since: datetime | None = None) -> dict | None:
    """Parse a session log incrementally: only bytes appended since the last call are read."""
    path = STATE_HOME / sid / "events.jsonl"
    if not path.is_file():
        return None
    key = (sid, since)
    state = STATE.get(key)
    stat = path.stat()
    with path.open("rb") as handle:
        head = handle.read(256)
    size, identity = stat.st_size, (stat.st_ino, stat.st_dev, head)
    if state is None or size < state["offset"] or state.get("identity") != identity:
        state = STATE[key] = fresh_state(sid)
        state["identity"] = identity
    if size > state["offset"]:
        with path.open("rb") as handle:
            handle.seek(state["offset"])
            chunk = handle.read(size - state["offset"])
        complete = chunk.rfind(b"\n") + 1
        tail = chunk[complete:]
        if tail.strip():
            try:
                json.loads(tail)
                complete = len(chunk)
            except ValueError:
                pass
        for line in chunk[:complete].splitlines():
            consume(state, line, since)
        state["offset"] += complete
    return derive(state)


def consume(state: dict, line: bytes, since: datetime | None) -> None:
    info = state["info"]
    try:
        event = json.loads(line)
    except ValueError:
        return
    if not isinstance(event, dict):
        return
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    kind = event.get("type")
    stamp = when(event["timestamp"]) if isinstance(event.get("timestamp"), str) else None
    if kind == "session.usage_record" and not info["baseline"]:
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        info["baseline"] = as_int(usage.get("inputTokens"))
    if since and stamp and stamp < since:
        return
    if stamp:
        info["start"] = min(info["start"], stamp) if info["start"] else stamp
        info["end"] = max(info["end"], stamp) if info["end"] else stamp
    if kind == "session.start":
        info["model"] = data.get("selectedModel") if isinstance(data.get("selectedModel"), str) else info["model"]
        if not since and isinstance(data.get("startTime"), str):
            info["start"] = when(data["startTime"]) or info["start"]
    elif kind == "subagent.selected":
        name = data.get("agentName") if isinstance(data.get("agentName"), str) else None
        if not info["turns"] and state["turn_open"] is None:
            info["agent"] = name
        elif name and REVIEWER.fullmatch(name):
            info["reviews"].add(name)
    elif kind == "skill.invoked" and REVIEWER.fullmatch(str(data.get("name") or data.get("skillName") or "")):
        info["reviews"].add(str(data.get("name") or data.get("skillName")))
    elif kind == "tool.execution_start" and data.get("toolName") == "task" and isinstance(data.get("arguments"), dict) \
            and REVIEWER.fullmatch(str(data["arguments"].get("agent_type", ""))):
        info["reviews"].add(str(data["arguments"]["agent_type"]))
    elif kind == "assistant.turn_start":
        state["turn_open"] = stamp
        if info["completed"]:
            info["turn_after_complete"] = True
    elif kind == "session.task_complete":
        info["completed"], info["turn_after_complete"] = stamp, False
    elif kind == "assistant.turn_end" and state["turn_open"] and stamp:
        info["turns"].append((state["turn_open"], stamp))
        state["turn_open"] = None
    elif kind == "session.usage_record":
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        prompt, cached = as_int(usage.get("inputTokens")), as_int(usage.get("cacheReadTokens"))
        info["calls"] += 1
        info["input"] += max(prompt - cached, 0)
        info["cached"] += cached
        info["output"] += as_int(usage.get("outputTokens"))
        info["max_context"] = max(info["max_context"], prompt)
        if prompt:
            if not info["context_at"] or (stamp and stamp >= info["context_at"]):
                info["context"], info["context_at"] = prompt, stamp
        info["context_limit"] = max(info["context_limit"], as_int(usage.get("maxPromptTokens")))
        if isinstance(usage.get("model"), str):
            info["model"] = usage["model"]
    elif kind == "tool.execution_start" and data.get("toolName") in SPAWN_TOOLS:
        args = data.get("arguments") if isinstance(data.get("arguments"), dict) else {}
        kickoff = args.get("kickoff") if isinstance(args.get("kickoff"), dict) else {}
        name = args.get("name") if isinstance(args.get("name"), str) else str(data.get("toolName"))
        state["pending"][str(data.get("toolCallId"))] = (name, kickoff.get("agent") if isinstance(kickoff.get("agent"), str) else None)
    elif kind == "tool.execution_complete" and str(data.get("toolCallId")) in state["pending"]:
        match = SESSION_ID.search(json.dumps(data.get("result", "")))
        name, agent = state["pending"].pop(str(data.get("toolCallId")))
        if match:
            info["children"].append({"id": match.group(1).lower(), "name": name, "agent": agent})


def derive(state: dict) -> dict:
    """Return a snapshot with computed fields; the parse state is not mutated."""
    info = dict(state["info"])
    info["turns"] = list(info["turns"]) + ([(state["turn_open"], info["end"])] if state["turn_open"] and info["end"] else [])
    info["children"], info["reviews"] = list(info["children"]), set(info["reviews"])
    merged: list[tuple[datetime, datetime]] = []
    for a, b in sorted(info["turns"]):
        if merged and (a - merged[-1][1]).total_seconds() < 60:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    info["spans"] = merged
    info["active_min"] = sum((b - a).total_seconds() for a, b in info["turns"]) / 60
    info["wall_min"] = ((info["end"] - info["start"]).total_seconds() / 60) if info["start"] and info["end"] else 0
    info["idle_min"] = ((datetime.now(timezone.utc) - info["end"]).total_seconds() / 60) if info["end"] else None
    info["done"] = bool(info["completed"]) and not info["turn_after_complete"]
    context, limit, base = info["context"], info["context_limit"], info["baseline"] or 1
    frac = context / limit if limit else 0
    # A fresh session already carries the system prompt and tools; only growth beyond that baseline is sheddable.
    growth, headroom = context - base, max(limit - base, 1)
    info["rotate"] = None if info["done"] else (
        "hard" if frac >= 0.45 and (context >= 2 * base or growth >= 0.5 * headroom)
        else "soft" if (frac >= 0.30 or context >= 300_000) and (context >= 1.5 * base or growth >= 0.25 * headroom)
        else None)
    return info


def state_of(s: dict, lane: dict) -> str:
    label = lane.get("state") or ("coordinator" if s.get("name") == "Coordinator" else "")
    idle = s.get("idle_min")
    rotate = {"hard": " · rotate at next task boundary", "soft": " · context high"}.get(s.get("rotate") or "", "")
    activity = ("task completed" if s.get("done") else "no log" if idle is None
                else "active now" if idle < 10 else f"idle {idle:.0f} min")
    return (f"{label} · {activity}" if label else activity) + rotate


def esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def num(value: float) -> str:
    return f"{value / 1_000_000:.1f}M" if value >= 1_000_000 else f"{value / 1000:.0f}k" if value >= 1000 else f"{value:.0f}"


RESOLVED: dict[tuple[str, str], bool] = {}


def evidence_resolves(evidence: str, repos: list[Path]) -> bool:
    if re.search(r"\bartifact\s*:|\bsha256\b|\b[0-9a-fA-F]{64}\b", evidence, re.I):
        return False
    for sha in re.findall(r"(?<![0-9a-fA-F])[0-9a-fA-F]{7,40}(?![0-9a-fA-F])", evidence):
        for repo in repos:
            key = (str(repo), sha)
            if key in RESOLVED or gate.git(repo, "cat-file", "-e", f"{sha}^{{commit}}") is not None:
                RESOLVED[key] = True
                return True
    return False


def evidence_identity(evidence: str, ledger: Path, repos: list[Path]) -> dict:
    """Recognize identity only; declared review bindings do not certify semantic quality."""
    starts = list(re.finditer(r"\bartifact\s*:", evidence, re.I))
    if starts:
        results = []
        for start in starts:
            try:
                item, _ = json.JSONDecoder().raw_decode(evidence[start.end():].lstrip())
            except ValueError:
                results.append(("unsupported", "artifact metadata must be a JSON object"))
                continue
            if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not item["path"].strip():
                results.append(("unsupported", "artifact metadata needs a local path"))
                continue
            locator = item["path"]
            digest = item.get("sha256")
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
                results.append(("incomplete", f"{locator}: missing or invalid sha256"))
                continue
            path = Path(locator).expanduser()
            path = path if path.is_absolute() else ledger / path
            try:
                actual = hashlib.sha256(path.read_bytes()).hexdigest()
            except FileNotFoundError:
                results.append(("missing", f"{locator}: artifact missing"))
                continue
            except OSError as exc:
                results.append(("unavailable", f"{locator}: cannot read artifact ({exc})"))
                continue
            if actual != digest.lower():
                results.append(("changed", f"{locator}: content changed (expected {digest.lower()}, actual {actual})"))
            else:
                bound = str(item.get("reviewed_sha256", "")).lower() == actual
                passed = gate.review_passed(evidence)
                verified = gate.review_passed(evidence, strict=True)
                review = ("declared digest binding; review execution verified" if verified else
                          "declared digest binding; review note only") if bound and passed else "review binding missing or mismatched"
                results.append(("verified", f"{locator}: SHA256 identity verified; {review}"))
        failed = next((state for state, _ in results if state != "verified"), None)
        return {"state": failed or "verified", "detail": "; ".join(detail for _, detail in results)}
    if evidence.strip() in {"", "-"}:
        return {"state": "missing", "detail": "no evidence supplied"}
    # A bare digest is not a commit locator, even when accompanied by an unrelated commit.
    if re.search(r"\b(?:sha256|[0-9a-fA-F]{64}\b)", evidence, re.I):
        return {"state": "unsupported", "detail": "digest evidence needs artifact path/sha256 metadata"}
    if evidence_resolves(evidence, repos):
        return {"state": "commit", "detail": "commit exists; artifact identity and behavioral acceptance not established"}
    return {"state": "unsupported", "detail": "no supported artifact metadata or resolving commit"}


def build(ledger: Path, coordinator: str, selected: list[str] | None = None) -> dict:
    path = ledger / "SPEC.md"
    source_bytes = path.read_bytes()
    text = source_bytes.decode("utf-8-sig")
    reqs, _corrections, errors = gate.parse_requirements(text)
    lanes = gate.ledger_table(text, ("lane", "repo", "project id"), gate.LANE_COLUMNS)
    config = gate.load_config(ledger) if (ledger / "architrave.config.json").is_file() else {}
    more, blockers, notes = gate.chain_errors(ledger, text, reqs, config)
    cap, cap_error = gate.parallel_cap(config)
    errors += more + gate.header_errors(text) + gate.lane_errors(text, reqs, cap) + ([cap_error] if cap_error else [])
    if selected is not None:
        if not selected:
            raise ValueError("session scope needs at least one REQ ID")
        unknown = set(selected) - reqs.keys()
        if unknown:
            raise ValueError("unknown session REQ IDs: " + ", ".join(sorted(unknown)))
        reqs = {rid: row for rid, row in reqs.items() if rid in selected}
        lanes = [dict(lane, **{"req ids": ", ".join(rid for rid in gate.lane_reqs(lane) if rid in reqs)})
                 for lane in lanes if set(gate.lane_reqs(lane)) & reqs.keys()]
    repos = [ledger] + [gate.component_path(ledger, c["path"]) for c in config.get("components") or []
                        if isinstance(c, dict) and isinstance(c.get("path"), str)]
    repos = [r for r in repos if gate.git(r, "rev-parse", "--git-dir") is not None]
    reviewed = {rid for rid, r in reqs.items() if gate.review_passed(r["evidence"])}
    verified = {rid for rid, r in reqs.items() if gate.review_passed(r["evidence"], strict=True)}
    strict = gate.strict_reviews()
    review_cfg = config.get("review") if isinstance(config.get("review"), dict) else {}
    cross = bool(review_cfg.get("crossFamily"))
    identities = {rid: evidence_identity(r["evidence"], ledger, repos) for rid, r in reqs.items()}
    unverified = {rid for rid, r in reqs.items() if r["status"].lower() == "accepted"
                  and identities[rid]["state"] not in {"verified", "commit"}}
    laned = {rid.upper() for lane in lanes for rid in re.findall(r"REQ-[A-Za-z0-9_.-]+", lane["req ids"], re.I)}
    loose = [rid for rid, r in reqs.items() if rid not in laned and r["status"].lower() not in gate.REQ_CLOSED]
    if loose:
        lanes = lanes + [dict.fromkeys(gate.LANE_COLUMNS, "") | {"lane": "Not in a lane" if lanes else "Requirements",
                                                                 "repo": ledger.name, "state": "idle", "req ids": ", ".join(loose), "synthetic": True}]
    commit = gate.git(ledger, "rev-parse", "HEAD") or "unavailable (no repository HEAD)"
    tracked = gate.git(ledger, "ls-files", "--error-unmatch", "--", path.name) is not None
    dirty = gate.git(ledger, "status", "--porcelain", "--untracked-files=all", "--", path.name)
    source_state = "untracked" if not tracked else "modified" if dirty else "clean"
    source_digest = hashlib.sha256(source_bytes).hexdigest()
    root = read_session(coordinator)
    sessions = [root] if root else []
    names = {}
    queue = list((root or {}).get("children", []))
    while queue:
        child = queue.pop(0)
        if child["id"] in names or child["id"] == coordinator.lower():
            continue
        info = read_session(child["id"])
        names[child["id"]] = child["name"]
        if info and root and info["start"] and info["start"] < root["start"]:
            info = read_session(child["id"], root["start"])
        if info:
            info["name"], info["agent"] = child["name"], child["agent"] or info["agent"]
            sessions.append(info)
            queue.extend(info["children"])
    if root:
        root["name"] = "Coordinator"
    lane_by_session = {lane["session id"]: lane for lane in lanes if lane["session id"] not in {"", "-"}}
    seen = {s["id"].lower() for s in sessions}
    for sid, lane in lane_by_session.items():
        if sid not in seen and re.fullmatch(r"[0-9a-fA-F-]{36}", sid) and (info := read_session(sid, root["start"] if root else None)):
            info["name"] = lane["lane"]
            sessions.append(info)
            seen.add(sid.lower())
    sessions = [x for x in sessions if x["start"] and x["end"]]
    seen = {x["id"].lower() for x in sessions}
    remote = [lane for sid, lane in lane_by_session.items() if sid.lower() not in seen and lane["state"].lower() not in {"superseded", "stopped"}]
    return {"ledger": ledger, "commit": commit, "reqs": reqs, "lanes": lanes, "sessions": sessions, "remote": remote,
            "lane_by_session": lane_by_session, "errors": errors, "unverified": unverified, "reviewed": reviewed, "verified": verified,
            "strict": strict, "cross": cross, "generated": datetime.now(timezone.utc), "coordinator": coordinator,
            "identities": identities, "notes": notes, "blockers": blockers,
            "configured": (ledger / "architrave.config.json").is_file(), "source_state": source_state,
            "source_digest": source_digest, "selected": selected}


def timeline(sessions: list[dict], lane_by_session: dict, remote: list[dict] = ()) -> str:
    timed = [s for s in sessions if s["start"] and s["end"]]
    if not timed:
        return "<p class='note'>No local session logs found for this program.</p>"
    t0, t1 = timed[0]["start"], max(s["end"] for s in timed)
    timed = [s for s in timed if s["end"] >= t0]
    span = max((t1 - t0).total_seconds(), 60)
    top_tokens = max(s["input"] + s["cached"] + s["output"] for s in timed) or 1
    width, row, left, gauge = 300, 40, 104, 92
    rows = []
    for i, s in enumerate(timed):
        y = 16 + i * row
        lane = lane_by_session.get(s["id"]) or {}
        tone = "done" if s.get("done") else LANE_TONE.get(lane.get("state", "").lower(), "active")
        x = left + max((s["start"] - t0).total_seconds(), 0) / span * width
        w = max((s["end"] - max(s["start"], t0)).total_seconds() / span * width, 2)
        marks = "".join(f"<rect class='turn' x='{left + (a - t0).total_seconds() / span * width:.1f}' y='{y + 2}' "
                        f"width='{max((b - a).total_seconds() / span * width, 1):.1f}' height='6'/>" for a, b in s["spans"] if b >= t0)
        ctx = (s["context"] / s["context_limit"]) if s["context_limit"] else 0
        tok = (s["input"] + s["cached"] + s["output"]) / top_tokens
        gx = left + width + 12
        agent = (s["agent"] or "default").replace("architrave:", "")
        rows.append(
            f"<g><title>{esc(s['name'])}: {s['wall_min']:.0f} min wall, {s['active_min']:.0f} min model; "
            f"{('ran reviewer ' + ', '.join(sorted(s['reviews'])) + ' (verdict is in the ledger, not checked here)') if s['reviews'] else 'no reviewer run'}; {s['calls']} calls; {s['input']:,} fresh in, {s['cached']:,} cached, {s['output']:,} out tokens; context now {s['context']:,}, peak {s['max_context']:,} of {s['context_limit']:,}</title>"
            f"<text class='label' x='0' y='{y + 8}'>{esc(s['name'] if len(s['name']) <= 15 else s['name'][:14] + '…')}"
            f"<tspan class='nrv'> {'✓' if s['reviews'] else '○'}</tspan>"
            f"{'<tspan class=rot> ↻</tspan>' if s.get('rotate') == 'hard' else ''}</text>"
            f"<text class='sub' x='0' y='{y + 19}'>{esc(agent[:22])}</text>"
            f"<rect class='lane-bg' x='{left}' y='{y}' width='{width}' height='10'/>"
            f"<rect class='track {tone}' x='{x:.1f}' y='{y}' width='{w:.1f}' height='10'/>{marks}"
            f"<text class='sub' x='{left}' y='{y + 22}'>{'started earlier · ' if s['start'] < t0 else ''}{s['active_min']:.0f} model / {s['wall_min']:.0f} wall min · {esc(state_of(s, lane))}</text>"
            f"<rect class='gauge' x='{gx}' y='{y}' width='{gauge}' height='4'/><rect class='ctxfill' x='{gx}' y='{y}' width='{gauge * min(ctx, 1):.1f}' height='4'/>"
            f"<text class='sub' x='{gx}' y='{y + 12}'>ctx {num(s['context'])} / {num(s['context_limit'])}</text>"
            f"<rect class='gauge' x='{gx}' y='{y + 16}' width='{gauge}' height='4'/><rect class='tokfill' x='{gx}' y='{y + 16}' width='{gauge * tok:.1f}' height='4'/>"
            f"<text class='sub' x='{gx}' y='{y + 28}'>tok {num(s['input'])} new · {num(s['cached'])} cache · {num(s['output'])} out</text></g>")
    for j, lane in enumerate(remote):
        y = 16 + (len(timed) + j) * row
        rows.append(f"<g><text class='label' x='0' y='{y + 8}'>{esc(lane['lane'][:17])}</text>"
                    f"<rect class='lane-bg remote' x='{left}' y='{y}' width='{width}' height='10'/>"
                    f"<text class='sub' x='{left}' y='{y + 22}'>{esc(lane['state'])} · not logged on this machine</text></g>")
    ticks = "".join(f"<text class='tick' x='{left + f * width:.0f}' y='9' text-anchor='{'start' if f == 0 else 'end' if f == 1 else 'middle'}'>"
                    f"{datetime.fromtimestamp(t0.timestamp() + f * span, timezone.utc).strftime('%m-%d %H:%M')} UTC</text>" for f in (0, .5, 1))
    heads = (f"<text class='tick' x='{left + width + 12}' y='9'>context now · tokens</text>")
    return (f"<svg class='timeline' viewBox='0 0 {left + width + 12 + gauge} {16 + (len(timed) + len(remote)) * row}' role='img' "
            f"aria-label='How the sessions ran'>{ticks}{heads}{''.join(rows)}</svg>"
            f"<p class='note'>Bar: first to last event; dark marks: model turns. Gauges: current context against the "
            f"model limit, and tokens relative to the busiest session. All dates/times are UTC. "
            f"<span class='interactive-only'>Hover a row for exact numbers; full names and values follow.</span></p>")


def session_details(sessions: list[dict], lane_by_session: dict, remote: list[dict]) -> str:
    rows = []
    for s in sessions:
        rows.append(
            f"<article class='session-record'><h3>{esc(s['name'])}</h3>"
            f"<p>{esc(s['id'])} · {esc(s['agent'] or 'default')} · {esc(s['model'] or 'model unavailable')}</p>"
            f"<p>{s['start'].astimezone(timezone.utc).isoformat(timespec='seconds')} to "
            f"{s['end'].astimezone(timezone.utc).isoformat(timespec='seconds')} · {esc(state_of(s, lane_by_session.get(s['id']) or {}))}</p>"
            f"<p>{s['input']:,} new input / {s['cached']:,} cached / {s['output']:,} output tokens; "
            f"context {s['context']:,} / {s['context_limit']:,} (peak {s['max_context']:,}); {s['calls']:,} calls; "
            f"{s['active_min']:.1f} model / {s['wall_min']:.1f} wall minutes.</p></article>")
    for lane in remote:
        rows.append(f"<article class='session-record'><h3>{esc(lane['lane'])}</h3>"
                    f"<p>{esc(lane['session id'])} · {esc(lane['state'])} · not logged on this machine; metrics unavailable.</p></article>")
    return "".join(rows) or "<p>No local history observed.</p>"


def render(data: dict) -> str:
    reqs, lanes, sessions = data["reqs"], data["lanes"], data["sessions"]
    active_req = {rid: r for rid, r in reqs.items() if r["status"].lower() not in gate.REQ_CLOSED}
    accepted = sum(1 for r in active_req.values() if r["status"].lower() == "accepted")
    total_in, total_out = sum(s["input"] for s in sessions), sum(s["output"] for s in sessions)
    total_cached = sum(s["cached"] for s in sessions)
    unverified, reviewed, verified = data["unverified"], data["reviewed"], data["verified"]
    unreviewed_accepted = [r for r in active_req if active_req[r]["status"].lower() == "accepted" and r not in reviewed]
    active = sum(s["active_min"] for s in sessions)
    wall = ((max(s["end"] for s in sessions) - sessions[0]["start"]).total_seconds() / 60) if sessions else 0
    running = sum(1 for lane in lanes if lane["state"].lower() == "running")
    workers = [lane for lane in lanes if not lane.get("synthetic")]
    stats = [("REQs accepted", f"{accepted}/{len(active_req)}"),
             ("repository ledger structural checks", "PASS" if not data["errors"] else f"{len(data['errors'])} issues"),
             ("lanes missing a review (blocks --done)", str(sum(1 for lane in lanes if not lane.get("synthetic")
                                                                 and gate.lane_review_gaps(lane, reqs, data["strict"], data["cross"])))),
             ("accepted, evidence unresolved", str(len(unverified & set(active_req)))),
             ("accepted, not reviewed", str(len(unreviewed_accepted))),
             ("PASS review executions verified", f"{len(verified & set(active_req))}/{len(reviewed & set(active_req))}"),
             ("worker lanes running", f"{running}/{len(workers)}"),
             ("history sessions", str(len(sessions))), ("history tokens new/cache/out", f"{num(total_in)}/{num(total_cached)}/{num(total_out)}"),
             ("model min, cumulative history", f"{active:.0f}"), ("history span min", f"{wall:.0f}")]
    overview = "".join(f"<div><b>{esc(v)}</b><span>{esc(k)}</span></div>" for k, v in stats)
    boxes = []
    for lane in lanes:
        ids = [rid.upper() for rid in re.findall(r"REQ-[A-Za-z0-9_.-]+", lane["req ids"], re.I)]
        delivered = {r for r in ids if lane["state"].lower() == "done" and r in reqs
                     and reqs[r]["status"].lower() not in gate.REQ_CLOSED | {"accepted", "blocked"}}
        squares = "".join(
            f"<button class='sq {'delivered' if r in delivered else REQ_TONE.get(reqs[r]['status'].lower(), 'open') if r in reqs else 'open'}{' warn' if r in unverified else ''}{' rev' if r in reviewed else ''}{' vrf' if r in verified else ''}' "
            f"data-d='{esc(r)} · {esc(reqs[r]['status'] if r in reqs else 'unknown')}{' · delivered by this lane, awaiting acceptance' if r in delivered else ''} · {esc(data['identities'].get(r, {}).get('detail', 'no evidence'))}{' · review execution verified in its session log' if r in verified else ' · reviewed (note only)' if r in reviewed else ' · not reviewed'} · {esc((reqs[r]['requirement'] if r in reqs else ''))}' "
            f"aria-label='{esc(r)} {esc(reqs[r]['status'] if r in reqs else 'unknown')}: {esc(reqs[r]['requirement'] if r in reqs else '')}'></button>" for r in ids)
        done = sum(1 for r in ids if r in reqs and reqs[r]["status"].lower() == "accepted")
        rev = sum(1 for r in ids if r in reviewed)
        missing = bool(gate.lane_review_gaps(lane, reqs, data["strict"], data["cross"])) and not lane.get("synthetic")
        risky = missing or (lane.get("synthetic") and any(
            r in reqs and reqs[r]["status"].lower() == "accepted" and r not in reviewed for r in ids))
        tone = LANE_TONE.get(lane["state"].lower(), "open")
        boxes.append(f"<section class='box {tone}{' unrev' if risky else ''}'><h3>{esc(lane['lane'])}</h3>"
                     f"<p>{'Synthetic requirement group (not a worker lane)' if lane.get('synthetic') else esc(lane['state'])}{' · review missing' if missing else ''} · {done}/{len(ids)} accepted · reviewed {rev}/{len(ids)}</p>"
                     f"<div class='grid'>{squares}</div></section>")
    css = """
:root{color-scheme:dark;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#10161e;color:#edf3f8}
*{box-sizing:border-box}body{margin:0}main{padding:14px 14px 12px;max-width:760px;margin:auto}
h1{margin:0;font-size:17px;font-weight:650;letter-spacing:-.02em}h2{margin:16px 0 6px;font-size:11px;font-weight:600;color:#b8c6d5;text-transform:uppercase;letter-spacing:.06em}
.note{margin:3px 0;font-size:10px;color:#b8c6d5}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:#2a3644;margin-top:10px;border:1px solid #2a3644}
.stats div{background:#1b2632;padding:7px 8px}.stats b{display:block;font-size:15px;font-variant-numeric:tabular-nums}.stats span{font-size:10px;color:#b8c6d5}
.legend{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:10px;color:#d3dee8;margin:4px 0 8px}.legend i{display:inline-block;width:9px;height:9px;margin-right:4px;vertical-align:-1px}.legend i.warn{box-shadow:inset 0 0 0 2px #d6aa4b}.legend i.sq{width:9px;height:9px}.legend i.unrevkey{border:2px solid #d6aa4b}
.done{background:#38aa6b;fill:#38aa6b}.active{background:#479bc1;fill:#479bc1}.blocked{background:#e05b6b;fill:#e05b6b}.open{background:#506071;fill:#506071}.gone{background:#33404e;fill:#33404e}
.boxes{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:6px}
.box{background:#1b2632;border:1px solid #7a8c9e;padding:5px 6px 6px}.box.blocked{border-color:#f08895}.box.done{border-color:#38aa6b}.box.gone{opacity:.45}
.box h3{margin:0;font-size:10.5px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.box p{margin:0 0 4px;font-size:9px;color:#bacada}
.grid{display:grid;grid-template-columns:repeat(auto-fill,11px);gap:1px}
.sq{width:11px;height:11px;padding:0;border:0;cursor:pointer}.sq.warn{box-shadow:inset 0 0 0 2px #d6aa4b}.delivered{background:repeating-linear-gradient(135deg,#38aa6b 0 2px,#1b2632 2px 4px)}.sq{position:relative}.sq.rev::after{content:"";position:absolute;right:0;top:0;border-style:solid;border-width:0 5px 5px 0;border-color:transparent #8fa1b3 transparent transparent}.sq.vrf::after{border-color:transparent #fff transparent transparent}.box.unrev{border-color:#d6aa4b;box-shadow:inset 0 0 0 1px #d6aa4b}.rot{fill:#d6aa4b}.rv{fill:#38aa6b}.nrv{fill:#8fa1b3}.remote{fill:none;stroke:#506071;stroke-dasharray:3 2}.issues{margin:6px 0 0;padding-left:16px;font-size:10px;color:#f0a0aa}.sq:hover,.sq:focus-visible,.sq.sel{outline:1.5px solid #fff;outline-offset:0}
#detail{min-height:28px;margin:8px 0 0;padding-top:6px;border-top:1px solid #415064;font-size:11px;color:#c6d4e1;overflow-wrap:anywhere}
.timeline{width:100%;display:block}.timeline .label{fill:#edf3f8;font-size:8.5px;font-weight:600}.timeline .sub{fill:#9fb0c1;font-size:6.5px}.timeline .tick{fill:#8fa1b3;font-size:6.5px}.lane-bg,.gauge{fill:#1b2632}.turn{fill:#0b1016;opacity:.55}.ctxfill{fill:#d6aa4b}.tokfill{fill:#479bc1}
footer{font-size:9px;color:#8fa1b3;margin-top:10px;line-height:1.5}
.provenance,.session-record,.evidence-record{overflow-wrap:anywhere}
.session-record{border-top:1px solid #415064;padding:6px 0;font-size:11px}
.session-record h3{margin:0;font-size:12px}.session-record p{margin:3px 0}
.evidence-record{font-size:11px;margin:6px 0}
summary{cursor:pointer;font-size:11px;margin:8px 0}
@media print{
@page{size:A4;margin:14mm}
:root,body{color-scheme:light;background:white;color:#111}
main{max-width:none;padding:0}
.stats{grid-template-columns:repeat(3,1fr);background:white}
.stats div,.box{background:white;color:#111}
.stats span,.box p,.note,.legend,h2,footer{color:#333}
.box h3{white-space:normal;overflow:visible}
.box,.session-record,.evidence-record,.stats div{break-inside:avoid}
h2,h3,summary{break-after:avoid}
.timeline,.interactive-only,#detail,script{display:none!important}
.session-record p{font-size:10pt;line-height:1.35}
.session-record h3{font-size:11pt}
.issues{color:#8b1020}
details,details>*,details::details-content{display:block;content-visibility:visible}
}
"""
    legend = ("<div class='legend'><span><i class='done'></i>accepted</span><span><i class='active'></i>claimed</span>"
              "<span><i class='delivered'></i>delivered, awaiting acceptance</span><span><i class='blocked'></i>blocked</span><span><i class='open'></i>open</span><span><i class='open warn'></i>evidence unresolved</span>"
              "<span><i class='sq rev open'></i>reviewed</span><span><i class='unrevkey'></i>done or accepted work without a PASS review</span></div>")
    script = ("<script>const d=document.getElementById('detail');document.querySelectorAll('button.sq').forEach(b=>b.onclick=()=>{"
              "document.querySelectorAll('.sq.sel').forEach(x=>x.classList.remove('sel'));b.classList.add('sel');d.textContent=b.dataset.d});"
              "const snapshot=document.getElementById('snapshot').dataset.snapshot;"
              "document.getElementById('page-observation').textContent='Page observed at '+new Date().toISOString()+' · snapshot '+snapshot+'. This does not observe later file rewrites.';"
              "addEventListener('beforeprint',()=>{document.getElementById('export-observation').textContent="
              "'Print/export requested at '+new Date().toISOString()+' · snapshot '+snapshot+'; export completion is not observed.';});</script>")
    generated = data["generated"].isoformat(timespec="microseconds")
    snapshot = generated + "/" + data["source_digest"][:12]
    root = next((s for s in sessions if s["id"] == data["coordinator"]), None)
    terminal = (f"Host task completion observed at {root['completed'].astimezone(timezone.utc).isoformat()}" if root and root["done"] else
                "Host terminal completion not observed; pre-completion projection")
    mode = ("Stopped watcher; static snapshot" if data.get("stopped") else
            f"Auto-refresh snapshot every {data['refresh']}s (watcher liveness not established by this page)" if data.get("refresh")
            else "Static snapshot; not live")
    completion = ("not evaluated; run requirements --done with the repository configuration" if data["configured"] else
                  "unavailable here: no repository configuration (plugin-only structural checks only; no adoption required)")
    scope = ("Session requirements: " + ", ".join(data["selected"]) + " · other repository requirements excluded"
             if data["selected"] is not None else "Repository-wide requirements · includes historical work, not this session's scope")
    identity_rows = "".join(f"<li class='evidence-record'>{esc(rid)}: {esc(identity['state'])} · {esc(identity['detail'])}</li>"
                            for rid, identity in data["identities"].items() if rid in active_req
                            and (rid in unverified or identity["state"] == "verified"))
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
            + (f"<meta http-equiv='refresh' content='{data['refresh']}'>" if data.get("refresh") else "") + f"<title>Program board</title><style>{css}</style></head><body><main>"
            f"<h1>{esc(data['ledger'].name)} · program</h1><div class='note provenance'>"
            f"<p id='requirement-scope'>{esc(scope)}</p>"
            f"<p id='snapshot' data-snapshot='{esc(snapshot)}'>{esc(mode)} · generated bytes at {esc(generated)} UTC</p>"
            f"<p>Repository HEAD: {esc(data['commit'])}<br>Ledger: working-tree SPEC.md ({esc(data['source_state'])}) · SHA256 {data['source_digest']}</p>"
            f"<p>Session-log observation cutoff: {esc(max((s['end'].astimezone(timezone.utc) for s in sessions), default='unavailable'))} · {esc(terminal)}</p>"
            f"<p id='page-observation'>Page observation unavailable until loaded in a script-enabled consumer.</p>"
            f"<p id='export-observation'>No print/export observation recorded in these generated bytes.</p></div>"
            f"<div class='stats'>{overview}</div>"
            f"<p class='note'>Cumulative history totals: {total_in:,} new input / {total_cached:,} cached / {total_out:,} output tokens.</p>"
            f"<p class='note'>Completion acceptance: {esc(completion)}.</p>"
            + ("<ul class='issues'>" + "".join(f"<li>{esc(e)}</li>" for e in data["errors"]) + "</ul>" if data["errors"] else "")
            + ("<ul class='issues'>" + "".join(f"<li>Open serious finding blocks completion: {esc(e)}</li>" for e in data["blockers"]) + "</ul>" if data["blockers"] else "")
            + ("<ul class='note'>" + "".join(f"<li>{esc(e)}</li>" for e in data["notes"]) + "</ul>" if data["notes"] else "")
            + f"<h2>Lanes</h2>{legend}<div class='boxes'>{''.join(boxes) or '<p class=note>No lane table.</p>'}</div>"
            f"<p id='detail' role='status'>Select a square to see its requirement.</p>"
            + (f"<details open><summary>Artifact identity and unresolved evidence</summary><ul>{identity_rows}</ul></details>" if identity_rows else "")
            + f"<h2>Cumulative session history (not current-task cost)</h2>"
            f"<p class='note'>Selected REQs above; recursive coordinator history below may span multiple tasks. "
            f"Child metrics start no earlier than the coordinator. Synthetic requirement groups are not workers.</p>"
            f"{timeline(sessions, data['lane_by_session'], data['remote'])}"
            f"<details open><summary>Full session names and exact history metrics (UTC)</summary>"
            f"{session_details(sessions, data['lane_by_session'], data['remote'])}</details>"
            f"<footer>Squares show ledger status. A gold ring marks unsupported, incomplete, missing, changed or unreadable evidence. "
            f"A resolving commit establishes existence only, not a particular artifact's identity. Artifact SHA256 and declared review "
            f"binding are separate from semantic quality and behavioral acceptance. Structural checks are not completion acceptance. "
            f"Sidecar files alone never establish live workers.</footer>{script}</main></body></html>")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ledger", help="directory with the requirements file (default: resolved from the current repo)")
    parser.add_argument("--session", default=os.environ.get("COPILOT_AGENT_SESSION_ID"), help="coordinator session id (default: this session)")
    parser.add_argument("--output", help="HTML file (default: this session's files/program-board.html)")
    parser.add_argument("--watch", type=int, metavar="SECONDS", help="regenerate every SECONDS until the program is quiet for 2 hours")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--reqs", help="comma-separated REQ IDs handled by this session")
    scope.add_argument("--all-reqs", action="store_true", help="deliberately show the entire repository ledger, including history")
    args = parser.parse_args()
    if args.reqs is not None:
        args.reqs = list(dict.fromkeys(rid.strip().upper() for rid in args.reqs.split(",") if rid.strip()))
        if not args.reqs:
            parser.error("--reqs needs at least one REQ ID")
    if not args.session:
        print("program-board: no --session and COPILOT_AGENT_SESSION_ID is unset", file=sys.stderr)
        return 2
    args.session = args.session.lower()
    if not gate.SESSION_UUID.fullmatch(args.session):
        print(f"program-board: --session {args.session!r} is not a host session UUID", file=sys.stderr)
        return 2
    if args.ledger:
        ledger = Path(args.ledger).expanduser().resolve()
    elif (Path.cwd() / "SPEC.md").is_file():
        ledger = Path.cwd().resolve()
    else:
        root = Path(gate.git(Path.cwd(), "rev-parse", "--show-toplevel") or Path.cwd())
        value = gate.configured_requirements(root, gate.load_config(root))
        ledger = (root / str(value)).resolve().parent if value else root
    args.output = args.output or str(STATE_HOME / args.session / "files" / "program-board.html")
    if not (ledger / "SPEC.md").is_file():
        print(f"program-board: {ledger}/SPEC.md not found", file=sys.stderr)
        return 2
    out = Path(args.output).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    lock = out.with_suffix(".pid")
    if args.watch:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            other = None
            try:
                other = int(lock.read_text())
                if not gate.pid_alive(other):
                    raise ValueError("stale")
                print(f"program-board: watcher {other} already running for {out}")
                return 0
            except (OSError, ValueError):
                stale = lock.with_suffix(f".stale.{os.getpid()}")
                try:
                    lock.rename(stale)
                    if stale.read_text().strip() != str(other):
                        stale.rename(lock)
                        print(f"program-board: another watcher took {lock}")
                        return 0
                    stale.unlink()
                    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                except OSError:
                    print(f"program-board: could not take {lock}; another watcher won", file=sys.stderr)
                    return 0
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
    pointer = STATE_HOME / args.session / "files" / gate.BOARD_POINTER
    stopped = threading.Event()
    handlers = {}
    if args.watch:
        for sig in (signal.SIGTERM, signal.SIGINT):
            handlers[sig] = signal.signal(sig, lambda _sig, _frame: stopped.set())
    try:
        if args.watch:
            pointer.parent.mkdir(parents=True, exist_ok=True)
            pointer.write_text(json.dumps({"pid": os.getpid(), "output": str(out), "ledger": str(ledger),
                                           "interval": max(args.watch, 30), "reqs": args.reqs}), encoding="utf-8")
        while True:
            try:
                data = build(ledger, args.session, args.reqs)
                data["refresh"] = args.watch
                tmp = out.with_suffix(f".{os.getpid()}.tmp")
                tmp.write_text(render(data), encoding="utf-8")
                tmp.replace(out)
                sidecar = out.with_suffix(".rotate.json")
                try:
                    previous = json.loads(sidecar.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    previous = {}
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                sidecar.write_text(json.dumps({x["id"]: {"flag": "rotate", "since": (previous.get(x["id"]) or {}).get("since", now)
                                                         if isinstance(previous.get(x["id"]), dict) else now}
                                               for x in data["sessions"] if x["rotate"] == "hard"}, indent=1), encoding="utf-8")
                print(f"program-board: {len(data['lanes'])} lanes, {len(data['sessions'])} sessions -> {out}", flush=True)
                newest = max((x["end"] for x in data["sessions"]), default=None)
            except Exception as exc:  # keep the last good board, report, retry next interval
                print(f"program-board: refresh failed: {exc}", file=sys.stderr, flush=True)
                if not args.watch:
                    return 1
                newest = datetime.now(timezone.utc)
            if not args.watch or newest is None or (datetime.now(timezone.utc) - newest).total_seconds() > 7200:
                return 0
            if stopped.wait(max(args.watch, 30)):
                return 0
    finally:
        if args.watch:
            try:
                data = build(ledger, args.session, args.reqs)
                data["stopped"] = True
                tmp = out.with_suffix(f".{os.getpid()}.tmp")
                tmp.write_text(render(data), encoding="utf-8")
                tmp.replace(out)
            except Exception as exc:
                print(f"program-board: final stopped snapshot failed; previous bytes retained: {exc}", file=sys.stderr, flush=True)
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
        if args.watch and lock.is_file() and lock.read_text().strip() == str(os.getpid()):
            lock.unlink()
            try:
                if json.loads(pointer.read_text(encoding="utf-8")).get("pid") == os.getpid():
                    pointer.unlink()
            except (OSError, ValueError, AttributeError):
                pass


if __name__ == "__main__":
    sys.exit(main())
