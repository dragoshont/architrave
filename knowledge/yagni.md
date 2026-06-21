# YAGNI pack

The cited rule base for Architrave's minimum-sufficient-change discipline: build only what the current task proves it needs, prefer existing repo/platform capability, and keep the system easy to change instead of predicting a speculative future.

Grounded in current practice:
- **Ward's Wiki / XP:** YAGNI means "Always implement things when you actually need them, never when you just foresee that you need them." The benefit is avoiding unused code and guesses that become wrong but stick around.
- **Martin Fowler — Yagni:** presumptive features carry build cost, delay cost, carry cost, and repair cost. YAGNI applies to capabilities and speculative abstractions, not to enabling practices like refactoring, tests, and continuous delivery that keep the code malleable.
- **Ponytail:** an agent skill/plugin that turns YAGNI into a concrete ladder: ask whether the code needs to exist, then prefer standard library, native platform features, installed dependencies, one-liners, and only then minimum custom code. Its useful contribution is the ladder + carve-outs + review tags, not a runtime library.
- **Caveman comparison:** Caveman primarily compresses agent prose/output tokens. Ponytail targets the code diff itself. They are complementary; terse speech is not the same as minimal implementation.

## Architrave decision ladder

Before writing code, stop at the first rung that satisfies the acceptance criteria:

1. **Do nothing / delete:** Is the requested capability speculative, already satisfied, or outside the signed-off scope? Skip it, or delete dead/speculative code.
2. **Existing repo source of truth:** Is there already a Storybook component, design-map entry, backend contract, source adapter, helper, ADR, script, or gate that covers it? Reuse that.
3. **Platform/native feature:** Does the platform solve it? Use system UI, browser/native inputs, database constraints, OS APIs, framework validation, or built-in routing before custom code.
4. **Standard library:** Does the language/runtime standard library solve it correctly, including edge cases? Use it.
5. **Already-installed dependency:** If a dependency is already in the repo and fits the task, use it. Do not add a new dependency for what a few clear lines can do.
6. **Tiny local implementation:** Write the smallest local code that satisfies the criteria and tests.
7. **New abstraction/dependency/config:** Add only with evidence: at least two concrete uses, a current contract/ADR, measurable need, or explicit user requirement. Otherwise document the future path as a candidate lesson, not code.

The ladder is a reflex, not a research project. If two rungs work, choose the higher rung and move on. The first correct minimal solution wins.

## What YAGNI does not mean

- Do not cut input validation at trust boundaries.
- Do not cut error handling that prevents data loss or hidden failure.
- Do not cut security, authorization, privacy, policy compliance, accessibility, or capability honesty.
- Do not cut tests for non-trivial logic. Keep the smallest meaningful check that would catch the failure.
- Do not use YAGNI to justify sloppy design. Refactoring, design-token reconciliation, contracts, and clear seams are enabling practices that make later changes cheap.
- Do not argue after the user explicitly asks for the full version; build it, still using repo patterns.

## Ponytail evaluation

Ponytail is not a library Architrave should import. The relevant package is an agent skill/plugin (`DietrichGebert/ponytail`, npm `opencode-ponytail`); the npm package named `ponytail` is unrelated site-maintenance code, and the PyPI package named `ponytail` is log-tail functionality.

Ponytail's corrected agentic benchmark is more useful than its original single-shot numbers. It used real headless Claude Code sessions on `tiangolo/full-stack-fastapi-template`, with baseline, Ponytail, Caveman, and a short `YAGNI + one-liners` prompt arm. Its reported feature-task means for Haiku 4.5 were: Ponytail `-54%` LOC, `-22%` tokens, `-20%` cost, `-27%` time versus no-skill baseline; Caveman cut only LOC and increased tokens/cost/time; the one-line YAGNI prompt helped but was less consistent. In the safety tier, Ponytail kept `100%` safety while the one-line prompt dropped a guard once (`95%`).

Read those results with caveats: one public benchmark, one main model, limited tasks, and LLM judges for completeness/over-engineering. The defensible lesson for Architrave is not to vendor Ponytail or copy its persona. The lesson is to encode a concrete decision ladder, safety carve-outs, over-engineering review tags, and gate evidence.

## Review tags

Use these in judge findings and self-review when a diff gets larger than needed:

- `delete:` dead code, unused flexibility, speculative feature.
- `reuse:` existing repo component/helper/contract already covers this.
- `native:` platform/framework/browser/database feature replaces custom code.
- `stdlib:` standard library replaces hand-rolled code.
- `yagni:` abstraction with one implementation, config nobody sets, factory with one product, layer with one caller, future-proofing without current use.
- `shrink:` same behavior, fewer files/lines/dependencies.

## Positioning consequence

Generic development agents are broad and easy to forget. Architrave should position itself as a specialist: **the Storybook-first, contract-first agent that builds only the repo-proven slice**. Its wedge is not "agent that codes." It is "asked for UI, starts in Storybook; asked for full-stack, starts with the contract; asked for infra, stops at plan; all of it passes YAGNI and judge gates."

## Citations

- Ward Cunningham's Wiki — *You Arent Gonna Need It* (XP practice and original phrasing).
- Martin Fowler — *Yagni* (cost of build/delay/carry/repair, presumptive features, enabling practices).
- Wikipedia — *You aren't gonna need it* (XP context and relationship to refactoring/unit tests/CI).
- DietrichGebert/ponytail — README, `skills/ponytail/SKILL.md`, `skills/ponytail-review/SKILL.md`, and `benchmarks/results/2026-06-18-agentic.md`.
- JuliusBrussee/caveman — README (terse-output/token-compression comparison).