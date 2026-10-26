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


def read_session(sid: str) -> dict | None:
    path = STATE_HOME / sid / "events.jsonl"
    if not path.is_file():
        return None
    info = {"id": sid, "start": None, "end": None, "turns": [], "calls": 0, "input": 0, "output": 0,
            "max_context": 0, "context_limit": 0, "model": None, "agent": None, "complete": False, "children": []}
    pending: dict[str, tuple[str, str | None]] = {}
    turn_open = None
    for line in path.open(encoding="utf-8", errors="ignore"):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        kind, data, stamp = event.get("type"), event.get("data") or {}, when(event.get("timestamp"))
        if stamp:
            info["start"] = info["start"] or stamp
            info["end"] = stamp
        if kind == "session.start":
            info["model"] = data.get("selectedModel")
            info["start"] = when(data.get("startTime")) or info["start"]
        elif kind == "subagent.selected" and not info["turns"] and turn_open is None:
            info["agent"] = data.get("agentName")
        elif kind == "assistant.turn_start":
            turn_open = stamp
        elif kind == "assistant.turn_end" and turn_open and stamp:
            info["turns"].append((turn_open, stamp))
            turn_open = None
        elif kind == "session.usage_record":
            usage = data.get("usage") or {}
            info["calls"] += 1
            info["input"] += int(usage.get("inputTokens") or 0)
            info["output"] += int(usage.get("outputTokens") or 0)
            info["max_context"] = max(info["max_context"], int(usage.get("inputTokens") or 0))
            info["context_limit"] = max(info["context_limit"], int(usage.get("maxPromptTokens") or 0))
            info["model"] = usage.get("model") or info["model"]
        elif kind == "session.task_complete":
            info["complete"] = True
        elif kind == "tool.execution_start" and data.get("toolName") == "create_session":
            args = data.get("arguments") or {}
            pending[data.get("toolCallId")] = (args.get("name") or "child", (args.get("kickoff") or {}).get("agent"))
        elif kind == "tool.execution_complete" and data.get("toolCallId") in pending:
            match = re.search(r"\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b",
                              json.dumps(data.get("result", "")))
            name, agent = pending.pop(data.get("toolCallId"))
            if match:
                info["children"].append({"id": match.group(1), "name": name, "agent": agent})
    if turn_open and info["end"]:
        info["turns"].append((turn_open, info["end"]))
    merged: list[tuple[datetime, datetime]] = []
    for a, b in sorted(info["turns"]):
        if merged and (a - merged[-1][1]).total_seconds() < 60:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    info["spans"] = merged
    info["idle_min"] = ((datetime.now(timezone.utc) - info["end"]).total_seconds() / 60) if info["end"] else None
    info["active_min"] = sum((b - a).total_seconds() for a, b in info["turns"]) / 60
    info["wall_min"] = ((info["end"] - info["start"]).total_seconds() / 60) if info["start"] and info["end"] else 0
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


def build(ledger: Path, coordinator: str) -> dict:
    text = (ledger / "SPEC.md").read_text(encoding="utf-8")
    reqs, _corrections, _errors = gate.parse_requirements(text)
    lanes = gate.ledger_table(text, ("lane", "repo", "project id"), gate.LANE_COLUMNS)
    commit = subprocess.run(["git", "-C", str(ledger), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    root = read_session(coordinator)
    sessions = [root] if root else []
    names = {}
    for child in (root or {}).get("children", []):
        if child["id"] in names:
            continue
        info = read_session(child["id"])
        names[child["id"]] = child["name"]
        if info:
            info["name"], info["agent"] = child["name"], child["agent"] or info["agent"]
            sessions.append(info)
    if root:
        root["name"] = "Coordinator"
    lane_by_session = {lane["session id"]: lane for lane in lanes if lane["session id"] not in {"", "-"}}
    return {"ledger": ledger, "commit": commit, "reqs": reqs, "lanes": lanes, "sessions": sessions,
            "lane_by_session": lane_by_session, "generated": datetime.now(timezone.utc)}


def timeline(sessions: list[dict], lane_by_session: dict) -> str:
    timed = [s for s in sessions if s["start"] and s["end"]]
    if not timed:
        return "<p class='note'>No local session logs found for this program.</p>"
    t0, t1 = min(s["start"] for s in timed), max(s["end"] for s in timed)
    span = max((t1 - t0).total_seconds(), 60)
    top_tokens = max(s["input"] + s["output"] for s in timed) or 1
    width, row, left, gauge = 300, 40, 104, 92
    rows = []
    for i, s in enumerate(timed):
        y = 16 + i * row
        lane = lane_by_session.get(s["id"]) or {}
        tone = LANE_TONE.get(lane.get("state", "").lower(), "active")
        x = left + (s["start"] - t0).total_seconds() / span * width
        w = max((s["end"] - s["start"]).total_seconds() / span * width, 2)
        marks = "".join(f"<rect class='turn' x='{left + (a - t0).total_seconds() / span * width:.1f}' y='{y + 2}' "
                        f"width='{max((b - a).total_seconds() / span * width, 1):.1f}' height='6'/>" for a, b in s["spans"])
        ctx = (s["max_context"] / s["context_limit"]) if s["context_limit"] else 0
        tok = (s["input"] + s["output"]) / top_tokens
        gx = left + width + 12
        agent = (s["agent"] or "default").replace("architrave:", "")
        rows.append(
            f"<g><title>{esc(s['name'])}: {s['wall_min']:.0f} min wall, {s['active_min']:.0f} min model; "
            f"{s['calls']} calls; {s['input']:,} in / {s['output']:,} out tokens; peak context {s['max_context']:,} of {s['context_limit']:,}</title>"
            f"<text class='label' x='0' y='{y + 8}'>{esc(s['name'] if len(s['name']) <= 17 else s['name'][:16] + '…')}</text>"
            f"<text class='sub' x='0' y='{y + 19}'>{esc(agent[:22])}</text>"
            f"<rect class='lane-bg' x='{left}' y='{y}' width='{width}' height='10'/>"
            f"<rect class='track {tone}' x='{x:.1f}' y='{y}' width='{w:.1f}' height='10'/>{marks}"
            f"<text class='sub' x='{left}' y='{y + 22}'>{s['active_min']:.0f} model / {s['wall_min']:.0f} wall min · {esc(state_of(s, lane))}</text>"
            f"<rect class='gauge' x='{gx}' y='{y}' width='{gauge}' height='4'/><rect class='ctxfill' x='{gx}' y='{y}' width='{gauge * min(ctx, 1):.1f}' height='4'/>"
            f"<text class='sub' x='{gx}' y='{y + 12}'>ctx {num(s['max_context'])} / {num(s['context_limit'])}</text>"
            f"<rect class='gauge' x='{gx}' y='{y + 16}' width='{gauge}' height='4'/><rect class='tokfill' x='{gx}' y='{y + 16}' width='{gauge * tok:.1f}' height='4'/>"
            f"<text class='sub' x='{gx}' y='{y + 28}'>tok {num(s['input'])} in · {num(s['output'])} out</text></g>")
    ticks = "".join(f"<text class='tick' x='{left + f * width:.0f}' y='9' text-anchor='{'start' if f == 0 else 'end' if f == 1 else 'middle'}'>"
                    f"{datetime.fromtimestamp(t0.timestamp() + f * span).strftime('%H:%M')}</text>" for f in (0, .5, 1))
    heads = (f"<text class='tick' x='{left + width + 12}' y='9'>context peak · tokens</text>")
    return (f"<svg class='timeline' viewBox='0 0 {left + width + 12 + gauge} {16 + len(timed) * row}' role='img' "
            f"aria-label='How the sessions ran'>{ticks}{heads}{''.join(rows)}</svg>"
            f"<p class='note'>Bar: first to last event; dark marks: model turns. Gauges: peak context against the "
            f"model limit, and tokens relative to the busiest session. Hover a row for exact numbers.</p>")


def render(data: dict) -> str:
    reqs, lanes, sessions = data["reqs"], data["lanes"], data["sessions"]
    active_req = {rid: r for rid, r in reqs.items() if r["status"].lower() not in gate.REQ_CLOSED}
    accepted = sum(1 for r in active_req.values() if r["status"].lower() == "accepted")
    total_in, total_out = sum(s["input"] for s in sessions), sum(s["output"] for s in sessions)
    active = sum(s["active_min"] for s in sessions)
    wall = max((s["wall_min"] for s in sessions), default=0)
    running = sum(1 for lane in lanes if lane["state"].lower() == "running")
    stats = [("REQs accepted", f"{accepted}/{len(active_req)}"), ("lanes running", f"{running}/{len(lanes)}"),
             ("sessions", str(len(sessions))), ("tokens in/out", f"{num(total_in)}/{num(total_out)}"),
             ("model min", f"{active:.0f}"), ("wall min", f"{wall:.0f}")]
    overview = "".join(f"<div><b>{esc(v)}</b><span>{esc(k)}</span></div>" for k, v in stats)
    boxes = []
    for lane in lanes:
        ids = [rid.upper() for rid in re.findall(r"REQ-[A-Za-z0-9_.-]+", lane["req ids"], re.I)]
        squares = "".join(
            f"<button class='sq {REQ_TONE.get(reqs[r]['status'].lower(), 'open') if r in reqs else 'open'}' "
            f"data-d='{esc(r)} · {esc(reqs[r]['status'] if r in reqs else 'unknown')} · {esc((reqs[r]['requirement'] if r in reqs else '')[:160])}' "
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
.legend{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:10px;color:#d3dee8;margin:4px 0 8px}.legend i{display:inline-block;width:9px;height:9px;margin-right:4px;vertical-align:-1px}
.done{background:#38aa6b;fill:#38aa6b}.active{background:#479bc1;fill:#479bc1}.blocked{background:#e05b6b;fill:#e05b6b}.open{background:#506071;fill:#506071}.gone{background:#33404e;fill:#33404e}
.boxes{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:6px}
.box{background:#1b2632;border:1px solid #7a8c9e;padding:5px 6px 6px}.box.blocked{border-color:#f08895}.box.done{border-color:#38aa6b}.box.gone{opacity:.45}
.box h3{margin:0;font-size:10.5px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.box p{margin:0 0 4px;font-size:9px;color:#bacada}
.grid{display:grid;grid-template-columns:repeat(auto-fill,11px);gap:1px}
.sq{width:11px;height:11px;padding:0;border:0;cursor:pointer}.sq:hover,.sq:focus-visible,.sq.sel{outline:1.5px solid #fff;outline-offset:0}
#detail{min-height:28px;margin:8px 0 0;padding-top:6px;border-top:1px solid #415064;font-size:11px;color:#c6d4e1;overflow-wrap:anywhere}
.timeline{width:100%;display:block}.timeline .label{fill:#edf3f8;font-size:8.5px;font-weight:600}.timeline .sub{fill:#9fb0c1;font-size:6.5px}.timeline .tick{fill:#8fa1b3;font-size:6.5px}.lane-bg,.gauge{fill:#1b2632}.turn{fill:#0b1016;opacity:.55}.ctxfill{fill:#d6aa4b}.tokfill{fill:#479bc1}
footer{font-size:9px;color:#8fa1b3;margin-top:10px;line-height:1.5}
"""
    legend = ("<div class='legend'><span><i class='done'></i>accepted</span><span><i class='active'></i>claimed</span>"
              "<span><i class='blocked'></i>blocked</span><span><i class='open'></i>open</span></div>")
    script = ("<script>const d=document.getElementById('detail');document.querySelectorAll('.sq').forEach(b=>b.onclick=()=>{"
              "document.querySelectorAll('.sq.sel').forEach(x=>x.classList.remove('sel'));b.classList.add('sel');d.textContent=b.dataset.d});</script>")
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
            f"<title>Program board</title><style>{css}</style></head><body><main>"
            f"<h1>{esc(data['ledger'].name)} · program</h1><p class='note'>ledger {esc(data['commit'])} · "
            f"{data['generated'].strftime('%Y-%m-%d %H:%M UTC')} snapshot</p>"
            f"<div class='stats'>{overview}</div>"
            f"<h2>Lanes</h2>{legend}<div class='boxes'>{''.join(boxes) or '<p class=note>No lane table.</p>'}</div>"
            f"<p id='detail'>Select a square to see its requirement.</p>"
            f"<h2>How the sessions ran</h2>{timeline(sessions, data['lane_by_session'])}"
            f"<footer>Squares show ledger status; acceptance evidence is not re-verified here. Metrics come from this "
            f"machine's session logs; input tokens include cached reads.</footer>{script}</main></body></html>")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ledger", required=True, help="directory containing the program SPEC.md")
    parser.add_argument("--session", required=True, help="coordinator session id")
    parser.add_argument("--output", required=True, help="HTML file to write")
    args = parser.parse_args()
    ledger = Path(args.ledger).expanduser().resolve()
    if not (ledger / "SPEC.md").is_file():
        print(f"program-board: {ledger}/SPEC.md not found", file=sys.stderr)
        return 2
    data = build(ledger, args.session)
    out = Path(args.output).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data), encoding="utf-8")
    print(f"program-board: {len(data['lanes'])} lanes, {len(data['sessions'])} sessions -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
