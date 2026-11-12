# Dispatch clearance
Status: Accepted
Owner: Compliance
Supersedes: 005-clearance

Release requires both workflow completion and approval of the current
certificate revision. Every listed obligation must be satisfied. A revoked
approval cannot release a parcel, including after a certificate revision.
Completion measures processing, not approval.

For express parcels only, an empty obligations list is permitted. Standard
parcels require at least one obligation. Express does not waive current
approval, revocation or workflow-completion checks.

The caller supplies a consistent snapshot; this library makes a pure decision.
Database locking across processes is outside this API's documented ownership.
