# Operations UX pack

The source-backed rule base for Architrave's operations/admin product awareness: onboarding, offboarding, inventories, app/package catalogs, user/team management, health/readiness, diagnostics, long-running action execution, scheduled jobs, scarce limits, and unfinished/error states.

Use this pack when a feature manages real-world resources, people, devices, services, apps, credentials, queues, jobs, health, policy, or evidence. It complements the platform packs (`apple.md`, `microsoft.md`, `web.md`): platform packs say what is idiomatic on the platform; this pack says what an operational product must make true and visible.

## Research Approach

The research path deliberately triangulated across four source families instead of trusting one product genre:

1. **Official platform guidance**: Apple HIG and Apple deployment/Configurator/Developer-team docs for onboarding, progress, alerts, settings, accessibility, Apple-device setup, and team invitations.
2. **Official admin/product mechanics**: Microsoft 365 admin center, Service health, Message center, Intune enrollment/status/device actions/diagnostics, Azure async operations, Kubernetes Jobs/CronJobs, GitHub Actions logs/rerun/cancel, OpenTelemetry traces.
3. **Recognized UX/design-system hubs**: Nielsen Norman Group, GOV.UK Design System, IBM Carbon, Atlassian Design System, PatternFly, Grafana.
4. **Shipped product precedents**: FleetDM, Tailscale, AltStore, SideStore, Sideloadly, SimpleMDM/Jamf/Kandji where public docs were accessible.

Drill-down method:

- Start from concrete workflow examples: device onboarding/offboarding, user onboarding, app store/catalog/upload IPA, autosigning job status.
- For each theme, find official docs that expose the real object model and failure modes before looking at visual inspiration.
- Follow recurring nouns across sources: device, user, team, role, app/package, profile/certificate, job/run/operation, queue, issue, diagnostic artifact, audit activity, status, source, timestamp.
- Keep patterns that appeared in at least two source families, or that came from the authoritative owner of the domain.
- Treat public marketing pages as weak evidence; use them only to confirm workflows, not to define interaction detail.

## Source Corpus

### Apple And Microsoft Official Sources

1. Apple HIG — Onboarding: brief, interactive, optional onboarding; postpone nonessential setup; request private access in context.
2. Apple HIG — Progress indicators: determinate when possible; be accurate; show stalled states; cancel/pause when safe; do not fake advancement.
3. Apple HIG — Alerts: alerts are for essential actionable interruptions; use inline/contextual status for routine recoverable issues.
4. Apple HIG — Settings: sensible defaults first; task-specific options belong in context, not buried in settings.
5. Apple HIG — Accessibility: contrast, system colors, non-color-only meaning, VoiceOver labels, keyboard access, hit targets, reduce motion, no time-boxed controls for critical interaction.
6. Apple Platform Deployment: Apple deployment projects manage hardware, software, apps, and services through Apple Business/School plus MDM.
7. Apple Configurator User Guide: device browser, Blueprints, profile installation, prepare/enroll flows, and physical-device setup realities.
8. Apple Developer — Invite team members: Account Holder/Admin gate, invite form, roles, acceptance link, invitation expiry.
9. Apple Developer System Status: simple service status and last-updated precedent.
10. Microsoft 365 Admin Center overview: common admin entry point; simplified vs dashboard view; Users, Teams/groups, Roles, Setup, Health, Reports, Settings.
11. Microsoft 365 Service Health: service table, incidents/advisories, issue detail with ID, last update, origin, status, user impact, update feed, history, tenant action items, report issue.
12. Microsoft 365 Message Center: change readiness as a table with service, tag, state, timing, act-by date, relevance, rollout status, archive/share/favorite, tasks.
13. Intune deployment guide — enrollment: staged rollout, prerequisites, device identity, unenroll/reset, restrictions, terms, MFA, categories, incomplete/abandoned enrollment reports.
14. Intune Enrollment Status Page: provisioning phases, blocking apps, timeout/error messaging, log collection, diagnostics page, bypass/reset options, technician/user phases.
15. Intune Device Actions: action matrix by platform, prerequisites, role/permission gates, action bar, bulk actions, status page, precedence of retire/wipe/delete.
16. Intune Collect Diagnostics: prerequisites, roles, network requirements, privacy warnings, status link, retention, download, known failures, bulk limits.
17. Azure Resource Manager async operations: 201/202 is not completion; monitor URL, Retry-After, status enum, start/end, percentComplete, terminal errors.
18. Microsoft Graph longRunningOperation: job object shape for status-bearing long work.
19. Windows accessibility overview: keyboard/Narrator/high contrast and ongoing verification.
20. Windows progress controls/dialogs/NavigationView: platform-specific progress, confirmation, and shell conventions.

### UX Hubs And Design-System Sources

21. NN/g — Progressive disclosure: show frequent/core features first; hide rare/advanced detail behind obvious labels; staged disclosure only when tasks are truly sequential.
22. NN/g — Progress indicators: immediate feedback; looped indicators only for short waits; percent/stage feedback for long waits; never static wait text or "do not click again" threats.
23. NN/g — Error-message guidelines: errors near source, noticeable and accessible, human language, precise issue, constructive remedy, preserve input.
24. NN/g — Empty states: distinguish loading/no data/error/filtered states; use empty states to communicate status, teach in context, and link to the next task.
25. GOV.UK — Complete multiple tasks: task list for long multi-session transactions; grouped tasks; short status labels; cannot-start-yet; completion can be user-marked.
26. GOV.UK — Check answers: review before submit; change links; preserve inputs; make the transaction incomplete until explicit confirmation.
27. GOV.UK — Error summary: top-of-main summary, focus management, links to fields, same wording as inline errors.
28. GOV.UK — Confirmation pages: receipt/reference, what happens next, contact path, save/record path, bookmark behavior.
29. Carbon — Empty states: no-data/user-action/error-management variants; one primary action; no dead ends; permission/config/system/action-not-supported cases.
30. Carbon — Data table: toolbar, title/source, search, filters, sort, pagination, selection, batch actions, inline actions, skeleton loading, row hover, row expansion for delayed data.
31. Carbon — Progress indicator: linear multistep flows, states (complete/current/not started/error/disabled), validation before continuing, clear step labels.
32. Atlassian — Dynamic table: sorting, pagination, loading, emptyView, overflow caution, row interactions, focus after row deletion.
33. Atlassian — Empty state: header/description/actions, permission examples, loading action state, accessible heading levels.
34. Atlassian — Section message: warning for auth/risky actions, error for access/connectivity/destruction, discovery for onboarding, actions inline.
35. PatternFly — Table: enterprise table patterns, selectable rows, action columns, expandable rows, sticky headers/columns, empty states, accessible labels.
36. PatternFly — Wizard: guided complex tasks, disabled/incremental/validated/progressive steps, focus content on next/back, progress after submission.
37. Grafana dashboards: panels answer scoped operational questions by querying/translating data; dashboards are not decorative cards.
38. Grafana Alerting: rules, notification routing, consolidated triage, fired/resolved state.

### Shipped Operational Product Precedents

39. GitHub Actions workflow run logs: failed steps auto-expanded, line permalinks, search, download, job summary.
40. GitHub Actions rerun/cancel: rerun all/failed/specific jobs, debug logging, cancel in-progress run, previous attempts.
41. Kubernetes Job: `spec`/`status`, pods status, start/completed/duration, events, logs, backoff, terminal Complete/Failed conditions, suspend/resume, TTL cleanup.
42. Kubernetes CronJob: schedule, job template, starting deadline, concurrency policy, suspension, history limits, time zone, missed runs, idempotency warning.
43. OpenTelemetry traces: trace ID/span ID, span attributes/events/links/status/kind, producer/consumer links for async queued work.
44. FleetDM REST API — hosts: inventory timestamps, last seen, MDM enrollment/status, filters, labels, health, issues, software, policies, device actions, activity, CSV export.
45. FleetDM REST API — software: catalog titles, package upload (`.pkg`, `.ipa`, etc.), app store apps, self-service categories, install/uninstall 202, install result output and status.
46. FleetDM REST API — scripts/batch scripts: execution IDs, upcoming activity, batch counts, host results, cancel, status, created/started/finished timestamps.
47. FleetDM REST API — users/invites: users, roles, invites, SSO/MFA/API-only users, sessions, password reset, invite verification/update/delete.
48. FleetDM REST API — commands/OS settings/setup experience: MDM commands, command UUID/status, setup experience software, bootstrap packages, profile resend, batch profile status.
49. Tailscale CLI/status/tags: active/idle/direct/relay status, netcheck, bugreport IDs, tag vs user identity, tag ownership, key expiry, clear naming conventions, ACL tests.
50. AltStore — Activating apps: only three active sideloaded apps, inactive section, activate/deactivate, data backup claim, slot pressure made explicit.
51. AltStore install docs: prerequisites, trust device, Wi-Fi sync, Apple ID, profile trust, Developer Mode.
52. SideStore troubleshooting: trust device, anisette server switching, 2FA code retrieval, pairing/debug server issues, sideloading recovery copy.
53. Sideloadly: four-step sideload model (download, load IPA, Apple ID, sideload), automatic refresh, Wi-Fi sideloading.
54. SimpleMDM/Jamf/Kandji public pages: Apple-focused MDM confirms enrollment/app/configuration/device-management workflow families; detailed UI evidence is limited without authenticated docs.

## Core Pattern Language

### 1. Operational Objects First

Model the real nouns separately. Do not flatten them into one dashboard card.

- **Person/user/member**: identity, role, invite, session, API token, ownership, last activity, offboarding state.
- **Team/scope/fleet/workspace**: membership, permissions, labels, policy scope, limits, inherited settings.
- **Device/host**: persisted known record, reachable/last-seen state, owner, platform, enrollment/trust, health, status source, stale policy.
- **Catalog artifact**: app/package/profile/script/template uploaded or discovered; hash, version, bundle/package ID, icon, size, validation state.
- **Installation/assignment/slot**: artifact applied to a target; status, expiry, last refresh, verification source, scarce limit consumption.
- **Operation/job/run**: durable action instance with actor, target, stages, timestamps, terminal state, retry/cancel rules, output, trace/log links.
- **Issue/diagnostic**: grouped failure with severity, affected objects, first/last seen, evidence, recovery action, linked operations.
- **Audit activity**: immutable who/what/when/where/outcome record.

If the UI cannot name the object, the backend contract is probably too vague.

### 2. Setup And Onboarding

Use a **setup center** when setup spans prerequisites over time. Use a **wizard** only when steps are linear and interdependent.

Required anatomy:

- Tasks grouped into stages such as prerequisites, identity/access, resource connection, first object, verification, schedule/automation.
- Status per task: `not-started`, `in-progress`, `blocked`, `cannot-start-yet`, `complete`, `problem`.
- Detected vs guided state: a system-detected fact is not the same as a human instruction.
- Detail panel with one current action, source, timestamp, and recovery path.
- Optional/contextual tips where possible; avoid forced tutorial bloat.
- Keep setup out of settings when it affects the current task.

### 3. Offboarding And Destructive Flows

Offboarding is a sequence, not a delete button.

Required anatomy:

- Impact summary: target, dependents, data retained/deleted, access revoked, devices retired/wiped, licenses reclaimed, jobs canceled, audit retained.
- Preflight: blockers, warnings, role/approval requirement, unsupported targets, offline targets, stale data.
- Review step: check answers with change links before irreversible mutation.
- Confirmation: name the exact object and consequence; typed confirmation for severe irreversible actions.
- Recovery/receipt: reference/operation ID, what happens next, where to track status, support/audit link.

Never hide destructive commands when unavailable; show them disabled with reason when the operator expects them.

### 4. Inventory And Management Lists

Desktop operations UI is usually a list/table product. Cards can summarize; they should not replace the work surface.

Required anatomy:

- Search over human identifiers plus stable IDs.
- Facets/filters for state, platform/type, owner/team/scope, health/risk, last seen, policy, source, capability, and failed/pending work.
- Sortable/sticky columns where density warrants it.
- Row action column or persistent overflow; hover-only critical actions are not enough.
- Row detail pane or dedicated detail route for complex work; expansion only for supporting detail or delayed lightweight queries.
- Bulk mode only for safe repeated operations; disable row actions while batch mode is active.
- Mobile fallback as grouped cards/lists with the same status and actions, not a squeezed wide table.
- Export/download only when the repo can truthfully provide the filtered dataset.

### 5. App/Package/Catalog/Upload Flows

Separate `CatalogApp` from `InstalledApp` from `Registration` from `Operation`.

Required anatomy:

- Two entry paths when relevant: curated/store app and upload/import custom package.
- File upload/import must inspect before commit: type, size, hash, bundle/package ID, version, icon, entitlements/capabilities, minimum OS, signature/profile/cert state.
- Keep user input on validation failure.
- Preflight before install/sign/register: target device, slot/licence/cert/profile limits, permission, online/trust state, planned mutations, warnings.
- Show scarce limits before submission: active slots, app ID quotas, certificate/profile expiry, upload size, store availability, rate limits.
- Execution becomes a job/operation; button click does not equal install complete.

### 6. Action Execution And Job Status

Every non-trivial mutation is an observable operation.

Contract checklist:

- `operationId`, `type`, `actor`, `targetIds`, `createdAt`, `startedAt`, `updatedAt`, `completedAt`.
- `status`: `queued`, `waiting`, `running`, `blocked`, `canceling`, `canceled`, `succeeded`, `failed`, `partial`, `expired`, `unknown`.
- `stage`: stable ordered stages with `status`, `startedAt`, `completedAt`, `message`, `error`, optional output/artifacts.
- `progress`: percent only when honest; otherwise stage index or completed/total counts.
- `retryAfter` or next poll guidance for async APIs.
- `cancelable`, `retryable`, `rerunnable`, and idempotency key/attempt.
- Terminal error object: code, human reason, remediation, correlation/error UUID, log/trace links.
- Artifacts: logs, downloads, diagnostics, receipts, signed files, reports, expiry.

UX requirements:

- Immediate acknowledgement after submit.
- Visible current operation plus queued work.
- Failed stage auto-expanded; logs searchable/downloadable/linkable when logs exist.
- Rerun failed/specific item only when the backend can prove it is safe.
- Cancel only while safe; explain consequences if cancel loses progress or leaves partial state.

### 7. Scheduled Jobs And Automation

Scheduled automation needs its own status, not just a cron string.

Show:

- Schedule, time zone, next run, previous run, missed run reason, concurrency policy, pause/suspend state, history limits/retention, stale data policy.
- Current lock/single-flight owner where only one job can run.
- Catch-up behavior and idempotency expectations.
- Manual run/rerun controls with preflight and operation tracking.

### 8. Health, Readiness, And Diagnostics

Health must be scoped, sourced, timestamped, and actionable.

Required anatomy:

- Split **readiness** (can perform core work now) from **health** (observed service/resource state) and **incidents/issues** (known failures requiring triage).
- For each check: source, last checked, status, reason, affected objects, next action.
- Group issues first; raw logs second.
- Issue detail: affected object, first/last seen, count, severity, operation IDs, trace ID, log excerpt, diagnostics artifact, remediation.
- Trace/log model: trace ID/span ID, spans/stages, events, attributes, producer/consumer links for queued work.
- Keep advanced query builders behind an advanced/explore surface.

### 9. User, Role, Team, And Scope Management

Keep human identity, service identity, product workspace, and provider account distinct.

Required anatomy:

- Users table: name/email, role, scope/team, status (`active`, `invited`, `suspended`, `disabled`), MFA/SSO/API-only/session state, last active.
- Invite flow: role/scope first, invite state, expiry/resend/revoke, acceptance requirements.
- Role matrix or effective permissions: what each role can read, mutate, approve, and administer.
- API/service users separate from human users.
- Offboarding checklist: block sign-in, revoke sessions/tokens, transfer ownership, preserve/delete data, remove from scopes, revoke provider access, audit receipt.
- Never conflate provider teams/accounts with app workspace teams.

### 10. Empty, Loading, Partial, And Error States

State copy must answer: is the system still working, is there no data, is data blocked, or did something fail?

State types:

- `loading`: skeletons for lists/tables; inline button progress for quick action; progress/stages for long work.
- `no-data`: what would appear here, why it is empty, one next action.
- `no-results`: filters/search produced nothing; show clear/reset and preserve filter context.
- `permission`: user lacks scope; show request-access or role explanation if supported.
- `configuration-required`: missing setup; link directly to setup task.
- `system-error`: dependency failed; show source/timestamp and retry/support path.
- `partial`: some data sources failed; show what is live, what is missing, and how stale each source is.
- `planned/mock`: label clearly; do not mix with live as if equivalent.

Never show "0" as final before loading finishes. Never show an empty table with headers before the user hears why there is no content if the table itself is replaced by an empty state.

## Operations UX Data-Contract Checklist

Ask the Service Architect to require these fields before the UI claims the capability:

- **Capability matrix**: resource type, action, platform/source, role/scope, prerequisites, support state, failure modes.
- **Source labels**: live/derived/mock/planned/stale plus source URL/service and timestamp.
- **Health/readiness**: status, reason, source, checkedAt, affected resources, next action.
- **Preflight**: ready, blockers, warnings, planned mutations, scarce limits, required confirmations, canQueueOffline, idempotency key.
- **Operation/job**: operation ID, type, actor, targets, status, stages, timestamps, attempt, retry/cancel/rerun flags, output preview, error, artifacts, trace/log IDs.
- **Scheduler/queue**: schedule, timezone, next/last/missed runs, concurrency policy, lock owner, history/retention, pause state.
- **Diagnostic issue**: category, severity, status, affected objects, first/last seen, occurrence count, linked operations, evidence, remediation.
- **Inventory object**: stable ID, display name, owner/team/scope, last seen/updated, platform/type, health, labels/tags, policies, status reason.
- **Catalog artifact**: source, upload/createdAt, hash, size, version, package/bundle ID, icon, validation/inspection result, supported targets, install/uninstall scripts, signature/profile/cert details where relevant.
- **User/member**: role/scope, invite/session/token/MFA/SSO state, last active, effective permissions, offboarding state.
- **Audit event**: actor, action, target, timestamp, request ID, outcome, before/after pointer, correlation ID.
- **Privacy/security metadata**: secret references only, redaction state, diagnostic-retention policy, PII classification.

## Review Prompts For Agents

### Product Research

- Which shipped products expose this workflow? What do they show as objects, states, actions, and evidence?
- Which source family is authoritative for the workflow: platform guideline, admin docs, API contract, or product screenshot?
- What backend fields do those products rely on that this repo lacks?

### UX Architect

- What is the operator trying to decide in the first five seconds?
- Is this a setup center, inventory, detail, preflight, queue, issue, or audit workflow?
- What are the empty/loading/partial/error states and the primary action for each?
- Are unsupported actions visible with reasons?

### UI Visual

- Is the page dense and scannable enough for repeated operations work?
- Are colors only small semantic cues, backed by text/icons and accessible contrast?
- Are tables/lists/timelines using stable dimensions and responsive behavior?

### Service Architect

- Is every visible state backed by a contract field?
- Is every mutation an observable operation with durable status and errors?
- Are scarce limits, permissions, and capability boundaries represented before execution?

### Backend Planner

- Does the plan land contract/read model before UI claims?
- Are migrations and background jobs reversible/idempotent?
- Is the first slice operationally useful without fake metrics?

### Adversarial Judge

- Fail any proposal that uses generic dashboards where the domain needs object lists, queues, issues, or evidence.
- Fail any status without source/timestamp/scope, any action without job/preflight semantics, or any destructive action without impact/recovery.
- Treat missing operations-UX contract fields as product-truth concerns, not visual polish.

## Anti-Patterns

- Generic hero/dashboard cards, decorative charts, invented KPIs, vague "system healthy" badges.
- Button click treated as completed operation.
- Hidden spinners for long-running work.
- Toast-only errors for failures that require action.
- Route load causing mutation, refresh, sign, install, or destructive work.
- Raw logs as the first diagnostic screen.
- Unknown statuses with no reason/source.
- Disabled actions with no explanation.
- Empty state that hides loading, error, permissions, or filters.
- User/team/provider/account concepts flattened into one bucket.
- Destructive/offboarding flow without data-retention, dependency, access, and recovery summary.
- Bulk action without affected-count preview and rollback/cancel semantics.

## Source Limitations

- Apple Business and some Apple/App Store Connect help pages are official but sparse or reorganized; use them for domain truth, not detailed UI anatomy.
- Jamf/SimpleMDM/Kandji public pages confirm workflow families but often hide detailed console docs behind authentication or changed URLs.
- Product marketing pages such as Sideloadly are useful for user mental models but weaker than API/admin docs for contract details.
- Screenshots and docs can lag shipped products; treat them as precedents to test against current repo truth, not as pixel specs.