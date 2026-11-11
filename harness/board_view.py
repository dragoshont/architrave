#!/usr/bin/env python3
"""Shared, offline HTML/CSS/SVG dashboard; display only, never a lifecycle writer."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path

ASSETS = Path(__file__).resolve().parent


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def compact(value) -> str:
    if value is None:
        return "Unknown"
    if 0 < value < 1:
        return "<1"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1000:
        return f"{value / 1000:.1f}k"
    return f"{value:,.0f}"


def date(value) -> str:
    if not value:
        return "Unknown"
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%d %b %H:%M UTC")


def details(label: str, body: str, cls="") -> str:
    return f"<details class='{cls}'><summary>{esc(label)}</summary>{body}</details>"


def facts(rows) -> str:
    return "<dl class='facts'>" + "".join(
        f"<div><dt>{esc(k)}</dt><dd>{esc('Unknown' if v is None else v)}</dd></div>" for k, v in rows) + "</dl>"


def listing(rows, empty="None recorded") -> str:
    rows = list(rows)
    return "<ul>" + "".join(f"<li>{esc(row)}</li>" for row in rows) + "</ul>" if rows else f"<p class='muted'>{esc(empty)}</p>"


def badge(text, tone="neutral") -> str:
    return f"<span class='badge {esc(tone)}'>{esc(text)}</span>"


def task_state(task) -> tuple[str, str]:
    progress = {"Code ready": "ready", "In progress": "working", "": "open"}[task["progress"]]
    return progress, task["progress"] or "Not started"


def task_inspector(task, view) -> str:
    progress, label = task_state(task)
    criteria = []
    for criterion in task["acceptance"]:
        proofs = []
        for proof in criterion["evidence"]:
            applicability = proof["applicability"]
            status = f"{proof['result'].capitalize()} recorded / {applicability}"
            proofs.append(details(status, facts([
                ("Method", proof["method"]), ("Artifact", proof["artifact"]),
                ("Observed", proof["observed_at"]), ("Binding", applicability),
                ("Checked subject", json.dumps(proof.get("identity", "unavailable"), sort_keys=True)),
                ("Attempt", proof.get("attempt_id", "unavailable")), ("Limitations", proof["limitations"]),
            ]), "proof"))
        criteria.append(f"<li class='criterion'><span class='kind'>{esc(criterion['kind'])}</span>"
                        f"<p>{esc(criterion['expected'])}</p>"
                        + ("".join(proofs) if proofs else "<p class='muted'>Acceptance unverified: no evidence recorded.</p>") + "</li>")
    corrections = [c for c in view["corrections"] if c["target"] == task["id"]
                   or c["collection"] in {"constraints", "decisions", "goals"}]
    audit = "".join(details(f"Revision {c['revision']} / {c['kind']}",
                           f"<p>before: {esc(json.dumps(c['before'], sort_keys=True))}</p>"
                           f"<p>after: {esc(json.dumps(c['after'], sort_keys=True))}</p>"
                           f"<p>Sources: {esc(', '.join(c['source_refs']))}</p>") for c in corrections)
    owners = "; ".join(f"{o['worker']}: {o['activity']} / stop {o['stop']}" for o in task["owners"])
    return (f"<details class='inspector' id='task-{esc(task['id'])}' data-inspector='{esc(task['id'])}'>"
            f"<summary>{esc(task['title'])}</summary><div class='inspector-body'>"
            f"<h3 id='inspect-title-{esc(task['id'])}' tabindex='-1'>{esc(task['title'])}</h3><div class='badges'>{badge(label, progress)}"
            f"{badge('Readiness: ' + task['readiness'], 'warning' if task['readiness'] in {'stale', 'unavailable'} else 'neutral')}"
            f"{badge(task['disposition'])}</div>"
            f"<p class='owner'>{esc(owners or 'No live owner recorded; current host activity is unknown.')}</p>"
            + (f"<h4>Holds &amp; reservations</h4>{listing(task['holds'])}" if task["holds"] else "")
            + f"<h4>Acceptance &amp; evidence</h4><ol class='criteria'>{''.join(criteria)}</ol>"
            + ("<p class='muted'>No acceptance criteria declared for this item.</p>" if not criteria else "")
            + "<p class='boundary'>A matching recorded pass is source-bound evidence, not a new verification of the current workspace.</p>"
            + (f"<h4>Applicable constraints</h4>{listing(c['statement'] for c in task['constraints'])}" if task["constraints"] else "")
            + details("Task provenance & history", facts([
                ("Stable ID", task["id"]), ("Goal", task["goal_id"]), ("Activation", task["activation"]),
                ("Dependencies", ", ".join(task["depends_on"]) or "None"),
                ("Source references", ", ".join(task["source_refs"])),
            ]) + audit)
            + "</div></details>")


def session_history(sessions) -> str:
    if not sessions or all(session["coverage"] == "unavailable" for session in sessions):
        return ("<div class='empty'><h3>No session observations yet</h3>"
                "<p>Task progress above is available. Collect the explicitly selected sessions into observations YAML "
                "to see supported activity and usage here. Missing values are not zero.</p></div>")
    starts = [datetime.fromisoformat(s["start"].replace("Z", "+00:00")).timestamp() for s in sessions if s["start"]]
    ends = [datetime.fromisoformat(s["end"].replace("Z", "+00:00")).timestamp() for s in sessions if s["end"]]
    t0, t1 = min(starts, default=0), max(ends, default=0)
    span = max(t1 - t0, 1)
    rows = []
    for session in sessions:
        bars = []
        for a, b in session["intervals"]:
            x = max(0, (datetime.fromisoformat(a.replace("Z", "+00:00")).timestamp() - t0) / span * 600)
            width = max(1, (datetime.fromisoformat(b.replace("Z", "+00:00")).timestamp()
                            - datetime.fromisoformat(a.replace("Z", "+00:00")).timestamp()) / span * 600)
            bars.append(f"<rect x='{x:.3f}' y='2' width='{width:.3f}' height='8' rx='1'/>")
        metrics = session["metrics"]
        context = session["context"]
        ring = "<div class='context-unknown'>Unknown<span>Context</span></div>"
        if context["used"] is not None:
            percentage = context["used"] / context["limit"] * 100
            ring = (f"<svg class='context-ring' viewBox='0 0 80 80' role='img' "
                    f"aria-label='{context['used']:,} of {context['limit']:,} reported context tokens'>"
                    "<circle class='ring-track' cx='40' cy='40' r='34'/>"
                    f"<circle class='ring-value' cx='40' cy='40' r='34' pathLength='100' "
                    f"stroke-dasharray='{percentage:.3f} {100 - percentage:.3f}' transform='rotate(-90 40 40)'/>"
                    f"<text x='40' y='39' text-anchor='middle'>{esc(compact(context['used']))}</text>"
                    "<text class='ring-caption' x='40' y='53' text-anchor='middle'>Context</text></svg>")
        name = "Coordinator" if session["coordinator"] else "Assigned session"
        counts = " / ".join(compact(metrics[k]) for k in ("input_tokens", "output_tokens", "cache_read_tokens"))
        model = session["model"] or session["selected_model"] or "Model unavailable"
        model_kind = "Observed" if session["model"] else "Selected" if session["selected_model"] else "Unreported"
        provenance = facts([("Session", session["id"]), ("Task links", ", ".join(session["task_ids"]) or "Coordinator source"),
                            ("Source", session["source"]), ("Source generation", session["source_identity"]),
                            ("Captured", session["captured_at"]), ("Activity observed", session["observed_at"]),
                            ("Context observed", context["observed_at"]), ("Context capacity", context["limit"]),
                            ("Event window", session["coverage"]), ("Input / output / cache", counts),
                            ("Recorded turn seconds", metrics["assistant_turn_seconds"])])
        rows.append(f"<article class='session-row'><div class='session-name'><h3>{esc(name)}</h3>"
                    f"<p>{esc(model_kind)}: {esc(model)}</p></div><div class='session-chart'>"
                    "<svg class='waterfall' viewBox='0 0 600 12' preserveAspectRatio='none' role='img' "
                    "aria-label='Recorded assistant-turn intervals, not provider inference time'>"
                    "<rect class='waterfall-track' width='600' height='12'/>"
                    + "".join(bars) + "</svg>"
                    + (f"<p>{esc(compact(metrics['turn_count']))} recorded turns"
                       f" &middot; <span data-observed='{esc(session['observed_at'])}'>"
                       f"Last observed: {esc(session['activity'])}</span></p>")
                    + f"<p class='muted'>{esc(counts)} &middot; reported input / output / cache tokens</p>"
                    + "</div>" + ring
                    + details("Observation details", provenance + listing(session["diagnostics"], "No source diagnostics"), "session-provenance")
                    + "</article>")
    return (f"<div class='time-axis'><span>{esc(date(datetime.fromtimestamp(t0, timezone.utc).isoformat()) if starts else 'Unknown start')}</span>"
            f"<span>{esc(date(datetime.fromtimestamp(t1, timezone.utc).isoformat()) if ends else 'Unknown end')}</span></div>"
            + "".join(rows)
            + "<p class='boundary'>Session/event-window observations, not current-task cost or product acceptance. "
              "Counters sum reported fields; incomplete source coverage is disclosed in each observation. "
              "Context is shown only when the host reports occupancy and capacity.</p>")


def render(data: dict) -> str:
    model = data["dashboard"]
    view, counts = model["lifecycle"], model["counts"]
    css = (ASSETS / "board.css").read_text(encoding="utf-8")
    js = (ASSETS / "board.js").read_text(encoding="utf-8")
    def csp_hash(value):
        return base64.b64encode(hashlib.sha256(value.encode()).digest()).decode()
    csp = (f"default-src 'none'; script-src 'sha256-{csp_hash(js)}'; style-src 'sha256-{csp_hash(css)}'; "
           "base-uri 'none'; form-action 'none'; connect-src 'none'; img-src data:")
    task_by_id = {t["id"]: t for t in view["tasks"]}
    goals, inspectors = [], []
    goal_order = {}
    for index, task in enumerate(view["tasks"]):
        goal_order.setdefault(task["goal_id"], index)
    for goal in sorted(view["goals"], key=lambda item: goal_order.get(item["id"], len(task_by_id))):
        rows = [t for t in view["tasks"] if t["goal_id"] == goal["id"]]
        squares, listing_rows = [], []
        for task in rows:
            progress, label = task_state(task)
            mark = "&#10003;" if progress == "ready" else "&#8250;" if progress == "working" else "&#183;"
            status = f"{label}; readiness {task['readiness']}; {task['disposition']}"
            attrs = (f"data-task='{esc(task['id'])}' data-progress='{progress}' "
                     f"data-readiness='{esc(task['readiness'])}' data-disposition='{esc(task['disposition'])}' "
                     f"data-attention='{'yes' if task['blocking_holds'] or task['readiness'] in {'stale', 'unavailable'} else 'no'}' "
                     f"data-search='{esc(task['title'].lower() + ' ' + task['id'].lower())}'")
            squares.append(f"<a class='task-square' href='#task-{esc(task['id'])}' {attrs} "
                           f"aria-label='{esc(task['title'] + ': ' + status)}' title='{esc(task['title'] + ': ' + status)}'>"
                           f"<span aria-hidden='true'>{mark}</span></a>")
            listing_rows.append(f"<a class='task-list-row' href='#task-{esc(task['id'])}' {attrs}>"
                                f"<span>{esc(task['title'])}</span>{badge(label, progress)}</a>")
            inspectors.append(task_inspector(task, view))
        written = sum(t["progress"] == "Code ready" for t in rows)
        goals.append(f"<section class='goal-group'><h3>{esc(goal['outcome'])}</h3>"
                     f"<p>{written}/{len(rows)} code written &middot; {esc(goal['disposition'])}</p>"
                     f"<div class='task-map'>{''.join(squares)}</div><div class='task-list'>{''.join(listing_rows)}</div></section>")
    def tile(value, label, note):
        return f"<div class='metric'><strong>{esc(value)}</strong><span>{esc(label)}</span><small>{esc(note)}</small></div>"
    def total(key):
        values = [s["metrics"][key] for s in model["sessions"] if s["metrics"][key] is not None]
        return compact(sum(values)) if values else "Unknown"
    metrics = (tile(f"{counts['written']}/{counts['total']}", "Code written", "Selected scope; not delivery acceptance")
               + tile(f"{counts['current']}/{counts['total']}", "Current readiness",
                      f"{counts['stale']} stale / {counts['unavailable']} binding unavailable")
               + tile(counts["held"], "Needs attention", f"{counts['decisions']} unresolved decisions / {counts['owned']} owned items")
               + tile(f"{sum(s['coverage'] != 'unavailable' for s in model['sessions'])}/{len(model['sessions'])}"
                      if model["sessions"] else "Not collected", "Session sources", "Available / selected sources; not a live worker count")
               + tile(" / ".join(total(k) for k in ("input_tokens", "output_tokens", "cache_read_tokens")),
                      "Reported input / output / cache", "Recorded event values; not billing")
               + tile(total("assistant_turn_seconds"), "Recorded turn seconds", "Not provider inference time"))
    next_action = view["next_action"]
    tid = next_action.get("task_id")
    next_label = task_by_id[tid]["title"] if tid in task_by_id else next_action.get("reason", "Inspect current holds")
    next_kind = next_action["kind"].capitalize()
    if next_action["kind"] == "hold" and counts["owned"] and not counts["held"]:
        next_kind = "Owned work"
        next_label = f"{counts['owned']} items have recorded owners. No unclaimed work is currently eligible."
    next_link = f"<a href='#task-{esc(tid)}' data-select='{esc(tid)}'>{esc(next_label)}</a>" if tid in task_by_id else esc(next_label)
    evidence = "".join(f"<div><h3>{esc(kind.capitalize())}</h3><p>"
                       + (f"<strong>{count['recorded_pass']}/{count['declared']}</strong> criteria with matching recorded passes"
                          if count["declared"] else "Not declared in this scope")
                       + "</p></div>" for kind, count in model["evidence_kinds"].items())
    decisions = [d for d in view["decisions"] if d["resolution"] is None and not d.get("superseded_by")]
    decision_html = "".join(f"<li><strong>{esc(d['question'])}</strong><p>{esc(' / '.join(d['alternatives']))}</p>"
                            f"<small>Affects {esc(', '.join(d['affected']))}</small></li>" for d in decisions)
    insights = model["insights"]
    if insights is None:
        analysis = "<p class='muted'>Not generated. The dashboard does not call a model on refresh.</p>"
    else:
        content = f"<p class='analysis-summary'>{esc(insights['summary'])}</p><ul>" + "".join(
            f"<li>{badge(item['kind'])}<p>{esc(item['text'])}</p>"
            f"<small>Task references: {esc(', '.join(item['task_ids']) or 'none')}</small></li>"
            for item in insights["items"]) + "</ul>"
        provenance = facts([("Reported model", insights["model"]), ("Generated", insights["captured_at"]),
                            ("Based on state revision", insights["state_revision"]),
                            ("Relevant fact fingerprint", insights["input_fingerprint"])])
        analysis = (content + details("Analysis provenance", provenance) if insights["applicability"] == "current" else
                    details("Stale interpretation / not a current recommendation", content + provenance))
    refresh = data.get("refresh") if not data.get("stopped") else None
    mode = "Stopped watcher; not live" if data.get("stopped") else (
        f"Refresh requested every {refresh}s; watcher liveness unverified" if refresh else "Static snapshot; not live")
    errors = ([f"Refresh failed; STALE: {data['refresh_error']}"] if data.get("refresh_error") else []) + model["diagnostics"]
    banner = "<div class='alerts' role='alert'>" + listing(errors) + "</div>" if errors else ""
    history = "".join(details(f"Revision {c['revision']} / {c['kind']} / {c['target']}",
                              f"<p>before: {esc(json.dumps(c['before'], sort_keys=True))}</p>"
                              f"<p>after: {esc(json.dumps(c['after'], sort_keys=True))}</p>"
                              f"<p>Sources: {esc(', '.join(c['source_refs']))}</p>") for c in view["corrections"])
    constraints = listing(f"{c['id']} [{c['disposition']}]: {c['statement']}" for c in view["constraints"])
    attempts = listing(f"{a['id']}: {a['activity']}, stop {a['stop']}; {a['applicability']}; "
                       f"assigned scope {json.dumps(a.get('scope', 'unavailable'), sort_keys=True)}; result {a['result'] or 'unknown'}"
                       for a in view["attempts"])
    provenance = facts([("Project", view["project_id"]), ("State revision", view["revision"]),
                        ("State source identity", view["source_identity"]), ("Schema", view["schema"]),
                        ("State updated", view["updated_at"]), ("Generated", view["generated_at"]),
                        ("Observations revision", model["observations_revision"]),
                        ("Observations captured", model["observations_captured_at"]),
                        ("Observation identity", model["observations_identity"]), ("Renderer", "architrave.dashboard.v1")])
    return (f"<!doctype html><html lang='en' data-theme='dark'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width, initial-scale=1'><meta http-equiv='Content-Security-Policy' content=\"{esc(csp)}\">"
            f"<meta name='theme-color' content='#10161e'><title>Lifecycle board</title><style>{css}</style></head>"
            f"<body data-project='{esc(view['project_id'])}' data-scope='{esc(','.join(task_by_id))}' "
            f"data-generated='{esc(view['generated_at'])}' data-refresh='{int(refresh or 0)}'>"
            "<a class='skip-link' href='#main'>Skip to work board</a><main id='main'>"
            "<header class='page-header'><div>"
            f"<h1>{esc(data['title'])}</h1><p class='project-name'>{esc(view['project_id'])}</p></div>"
            "<div class='header-actions'><button id='theme-toggle' type='button'>Light theme</button>"
            "<button id='refresh-now' type='button'>Refresh snapshot</button>"
            "<button id='pause-updates' type='button' hidden>Pause updates</button></div></header>"
            f"{banner}<div class='metrics'>{metrics}</div>"
            f"<p id='freshness' class='freshness' role='status'>{esc(mode)} &middot; revision {view['revision']} &middot; "
            f"generated <time datetime='{esc(view['generated_at'])}'>{esc(date(view['generated_at']))}</time></p>"
            "<p id='client-status' class='muted' role='status'></p>"
            f"<section class='next-action' data-next-action='{esc(next_action['kind'])}' aria-label='Next eligible work'><span>{esc(next_kind)}</span>"
            f"<p>{next_link}</p><small>Phase: {esc(view['phase'])}. Eligibility comes from canonical state, not AI interpretation.</small></section>"
            "<nav class='section-nav' aria-label='Board sections'><a href='#tasks'>Tasks</a><a href='#sessions'>Session history</a>"
            "<a href='#evidence'>Evidence</a><a href='#interpretation'>AI interpretation</a></nav>"
            "<section id='tasks'><div class='section-heading'><h2>Tasks</h2>"
            f"<p>Scope: {counts['total']} selected items &middot; <span id='visible-count'>{counts['total']} visible</span></p></div>"
            "<div class='task-toolbar'><label>Find a task<input id='task-search' type='search' placeholder='Title or ID' autocomplete='off'></label>"
            "<label>Show<select id='task-filter' aria-label='Show tasks'><option value='all'>All items</option><option value='attention'>Needs attention</option>"
            "<option value='working'>In progress</option><option value='ready'>Code ready</option><option value='deferred'>Deferred</option></select></label>"
            "<button id='list-toggle' type='button' aria-pressed='false'>List view</button></div>"
            "<div class='legend'><span><i class='open'></i>Not started</span><span><i class='working'></i>In progress</span>"
            "<span><i class='ready'></i>Code ready</span><span><i class='uncertain'></i>Stale / binding unavailable</span></div>"
            "<p class='boundary'>Code ready is not verified acceptance. Search and filters do not change the scoped totals.</p>"
            f"<div class='work-layout'><div id='task-groups'>{''.join(goals)}<p id='no-matches' class='empty' hidden>No matching tasks. Clear the search or choose All items.</p></div>"
            f"<aside id='task-inspectors' aria-label='Selected task details'>{''.join(inspectors) or '<p class=empty>No tasks in this scope.</p>'}</aside></div></section>"
            + (f"<section class='decisions'><h2>Decisions awaiting an answer</h2><ul>{decision_html}</ul></section>" if decisions else "")
            + f"<section id='sessions'><div class='section-heading'><h2>Session history</h2><p>Source-backed observations</p></div>{session_history(model['sessions'])}</section>"
            f"<section id='evidence'><h2>Evidence, kept separate</h2><div class='evidence-grid'>{evidence}</div>"
            "<p class='boundary'>Recorded results are not a fresh verification, release authorization or acceptance of the product.</p></section>"
            f"<section id='interpretation'><div class='section-heading'><h2>AI interpretation</h2>{badge('Advisory / not authority')}</div>{analysis}"
            "<p class='boundary'>Source references do not prove an interpretation is true. This panel cannot change tasks, permissions or execution.</p></section>"
            "<footer>" + details("Snapshot provenance & source history", provenance
                                  + "<h3>Scope corrections</h3>" + (history or "<p>None recorded.</p>")
                                  + "<h3>Applicable and historical constraints</h3>" + constraints
                                  + "<h3>Attempts and retained results</h3>" + attempts
                                  + "<h3>External operations</h3>" + listing(
                                      f"{o['id']}: {o['action']} / {o['outcome']} / observed {o['observation'] or 'unknown'}"
                                      for o in view["operations"]))
            + "<p class='boundary'>Read-only, YAML-backed display. No external assets or model calls. "
              "Task text can be sensitive; review exported HTML before sharing it.</p></footer>"
            f"</main><script>{js}</script></body></html>")
