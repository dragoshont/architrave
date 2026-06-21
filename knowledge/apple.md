# Apple platform pack — HIG → SwiftUI

Loaded by the Platform Design agent when `config.platform = apple-macos | apple-ios`.

Source: Apple **Human Interface Guidelines** (developer.apple.com/design/human-interface-guidelines) — Foundations: Accessibility, Color, Layout, Materials, Typography, SF Symbols; plus *Designing for macOS / iOS*. Re‑verify the live HIG for big calls.

## Principles
Design for **hierarchy, harmony, and consistency**; defer to content; use system components and conventions rather than reinventing. Don't copy Apple Music/Mail pixel‑for‑pixel — use them as IA references.

## Typography (SF Pro + Dynamic Type)
- System font **SF Pro** (Text/Display optical sizes); use **semantic text styles** (Large Title → Title → Headline → Body → Callout → Subhead → Footnote → Caption), not hard‑coded sizes.
- Default / minimum body sizes: **macOS 13 pt / 10 pt min**; **iOS·iPadOS 17 pt / 11 pt min**.
- Support **Dynamic Type**; with thin weights, go larger. Set hierarchy via weight/size/secondary color — never Ultralight/Thin/Light for UI text.

## Color
- Prefer **system semantic colors** (`Color.primary`, `.secondary`, `Color(nsColor:)`/`Color(uiColor:)` system colors) — they auto‑adapt to Dark Mode and **Increase Contrast**.
- Don't hard‑code hex; don't use a service/brand color as a full‑page theme — only a small source cue.
- **Never rely on color alone** to convey meaning — add a shape, icon, or label (e.g. `slash` for unavailable).

## Layout, hit targets & spacing
- Minimum control size: **iOS·iPadOS 44×44 pt** (20–28 pt absolute min), **macOS 28×28 pt** (20×20 min).
- Padding: ~**12 pt** around bezeled controls, ~**24 pt** around non‑bezeled elements.
- Repeated‑item corner radius ≤ 8 pt; align to a consistent grid; build on existing spacing tokens (8/12/20), don't invent parallel scales.

## Materials (vibrancy / Liquid Glass)
- Use materials + vibrancy in the **control/navigation layer** (sidebar, toolbar, now‑playing bar) — **not** the content layer (lists, artwork). Don't fight system toolbar materials with custom backgrounds.

## SF Symbols
- Use SF Symbols for iconography (never in app icons/logos). Match symbol **weight/scale to adjacent text**; use **fill vs outline vs slash** to encode state. Keep symbol animation purposeful and rare.

## macOS structural components (the native building blocks)
What makes an app read as native macOS (Music.app / Apple Music / Mail are the IA references — reproduce the *structure*, not the pixels):
- **Three‑pane shell:** `NavigationSplitView` — **sidebar** (a `List` of `Section`s, each row a `Label` + SF Symbol: Search / Home / Library / Devices / Playlists) │ **content** │ optional **inspector** (trailing drawer). Sidebar + toolbar sit in the material/control layer.
- **List vs Table:** a multi‑attribute collection (Song · Artist · Album · Time) is a **`Table`** with `TableColumn`s — **columns stretch to fill the width** and are user‑resizable, with **click‑to‑sort headers** (`sortOrder` + `KeyPathComparator`). Use a **`List` + custom row** (e.g. `SongRow`) only for compact / art‑led / iOS layouts. **Don't fake a table** with hand‑laid `HStack` columns.
- **Toolbar (top):** `.toolbar { ToolbarItem(placement: .primaryAction / .navigation) }` — the trailing cluster: download, the **•••** overflow `Menu`, and the **sort/filter `Menu`** (Playlist Order · Title · Genre · Year · Artist · Album · Time + Ascending / Descending). Never hand‑roll a toolbar strip in the content layer.
- **Search (top):** `.searchable(text:, placement: .toolbar)` for the "Find in …" field, scoped to the visible list — not a custom text field.
- **Inspector / right drawer:** the Up Next / queue / Get‑Info panel = `.inspector(isPresented:)` (macOS 14+) or a trailing `NavigationSplitView` column — a dismissible trailing pane, **not** a modal sheet.
- **Context menus:** `.contextMenu` on each row for its actions (Add to Library, Play Next, Get Info, Favourite, Share…). The menu **mirrors** the row's affordances — it never *hides* the primary action.
- **Transport:** the now‑playing bar is a persistent bottom control‑layer surface (`safeAreaInset(edge: .bottom)`), wired to media keys / `MPRemoteCommandCenter`.

## Accessibility (WCAG AA, enforced)
- Contrast: **≤17 pt → 4.5:1**; **≥18 pt or bold → 3:1**. Verify in **both** light and dark; honor **Increase Contrast**.
- **VoiceOver:** every control labeled, sensible reading order. **Full Keyboard Access** + standard shortcuts (don't override system ones). **Switch Control** friendly.
- **Reduce Motion:** tighten springs, track gestures directly, avoid z‑axis depth, replace x/y/z transitions with fades, avoid animating into/out of blurs.
- Minimize time‑boxed/auto‑dismiss elements; **double‑confirm** hard‑to‑recover actions (delete).

## SwiftUI mapping (how to reproduce)
- Colors/materials/fonts → semantic APIs: `Color`, `Material`, `Font` styles; assets in an asset catalog colorset (so tokens compile to adaptable colors).
- Sizes/spacing → a `DesignTokens` enum (pt), not literals.
- A11y → `.accessibilityLabel/Value/Hint`, `.accessibilityElement`, Dynamic Type, `.controlSize`.
- Validate the look in Storybook (light + dark + a11y) before building; reproduce by the design map's component/glossary name.

## Citations
HIG home, Accessibility (sizes/contrast/targets/Reduce Motion), Color, Typography, Layout, Materials, SF Symbols — all under developer.apple.com/design/human-interface-guidelines.
