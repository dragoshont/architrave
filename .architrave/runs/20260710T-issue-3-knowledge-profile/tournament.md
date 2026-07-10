# Tournament of Options

## Option A - Installer-Only Profile

Small, but leaves the schema incapable of expressing the generated config.

## Option B - Strict Knowledge Discriminator

Add one explicit `kind: knowledge` branch, keep the legacy branch unchanged,
and update existing installers, gates, agents, and tests. Moderate bounded blast
radius, high durability, and no runtime dependency.

## Option C - Generic Lanes And Auto-Detection

Flexible, but speculative and ambiguous. It expands schema, migration, and test
complexity beyond the current evidence.

## Option D - Keep The Workaround

Zero implementation effort, but future chats continue receiving false UI
context and the root cause remains.

## Decision Matrix

| Option | Safety | Clarity | Durability | Verification | Decision |
|---|---|---|---|---|---|
| A | low | medium | low | installer only | lose |
| B | high | high | high | schema + installers + gates + UI smoke | win |
| C | medium | low | unknown | large matrix | lose |
| D | low | low | none | none | lose |

## Winner

Option B. It is the first YAGNI rung that fixes the config contract and the
actual consumer without inventing future profiles.