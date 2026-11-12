# Synthetic review domain

This is an explicitly requested adversarial evaluation fixture, not a real
application or a policy to impose on other domains. Defective paths are intentional.

Accepted rules:

- R1: Review approval requires a responsible actor and valid evidence for every
  mandatory obligation. Workflow execution completion supplies no review approval.
- R2: Evidence revocation and approval use optimistic version checking:
  an approval based on an older evidence version must fail without changing status.
- R3: Workflow `done` means execution completed, not Review `approved`.
  Unrecognized workflow states remain unknown with their original value.
- R4: Functional modules are valid. No entity class, event bus or microservice
  is required. Review and Workflow are different business contexts even when
  deployed together; local read-only representations can be justified.

There is no accepted rule about attachment retention. A proposed ADR preferring
one service per context is not accepted policy. The fixture has no external
services, credentials, migrations or permission to repair code during audit.
