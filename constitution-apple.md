# Architrave Constitution — Native Apple App Synthesis (SwiftUI · macOS / iOS / iPadOS)

> The non‑negotiable rule‑base for any Architrave lane that **designs, reviews, reverse‑engineers, or
> generates a native Apple app**. Its single purpose: let Architrave build native apps in **Swift /
> SwiftUI** that are *indistinguishable from first‑party engineering* — **grounding every decision in
> official Apple documentation and WWDC sessions, and reusing system components instead of guessing,
> approximating, or reinventing them.**

This document is **Apple‑only** (macOS, iOS, iPadOS; the same engine extends to tvOS / watchOS /
visionOS). Windows / Fluent guidance lives elsewhere and is out of scope here.

---

## 0. Epistemic mandate (read first)

1. **Ground in ground truth.** Every structural, typographic, color, material, iconography, and
   accessibility decision must trace to a primary Apple source: the **Human Interface Guidelines
   (HIG)**, **Apple developer documentation** (SwiftUI / AppKit / UIKit / Symbols), **WWDC engineering
   sessions**, **SF Symbols**, and **Apple Design Resources**. Cite the source for any non‑trivial call.
2. **Reuse, don't reinvent.** If a native system component, modifier, or scene type satisfies the
   requirement, use it. A custom control is a *last resort* that must be justified against the
   system component it replaces.
3. **No guessing.** If a spec (a size, a token, an API name, a behavior) is uncertain, **verify it
   against the live HIG / developer docs** before emitting code — do not approximate from memory or
   from community blog posts. Models are frequently trained on outdated or low‑quality SwiftUI; treat
   internal recall as a hypothesis to confirm, never as authority.
4. **Modern over legacy.** Adopt the current design system (**Liquid Glass**, WWDC25 → refined WWDC26)
   and modern structural APIs (`NavigationSplitView`, `.inspector`, `Scene` types, `symbolEffect`).
   Treat deprecated paradigms (`NavigationView` nesting, hard‑coded backgrounds behind system bars,
   `controlActiveState`) as migration targets, not patterns to reproduce.
5. **Let the system do the work.** Standard components automatically pick up the latest material,
   shape, spacing, Dark Mode, Dynamic Type, and accessibility behavior. The most native code is
   usually the code you *don't* write.

### Forbidden by default
- Hard‑coding font point sizes (`.font(.system(size: 17))`) for body/UI text — use **semantic text styles**.
- Hard‑coding color hex values — use **semantic system colors** / asset‑catalog colorsets.
- Hard‑coding `.frame(width:height:)` for layout — use relative sizing, `Spacer`, `padding`, `maxWidth: .infinity`.
- Painting custom backgrounds behind system bars, sidebars, toolbars, split views, or sheets (it fights Liquid Glass and the scroll‑edge effect).
- Stacking translucent / Liquid Glass layers on top of each other.
- Using SF Symbols (or look‑alikes) in **app icons or logos** (prohibited by the SF Symbols license).
- Inventing a parallel spacing/type/color scale when the system already defines one.

---

## 1. Foundations

### 1.1 Typography — SF Pro + semantic text styles

**System families.** **San Francisco (SF Pro** on macOS/iOS/iPadOS, **SF Compact** on watchOS) for UI;
**New York (NY)** is the system serif. SF and NY ship as **variable fonts** with **dynamic optical
sizing** (Text↔Display merge automatically) — never embed system fonts; reference them via
`Font.Design` (`.default`, `.serif`, `.rounded`, `.monospaced`).

**Rule:** drive all text from **semantic text styles** (`.font(.largeTitle / .title / .title2 /
.title3 / .headline / .body / .callout / .subheadline / .footnote / .caption / .caption2)`), never raw
sizes. Semantic styles give you Dynamic Type, optical sizing, and correct leading for free. Add
emphasis with the `.bold()` / `.weight()` symbolic traits, not a different typeface.

**macOS built‑in text styles** (Apple HIG *Typography → Specifications*, point @2x — use for reference/mockups only):

| Style | Weight | Size (pt) | Leading (pt) | Emphasized |
|---|---|---|---|---|
| Large Title | Regular | 26 | 32 | Bold |
| Title 1 | Regular | 22 | 26 | Bold |
| Title 2 | Regular | 17 | 22 | Bold |
| Title 3 | Regular | 15 | 20 | Semibold |
| Headline | Bold | 13 | 16 | Heavy |
| Body | Regular | 13 | 16 | Semibold |
| Callout | Regular | 12 | 15 | Semibold |
| Subheadline | Regular | 11 | 14 | Semibold |
| Footnote | Regular | 10 | 13 | Semibold |
| Caption 1 | Regular | 10 | 13 | Medium |
| Caption 2 | Medium | 10 | 13 | Semibold |

**iOS / iPadOS Dynamic Type — Large (default) sizes** (HIG *Typography → Specifications*; verify the full xSmall→AX5 ramp in the live HIG / Apple Design Resources before pixel work):

| Style | Weight | Size (pt) | Leading (pt) | Emphasized |
|---|---|---|---|---|
| Large Title | Regular | 34 | 41 | Bold |
| Title 1 | Regular | 28 | 34 | Bold |
| Title 2 | Regular | 22 | 28 | Bold |
| Title 3 | Regular | 20 | 25 | Semibold |
| Headline | Semibold | 17 | 22 | Semibold |
| Body | Regular | 17 | 22 | Semibold |
| Callout | Regular | 16 | 21 | Semibold |
| Subhead | Regular | 15 | 20 | Semibold |
| Footnote | Regular | 13 | 18 | Semibold |
| Caption 1 | Regular | 12 | 16 | Semibold |
| Caption 2 | Regular | 11 | 13 | Semibold |

> ⚠️ **Correction vs. common cheat‑sheets:** the macOS table is **not** the iOS table — macOS Body is
> **13 pt**, iOS Body is **17 pt**. Do not reuse iOS sizes on macOS or vice‑versa.

**Tracking (letter‑spacing).** In a running app the system **adjusts tracking dynamically at every
point size** — so **do not hard‑code tracking in production**. The official **Tracking values** table
exists only to make *static mockups* accurate. Representative SF Pro values (pt @2x), to refute wrong
third‑party charts: 11 pt → +0.06; 12 pt → 0.00; 13 pt → −0.08; 15 pt → −0.23; 16 pt → −0.31; 17 pt
→ −0.43; 20 pt → −0.45; 22 pt → −0.26; 28 pt → +0.38; 34 pt → +0.40. (Large display sizes trend
**positive**, not negative — a common cheat‑sheet error.)

**Weights & legibility.** Prefer **Regular / Medium / Semibold / Bold**. Avoid **Ultralight / Thin /
Light** for UI text; if a thin custom weight is unavoidable, increase the size. Minimize the number of
typefaces. SF Symbols share the nine SF weights, so symbols match adjacent text exactly.

**Minimum & default sizes** (HIG): **iOS/iPadOS 17 pt default / 11 pt min**; **macOS 13 pt default /
10 pt min**.

**Dynamic Type.** iOS/iPadOS support Dynamic Type — layouts must reflow (stacked layouts at large
sizes, fewer columns, no truncation of meaningful text, icons scale via SF Symbols). **macOS does not
support Dynamic Type**; use the dynamic system‑font control variants
(`controlContentFontOfSize`, `labelFontOfSize`, `menuFontOfSize`, …) to match standard controls.

### 1.2 Color — semantic, adaptive, never hard‑coded

- **Use semantic system colors** (`Color.primary`, `.secondary`, `Color(.label)`, `Color(.systemBackground)`,
  `Color(nsColor:)` / `Color(uiColor:)` system colors). They adapt automatically to **light**, **dark**,
  **Increase Contrast**, vibrancy, and Liquid Glass — and their published RGB values **change between
  releases**, so referencing them by hex is wrong by construction.
- **Define semantics, not appearances.** Don't repurpose a dynamic color against its meaning (e.g. the
  `separator` color is not a text color). On iOS use the **system** vs **grouped** background sets, each
  with primary/secondary/tertiary tiers to express hierarchy.
- **Custom colors** must live in an **asset‑catalog colorset** with **light + dark variants and an
  Increase‑Contrast variant** for each — *even if the app ships one appearance*, because Liquid Glass
  adapts across contexts.
- **Never rely on color alone** to convey state or meaning — pair it with a shape, icon, label, or SF
  Symbol variant (e.g. `.slash` for unavailable). Consider cultural color meaning (red ≠ universal).
- **Accent color.** macOS apps may declare an app **accent color** (overridden by the user's System
  Settings accent unless a sidebar icon uses a fixed semantic color). Don't theme an entire page in a
  brand/service color — use color as a small cue, not a wash.

### 1.3 Liquid Glass color
By default **Liquid Glass has no color** — it picks up the content behind it; small bars adapt their
labels light/dark monochromatically, sidebars are more opaque for legibility. **Apply tint sparingly:**
reserve color for a *single* emphasis target (status, or one **primary action**), and tint the
**background** of that control (the system does this for the prominent **Done** button), **not** every
toolbar item. On colorful/rich backgrounds prefer **monochromatic** toolbars and tab bars.

### 1.4 Layout, spacing & hit targets

- **Differentiate controls from content.** Controls and navigation float in the Liquid Glass layer
  *above* content; let content scroll and peek beneath, and use the **scroll‑edge effect** (not a solid
  background) for the transition. Extend backgrounds/artwork to the window edges; use
  `backgroundExtensionEffect()` to mirror content beneath a sidebar/inspector.
- **Group with negative space**, alignment, and grouping — not gratuitous dividers. Place the most
  important content top‑leading (reading order; honor right‑to‑left).
- **Hit targets / control sizes** (HIG Accessibility): **iOS/iPadOS 44×44 pt** (absolute min 28×28),
  **macOS 28×28 pt** (absolute min 20×20).
- **Padding:** ~**12 pt** around bezeled controls, ~**24 pt** around non‑bezeled elements; treat spacing
  between controls as as important as their size.
- **Repeated‑item corner radius** ≤ 8 pt; align to a consistent grid; build on the existing 8 / 12 / 20
  spacing rhythm rather than inventing a parallel scale.
- **Adaptivity.** Design the full‑size layout first and defer compact layouts as long as possible. Use
  **safe areas** and **layout guides** (avoid the Mac camera housing; never put critical controls at the
  bottom edge of a macOS window). Support continuous/arbitrary window resizing (split views reflow
  fluidly). On iOS use **size classes** (regular/compact) for adaptation.

### 1.5 Materials & Liquid Glass (the WWDC25/26 design system)

**Liquid Glass** is a dynamic material that forms a **distinct functional layer for controls and
navigation** (tab bars, sidebars, toolbars, bars, sheets, popovers) floating above content,
establishing hierarchy through real‑time blur, refraction, and adaptivity.

- **Never put Liquid Glass in the content layer.** Use **standard materials** (`.ultraThin`, `.thin`,
  `.regular`, `.thick`) for content‑layer separation (app backgrounds, grouped sections). The lone
  exception: a transient interactive element in content (a `Slider`/`Toggle` knob) may take a glass
  appearance *while active*.
- **Use glass effects sparingly.** System components adopt it automatically. For custom controls apply
  `glassEffect(_:in:)` only to the few most important functional elements, and combine multiple custom
  glass shapes in a **`GlassEffectContainer`** for performance + fluid morphing. Prefer the
  **`.glass` / `.glassProminent`** button styles over hand‑rolled glass.
- **Variants:** **regular** (blurs/adjusts luminosity for legibility — default; use for text‑heavy or
  legibility‑risk surfaces like sidebars, alerts, popovers) and **clear** (highly translucent — only
  over rich media; add a **35 % dark dimming layer** when the underlying content is bright).
- **Layer economy:** one primary translucent glass surface per view; never stack glass on glass.
- **Vibrancy:** put **vibrant system colors** on materials (don't pick a material for the apparent color
  it gives — system settings change it). Thicker materials = more contrast; thinner = more context.
- **Concentricity:** the hardware's curvature informs nested shapes. Use **`ConcentricRectangle`** /
  `rect(corners:isUniform:)` so controls, sheets, and popovers nest concentrically in their containers.
- **Adopt automatically:** building against the latest SDK makes standard `NavigationStack`,
  `NavigationSplitView`, `titleBar`, and `toolbar` pick up Liquid Glass — so **remove custom backgrounds**
  from those. To intentionally defer adoption, set `UIDesignRequiresCompatibility` (a temporary escape
  hatch, not a strategy).

### 1.6 SF Symbols — the iconography system

Use **SF Symbols** wherever an interface icon appears (toolbars, tab bars, menus, inline with text).
They align to the SF baseline and scale with Dynamic Type automatically. **Never** use them in app
icons/logos; some symbols depict Apple products and **cannot be customized**.

- **Rendering modes** — declare via `.symbolRenderingMode(_:)`:
  - **Monochrome** — one color across all layers (dense toolbars, inline text, legacy parity).
  - **Hierarchical** — one color, varied opacity per layer (depth/emphasis without clutter).
  - **Palette** — two+ explicit colors, one per layer (high‑contrast/brand states).
  - **Multicolor** — intrinsic real‑world colors (e.g. `leaf` green, `trash.slash` red for data loss).
  Use system colors so symbols adapt to Dark Mode/vibrancy/accessibility. (SF Symbols 7+: smooth
  **gradient** rendering from a single source color works in all modes.)
- **Variable color** — communicates a *changing quantity* (signal, capacity, progress) by lighting
  layers across thresholds. Use it for change, **not** for depth (use Hierarchical for depth).
- **Weights (9: ultralight→black)** match the SF font weights — match the symbol weight to adjacent
  text. **Scales (small / medium / large)** are relative to cap height; use `imageScale(_:)` to adjust
  emphasis without breaking weight matching.
- **Design variants** — `.fill`, `.slash`, `.circle`/`.square`/enclosures via `.symbolVariant(_:)`.
  Encode state with variants: `.fill` = selection/active (tab bars), `.slash` = unavailable, outline =
  alongside text (toolbars/lists). Often the container picks the variant (tab bar → fill, toolbar → outline).
- **Animations** (`symbolEffect`, `contentTransition(.symbolEffect(.replace))`): **appear / disappear,
  bounce, scale, pulse, variable color, replace (Magic Replace is the new default), wiggle, breathe,
  rotate, draw‑on / draw‑off**. Pick by intent — *discrete* (`.bounce`, `.pulse` once) for "an action
  happened"; *indefinite* (`.breathe`, `.rotate`, `.variableColor.iterative`) for ongoing activity;
  *content transition* (`.replace`) for state morphs (lock → checkmark). Animate **judiciously** — too
  many effects overwhelm. Always provide an **accessibility label** for every symbol.
- **Custom symbols** only when SF Symbols lacks one: export the closest template, match detail/optical
  weight/alignment/perspective, annotate layers for rendering modes + animation, supply VoiceOver
  descriptions. Don't replicate Apple products.

---

## 2. The new design system in practice (Design Language · Structure · Continuity)

Per **WWDC25 *Get to know the new design system*** the system reshapes the interface↔content
relationship along three axes — use them as a review lens:

- **Design language** — Liquid Glass material, dynamic/expressive **layered app icons** (compose in
  **Icon Composer**; default/dark/clear/tinted variants; let the system apply blur/shadow/specular),
  rounder concentric forms, refreshed controls that morph on interaction.
- **Structure** — a **clear, consistent navigation hierarchy that is visually distinct from content**.
  Navigation (tab bars, sidebars, toolbars) floats in the glass layer above the content layer; menus
  adopt icons for common actions; toolbars group related items with **`ToolbarSpacer`**.
- **Continuity** — one design across devices and input modes: tab bars can **adapt into sidebars**
  (`sidebarAdaptable`); split views reflow on resize; the same components read correctly on macOS,
  iPad, and iPhone.

---

## 3. macOS structural architecture (the native building blocks)

Reproduce a Mac app's **structure** (Music, Mail, Finder are IA references — copy the structure, never
the pixels) from these system primitives:

- **Scenes.** `WindowGroup` for primary windows; a dedicated **`Settings`** scene for preferences;
  **`MenuBarExtra`** for menu‑bar presence; **`UtilityWindow`** (`.floating` window level, Escape‑to‑
  dismiss, receives `FocusedValues`) for tool palettes / inspectors that live alongside the main scene.
  A settings window without tabs/toolbar is titled **"<App> Settings"** with maximize/minimize disabled
  and centered on first launch.
- **Three‑pane shell.** **`NavigationSplitView`** — **sidebar** (a `List` of `Section`s; each row a
  `Label` + SF Symbol) │ **content** │ optional **detail** — replaces all nested `NavigationView`.
  Two‑column = `{ sidebar, detail }`; three‑column = `{ sidebar, content, detail }`. Control resize
  behavior with **`navigationSplitViewStyle(.balanced | .prominentDetail | .automatic)`**.
- **Toolbar.** `.toolbar { ToolbarItem(placement:) }` with semantic placements (`.primaryAction`,
  `.navigation`, `.cancellation/.confirmationAction`). Pick a **`windowToolbarStyle`**:
  `.automatic` (title + items share a row) · **`.expanded`** (title gets its own row for dense
  toolbars) · `.unified` · `.unifiedCompact` (single‑view utility windows). Group items and separate
  clusters with **`ToolbarSpacer(.flexible)`**; represent common actions with **standard icons**
  (don't mix text + icons in one group); hide the **whole** toolbar item (not its content) when needed.
  Remove the title with `.toolbar(removing: .title)`; let content reach the top edge with
  `.toolbarBackgroundVisibility(.hidden, for: .windowToolbar)`. Never hand‑roll a toolbar strip in the content layer.
- **Search.** `.searchable(text:, placement: .toolbar)` scoped to the visible list — not a custom field.
- **Inspector / right drawer.** `.inspector(isPresented:)` (macOS 14+) with `inspectorColumnWidth` — a
  dismissible trailing pane, **not** a modal sheet. (On compact widths it adapts to a bottom sheet.)
- **Lists vs tables.** A multi‑attribute, sortable collection (Name · Kind · Date · Size) is a
  **`Table`** with `TableColumn`s — stretching, user‑resizable columns and click‑to‑sort headers
  (`sortOrder` + `KeyPathComparator`). Use **`List` + a custom row** only for compact / art‑led layouts.
  **Never fake a table** with hand‑laid `HStack` columns.
- **Context menus.** `.contextMenu` on each row, **mirroring** the row's affordances (never hiding the
  primary action).
- **Windows & modals.** Rounder corners, continuous resize, fluid split‑view reflow. **Sheets** adopt
  Liquid Glass + larger corner radius (don't add custom visual‑effect backgrounds). **Action sheets /
  confirmation dialogs** originate from their source control.

### 3.1 Active state & selection emphasis (the macOS "tell")
Inactive windows must recede. System `List`s handle this; **custom views do not**. Evaluate
**`@Environment(\.appearsActive)`** (the modern SwiftUI value; prefer it over the older
`controlActiveState`) and **dim** custom elements (e.g. `.opacity(0.5)` / desaturate) when it is
`false`. For a custom selection list, also track keyboard focus (`.focused()`) and only show the full
**accent** highlight when **both** the window appears active **and** the list is emphasized — otherwise
fall back to a gray (unfocused) selection.

### 3.2 Native component catalog (reuse targets — never reinvent these)
These are the native building blocks (iOS deltas in §4). When a task or screenshot implies one, **map it to the system component first**; each entry gives the rule set and the violations to reject.

- **Toolbar** — top‑edge commands + navigation + search (macOS: in the window frame; items have **no bezel**). `.toolbar { ToolbarItem(placement:) }` + `ToolbarSpacer` + `windowToolbarStyle`. *Three regions:* **leading** = back + sidebar toggle + title + a document menu (not customizable, always visible); **center** = common controls (customizable, **auto‑collapse into the system overflow** as the window narrows); **trailing** = inspector toggles + optional search + the **More (•••)** menu + the **one** `.prominent` primary action (e.g. Done), always visible. Prefer **system SF Symbols without borders**; **never add a manual overflow** (the system adds it); ≤ ~3 groups; keep text‑label buttons in their own group; **every toolbar item must also be a menu‑bar command**; title < 15 chars, never the app name. *Reject:* bordered/circled toolbar symbols, >1 primary action, an `HStack` "toolbar" in the content layer, an action that lives only in the toolbar.
- **Sidebar** — navigation between top‑level areas/collections; leading side; floats in the Liquid Glass layer. `NavigationSplitView` primary column = `List { Section { Label … } }` `.listStyle(.sidebar)`, or the `sidebarAdaptable` tab style. **≤ 2 levels of hierarchy** (deeper → add a content‑list column = 3‑pane split, not a nested drill); SF Symbols for rows; icons follow the **accent color** by default (fixed color only sparingly, for meaning); let people **hide/show** it (macOS *View ▸ Show/Hide Sidebar*, iPad edge‑swipe); extend content beneath via `backgroundExtensionEffect()`; **no critical actions at the bottom**. *Reject:* a 3‑level sidebar tree, bottom‑pinned critical controls, recoloring every icon off‑accent.
- **Lists vs Tables vs Collections** — **`Table`** (macOS/iPadOS) for multi‑attribute, sortable data (Song · Artist · Album · Time): **click a header to sort, re‑click reverses, columns resize, alternating rows for wide tables** (`Table` + `TableColumn` + `sortOrder` + `KeyPathComparator`). **`List` + custom row** for compact / art‑led / iOS (grouped style; **chevron = navigate deeper**, **info button = show details** — never conflate; edit mode to reorder/select). **`OutlineGroup`** for hierarchical disclosure. **`LazyVGrid`** for many images / widely varying sizes. Column headings: nouns, **title‑style capitalization**, no trailing punctuation. *Reject:* an `HStack`‑column fake table (no sort/resize), a chevron used as an info action, tabular data forced into cards.
- **Buttons & controls** — hit region **≥ 44×44 pt** (macOS pointer 28×28; visionOS 60×60); always a **press state**. Roles: `Normal` · **`.primary`** (accent fill, responds to **Return**, auto‑closes a sheet/alert) · **`.cancel`** · **`.destructive`** (system **red**) — **never a destructive primary**; ≤ **1–2 prominent** buttons per view; signal the preferred option by **style, not size**. **Ellipsis (…)** in a title that opens another window or needs more input (Rename…, Export…). macOS types: push (default/tintable), square/gradient (symbol, **inside a view — not the toolbar**), circular **help** (one per window), image. Pickers: pop‑up button (pick one of N) vs pull‑down `Menu` (a list of actions); `Toggle`/`Slider`/`Stepper` knobs take Liquid Glass while dragging. *Reject:* size used as hierarchy, a destructive primary, >2 prominent buttons, a custom button with no press/disabled state.
- **The menu bar (macOS/iPadOS)** — order **App · File · Edit · Format · View · ‹app‑specific› · Window · Help** (Apple menu leading, extras trailing); build with `commands { CommandMenu / CommandGroup }`. Keep the **standard menus, items, and shortcuts** (⌘C / ⌘V / ⌘X / ⌘S / ⌘P / ⌘Z — the system implements many for free); **always show the same items and disable (don't hide) unavailable ones**; **View** = appearance (Show/Hide Toolbar/Sidebar, Enter/Exit Full Screen), **Window** = window management (Minimize/Zoom) — don't swap them; **every command in a toolbar or context menu must also live in the menu bar** (discoverability + Full Keyboard Access). `MenuBarExtra` (24 pt bar) shows a **menu, not a popover**, unless genuinely complex. *Reject:* hidden‑until‑valid items, a command reachable only via toolbar/right‑click, a full‑screen toggle in the Window menu when a View menu exists.

---

## 4. iOS / iPadOS structural architecture

- **Concentrate on content:** limit on‑screen controls; make secondary actions discoverable with
  minimal interaction. Adapt to orientation, Dark Mode, and Dynamic Type.
- **Navigation:** **tab bars** (bottom) for top‑level sections; **`Tab(role: .search)`** so the system
  pins search to the trailing end; tab bars **float** and can **minimize on scroll**
  (`tabBarMinimizeBehavior(.onScrollDown)`) and **adapt into a sidebar** on iPad
  (`sidebarAdaptable`). Use `NavigationStack` for drill‑in.
- **Ergonomics:** prefer controls reachable in the middle/bottom of the display; support swipe‑back and
  swipe actions in list rows; avoid full‑width buttons that ignore safe‑area margins.
- **Sheets** adopt Liquid Glass; half‑sheets inset from the edge so content peeks beneath; section
  headers use **title‑style capitalization** (not all‑caps). Use **grouped** `Form`/`List` styles for
  automatic platform layout metrics.

---

## 5. SwiftUI code‑generation standards

1. **Semantic APIs over literals.** Colors/materials/fonts → `Color`, `Material`, semantic `Font`
   styles; sizes/spacing → a `DesignTokens` enum (pt), **never** magic numbers; never hard‑code system
   font sizes or hex.
2. **No hard‑coded frames** except fixed‑geometry icons/shapes. Layout via `padding`, `Spacer`,
   `frame(maxWidth: .infinity)`, layout guides, safe areas — so windows resize and Dynamic Type scales.
3. **Compose, don't monolith.** Fracture complex views into small, strongly‑typed subviews so SwiftUI's
   diffing stays performant and the code stays legible.
4. **Propagate state via `@Environment`** (and custom environment keys like `\.isEmphasized`) instead
   of threading booleans through initializers.
5. **Concurrency (Swift 6+).** Respect **`@MainActor`** isolation for UI; use structured `Task`s
   carefully for async data; never block the main thread.
6. **Bridging restraint.** Reach for `NSViewRepresentable` / `UIViewRepresentable` /
   `NSWindowController` **only** when SwiftUI genuinely can't express it (e.g. a specific
   `NSVisualEffectView` blend, deep window‑styling edge cases) and isolate the bridge to the smallest
   possible surface — keep everything else declarative.
7. **Let standard components carry the design.** Build against the latest SDK, remove custom backgrounds
   from system bars/sidebars/sheets, and verify in light + dark + Increase Contrast + Reduce
   Transparency + Reduce Motion.

---

## 6. Reverse‑engineering protocol (mockup / screenshot / existing app → `.swift`)

Execute in order; **stop and verify against official docs** at any uncertain step.

1. **Platform disambiguation.** Confirm the target is an Apple platform and which one — corner radii,
   **Liquid Glass** (vs Windows Mica/Acrylic), **SF Symbols** (vs Fluent icons), **SF Pro** baseline,
   traffic‑light window controls, sidebar/inspector idiom. If it's not Apple, this constitution doesn't apply.
2. **Structural mapping.** Decompose the flat UI into a SwiftUI scene hierarchy: root **`Scene`**
   (`WindowGroup` / `Settings` / `MenuBarExtra`) → navigation framework (**`NavigationSplitView`**
   columns; 2 vs 3 pane) → **toolbar** placements + style → does supplementary data want an
   **`.inspector`** or a detached **`UtilityWindow`**? Multi‑attribute collection → **`Table`**;
   art‑led/compact → **`List` + row**.
3. **Material & depth inference.** Separate Z‑layers: content layer (standard materials / app
   background) vs the **Liquid Glass functional layer** (bars, sidebar, toolbar) vs modal sheets.
   Assign `presentationBackground` / `containerBackground` / `glassEffect` only where the layer demands
   it; do **not** glass the content layer.
4. **State & environment inference.** Identify interactive states and where **`\.appearsActive`** and
   **`\.isEmphasized`** must dim/emphasize elements on focus shifts; map primary actions to prominent
   styles; map "unavailable" to `.slash` symbol variants, etc.
5. **Component mapping — reuse beats reinvention.** Map every element to its **nearest native system
   component** (sidebar row → `Label` in a `List` `Section`; sort control → `Menu`; overflow → `•••`
   `Menu`; search → `.searchable`; transport → bottom control surface via `safeAreaBar`/`safeAreaInset`).
   Only synthesize a custom control when no system component fits — and document why.
6. **Token extraction.** Snap arbitrary paddings to the spacing rhythm; resolve colors to **semantic
   system colors / colorsets**; resolve text to **semantic styles**; resolve icons to **SF Symbols**.
   Produce a `DesignTokens` enum, not literals.
7. **Validation.** Render in Storybook / Xcode Previews across **light + dark + Increase Contrast +
   Dynamic Type (iOS) + Reduce Motion**, confirm contrast and hit‑target minimums, and re‑check each
   non‑obvious choice against the cited HIG/section before sign‑off.

### 6.1 Auditing a shared screenshot, mockup, or task (HIG conformance pass)
When the user shares a screenshot, design, or a task that references one, **don't just reproduce it — grade it against the HIG first**, then build. Produce findings:

1. **Identify the surface** (window / sheet / sidebar / toolbar / list / now‑playing bar) and map each visible element to a native component (§3.2).
2. **Run the §9 sign‑off checklist** against what's shown: layer model, semantic typography (macOS vs iOS sizes), semantic color + dark mode, Liquid Glass placement, SF Symbols usage, hit targets + contrast, native‑component fidelity, active/emphasis state.
3. **Emit findings** as `violation → the HIG rule it breaks (cite §/page) → the native component / token / API that fixes it → severity`, separating **Blockers** (platform‑foreign control, reinvented component, contrast/hit‑target failure, dishonest disabled/empty state) from **polish**.
4. **Then** propose the fix in real component names. If the reference is non‑Apple (a Spotify / web screenshot), translate the **intent** to the native idiom — never copy the foreign chrome.

A shared image is **graded against the rules, not copied** — the antidote to "looks close enough."

---

## 7. Accessibility mandate (a conformance floor, not a nicety)

- **Contrast (WCAG AA, used by Accessibility Inspector):** text **≤ 17 pt → 4.5 : 1**; **18 pt → 3 : 1**;
  **bold → 3 : 1**. Verify in **both** light and dark; if default fails, provide an Increase‑Contrast scheme.
- **Hit targets:** iOS/iPadOS **44×44 pt**, macOS **28×28 pt** (see §1.4 for absolute minimums + padding).
- **Don't encode meaning in color alone** — add icon/shape/label (§1.2).
- **Dynamic Type (iOS):** layouts reflow, no truncation of meaningful text, icons scale (SF Symbols).
- **VoiceOver:** every control labeled (`.accessibilityLabel/Value/Hint`), sensible reading order,
  custom symbols described.
- **Full Keyboard Access + standard shortcuts:** never override system shortcuts; be Switch Control /
  Voice Control friendly.
- **Reduce Motion:** tighten springs, track gestures directly, avoid z‑axis depth, **replace x/y/z
  transitions with fades**, avoid animating into/out of blurs.
- **Cognitive:** minimize time‑boxed/auto‑dismiss UI; **double‑confirm** hard‑to‑recover actions
  (delete); don't autoplay media without controls.

---

## 8. Anti‑patterns (reject on sight)

- Hard‑coded font sizes / hex colors / `.frame` layout for adaptive UI.
- iOS sizes used on macOS (or vice‑versa); non‑Apple tracking cheat‑sheets.
- Custom backgrounds behind system bars/sidebars/sheets; stacked glass; glass in the content layer.
- A hand‑laid `HStack` "table"; a hand‑rolled toolbar strip; a modal sheet used where an `.inspector` belongs.
- A web hamburger menu or an iOS tab bar transplanted onto macOS; platform‑foreign controls.
- Copying a non‑Apple screenshot's chrome (web hamburger, Spotify cards) instead of translating the *intent* to the native idiom; a command reachable only via a toolbar or right‑click and missing from the menu bar.
- SF Symbols (or look‑alikes) in app icons/logos; reproducing Apple‑product symbols as custom art.
- A custom control where a native component exists; an invented spacing/type/color scale.
- Bright accent highlights left active while the window is in the background.

---

## 9. Sign‑off checklist

- [ ] Every type style is **semantic** (no raw sizes); macOS vs iOS table used correctly.
- [ ] Every color is a **semantic system color / colorset** with light + dark + Increase‑Contrast.
- [ ] Controls/navigation live in the **Liquid Glass functional layer**; content layer uses standard
      materials; no custom backgrounds on system bars; ≤ one glass surface per view.
- [ ] Structure uses native scenes + **`NavigationSplitView`** + semantic **toolbar** + **`.inspector`**;
      `Table` vs `List` chosen correctly.
- [ ] Native components match the **§3.2 catalog** (toolbar regions, sidebar ≤ 2 levels, `Table` vs `List`,
      button roles/prominence, menu‑bar order + every command in the menu bar) — nothing reinvented.
- [ ] All iconography is **SF Symbols** with correct rendering mode/variant/weight + accessibility labels.
- [ ] Hit targets, padding, and **contrast** meet the platform floor in light **and** dark.
- [ ] `\.appearsActive` / `\.isEmphasized` handled for custom views (macOS).
- [ ] Reduce Motion, Dynamic Type (iOS), VoiceOver, Full Keyboard Access verified.
- [ ] Code: composed subviews, `@Environment` propagation, `@MainActor` isolation, minimal AppKit/UIKit bridge.
- [ ] Every non‑trivial decision **cites** an official source below.

---

## 10. Citations (primary sources — verify the live page for big calls)

**Human Interface Guidelines** (`developer.apple.com/design/human-interface-guidelines/…`):
[Typography](https://developer.apple.com/design/human-interface-guidelines/typography) ·
[Color](https://developer.apple.com/design/human-interface-guidelines/color) ·
[Layout](https://developer.apple.com/design/human-interface-guidelines/layout) ·
[Materials](https://developer.apple.com/design/human-interface-guidelines/materials) ·
[SF Symbols](https://developer.apple.com/design/human-interface-guidelines/sf-symbols) ·
[Accessibility](https://developer.apple.com/design/human-interface-guidelines/accessibility) ·
[Designing for macOS](https://developer.apple.com/design/human-interface-guidelines/designing-for-macos) ·
[Designing for iOS](https://developer.apple.com/design/human-interface-guidelines/designing-for-ios) ·
[Toolbars](https://developer.apple.com/design/human-interface-guidelines/toolbars) ·
[Sidebars](https://developer.apple.com/design/human-interface-guidelines/sidebars) ·
[Lists and tables](https://developer.apple.com/design/human-interface-guidelines/lists-and-tables) ·
[Buttons](https://developer.apple.com/design/human-interface-guidelines/buttons) ·
[The menu bar](https://developer.apple.com/design/human-interface-guidelines/the-menu-bar) ·
[Windows](https://developer.apple.com/design/human-interface-guidelines/windows) ·
[Split views](https://developer.apple.com/design/human-interface-guidelines/split-views).

**Developer documentation:**
[Adopting Liquid Glass](https://developer.apple.com/documentation/TechnologyOverviews/adopting-liquid-glass) ·
[`NavigationSplitView`](https://developer.apple.com/documentation/SwiftUI/NavigationSplitView) ·
[`inspector(isPresented:)`](https://developer.apple.com/documentation/SwiftUI/View/inspector(isPresented:content:)) ·
[`glassEffect(_:in:)`](https://developer.apple.com/documentation/SwiftUI/View/glassEffect(_:in:)) ·
[`Material`](https://developer.apple.com/documentation/SwiftUI/Material) ·
[`Color`](https://developer.apple.com/documentation/SwiftUI/Color) ·
[Symbols framework / `SymbolEffect`](https://developer.apple.com/documentation/Symbols) ·
[Apple Design Resources](https://developer.apple.com/design/resources/).

**WWDC sessions:**
[Meet Liquid Glass (WWDC25 219)](https://developer.apple.com/videos/play/wwdc2025/219) ·
[Get to know the new design system (WWDC25 356)](https://developer.apple.com/videos/play/wwdc2025/356) ·
[Build an AppKit app with the new design (WWDC25 310)](https://developer.apple.com/videos/play/wwdc2025/310) ·
[What's new in SF Symbols 7 (WWDC25 337)](https://developer.apple.com/videos/play/wwdc2025/337) ·
[Get started with Dynamic Type (WWDC24 10074)](https://developer.apple.com/videos/play/wwdc2024/10074).

> **Operating reminder:** when in doubt, **open the live HIG / developer doc / WWDC session and confirm
> before emitting code.** Spec numbers (sizes, colors, device dimensions) and APIs evolve every release;
> this constitution is a grounding lattice, not a substitute for the source of truth.
