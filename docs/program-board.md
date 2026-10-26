# Program board

A one-page view of a coordinated program for the browser canvas. It answers
"what is running, what is done, and what did it cost" without a second state
store.

```text
python harness/program_board.py --ledger <dir with SPEC.md> --session <coordinator-session-id> --output board.html
```

Then open `board.html` in the browser canvas. Rerun to refresh; the page is a
dated snapshot.

## What it shows

| Section | Source |
|---|---|
| Overview: accepted REQs, running lanes, sessions, tokens, model and wall minutes | Requirements file and local session logs |
| Lanes: one rectangle per lane, one square per REQ (green accepted, blue claimed, red blocked, grey open); select a square for its requirement | `## GHC Scheduler` lane table and REQ rows |
| How the sessions ran: per session a time bar (first to last event, dark marks for model turns), agent, model/wall minutes, live state, a peak-context gauge against the model limit and a token gauge | `~/.copilot/session-state/<id>/events.jsonl` of the coordinator and the child sessions it created with `create_session` |

It is dense by design and fits a narrow side panel; there are no tables.

## Limits

- Dots show ledger status; acceptance evidence is not re-verified here (use `requirements`).
- Only sessions logged on this machine appear; sessions on other hosts are omitted.
- Input tokens include cached prompt reads, so they overstate fresh input.
- It reads files only. It does not change ledgers, sessions or repositories, and makes no network requests.
