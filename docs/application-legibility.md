# Application Legibility

Source/build success is not product success. Optional `config.runtime` commands
let Architrave collect bounded evidence through the repo's existing tools.

```bash
python3 harness/legibility.py --run-id <id> verify web
python3 harness/legibility.py --run-id <id> verify electron
python3 harness/legibility.py --run-id <id> verify ios
python3 harness/legibility.py --run-id <id> deployment-current
python3 harness/legibility.py --run-id <id> deployment-apply \
  --confirmed --expected-version 1.2.3 --expected-digest sha256:...
```

- Web: configured health plus structured evidence for a driven workflow,
  DOM/accessibility/screenshot artifact paths, and empty console/network errors.
- Electron: structured window count, route, screenshot, completed workflow, and
  empty crash/IPC/console errors; Web Chromium is insufficient.
- iOS: build, install, launch, screenshot, and blank-screen check; compile is
  insufficient. Set `screenshotPath` for built-in PNG pixel/luminance analysis,
  or provide a repo-native `blankScreenCheck` command.
- Runtime: bounded logs and health from configured commands/tools.
- Deployment: current/diff/apply/health/version/digest/rollback wrappers.
  Authorized apply requires expected version and digest and a stable precondition.

Deployment mutation needs an exact Run policy grant. Receipts record operation,
target, before, after, result, and verification. A stale version/digest, crash,
blank app, dead control, console/network failure, or unavailable real provider
fails the reality gate rather than being hidden behind compile success.

Every `reality`/`e2e` acceptance criterion owns the exact product surface
(`web`, `electron`, `ios`, `deployment`, or `runtime`) it verifies, declared
alongside the criterion in Run state. `record_gate` derives the surface the
supplied evidence actually proves (the legibility receipt's own `surface`
field; `deployment` for mutation receipts; `runtime` for external proofs) and
rejects a PASS whose evidence surface does not match the surface every bound
criterion owns -- a web-surfaced criterion can never be satisfied by iOS or
electron evidence, regardless of what the caller claims.
