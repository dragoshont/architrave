# Joined native semantic producer

`architrave_native_review` executes a **fresh** independent review through the
existing installed Copilot joined-host transport. It is not an importer for
copied task reports, a public producer-label setter, or a model selector.

Use the native bridge setup described in the README, then call with an absolute
`repo`, canonical `run_id`, `task_id`, and optional `reviewer`: `rubber-duck`
(default) or `code-review`. Host settings choose the actual model; no model,
family, claimed PASS, result file or event fields are accepted.
Structured JSON or one exact JSON code fence is accepted from the observed
reviewer only. The explicit Adversarial Judge's Markdown rubric report remains
separate requested coverage, not relabelled machine-producer evidence.

## Boundary and scope

The installed extension and pinned Python executor live outside the target.
Existing hashes are rechecked; the bridge owns a private per-invocation pipe.
This is the existing **trusted local producer** boundary, not cryptographic
provider attestation or protection against a malicious same-OS-user operator.
No provider SDK, agent CLI, daemon or transcript store.

Python binds Run/task/criteria/objective/frozen source, policy, pending human
holds and declarative task scope. A process-held single-use ticket owns a random
challenge, joined owner, outer invocation ID, expiry and canonical budget.
The model is invoked fresh, never reused from candidate implementation.
SDK completion/result must match the admitted agent. Observed SDK tasks RPC
1.0.93-1 identifies completion `data.toolCallId` with the admitted agent ID,
**not** the outer invocation ID. Missing, conflicting, cancelled, ephemeral,
stale or differently correlated metadata fails closed. No configured-model or
caller-labelled-family fallback.

Execution runs alone in its joined foreground session at a clean committed
boundary. The pre-tool guard permits only scoped standard view and source-inventory-bounded rg,
including the observed joined-host `grep` tool name with the same argument
allowlist and tracked-regular-file rewrite,
tool discovery and read-only review-skill loading. Shell/execution, mutation,
private `.git`/`.architrave` reads, control-plane and descendants are denied.
Recursive glob/directory views and hidden/ignore/follow overrides are denied.
Search roots are expanded to validated tracked regular files, never delegated
as unconstrained recursive roots. Paths are normalized inside the target. This does not replace host permissions
or claim an OS sandbox. Source, policy, holds and objective are rechecked.

## Receipts and gates

The trusted Python executor—not reviewer prose—registers an
`architrave.native-semantic-review.v1` artifact as `semantic-judge` and records
its gate. Actual first-dispatched model evidence identifies supported
OpenAI/Anthropic families; unknown mappings block. Requested high effort is not
a reported effective reasoning setting; host defaults remain inherited.

PASS consumes native evidence once. Replay, stale source/declarations/policy/
holds, wrong scope, altered bytes or a coordinator-labelled file cannot create
a current PASS. Older receipts remain historical and no longer satisfy current
risk floors. Same-role unchanged source/scope review is refused; real corrections
allow a fresh review. Non-PASS reports cannot be relabelled PASS.

Semantic PASS is not product acceptance, a policy grant or human-hold resolution.
Deterministic, product/reality, security and policy floors still apply. No
historical Run is promoted by copied reviews.

Focused fixtures: `python scripts/test-native-review.py` and
`node --experimental-vm-modules scripts/test-native-review.mjs`. Synthetic SDK
fixtures are not live evidence. Qualification separately records real joined
admission, exact source/agent/tool/completion identities, actual family and
gate/artifact references, plus normal CI.

Receipt and gate admission share one validated Run transaction. Rejected gate
registration leaves no committed producer artifact or role-retry blocker.
Cleanup warnings are reported separately from a durably admitted result;
unclosed owned jobs retain a recovery handle for the existing native cancel
surface. Cleanup failure is never reinterpreted as a missing source verdict.
Tracked-source inventory uses count-bound, byte-bounded transport frames rather
than embedding all paths in the prepared response. Required but uninspected
implementation is a REVISE coverage gap, not a full-source PASS.
