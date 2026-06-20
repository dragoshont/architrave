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
