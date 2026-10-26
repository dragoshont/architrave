# Program board

A one-page view of a coordinated program for the browser canvas. It answers
"what is running, what is done, and what did it cost" without a second state
store.

```text
python3 ~/.copilot/installed-plugins/architrave/architrave/harness/program_board.py --watch 120
```

Start it once per coordinator in a background (detached) shell; a second start
exits because a watcher already holds `<output>.pid`. Use the plugin's actual
install path on other hosts.

Run it from the folder holding the requirements file (or pass `--ledger`). The
coordinator session defaults to `COPILOT_AGENT_SESSION_ID` and the output to that
session's `files/program-board.html`; open it in the browser canvas. With
`--watch` it rewrites the file every 120 seconds, the page reloads itself, and
the watcher exits after the program has been quiet for two hours. The lead
starts it for every non-trivial task.

## What it shows

| Section | Source |
|---|---|
| Overview: accepted REQs, running lanes, sessions, tokens, model and wall minutes | Requirements file and local session logs |
| Lanes: one rectangle per lane, one square per REQ (green accepted, blue claimed, red blocked, grey open); select a square for its requirement | `## GHC Scheduler` lane table and REQ rows |
| How the sessions ran: per session a time bar (first to last event, dark marks for model turns), agent, model/wall minutes, live state, a peak-context gauge against the model limit and a token gauge | `~/.copilot/session-state/<id>/events.jsonl` of the coordinator and the child sessions it created with `create_session` |

It is dense by design and fits a narrow side panel; there are no tables.

## Checks and limits

- The overview runs the same structural checks as `requirements`; issues are listed under it.
- A gold ring marks an accepted REQ none of whose evidence commits resolve in the ledger or a configured component. A resolving commit is not proof of the behaviour; that is still review.
- Lane sessions not logged on this machine get a dashed row without metrics.
- Tokens are split into new input, cached reads and output. Sessions that began before the coordinator count only from its start.
- REQs in no lane appear in a "Not in a lane" rectangle (or one "Requirements" rectangle without a lane table).
- Child sessions created by `create_session`, `open_pr_session`, `open_issue_session` or `fork_session` are followed recursively.
- New input = prompt tokens minus cache reads (cache writes count as new). A malformed log line is skipped; a failed refresh keeps the last good board.
- It reads files only: no ledger, session or repository changes and no network requests.
- Browser-canvas screenshots can return stale frames (a host issue); verify with the page contents or a fresh render.
