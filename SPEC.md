# Architrave v1.0 specification

[Issue #90](https://github.com/dragoshont/architrave/issues/90) records the task list and failure history. The owner confirmed the workflow failed in use and stopped live testing. Treat that as a failed workflow, with the cause of the host behavior still unresolved. The issue records rejected approval transfer and a retired hook that kept running until a host restart. The earlier Copilot comparison never started, and the reported skill installation changed its baseline.

| Scope | Required behavior |
| --- | --- |
| Start and steer | Start the first useful action in the intended checkout. Follow the original request and later owner corrections. Keep stopped work stopped and preserve unrelated changes. |
| Delegate | Work directly by default. For requested delegation, provide bounded ownership, dependencies, and the governing request. Carry existing decisions via host-supported evidence. If the child cannot receive a decision it needs, explain once and do that part in the authorized session when possible. A copied claim grants no authority. Host controls apply. |
| Work | Use one assignment and one final worker return. Interrupt only when intervention is necessary. Resolve consequential uncertainty locally by comparing plausible options and challenging the choice once. Apply relevant skills and project conventions. |
| Review | Worker rows use **In progress** and **Code ready**. After every implementation row is **Code ready**, review the combined result once against the original request. Consolidate authorized fixes and review the affected areas after they are written. |
| Report | Verify the intended checkout before running checks and verify output paths before handing them off. Distinguish source, installed or loaded state, and observed user-visible behavior. Name the specific failed prerequisite or missing evidence. A failed check cannot authorize a stopped repair. |
| Close | **Feature ready** is a single feature-level line. Set it only when the original outcome is established by appropriate evidence. Report incomplete outcomes once and leave the line unset. |
| Setup | Keep generic skill use, Architrave setup, and release actions distinct. Architrave supplies instructions. The host owns approvals, loaded guidance, and session lifecycle. |

Keep the existing task list and optional Copilot entry point. The distribution contains the instructions, specification, task list, README and license. The executable control plane stays retired. Source review and package inspection cover this delivery. The stopped live approval exercise has no new result. If an owner later restarts the pilot, record the actual loaded guidance and baseline before drawing comparisons.

## Open issue disposition

| Issues | Relevance to v1.0 |
| --- | --- |
| #90, #83 | Apply the behavioral parts in the instructions. Approval transfer still depends on the host. |
| #82, #84, #76 | Keep source authority and the original outcome in the assignment and integrated review. The lightweight workflow uses the existing task list. |
| #89, #37 | Historical pilot and qualification scenarios. The owner stopped live testing. |
| #75, #53, #39 and beta runtime backlog | Historical failures and observations about the retired implementation. Native session continuation remains a host concern. |
| #88 | Separate architecture integration proposal, outside this change. |
