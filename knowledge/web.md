# Web platform pack — React + component‑driven design

Loaded by the Platform Design agent when `config.platform = web`.

Sources: **Component‑Driven Development** (componentdriven.org) · **Storybook** Component Story Format (storybook.js.org) · **Material 3** foundations (m3.material.io/foundations) · **Fluent 2 Web/React** (fluent2.microsoft.design) · **WCAG 2.2**.

## Method: Component‑Driven Development (CDD)
Build **bottom‑up**, and this *is* the design source of truth:
1. **Build one component in isolation**, defining its relevant **states** (default/hover/focus/active/disabled/loading/error/empty).
2. **Combine** small components into composite ones.
3. **Assemble pages** using **mock data** to reach hard states and edge cases.
4. **Integrate** into the app — connect data + business logic last.

Storybook is the workbench; the **Component Story Format (CSF)** is an open ES6‑module standard (non‑proprietary) — type stories with `Meta` / `StoryObj` from the framework package (`@storybook/react-vite`, `@storybook/nextjs`, `@storybook/tanstack-react`, …). Set up with `npm create storybook@latest` (Storybook 10.x; default addons: **vitest, a11y, docs, chromatic, mcp**); mock app context with **MSW** (`msw-storybook-addon`) so components reach real states in isolation. Mental model: **Atomic Design** (atoms → molecules → organisms → templates → pages). Benefits: quality (states in isolation), durability (test at component level), speed (reuse), efficiency (parallelize design/dev).

## React specifics
- Function components + **composition** over inheritance; controlled state; keep state out of presentational components.
- **Semantic HTML first**, then ARIA only where needed; manage focus (focus traps for dialogs, visible focus rings).
- Style from **tokens**: `*.tokens.json` → **CSS custom properties** (`:root { --sys-color-accent: … }`), or Griffel/CSS‑modules/Tailwind mapped to the same token names.

## Design systems you can stand on
- **Fluent React** — `@fluentui/react-components` + `@fluentui/tokens` (pairs with the Microsoft pack).
- **Material** — Material Web / MUI; Material 3 token tiers (ref/sys/comp).
- **Radix + shadcn/ui** — unstyled accessible primitives + token‑themed components.

## Structural components (the building blocks)
Reproduce real desktop‑class web app patterns with accessible primitives (Radix/shadcn, Fluent React, or Material) — not bespoke `<div>` soup:
- **Shell:** `<nav>` sidebar + `<main>` content + optional `<aside>` drawer; responsive (the drawer collapses on narrow viewports).
- **List vs Table:** a multi‑attribute collection (e.g. Title · Artist · Album · Time) is a real **`<table>`** with `<th scope="col">`, **resizable columns** and **sortable headers** (`aria-sort` + a sort control); use a **data‑grid** (TanStack Table / ARIA `role="grid"`) for large / virtualized sets, and cards or list rows only for compact / art‑led layouts. **Don't fake a table** with semantics‑free `<div>`s.
- **Toolbar (top):** a `role="toolbar"` cluster — an overflow menu (`aria-haspopup="menu"`) + the **sort/filter menu** (Title · Genre · Year · … + Asc/Desc).
- **Search (top):** `<input type="search">` (labeled), scoped + debounced to the visible list.
- **Drawer / right panel:** a **Sheet / Dialog** (`role="dialog"` or `complementary`) — focus‑trapped, ESC‑dismissible, returns focus; not a layout‑shifting toggle.
- **Context menu:** a right‑click **Context Menu** (Radix) plus a visible row `…` menu button (keyboard‑reachable); the menu **mirrors** the row's actions.
- Everything: visible focus, full keyboard operability, `aria-*` only where semantic HTML falls short.

## Material 3 foundations (reference)
Accessibility · content design · **design tokens** (reference→system→component) · interaction states · layout. Tokens are the single source of truth across design, tools, and code.

## Accessibility (WCAG 2.2 AA)
- Contrast **4.5:1** text (**3:1** large ≥18.66px/bold or UI components/graphics).
- **Visible focus**, full keyboard operability, logical tab order.
- **Target size** ≥ 24×24 CSS px (AA); ~44 px for touch.
- Never color‑only meaning; honor `prefers-reduced-motion`; label icon‑only controls.

## Testing / gates (Storybook 10.x)
- **Storybook Test = Vitest.** Stories run as component tests via `@storybook/addon-vitest` (`npx vitest --project storybook run`) — every story is a render test (a story that throws fails). This replaces the old `@storybook/test-runner` + Jest / Testing‑Library setup.
- **Interaction tests** = `play` functions (`@storybook/test`: `expect` / `userEvent`) executed inside Vitest — assert behavior + final state.
- **a11y** = the **a11y addon (axe)** in the test run. **Visual regression** = **Chromatic**. **App‑level e2e** = Playwright (separate from component tests).

## Storybook + agents (10.4)
Storybook is increasingly agent‑aware — lean on it:
- **Reuse, don't reinvent (the whole point):** if the repo runs **Storybook MCP for React** (10.3+) with **React Component Meta** (`features.experimentalReactComponentMeta: true`), pull existing component metadata from it to ground in and reproduce components — don't invent new ones.
- **Agentic setup:** to add Storybook to a repo, run `npm create storybook@latest` (or have the agent “set up Storybook … and follow its instructions precisely”) — it scaffolds config, MSW mocks, stories + interaction tests, and verifies they render *with styles*.
- **Review the diff:** use the sidebar **New / Modified / Related** filters (change detection) to review exactly the stories your change touched.
- **Sign‑off:** use **Publish / Share** (one‑click upload to Chromatic) to show the live preview for the human sign‑off step — no commit / PR / CI needed.

## Mapping (how to reproduce)
- Reproduce the **CSF story** as the app component — same component name, same states, same tokens.
- Tokens → CSS custom properties (or the chosen styling system) — never hard‑coded values.
- Every interactive state from the story must exist in the implementation; verify with the visual‑regression + a11y gate.

## Citations
componentdriven.org · storybook.js.org/docs/api/csf · storybook.js.org/docs/ai/setup · storybook.js.org/docs/writing-tests (Vitest) · storybook.js.org/blog/storybook-mcp-for-react · m3.material.io/foundations · fluent2.microsoft.design/components/web/react · w3.org/TR/WCAG22.
