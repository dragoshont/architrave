#!/usr/bin/env python3
"""Program board: one standalone HTML view of a coordinated program.

Usage: python harness/program_board.py --ledger <dir with SPEC.md> --session <coordinator-session-id> --output <file.html>

Reads only committed ledger tables (REQs, lanes) and the host's local session logs
(~/.copilot/session-state/<id>/events.jsonl) for the coordinator and the child
sessions it created. Writes one HTML file with no network requests; open it in
the browser canvas. It never changes a ledger, session or repository.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

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
SESSION_ID = re.compile(r"\b([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\b")


def as_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def read_session(sid: str, since: datetime | None = None) -> dict | None:
    path = STATE_HOME / sid / "events.jsonl"
    if not path.is_file():
        return None
    info = {"id": sid, "start": None, "end": None, "turns": [], "calls": 0, "input": 0, "cached": 0, "output": 0,
            "max_context": 0, "context_limit": 0, "model": None, "agent": None, "children": []}
    pending: dict[str, tuple[str, str | None]] = {}
    turn_open = None
    for line in path.open(encoding="utf-8", errors="ignore"):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        kind = event.get("type")
        stamp = when(event["timestamp"]) if isinstance(event.get("timestamp"), str) else None
        if since and stamp and stamp < since:
            continue
        if stamp:
            info["start"] = min(info["start"], stamp) if info["start"] else stamp
            info["end"] = max(info["end"], stamp) if info["end"] else stamp
        if kind == "session.start":
            info["model"] = data.get("selectedModel") if isinstance(data.get("selectedModel"), str) else info["model"]
            if not since and isinstance(data.get("startTime"), str):
                info["start"] = when(data["startTime"]) or info["start"]
        elif kind == "subagent.selected" and not info["turns"] and turn_open is None:
            info["agent"] = data.get("agentName") if isinstance(data.get("agentName"), str) else None
        elif kind == "assistant.turn_start":
            turn_open = stamp
        elif kind == "assistant.turn_end" and turn_open and stamp:
            info["turns"].append((turn_open, stamp))
            turn_open = None
        elif kind == "session.usage_record":
            usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
            prompt, cached = as_int(usage.get("inputTokens")), as_int(usage.get("cacheReadTokens"))
            info["calls"] += 1
            info["input"] += max(prompt - cached, 0)
            info["cached"] += cached
            info["output"] += as_int(usage.get("outputTokens"))
            info["max_context"] = max(info["max_context"], prompt)
            info["context_limit"] = max(info["context_limit"], as_int(usage.get("maxPromptTokens")))
            if isinstance(usage.get("model"), str):
                info["model"] = usage["model"]
        elif kind == "tool.execution_start" and data.get("toolName") in SPAWN_TOOLS:
            args = data.get("arguments") if isinstance(data.get("arguments"), dict) else {}
            kickoff = args.get("kickoff") if isinstance(args.get("kickoff"), dict) else {}
            name = args.get("name") if isinstance(args.get("name"), str) else str(data.get("toolName"))
            pending[str(data.get("toolCallId"))] = (name, kickoff.get("agent") if isinstance(kickoff.get("agent"), str) else None)
        elif kind == "tool.execution_complete" and str(data.get("toolCallId")) in pending:
            match = SESSION_ID.search(json.dumps(data.get("result", "")))
            name, agent = pending.pop(str(data.get("toolCallId")))
            if match:
                info["children"].append({"id": match.group(1).lower(), "name": name, "agent": agent})
    if turn_open and info["end"]:
        info["turns"].append((turn_open, info["end"]))
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
    return info


def state_of(s: dict, lane: dict) -> str:
    label = lane.get("state") or ("coordinator" if s.get("name") == "Coordinator" else "")
    idle = s.get("idle_min")
    activity = "no log" if idle is None else "active now" if idle < 10 else f"idle {idle:.0f} min"
    return f"{label} · {activity}" if label else activity


def esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def num(value: float) -> str:
    return f"{value / 1_000_000:.1f}M" if value >= 1_000_000 else f"{value / 1000:.0f}k" if value >= 1000 else f"{value:.0f}"


RESOLVED: dict[tuple[str, str], bool] = {}


def evidence_resolves(evidence: str, repos: list[Path]) -> bool:
    for sha in re.findall(r"(?<![0-9a-fA-F])[0-9a-fA-F]{7,40}(?![0-9a-fA-F])", evidence):
        for repo in repos:
            key = (str(repo), sha)
            if key not in RESOLVED:
                RESOLVED[key] = gate.git(repo, "cat-file", "-e", f"{sha}^{{commit}}") is not None
            if RESOLVED[key]:
                return True
    return False


def build(ledger: Path, coordinator: str) -> dict:
    path = ledger / "SPEC.md"
    text = path.read_text(encoding="utf-8")
    reqs, _corrections, errors = gate.parse_requirements(text)
    lanes = gate.ledger_table(text, ("lane", "repo", "project id"), gate.LANE_COLUMNS)
    config = gate.load_config(ledger) if (ledger / "architrave.config.json").is_file() else {}
    more, _blockers, _notes = gate.chain_errors(ledger, text, reqs, config)
    workers = config.get("workers") or {}
    cap = workers.get("maxParallel", 3) if isinstance(workers, dict) else 3
    errors += more + gate.header_errors(text) + gate.lane_errors(text, reqs, cap if isinstance(cap, int) else 3)
    repos = [ledger] + [gate.component_path(ledger, c["path"]) for c in config.get("components") or []
                        if isinstance(c, dict) and isinstance(c.get("path"), str)]
    repos = [r for r in repos if gate.git(r, "rev-parse", "--git-dir") is not None]
    unverified = {rid for rid, r in reqs.items() if r["status"].lower() == "accepted" and not evidence_resolves(r["evidence"], repos)}
    laned = {rid.upper() for lane in lanes for rid in re.findall(r"REQ-[A-Za-z0-9_.-]+", lane["req ids"], re.I)}
    loose = [rid for rid, r in reqs.items() if rid not in laned and r["status"].lower() not in gate.REQ_CLOSED]
    if loose:
        lanes = lanes + [dict.fromkeys(gate.LANE_COLUMNS, "") | {"lane": "Not in a lane" if lanes else "Requirements",
                                                                 "repo": ledger.name, "state": "idle", "req ids": ", ".join(loose)}]
    commit = subprocess.run(["git", "-C", str(ledger), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
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
            "lane_by_session": lane_by_session, "errors": errors, "unverified": unverified, "generated": datetime.now(timezone.utc)}


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
        tone = LANE_TONE.get(lane.get("state", "").lower(), "active")
        x = left + max((s["start"] - t0).total_seconds(), 0) / span * width
        w = max((s["end"] - max(s["start"], t0)).total_seconds() / span * width, 2)
        marks = "".join(f"<rect class='turn' x='{left + (a - t0).total_seconds() / span * width:.1f}' y='{y + 2}' "
                        f"width='{max((b - a).total_seconds() / span * width, 1):.1f}' height='6'/>" for a, b in s["spans"] if b >= t0)
        ctx = (s["max_context"] / s["context_limit"]) if s["context_limit"] else 0
        tok = (s["input"] + s["cached"] + s["output"]) / top_tokens
        gx = left + width + 12
        agent = (s["agent"] or "default").replace("architrave:", "")
        rows.append(
            f"<g><title>{esc(s['name'])}: {s['wall_min']:.0f} min wall, {s['active_min']:.0f} min model; "
            f"{s['calls']} calls; {s['input']:,} fresh in, {s['cached']:,} cached, {s['output']:,} out tokens; peak context {s['max_context']:,} of {s['context_limit']:,}</title>"
            f"<text class='label' x='0' y='{y + 8}'>{esc(s['name'] if len(s['name']) <= 17 else s['name'][:16] + '…')}</text>"
            f"<text class='sub' x='0' y='{y + 19}'>{esc(agent[:22])}</text>"
            f"<rect class='lane-bg' x='{left}' y='{y}' width='{width}' height='10'/>"
            f"<rect class='track {tone}' x='{x:.1f}' y='{y}' width='{w:.1f}' height='10'/>{marks}"
            f"<text class='sub' x='{left}' y='{y + 22}'>{'started earlier · ' if s['start'] < t0 else ''}{s['active_min']:.0f} model / {s['wall_min']:.0f} wall min · {esc(state_of(s, lane))}</text>"
            f"<rect class='gauge' x='{gx}' y='{y}' width='{gauge}' height='4'/><rect class='ctxfill' x='{gx}' y='{y}' width='{gauge * min(ctx, 1):.1f}' height='4'/>"
            f"<text class='sub' x='{gx}' y='{y + 12}'>ctx {num(s['max_context'])} / {num(s['context_limit'])}</text>"
            f"<rect class='gauge' x='{gx}' y='{y + 16}' width='{gauge}' height='4'/><rect class='tokfill' x='{gx}' y='{y + 16}' width='{gauge * tok:.1f}' height='4'/>"
            f"<text class='sub' x='{gx}' y='{y + 28}'>tok {num(s['input'])} new · {num(s['cached'])} cache · {num(s['output'])} out</text></g>")
    for j, lane in enumerate(remote):
        y = 16 + (len(timed) + j) * row
        rows.append(f"<g><text class='label' x='0' y='{y + 8}'>{esc(lane['lane'][:17])}</text>"
                    f"<rect class='lane-bg remote' x='{left}' y='{y}' width='{width}' height='10'/>"
                    f"<text class='sub' x='{left}' y='{y + 22}'>{esc(lane['state'])} · not logged on this machine</text></g>")
    ticks = "".join(f"<text class='tick' x='{left + f * width:.0f}' y='9' text-anchor='{'start' if f == 0 else 'end' if f == 1 else 'middle'}'>"
                    f"{datetime.fromtimestamp(t0.timestamp() + f * span).strftime('%H:%M')}</text>" for f in (0, .5, 1))
    heads = (f"<text class='tick' x='{left + width + 12}' y='9'>context peak · tokens</text>")
    return (f"<svg class='timeline' viewBox='0 0 {left + width + 12 + gauge} {16 + (len(timed) + len(remote)) * row}' role='img' "
            f"aria-label='How the sessions ran'>{ticks}{heads}{''.join(rows)}</svg>"
            f"<p class='note'>Bar: first to last event; dark marks: model turns. Gauges: peak context against the "
            f"model limit, and tokens relative to the busiest session. Hover a row for exact numbers.</p>")


def render(data: dict) -> str:
    reqs, lanes, sessions = data["reqs"], data["lanes"], data["sessions"]
    active_req = {rid: r for rid, r in reqs.items() if r["status"].lower() not in gate.REQ_CLOSED}
    accepted = sum(1 for r in active_req.values() if r["status"].lower() == "accepted")
    total_in, total_out = sum(s["input"] for s in sessions), sum(s["output"] for s in sessions)
    total_cached = sum(s["cached"] for s in sessions)
    unverified = data["unverified"]
    active = sum(s["active_min"] for s in sessions)
    wall = ((max(s["end"] for s in sessions) - sessions[0]["start"]).total_seconds() / 60) if sessions else 0
    running = sum(1 for lane in lanes if lane["state"].lower() == "running")
    stats = [("REQs accepted", f"{accepted}/{len(active_req)}"),
             ("gate", "PASS" if not data["errors"] else f"{len(data['errors'])} issues"),
             ("accepted, evidence unresolved", str(len(unverified & set(active_req)))), ("lanes running", f"{running}/{len(lanes)}"),
             ("sessions", str(len(sessions))), ("tokens new/cache/out", f"{num(total_in)}/{num(total_cached)}/{num(total_out)}"),
             ("model min, all sessions", f"{active:.0f}"), ("program min", f"{wall:.0f}")]
    overview = "".join(f"<div><b>{esc(v)}</b><span>{esc(k)}</span></div>" for k, v in stats)
    boxes = []
    for lane in lanes:
        ids = [rid.upper() for rid in re.findall(r"REQ-[A-Za-z0-9_.-]+", lane["req ids"], re.I)]
        squares = "".join(
            f"<button class='sq {REQ_TONE.get(reqs[r]['status'].lower(), 'open') if r in reqs else 'open'}{' warn' if r in unverified else ''}' "
            f"data-d='{esc(r)} · {esc(reqs[r]['status'] if r in reqs else 'unknown')}{' · no evidence commit resolves' if r in unverified else ''} · {esc((reqs[r]['requirement'] if r in reqs else '')[:160])}' "
            f"aria-label='{esc(r)} {esc(reqs[r]['status'] if r in reqs else 'unknown')}'></button>" for r in ids)
        done = sum(1 for r in ids if r in reqs and reqs[r]["status"].lower() == "accepted")
        tone = LANE_TONE.get(lane["state"].lower(), "open")
        boxes.append(f"<section class='box {tone}'><h3>{esc(lane['lane'])}</h3><p>{esc(lane['state'])} · {done}/{len(ids)}</p>"
                     f"<div class='grid'>{squares}</div></section>")
    css = """
:root{color-scheme:dark;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#10161e;color:#edf3f8}
*{box-sizing:border-box}body{margin:0}main{padding:14px 14px 12px;max-width:760px;margin:auto}
h1{margin:0;font-size:17px;font-weight:650;letter-spacing:-.02em}h2{margin:16px 0 6px;font-size:11px;font-weight:600;color:#b8c6d5;text-transform:uppercase;letter-spacing:.06em}
.note{margin:3px 0;font-size:10px;color:#b8c6d5}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:#2a3644;margin-top:10px;border:1px solid #2a3644}
.stats div{background:#1b2632;padding:7px 8px}.stats b{display:block;font-size:15px;font-variant-numeric:tabular-nums}.stats span{font-size:10px;color:#b8c6d5}
.legend{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:10px;color:#d3dee8;margin:4px 0 8px}.legend i{display:inline-block;width:9px;height:9px;margin-right:4px;vertical-align:-1px}.legend i.warn{box-shadow:inset 0 0 0 2px #d6aa4b}
.done{background:#38aa6b;fill:#38aa6b}.active{background:#479bc1;fill:#479bc1}.blocked{background:#e05b6b;fill:#e05b6b}.open{background:#506071;fill:#506071}.gone{background:#33404e;fill:#33404e}
.boxes{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:6px}
.box{background:#1b2632;border:1px solid #7a8c9e;padding:5px 6px 6px}.box.blocked{border-color:#f08895}.box.done{border-color:#38aa6b}.box.gone{opacity:.45}
.box h3{margin:0;font-size:10.5px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.box p{margin:0 0 4px;font-size:9px;color:#bacada}
.grid{display:grid;grid-template-columns:repeat(auto-fill,11px);gap:1px}
.sq{width:11px;height:11px;padding:0;border:0;cursor:pointer}.sq.warn{box-shadow:inset 0 0 0 2px #d6aa4b}.remote{fill:none;stroke:#506071;stroke-dasharray:3 2}.issues{margin:6px 0 0;padding-left:16px;font-size:10px;color:#f0a0aa}.sq:hover,.sq:focus-visible,.sq.sel{outline:1.5px solid #fff;outline-offset:0}
#detail{min-height:28px;margin:8px 0 0;padding-top:6px;border-top:1px solid #415064;font-size:11px;color:#c6d4e1;overflow-wrap:anywhere}
.timeline{width:100%;display:block}.timeline .label{fill:#edf3f8;font-size:8.5px;font-weight:600}.timeline .sub{fill:#9fb0c1;font-size:6.5px}.timeline .tick{fill:#8fa1b3;font-size:6.5px}.lane-bg,.gauge{fill:#1b2632}.turn{fill:#0b1016;opacity:.55}.ctxfill{fill:#d6aa4b}.tokfill{fill:#479bc1}
footer{font-size:9px;color:#8fa1b3;margin-top:10px;line-height:1.5}
"""
    legend = ("<div class='legend'><span><i class='done'></i>accepted</span><span><i class='active'></i>claimed</span>"
              "<span><i class='blocked'></i>blocked</span><span><i class='open'></i>open</span><span><i class='open warn'></i>accepted, evidence unresolved</span></div>")
    script = ("<script>const d=document.getElementById('detail');document.querySelectorAll('.sq').forEach(b=>b.onclick=()=>{"
              "document.querySelectorAll('.sq.sel').forEach(x=>x.classList.remove('sel'));b.classList.add('sel');d.textContent=b.dataset.d});</script>")
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
            + (f"<meta http-equiv='refresh' content='{data['refresh']}'>" if data.get("refresh") else "") + f"<title>Program board</title><style>{css}</style></head><body><main>"
            f"<h1>{esc(data['ledger'].name)} · program</h1><p class='note'>ledger {esc(data['commit'])} · "
            f"{data['generated'].strftime('%Y-%m-%d %H:%M UTC')} snapshot</p>"
            f"<div class='stats'>{overview}</div>"
            + ("<ul class='issues'>" + "".join(f"<li>{esc(e)}</li>" for e in data["errors"][:5]) + "</ul>" if data["errors"] else "")
            + f"<h2>Lanes</h2>{legend}<div class='boxes'>{''.join(boxes) or '<p class=note>No lane table.</p>'}</div>"
            f"<p id='detail'>Select a square to see its requirement.</p>"
            f"<h2>How the sessions ran</h2>{timeline(sessions, data['lane_by_session'], data['remote'])}"
            f"<footer>Squares show ledger status; a gold ring means no commit in its evidence resolves in the ledger or a "
            f"configured component. Gate issues come from the same checks as `requirements`. Sessions not logged on this "
            f"machine are listed without metrics.</footer>{script}</main></body></html>")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ledger", help="directory with the requirements file (default: resolved from the current repo)")
    parser.add_argument("--session", default=os.environ.get("COPILOT_AGENT_SESSION_ID"), help="coordinator session id (default: this session)")
    parser.add_argument("--output", help="HTML file (default: this session's files/program-board.html)")
    parser.add_argument("--watch", type=int, metavar="SECONDS", help="regenerate every SECONDS until the program is quiet for 2 hours")
    args = parser.parse_args()
    if not args.session:
        print("program-board: no --session and COPILOT_AGENT_SESSION_ID is unset", file=sys.stderr)
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
            other = int(lock.read_text())
            os.kill(other, 0)
            print(f"program-board: watcher {other} already running for {out}")
            return 0
        except (OSError, ValueError):
            lock.write_text(str(os.getpid()))
    try:
        while True:
            try:
                data = build(ledger, args.session)
                data["refresh"] = args.watch
                tmp = out.with_suffix(f".{os.getpid()}.tmp")
                tmp.write_text(render(data), encoding="utf-8")
                tmp.replace(out)
                print(f"program-board: {len(data['lanes'])} lanes, {len(data['sessions'])} sessions -> {out}", flush=True)
                newest = max((x["end"] for x in data["sessions"]), default=None)
            except Exception as exc:  # keep the last good board, report, retry next interval
                print(f"program-board: refresh failed: {exc}", file=sys.stderr, flush=True)
                if not args.watch:
                    return 1
                newest = datetime.now(timezone.utc)
            if not args.watch or newest is None or (datetime.now(timezone.utc) - newest).total_seconds() > 7200:
                return 0
            time.sleep(max(args.watch, 30))
    finally:
        if args.watch and lock.is_file() and lock.read_text().strip() == str(os.getpid()):
            lock.unlink()


if __name__ == "__main__":
    sys.exit(main())
