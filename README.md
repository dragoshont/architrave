# Architrave

A small set of instructions for an AI coding assistant. The host runs the
assistant; Architrave does not run or manage it.

## Use

Use [AGENTS.md](AGENTS.md) as the repository instructions. An optional Copilot
agent is in [.github/agents/architrave.agent.md](.github/agents/architrave.agent.md).
For another host, use the instructions directly. There is no installer.

Keep the user's asks in [tasks.md](tasks.md). Status is blank, **In progress**,
or **Code ready**. Written implementation and checking results are separate.

## Removed

The previous executable control plane is retired, not repaired. This checkout
has no hooks, test suites, gates, status service, manifests, checksum machinery,
installer, or automated scheduling and recovery. It makes no unattended
execution guarantee. Older published releases still contain the retired system.

Git history and local research have been preserved.

## License

[MIT](LICENSE).
