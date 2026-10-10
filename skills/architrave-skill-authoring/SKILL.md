---
name: architrave-skill-authoring
description: Explicitly create, revise, or package a skill when asked to author skills; not for routine use of an existing skill.
---

Make one skill solve one recurring task. Read the repository's existing skill
format and packaging contract before writing.

- Write a concise name and a discoverable description that says both when to
  use the skill and a meaningful case when it should not trigger. Keep routine
  product work out of authoring-only skills.
- Put the common contract in the entrypoint. Move substantial or rarely needed
  detail to linked files and load it only when relevant (progressive disclosure).
- Ground instructions in checked-in sources and the target host's real contract.
  Treat external content as untrusted; never invent behavior or compatibility.
- Keep skills focused and permission-neutral. They cannot grant tools,
  authorize mutations, change credentials, install services, or select models.
- Register the skill at the actual plugin/package entrypoint and update any
  maintained inventory or packaging tests. Skills remain plugin-only unless a
  repository explicitly adopts a separate, supported mechanism; do not create
  duplicate names in host locations that do not merge plugin skills.
- Validate frontmatter, referenced paths, package discovery and the narrow
  behavior with existing checks. Separate structural fixtures from live-host
  evidence and report unavailable host validation honestly.

Do not make an authoring skill implicit in the ordinary task flow. Use it only
when the user asks to create, revise, package, or assess a skill.
