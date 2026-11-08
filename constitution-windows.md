# Architrave Constitution — Native Windows App Synthesis (Fluent 2 · WinUI 3 / Windows App SDK · WPF .NET)

> The non‑negotiable rule‑base for any Architrave lane that **designs, reviews, reverse‑engineers, or
> generates a native Windows desktop app**. Its single purpose: let Architrave build native apps in
> **XAML + C#** (WinUI 3 / Windows App SDK first; WPF on .NET second) that are *indistinguishable from
> first‑party Microsoft engineering* — **grounding every decision in official Microsoft documentation
> (Fluent 2, the Windows 11 design guidance on Microsoft Learn, and the WinUI / Windows App SDK
> reference) and reusing system components instead of guessing, approximating, or reinventing them.**

This document is **Windows‑only** (WinUI 3 / Windows App SDK and WPF; the same Fluent language extends to
**Fluent React** on the web). Apple / SwiftUI guidance lives in `constitution-apple.md` and is out of
scope here. **Fluent 2 is the source of truth**; community blog posts, Metro/Windows‑8 patterns, and the
legacy **Microsoft Design Language 2 (MDL2)** are *not*, except as explicit migration targets.

---

## 0. Epistemic mandate (read first)

1. **Ground in ground truth.** Every structural, typographic, color, material, layering, iconography, and
   accessibility decision must trace to a primary Microsoft source: the **Fluent 2 design system**
   (`fluent2.microsoft.design`), the **Windows apps design** guidance on **Microsoft Learn**
   (`learn.microsoft.com/windows/apps/design`), the **WinUI / Windows App SDK** API reference, **Segoe
   Fluent Icons**, the **Windows design toolkit / Figma** kits, and **Microsoft Build** engineering
   sessions. Cite the source for any non‑trivial call.
2. **Reuse, don't reinvent.** If a native system control, style, or backdrop satisfies the requirement,
   use it. A custom/templated control is a *last resort* that must be justified against the WinUI control
   it replaces.
3. **No guessing.** If a spec (a ramp size, a token/brush key, a control name, a backdrop API, a corner
   radius) is uncertain, **verify it against the live Fluent 2 / Microsoft Learn / WinUI docs** before
   emitting code — do not approximate from memory or from community samples. Models are frequently trained
   on outdated or low‑quality XAML; treat internal recall as a hypothesis to confirm, never as authority.
4. **Modern over legacy.** Target the current system — **Fluent 2**, **WinUI 3 / Windows App SDK**, and
   **.NET 9** (WPF Fluent theme). Treat **UWP/WinUI 2**, **MDL2 / Metro**, hard‑coded backgrounds behind
   Mica, and WinForms paradigms as **migration targets**, not patterns to reproduce.
5. **Let the system do the work.** Standard WinUI controls automatically pick up the current type ramp,
   theme brushes, corner radii, Mica/Acrylic, Light/Dark/High‑Contrast, and accessibility behavior. The
   most native code is usually the code you *don't* write — reference **theme resources**, not literals.

### Forbidden by default
- Hard‑coding font sizes (`FontSize="17"`) for body/UI text — use the **Windows type ramp** `Style`s (`BodyTextBlockStyle`, `TitleTextBlockStyle`, …).
- Hard‑coding color hex values — use **theme brushes** via `{ThemeResource …}` (XAML) / `SystemColors` `DynamicResource` (WPF).
- Hard‑coding `Width`/`Height` for layout — use `Grid` with `*`/`Auto`, `StackPanel`, and alignment; reserve `Canvas` for true overlap only.
- Painting custom backgrounds behind **Mica** (it fights the desktop tint and active/inactive focus), or stacking materials (**Acrylic on Mica on Acrylic**).
- **MDL2 Assets / Metro** chrome, **UWP `ToastNotificationManager`**, or **`BinaryFormatter`** (removed in .NET 9) when a modern equivalent exists.
- **Bold** or **Italic** for emphasis, or **ALL‑CAPS** titles — the ramp uses **Semibold** for emphasis and **sentence case** everywhere.
- Inventing a parallel spacing / type / corner scale when Fluent already defines one (4 epx grid; 12/16‑style ramp; 4/8 px corners).

---

## 1. Foundations

### 1.1 Typography — Segoe UI Variable + the Windows type ramp

**System family.** **Segoe UI Variable** is the Windows 11 UI font — a variable font with two axes:
**weight** (`wght`, Thin 100 → Bold 700) and **optical size** (`opsz`, automatic, optimizing counters for
legibility from **8 pt to 36 pt**). In XAML common controls it is selected by default for supported
languages and optical sizing matches the requested size automatically. Named weights: **Light 300 ·
Semilight 350 · Regular 400 · Semibold 600 · Bold 700**. For non‑Latin scripts use the documented
per‑language UI fonts (Yu Gothic UI, Malgun Gothic, Microsoft YaHei/JhengHei UI, Nirmala UI, …).

**Rule:** drive all text from the **named type ramp**, never raw sizes. Sizes are in **effective pixels
(epx)** — a density‑independent unit that scales across DPI and viewing distance, so you design once.

**Windows 11 type ramp** (Microsoft Learn *Typography*; `size/line‑height` in epx):

| Ramp style | Weight | Size / line‑height (epx) | XAML `Style` resource |
|---|---|---|---|
| Caption | Regular (Small) | 12 / 16 | `CaptionTextBlockStyle` |
| Body | Regular | 14 / 20 | `BodyTextBlockStyle` |
| Body Strong | Semibold | 14 / 20 | `BodyStrongTextBlockStyle` |
| Body Large | Regular | 18 / 24 | *(ramp step — size manually)* |
| Subtitle | Semibold | 20 / 28 | `SubtitleTextBlockStyle` |
| Title | Semibold | 28 / 36 | `TitleTextBlockStyle` |
| Title Large | Semibold | 40 / 52 | `TitleLargeTextBlockStyle` |
| Display | Semibold | 68 / 92 | `DisplayTextBlockStyle` |

Apply via `Style="{StaticResource TitleTextBlockStyle}"` — never a raw `FontSize`. These resources follow
the XAML type‑ramp conventions and ship with WinUI.

**Best practices (verbatim from the docs).** Use **Regular** for most text and **Semibold** for titles
and emphasis. **Sentence case for all UI text, including titles** — *not* Title Case, *not* ALL‑CAPS.
**Bold and Italic are not in the ramp**: use Semibold for emphasis; Italic is excluded because it reduces
legibility (notably for dyslexia). Minimum legible sizes: **14 px Semibold / 12 px Regular**. Default
**left‑aligned** (ragged right); center only in rare cases (e.g. a label under an icon). Keep **50–60
characters per line**; truncate with **ellipses** (clip only in rare cases).

> ⚠️ **Correction vs. Apple/web cheat‑sheets:** Windows measures UI text in **epx**, not points; it uses
> **sentence case** (Apple uses title‑style headers; never bring ALL‑CAPS section headers here); and it
> emphasizes with **Semibold**, never Bold/Italic. Do not transplant an iOS/macOS or Material type scale.

### 1.2 Color — theme brushes, accent, never hard‑coded

- **Two color modes/themes — light and dark — plus High Contrast**, all first‑class. Each mode is a set of
  neutral values **auto‑adjusted for optimal contrast**: *darker* surfaces read as background/less
  important; *lighter/brighter* surfaces are highlighted/important (see §1.4 layering). Every surface must
  resolve correctly in **light + dark + High Contrast**.
- **Reference theme brushes, never hex.** In XAML consume them as `{ThemeResource …}` (e.g.
  `TextFillColorPrimaryBrush`, `LayerFillColorDefaultBrush`, `CardBackgroundFillColorDefaultBrush`,
  `AccentFillColorDefaultBrush`); they swap automatically across the three themes. In **WPF** reference
  `SystemColors.*Key` via **`DynamicResource`** so the app reacts to OS personalization.
- **Accent color** emphasizes important elements and signals interactive state. Its values are
  **generated automatically and optimized for contrast in both modes** — reference the accent **brush
  family** (`AccentFillColorDefault` + the system `Light1/Light2/Light3` and `Dark1/Dark2/Dark3` variants;
  WPF `AccentColorBrushKey` + `Light1/2/3`, `Dark1/2/3`). Use accent **sparingly** — to highlight, not to
  wash a whole surface.
- **Color principles** (docs): use color *meaningfully*; use one color to indicate *interactivity*; color
  is *personal* (honor the user's chosen accent + theme); color is *cultural* (meanings differ by region).
- **Never rely on color alone** to convey state/meaning — pair it with an icon, glyph, shape, or label.
  Design for color‑blindness (≈8 % of men are red‑green color‑blind) and ambient lighting.

### 1.3 Materials — Mica, Acrylic, Smoke (occluding vs. transparent)

Windows uses **materials** to tie surfaces to their environment and distinguish focused from unfocused
apps. Two families: **occluding** (Mica, Acrylic — base layers *beneath* interactive controls) and
**transparent** (Smoke — highlights immersive surfaces).

- **Mica** — an **opaque** material **subtly tinted with the user's desktop background color**; the base
  layer for **long‑lived window backgrounds** (low‑energy, sampled once). **Mode‑aware** and it indicates
  **window focus with built‑in active/inactive states** — so never paint a custom window background that
  defeats it. **Mica Alt** (`Kind="BaseAlt"`) is the deeper‑tinted variant for **tabbed** title‑bar
  experiences.
- **Acrylic** — a **semi‑transparent**, frosted‑glass material (in Windows 11 brighter and more
  translucent). Use **only for transient, light‑dismiss surfaces**: flyouts, menus, context menus,
  tooltips. **Mode‑aware.** Do **not** use Acrylic for a long‑lived window body (that's Mica's job).
- **Smoke** — a transparent dimming layer that **recedes the surfaces beneath a modal** (e.g. a
  `ContentDialog`) to signal blocked interaction. **Not mode‑aware** — always translucent black.

**Layer economy:** one base material per window; **never stack materials**. Apply backdrops with the
platform API (§4), not hand‑rolled blur.

### 1.4 Layering & elevation (the Windows hierarchy model)

Windows 11 expresses hierarchy with a **two‑layer system** plus **elevation** (shadow + contour):

- **Base layer** — the app's foundation: window background (Mica), app **menus, commanding, and
  navigation**. **Content layer** — the central experience, either one contiguous surface or segmented
  into **cards** (`CardBackgroundFillColorDefaultBrush`, layered atop the base via
  `LayerFillColorDefaultBrush`).
- **Elevation values** (shadow intensity + 1 px contour, per the docs): **Window 128 · Dialog 128 ·
  Flyout 32 · Tooltip 16 · Card 8 · Control 2 · Layer 1**. Controls vary elevation by **state**:
  **Rest 2 · Hover 2 · Pressed 1**. Higher elevation → larger, softer shadow.
- Use **shadows purposefully, not decoratively** — standard flyouts/dialogs/tooltips already carry the
  right shadow for their elevation. For custom depth use **`ThemeShadow`** / `DropShadow`, sparingly.

### 1.5 Shapes & geometry — corners and the 4‑epx grid

- **Spacing** snaps to a **4‑epx grid** — consistent gutters/margins; build on Fluent's rhythm rather than
  inventing a parallel scale.
- **Rounded corners — three levels** (Microsoft Learn *Geometry*):
  - **8 px** — top‑level containers: **app windows, flyouts, dialogs** (resource `OverlayCornerRadius`,
    default 8).
  - **4 px** — in‑page elements: **buttons, list backplates, text boxes, combo boxes, bars** (ProgressBar/
    ScrollBar/Slider), and **ToolTip** (a small‑size exception) — resource `ControlCornerRadius`, default 4.
  - **0 px** — straight edges that intersect other straight edges, and windows when **snapped/maximized**.
- **Don't round** where elements meet flush: the two halves of a **`SplitButton`**, or the edge where a
  flyout connects to the control that invoked it. Override globally only via `ControlCornerRadius` /
  `OverlayCornerRadius` in `App.xaml`.

### 1.6 Iconography — Segoe Fluent Icons (the Windows symbol system)

Use **Segoe Fluent Icons** wherever a system glyph appears (nav, command bars, buttons, status). It
**replaced `Segoe MDL2 Assets`** in Windows 11; glyphs live in the Unicode **Private Use Area** (E700–
F8CC). Ranges **E0‑–E5‑ are legacy/deprecated** — don't use them.

- **Reference by control, not raw text.** Use **`SymbolIcon`** with the `Symbol` enum
  (`<SymbolIcon Symbol="Find"/>`), or **`FontIcon`** with `Glyph` + `FontFamily="Segoe Fluent Icons"`
  (or `{StaticResource SymbolThemeFontFamily}`) for glyphs outside the enum. (Web/Fluent React: use
  **Fluent UI System Icons** — regular/filled.)
- **Sizes:** render at **16, 20, 24, 32, 40, 48, 64** for crisp outlines; off‑grid sizes blur. Match icon
  size/weight to adjacent text; **filled** variants for selected/active state, outline otherwise.
- Glyphs share a **fixed width, height, and left origin**, enabling **layering/colorization**; many have
  **mirrored forms** for RTL (Arabic/Hebrew). Icons are **not** meant inline with running text.
- **Common glyphs** (name · PUA): GlobalNavButton `E700` · Back `E72B` · Search `E721` · Settings `E713`
  · More (•••) `E712` · Add `E710` · Cancel `E711` · Save `E74E` · Delete `E74D` · Filter `E71C` · Sort
  `E8CB` · Share `E72D` · Play `E768` · Pause `E769` · ChevronRight `E76C`.
- **Never** put system glyphs in an app icon/logo; don't ship Segoe Fluent Icons to other platforms
  (license). Custom icons only when the set lacks one — match the softer Fluent geometry and metric grid.

---

## 2. The design system in practice (Principles · Pillars · Signature experiences)

Use these as the review lens — the Windows analog of "design language / structure / continuity".

- **Five design principles** (Windows 11): **Effortless** (fast, intuitive, precise) · **Calm** (soft,
  decluttered, recedes so the user stays focused) · **Personal** (adapts to the user's accent, theme, and
  habits) · **Familiar** (refreshed yet recognizably Windows — no learning curve) · **Complete +
  Coherent** (one consistent experience across surfaces). Grade designs against these qualities.
- **Five Fluent pillars:** **Light · Depth · Motion · Material · Scale** — the physical model behind
  Mica/Acrylic (Material), elevation/shadow (Depth/Light), reactive animation (Motion), and adaptive
  layout (Scale).
- **Seven signature experiences** (the foundation categories, each with a Learn page): **Color · Elevation
  & layering · Iconography · Materials · Shapes & geometry · Typography · Motion.** Every screen should be
  decomposable into these.
- **Motion** is **reactive, direct, and context‑appropriate** — it gives feedback to input and reinforces
  spatial way‑finding (connected animations, content transitions). Honor the user's *Animations off*
  / reduced‑motion setting; never animate decoratively.

---

## 3. Windows structural architecture (the native building blocks)

Reproduce a Windows app's **structure** (Windows 11 Settings, Mail, File Explorer, Media Player are the IA
references — copy the structure, never the pixels) from these WinUI primitives:

- **App window & title bar.** Use the **Windows App SDK `AppWindow`**; **extend content into the
  non‑client area** and host a custom **`TitleBar`** so **Mica renders through the title bar**. Keep the
  system caption buttons (minimize/maximize/close) and define the icon via a `FontIconSource`.
- **Shell / navigation.** **`NavigationView`** (left pane = sidebar, or `Top` mode) with `MenuItems` +
  `FooterMenuItems`, an integrated **back button**, and `PaneTitle`; keep hierarchy **shallow**. The
  content frame hosts pages.
- **Commanding (toolbar).** **`CommandBar`** with `PrimaryCommands` + a `…` overflow of
  `SecondaryCommands` (each an `AppBarButton`/`AppBarToggleButton` with a Segoe Fluent icon **and** a
  label). A **`MenuBar`** for classic File/Edit menus; **`MenuFlyout`** / **`CommandBarFlyout`** for
  context menus.
- **Search.** **`AutoSuggestBox`** (the Fluent search field, with `QueryIcon="Find"`) in the header /
  command bar, scoped to the list.
- **Collections.** A multi‑attribute, **sortable** collection (Name · Kind · Date · Size) is the
  **`DataGrid`** (Community Toolkit) — **resizable, stretching columns + click‑to‑sort headers**. Use
  **`ListView`** for row‑ / art‑led lists, **`GridView`** for tiles, **`ItemsRepeater`** for custom
  layouts. **Never** hand‑lay columns in a `StackPanel`.
- **Inspector / right drawer.** A trailing **`SplitView`** pane or a **list‑detail** layout — persistent /
  dismissible, **not** a modal `ContentDialog`.
- **Dialogs & transient surfaces.** **`ContentDialog`** for modal decisions (rides on **Smoke**);
  **`Flyout`** / **`TeachingTip`** for transient/contextual UI (on **Acrylic**); **`InfoBar`** for
  inline, non‑blocking status. Match the surface to the job.

### 3.1 Window focus & active state (the Windows "tell")
Mica conveys **active vs. inactive** automatically; inactive windows recede. **Custom surfaces must
respect this** — don't keep a bright **accent** highlight active while the window is in the background, and
don't paint a window background that overrides Mica's focus states. Standard controls handle hover/pressed
elevation (§1.4) for free.

### 3.2 Native component catalog (reuse targets — never reinvent these)
When a task or screenshot implies one, **map it to the WinUI control first**; each entry gives the rule set
and the violations to reject.

- **`NavigationView` (shell / sidebar)** — top‑level navigation between areas. Left pane (or `Top`);
  `MenuItems` + `FooterMenuItems` (settings/account pinned to the footer); integrated **back button** and
  pane toggle; **`NavigationViewItem`** = Segoe Fluent icon + short label; keep hierarchy **shallow**
  (use a content list‑pane for a third level, not deep nesting). *Reject:* a web **hamburger** drawer or
  an Electron sidebar transplanted as custom XAML; critical actions buried below the fold; a 3‑level
  nav tree.
- **`CommandBar` (commanding)** — top‑edge commands. `PrimaryCommands` visible; the rest collapse into the
  **`…` (More) overflow** as `SecondaryCommands`; each `AppBarButton` carries a **Segoe Fluent icon + a
  label**; group related commands; put the right commands on the right surface (page vs. selection). *Reject:*
  a hand‑laid `StackPanel` "toolbar"; icon‑only commands with no label/tooltip; a manual overflow (the
  control provides one).
- **`ListView` / `GridView` / `ItemsRepeater` vs `DataGrid`** — **`DataGrid`** for multi‑attribute,
  sortable, **resizable‑column** data (click a header to sort, re‑click reverses); **`ListView`** for
  row/art‑led lists, **`GridView`** for tiles, **`ItemsRepeater`** for bespoke virtualized layouts.
  Headers: nouns, sentence case. *Reject:* a `StackPanel`‑column fake table (no sort/resize); tabular data
  forced into cards.
- **Buttons & controls** — **`Button`** (standard) · **Accent button** (`Style="{StaticResource
  AccentButtonStyle}"`, the **one** primary action per view, responds to **Enter/default**) · **`Hyperlink
  Button`** · **`ToggleButton`** · **`SplitButton`** / **`DropDownButton`** (a default action + a menu) ·
  **`ToggleSwitch`** for on/off. Destructive actions are explicit and **confirmed**, **never** the default
  accent. Signal the preferred option by **style, not size**; ≤ **1** accent button per view. *Reject:*
  size used as hierarchy; a destructive default; >1 accent button; a templated control with no hover/
  pressed/disabled state.
- **Dialogs, flyouts & status** — **`ContentDialog`** (modal, on Smoke; ≤ 3 buttons:
  primary/secondary/close) · **`Flyout`** & **`TeachingTip`** (transient, contextual, on Acrylic) ·
  **`InfoBar`** (inline, dismissible status — info/success/warning/error) · **`ToolTip`** (hover hint,
  4 px corners). *Reject:* a `ContentDialog` used where an inline `InfoBar` or a dismissible `SplitView`
  inspector belongs; a custom modal that doesn't dim with Smoke.
- **Notifications** — app/toast notifications via the **Windows App SDK `AppNotificationManager` +
  `AppNotificationBuilder`**. *Reject:* the deprecated UWP `ToastNotificationManager`.

---

## 4. Framework deltas — WinUI 3 / Windows App SDK vs. WPF (.NET)

**WinUI 3 / Windows App SDK is the primary, fully‑native Fluent target.** WPF is a first‑class secondary
target via the **.NET 9 Fluent theme**. UWP/WinUI 2 and WinForms are legacy/migration only.

**WinUI 3 / Windows App SDK** (declarative, no interop):
- **Backdrops:** set `Window.SystemBackdrop` to **`<MicaBackdrop/>`** or **`<DesktopAcrylicBackdrop/>`**;
  Mica Alt via **`<MicaBackdrop Kind="BaseAlt"/>`**.
- **Title bar:** hide the default bar, extend into the non‑client area, host a custom **`TitleBar`** so
  Mica shows through; map the icon via `FontIconSource`.
- **Theme resources:** `{ThemeResource …}` keys + theme dictionaries (Light/Dark/HighContrast).
- **Notifications:** `AppNotificationManager` (not UWP toast APIs).

**WPF (.NET 9 Fluent theme)** (XAML bindings exist; backdrops need DWM interop):
- **Enable Fluent:** declare **`ThemeMode="System"`** on `<Application>` (or merge
  `pack://application:,,,/PresentationFramework.Fluent;component/Themes/Fluent.xaml`). The `ThemeMode`
  API is experimental — suppress **`WPF0001`** (`<NoWarn>$(NoWarn);WPF0001</NoWarn>` or `#pragma`).
- **Mica/Acrylic & corners (DWM P/Invoke):** WPF has no native Mica binding — call
  `DwmSetWindowAttribute` (`dwmapi.dll`): **Mica** = `DWMWA_SYSTEMBACKDROP_TYPE (38)` →
  `DWMSBT_MAINWINDOW (2)`; **Acrylic** = `(38)` → `DWMSBT_TRANSIENTWINDOW (3)`; **dark frame** =
  `DWMWA_USE_IMMERSIVE_DARK_MODE (20)` → TRUE; **rounded corners** =
  `DWMWA_WINDOW_CORNER_PREFERENCE (33)` → `DWMWCP_ROUND (2)` / `DWMWCP_ROUNDSMALL (3)`.
- **Accent & theming:** reference `SystemColors.AccentColorBrushKey` (+ `Light1/2/3`, `Dark1/2/3`) via
  **`DynamicResource`** so OS personalization flows through.
- **Security:** **never** emit `BinaryFormatter` (removed in .NET 9 — deserialization risk); for
  clipboard/state/drag‑drop use **`System.Text.Json`**.

---

## 5. XAML / C# code‑generation standards

1. **Theme resources over literals.** Colors/brushes → `{ThemeResource …}` (WPF `DynamicResource`
   `SystemColors`); text → type‑ramp `Style`s; spacing/sizes → a `Thickness`/`x:Double` **resource set**,
   never magic numbers; never hard‑code hex or `FontSize`.
2. **No hard‑coded frames** except fixed‑geometry icons/shapes. Layout via **`Grid`** (`*`/`Auto`),
   `StackPanel`, `RelativePanel`, alignment, and `Margin`/`Padding` — so windows resize and epx scaling
   works. Reserve `Canvas` for genuine overlap.
3. **MVVM by default.** Prefer compiled **`{x:Bind}`** (with `x:DataType`) over `{Binding}`; ViewModels
   with `INotifyPropertyChanged` (**`CommunityToolkit.Mvvm`** `ObservableObject` / `[ObservableProperty]`
   / `[RelayCommand]`); commands over event handlers; keep code‑behind thin.
4. **Compose, don't monolith.** Fracture complex views into small `UserControl`s / `DataTemplate`s with
   `x:DataType`; use `ResourceDictionary` (incl. **theme dictionaries** for Light/Dark/HighContrast) and
   implicit styles.
5. **Let standard controls carry the design.** Restyle via **`Style` / `ControlTemplate` lightweight
   styling** (override theme‑resource keys), not by rebuilding a control; keep custom templates minimal.
6. **Async & threading.** Marshal UI updates to the **dispatcher** (`DispatcherQueue`); never block the UI
   thread; use `async`/`await` for I/O.
7. **Verify across themes.** Build against the latest SDK and confirm in **Light + Dark + High Contrast**,
   with **Narrator**, and at multiple DPI/window sizes before sign‑off.

---

## 6. Reverse‑engineering protocol (mockup / screenshot / existing app → XAML)

Execute in order; **stop and verify against official docs** at any uncertain step.

1. **Platform disambiguation.** Confirm the target is Windows and which framework — **Mica/Acrylic** (vs.
   Apple **Liquid Glass**), **Segoe Fluent Icons** (vs. SF Symbols), **Segoe UI Variable**, **min/max/close
   caption buttons** top‑right, NavigationView/CommandBar idiom, 8/4 px corners. If it isn't Windows, this
   constitution doesn't apply.
2. **Spatial & grid topology.** Snap arbitrary padding/margins to the nearest **4 epx**; translate absolute
   (CSS `position:absolute`, Electron) layouts into resilient **`Grid`** `*`/`Auto` (and `StackPanel`),
   limiting `Canvas` to true overlap.
3. **Material & layering inference.** Separate Z‑layers: wallpaper‑tinted window body → **Mica** (Mica Alt
   if tabbed); translucent transient menu/popup → **Acrylic**; solid surface above the base → a **card**
   (`CardBackgroundFillColorDefaultBrush`) on a **layer** (`LayerFillColorDefaultBrush`); modal dim →
   **Smoke**. Apply via `SystemBackdrop` (WinUI) or DWM (WPF) — never a hand‑rolled blur.
4. **Control mapping & translation.** Aggressively map every non‑native pattern to its **nearest WinUI
   control** (web hamburger → `NavigationView`; web toolbar → `CommandBar`; sort control → header sort /
   `DropDownButton` + `MenuFlyout`; overflow → `…` `SecondaryCommands`; search → `AutoSuggestBox`; modal →
   `ContentDialog`; inline banner → `InfoBar`). Synthesize a custom control only when none fits — and
   document why.
5. **State & focus inference.** Identify interactive states and where **active/inactive** (Mica focus),
   **hover/pressed** elevation, and **accent** selection apply; map "unavailable" to a disabled (not
   hidden) state; map destructive actions to a confirmed, non‑accent button.
6. **Token extraction.** Resolve text to **type‑ramp `Style`s**, colors to **theme brushes**, corners to
   `ControlCornerRadius`/`OverlayCornerRadius`, spacing to the **4‑epx** set. Produce resource references,
   not literals.
7. **Validation.** Render across **Light + Dark + High Contrast**, verify **contrast** and **keyboard /
   Narrator** support, and re‑check each non‑obvious choice against the cited Fluent/Learn section before
   sign‑off.

### 6.1 Auditing a shared screenshot, mockup, or task (Fluent conformance pass)
When the user shares a screenshot, design, or a task that references one, **don't just reproduce it — grade
it against Fluent 2 / the Windows guidance first**, then build. Produce findings:

1. **Identify the surface** (window / title bar / NavigationView / CommandBar / list / dialog / inspector)
   and map each visible element to a native control (§3.2).
2. **Run the §9 sign‑off checklist** against what's shown: type ramp + sentence case, theme brushes + the
   three themes, material/layer model (Mica vs. Acrylic vs. Smoke), elevation, corner radii, Segoe Fluent
   iconography, contrast + keyboard/Narrator, native‑control fidelity, active/inactive focus.
3. **Emit findings** as `violation → the Fluent/Learn rule it breaks (cite §/page) → the WinUI control /
   theme resource / API that fixes it → severity`, separating **Blockers** (platform‑foreign control,
   reinvented component, stacked materials, contrast failure, dishonest disabled/empty state) from
   **polish**.
4. **Then** propose the fix in real control names. If the reference is non‑Windows (an Apple / web
   screenshot), translate the **intent** to the Fluent idiom — never copy the foreign chrome.

A shared image is **graded against the rules, not copied** — the antidote to "looks close enough."

---

## 7. Accessibility mandate (a conformance floor, not a nicety)

- **Contrast (WCAG 2.x AA):** text **4.5 : 1** (≥ 18 pt or bold **3 : 1**); meaningful UI/graphics **3 : 1**.
  Verify in **light, dark, and High Contrast**; ship and test the **High‑Contrast** theme (it is
  first‑class on Windows, not optional).
- **Full keyboard support:** logical **Tab** order, **access keys** (`AccessKey`) and accelerators, and a
  **visible focus visual** on every interactive element; nothing reachable by pointer only.
- **Narrator / UI Automation:** label every control via **`AutomationProperties.Name`** (and
  `HelpText`/`LabeledBy` as needed); use **`LiveRegion`** for async status; expose correct control
  patterns; logical reading order.
- **Don't encode meaning in color alone** — add icon/glyph/shape/label (§1.2).
- **Targets & input:** comfortable hit targets for touch/pen/mouse; support pointer, keyboard, pen, and
  gamepad where relevant.
- **Motion:** honor **Animations off** / reduced‑motion — disable connected animations and parallax; keep
  essential feedback.
- **Cognitive:** minimize time‑boxed/auto‑dismiss UI; **double‑confirm** hard‑to‑recover (destructive)
  actions; don't autoplay media without controls.

---

## 8. Anti‑patterns (reject on sight)

- Hard‑coded `FontSize` / hex colors / `Width`·`Height` layout for adaptive UI; a parallel type/spacing/
  corner scale.
- **Bold/Italic** emphasis or **ALL‑CAPS** / Title‑Case headers (use **Semibold** + **sentence case**);
  an iOS/macOS or Material type scale transplanted onto Windows.
- Custom backgrounds that defeat **Mica** focus; **stacked materials** (Acrylic on Mica on Acrylic);
  Acrylic on a long‑lived window body; a custom modal that doesn't dim with **Smoke**.
- A hand‑laid `StackPanel` "table" (no sort/resize) or "toolbar"; a `ContentDialog` where an `InfoBar` or
  a `SplitView` inspector belongs.
- A web **hamburger** drawer, an Electron/web chrome, or an Apple sidebar/tab bar transplanted onto
  Windows; copying a non‑Windows screenshot's chrome instead of translating the *intent* to Fluent.
- **MDL2 Assets / Metro** glyphs and styling; legacy **E0‑/E5‑** Segoe glyphs; **UWP
  `ToastNotificationManager`**; **`BinaryFormatter`**; UWP/WinUI 2 patterns where WinUI 3 exists.
- >1 **accent** button per view; a **destructive default**; size used as hierarchy; a templated control
  with no hover/pressed/disabled/focus state.
- A bright accent highlight left active while the window is **inactive**.

---

## 9. Sign‑off checklist

- [ ] Every type style is a **ramp `Style`** (no raw `FontSize`); **sentence case**; **Semibold** (not
      Bold/Italic) for emphasis.
- [ ] Every color is a **theme brush** (`{ThemeResource}` / WPF `SystemColors` `DynamicResource`) — resolves
      in **light + dark + High Contrast**; accent used sparingly.
- [ ] Materials correct: **Mica** base (Mica Alt if tabbed), **Acrylic** only on transient surfaces,
      **Smoke** behind modals; **no stacked materials**; window background doesn't defeat Mica focus.
- [ ] Layering/elevation + **corner radii** (8 px containers / 4 px in‑page / 0 px flush) match the model;
      spacing on the **4‑epx** grid.
- [ ] Structure uses native **`AppWindow` + custom `TitleBar` + `NavigationView` + `CommandBar`** and a
      `SplitView`/list‑detail inspector; **`DataGrid` vs `ListView`/`GridView`** chosen correctly.
- [ ] Native controls match the **§3.2 catalog** (NavigationView, CommandBar overflow, DataGrid sort/
      resize, button roles/one accent, dialog vs InfoBar vs inspector) — nothing reinvented.
- [ ] All iconography is **Segoe Fluent Icons** (Fluent UI System Icons on web) at on‑grid sizes; filled =
      selected; mirrored for RTL.
- [ ] **Contrast** + hit targets meet AA in all three themes; full **keyboard** + **Narrator**
      (`AutomationProperties.Name`) + visible focus; reduced‑motion honored.
- [ ] Window **active/inactive** focus handled for custom surfaces.
- [ ] Code: **MVVM** with `{x:Bind}`, composed `UserControl`s, theme dictionaries, lightweight styling,
      dispatcher‑marshaled UI, `System.Text.Json` (no `BinaryFormatter`).
- [ ] Framework deltas applied (WinUI `SystemBackdrop` vs. WPF `ThemeMode`/DWM); every non‑trivial decision
      **cites** an official source below.

---

## 10. Citations (primary sources — verify the live page for big calls)

**Fluent 2 design system:** [fluent2.microsoft.design](https://fluent2.microsoft.design/) —
[Typography](https://fluent2.microsoft.design/typography) ·
[Color](https://fluent2.microsoft.design/color) ·
[Material](https://fluent2.microsoft.design/material) ·
[Elevation](https://fluent2.microsoft.design/elevation) ·
[Shapes](https://fluent2.microsoft.design/shapes).

**Windows apps design (Microsoft Learn — `learn.microsoft.com/windows/apps/design/…`):**
[Design overview](https://learn.microsoft.com/windows/apps/design/) ·
[Design principles](https://learn.microsoft.com/windows/apps/design/design-principles) ·
[Typography](https://learn.microsoft.com/windows/apps/design/signature-experiences/typography) ·
[Color](https://learn.microsoft.com/windows/apps/design/signature-experiences/color) ·
[Materials](https://learn.microsoft.com/windows/apps/design/signature-experiences/materials) ·
[Layering & elevation](https://learn.microsoft.com/windows/apps/design/signature-experiences/layering) ·
[Geometry](https://learn.microsoft.com/windows/apps/design/signature-experiences/geometry) ·
[Rounded corners](https://learn.microsoft.com/windows/apps/design/style/rounded-corner) ·
[Mica](https://learn.microsoft.com/windows/apps/design/style/mica) ·
[Acrylic](https://learn.microsoft.com/windows/apps/design/style/acrylic) ·
[Segoe Fluent Icons](https://learn.microsoft.com/windows/apps/design/style/segoe-fluent-icons-font) ·
[Controls](https://learn.microsoft.com/windows/apps/design/controls/) ·
[NavigationView](https://learn.microsoft.com/windows/apps/design/controls/navigationview) ·
[CommandBar](https://learn.microsoft.com/windows/apps/design/controls/command-bar) ·
[Accessibility](https://learn.microsoft.com/windows/apps/design/accessibility/accessibility).

**Develop (WinUI / Windows App SDK / theming):**
[WinUI 3](https://learn.microsoft.com/windows/apps/winui/winui3/) ·
[Windows App SDK](https://learn.microsoft.com/windows/apps/windows-app-sdk/) ·
[Theming](https://learn.microsoft.com/windows/apps/develop/ui/theming) ·
[XAML theme resources](https://learn.microsoft.com/windows/apps/develop/platform/xaml/xaml-theme-resources) ·
[Apply Mica (desktop)](https://learn.microsoft.com/windows/apps/desktop/modernize/ui/apply-mica) ·
[`SystemBackdrop`](https://learn.microsoft.com/windows/windows-app-sdk/api/winrt/microsoft.ui.xaml.media.systembackdrop) ·
[App notifications](https://learn.microsoft.com/windows/apps/windows-app-sdk/notifications/app-notifications/).

**WPF (.NET 9 Fluent theme):**
[What's new in WPF for .NET 9](https://learn.microsoft.com/dotnet/desktop/wpf/whats-new/net90) ·
[Styles & templates](https://learn.microsoft.com/dotnet/desktop/wpf/controls/styles-templates-overview).

**Engineering sessions:** [Microsoft Build](https://build.microsoft.com/) — WinUI / Windows App SDK
sessions; [Windows App SDK release notes](https://learn.microsoft.com/windows/apps/windows-app-sdk/release-channels);
[WinUI 3 Gallery](https://github.com/microsoft/WinUI-Gallery) (live, interactive control reference).

> **Operating reminder:** when in doubt, **open the live Fluent 2 / Microsoft Learn / WinUI doc and confirm
> before emitting code.** Spec numbers (ramp sizes, corner radii, brush keys, backdrop APIs) and controls
> evolve every release; this constitution is a grounding lattice, not a substitute for the source of truth.
