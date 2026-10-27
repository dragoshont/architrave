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
starts it for every non-trivial task. A watcher registers itself in the
coordinator session's `files/program-board.watch`; while lanes are running,
`requirements` run by the coordinator prints a note when no live watcher is
registered (lane sessions are never reminded). It is a reminder, not a failure.

## What it shows

| Section | Source |
|---|---|
| Overview: accepted REQs, running lanes, sessions, tokens, model and wall minutes | Requirements file and local session logs |
| Lanes: one rectangle per lane, one square per REQ (green accepted, green hatching delivered by a done lane but not yet accepted, blue claimed, red blocked, grey open); select a square for its requirement | `## GHC Scheduler` lane table and REQ rows |
| How the sessions ran: per session a time bar (first to last event, dark marks for model turns), agent, model/wall minutes, live state, a current-context gauge (latest prompt size) against the model limit and a token gauge | `~/.copilot/session-state/<id>/events.jsonl` of the coordinator and the child sessions it created with `create_session` |

It is dense by design and fits a narrow side panel; there are no tables.

## Completion

A session whose last action was the host's "Task completed" (no model turn after it) shows a green bar and "task completed", even if its lane row is not yet updated. A later turn makes it active again.

## Context flags

Context is the latest prompt size, not the peak, judged against the session's
first prompt (its system prompt and tools), even when earlier events are
clipped. "context high" (≥30% of the limit or ≥300k, with 1.5× the first prompt
or a quarter of the remaining room used) is information; "rotate at next task
boundary" with a gold ↻ (≥45%, with 2× the first prompt or half the remaining
room used) is listed in `<output>.rotate.json` with the time it was first
flagged. A fresh session on a small-window model is never flagged. Rotation steps and evidence are in
`knowledge/execution-policy.md` (Context rotation).

## Review marks

- Session row: grey ✓ when the session ran a reviewer agent (adversarial judge, code review, rubber duck, security review or `architrave-review`); ○ when none. It shows that a review ran, not its verdict.
- Square: a corner when the REQ's latest `review: <reviewer> <verdict>` note (at the start of the cell or after `;` or `,`) is PASS — white when the note names a reviewer session whose local log shows a reviewer role ending in PASS, grey when the note can't be checked. Findings verifiers do not count. The overview shows how many PASS reviews are verified.
- Lane: "reviewed k/n"; a gold border and "review missing" when a `done` lane has any open REQ, or any lane has an accepted REQ, without a PASS review (withdrawn and superseded REQs are skipped). This is the same rule `requirements --done` enforces for ledger lanes; the "Not in a lane" box only gets the gold border for accepted, unreviewed REQs.
- Review notes attach to REQs, not lanes: one PASS on a REQ covers every lane that lists it. The overview counts accepted but unreviewed REQs.
- The `requirements` gate parses every note, requires the latest to be PASS for an accepted REQ, and rejects a reviewer named like the REQ's owner. A note naming a full session UUID is checked against `session-state/<uuid>/events.jsonl`: the kickoff agent (selected before the first turn) must be a reviewer role, and the ruling of the session's last report (its `task_complete` summary or a message it sent another session) must match. A ruling is the first labelled line (`Verdict: REVISE`, `Re-review of X: PASS`), else the first line opening with an upper-case verdict (`**PASS** on …`); quoted, backticked, `>` and table text and mid-sentence verdict words never count, so reviewers should start their report with a `Verdict:` line. Earlier notes naming the same session (a re-review) need only match one of its reports. A contradiction fails the gate. Use a fresh reviewer session for each delivery: a reused session's later ruling contradicts the earlier note.
- Where local session logs exist (the Copilot app and CLI), `requirements --done` and the board's "review missing" count only verified PASS notes, so role names and sessions from other machines do not close a lane. On hosts without those logs every note is unverified and accepted as written. A reviewer that ran elsewhere (a cloud, Claude or Codex session) cannot close a lane on a machine that has logs; run the review as a local visible session. With `review.crossFamily`, every model the lane and the reviewer sessions used (start and mid-session switches) must be logged, not `auto`, and share no family, otherwise the lane shows a gap.
- This catches mistakes and stale claims, not deliberate forgery: an agent that can write files can fake a log.

## Checks and limits

- The overview runs the same structural checks as `requirements`; issues are listed under it.
- A gold ring marks an accepted REQ none of whose evidence commits resolve in the ledger or a configured component. A resolving commit is not proof of the behaviour; that is still review.
- Lane sessions not logged on this machine get a dashed row without metrics.
- Tokens are split into new input, cached reads and output. Sessions that began before the coordinator count only from its start.
- REQs in no lane appear in a "Not in a lane" rectangle (or one "Requirements" rectangle without a lane table).
- Child sessions created by `create_session`, `open_pr_session`, `open_issue_session` or `fork_session` are followed recursively.
- New input = prompt tokens minus cache reads (cache writes count as new). A malformed log line is skipped; a failed refresh keeps the last good board.
- Logs are read incrementally (only new bytes each refresh); requirement text is copied into the board file in the session folder.
- Rotation's benefit is not measured yet; thresholds are a published-evidence heuristic, not tuned for coding.
- It reads files only: no ledger, session or repository changes and no network requests.
- Browser-canvas screenshots can return stale frames (a host issue); verify with the page contents or a fresh render.
