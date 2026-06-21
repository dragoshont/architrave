# Microsoft platform pack — Fluent 2 / WinUI

Loaded by the Platform Design agent when `config.platform = windows` (and usable for Fluent‑React web).

Sources: **Fluent 2** design system (fluent2.microsoft.design — Web/React, iOS, Android, **Windows**) · **Windows app design** on Microsoft Learn (learn.microsoft.com/windows/apps/design). Windows guidance is "a living document, not a list of prescriptive rules."

## Principles & materials
Fluent's pillars: **Light, Depth, Motion, Material, Scale**. Windows 11 materials:
- **Mica** — opaque, desktop‑tinted base layer for long‑lived window backgrounds (low energy).
- **Acrylic** — translucent, blurred material for **transient** surfaces (flyouts, menus, dialogs).
- **Smoke** — dim layer behind modal dialogs. Use depth/elevation to express hierarchy.

## Layout & structure (Windows design basics)
- **App silhouette** + **Windows 11 Signature Experiences** — start from the standard app shell.
- **Navigation:** `NavigationView` (top or left nav); keep hierarchy shallow; back navigation.
- **Commanding:** buttons, **CommandBar**, context menus, **MenuFlyout** — put commands on the right surface.
- **Content basics:** Windows **spacing rationale** (4px grid), use the **type ramp** for hierarchy, **lists & grids** (`ListView`/`GridView`/`ItemsRepeater`), and group related controls.

## Type ramp (Segoe UI Variable)
Caption 12 · Body 14 · Body Strong 14/600 · Subtitle 20 · Title 28 · Title Large 40 · Display 68. Use the named ramp, not arbitrary sizes.

## Color & theming
- **Light / Dark / High‑Contrast** themes are first‑class — every surface must resolve in all three.
- System **accent color** (user‑chosen) + neutral ramps. Reference theme brushes, never hard‑coded hex.

## Design tokens
Fluent ships **global + alias design tokens** (`@fluentui/tokens`) and Figma UI kits. Map your `*.tokens.json` system tier onto Fluent alias tokens / WinUI `ThemeResource` keys.

## Icons
**Fluent UI System Icons** (regular/filled) — match weight/size to text; filled for selected/active state.

## Structural components (the native building blocks)
Reproduce a Windows app from Fluent/WinUI system components (Windows 11 Settings, Mail, Media Player are the IA references):
- **Shell:** `NavigationView` (left pane = sidebar, or top) + content; a **list‑detail** layout or a trailing `SplitView` pane for the **details / inspector** drawer.
- **List vs grid/table:** a multi‑column, sortable collection = the **`DataGrid`** (Community Toolkit) — **resizable, stretching columns** + **click‑to‑sort headers**; use `ListView` / `ItemsRepeater` for row‑ or card‑led lists. Don't hand‑lay columns in a `StackPanel`.
- **Commanding (toolbar):** `CommandBar` (primary commands + `…` overflow) in the header; the **sort/filter** control = a `DropDownButton` / `CommandBar` button opening a `MenuFlyout`.
- **Search:** `AutoSuggestBox` in the header / command bar (the Fluent search field), scoped to the list.
- **Inspector / right drawer:** a trailing `SplitView` pane, or the details pane of the list‑detail pattern — persistent / dismissible, **not** a modal `ContentDialog`.
- **Context menus:** `MenuFlyout` via `ContextFlyout` on each item; mirror the row's commands, don't hide them.
- Transient surfaces (flyouts/menus) ride on **Acrylic**; long‑lived window backgrounds on **Mica**.

## Accessibility
WCAG 2.x AA contrast; ship **High‑Contrast** themes; full **keyboard** support + visible focus visuals; **Narrator** labels via UI Automation (`AutomationProperties.Name`); logical tab/focus order.

## Mapping (how to reproduce)
- **WinUI / XAML:** tokens → `ResourceDictionary` keys consumed via `{ThemeResource …}` / `{StaticResource …}`; theme dictionaries for Light/Dark/HighContrast. Controls: `NavigationView`, `CommandBar`, `InfoBar`, `ContentDialog`, `ItemsRepeater`.
- **Fluent React (web):** `@fluentui/react-components` + Griffel `makeStyles` + `tokens` from `@fluentui/tokens`; wrap app in `FluentProvider` with a theme.
- Validate in Storybook (Fluent React) or the XAML designer across Light/Dark/HighContrast before building; reproduce by component name.

## Citations
learn.microsoft.com/windows/apps/design/basics (navigation/command/content basics, spacing, type ramp) · fluent2.microsoft.design (components Web‑React / Windows, tokens, materials).
