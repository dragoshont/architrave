---
name: architrave-agent-authoring
description: Explicitly create, revise, or review an agent role when asked to author agents; not for routine use of an existing role.
---

Use the repository's existing role format and target host contract. Keep one
clear responsibility, define non-goals, and give the role a trigger that
distinguishes when it should and should not be selected.

- Ground instructions in repository contracts and existing roles. Extend a
  current role rather than creating a duplicate or a new layer of supervision.
- Request only the tools needed for the bounded responsibility. State read-only
  and approval boundaries; a role or skill never grants host permissions.
- Keep model and provider selection host-owned. Do not pin model IDs, assume
  host-specific capabilities, or claim that a worktree is a security sandbox.
- Match the target host's supported frontmatter, tool and registration format.
  Keep shared role sources and generated registrations consistent; never assume
  one host discovers another host's format.
- Define acceptance in observable terms and add or update a focused fixture or
  check where the contract can be tested. Validate manifests and relevant
  host-specific role loading without treating a fixture as live-host proof.

Example: a runtime observer should be read-only by default, report source-backed
observations and unavailable evidence explicitly, and never infer deployed
health from a successful build.

Do not use this skill to assign work to an existing agent or expand a role's
permissions; use the existing role and host authorization flow instead.
