# Design tokens & design↔code reconciliation

The backbone that makes one process serve Apple, Windows, and Web — and that makes "reconcile any design/code variation" a mechanical step instead of a judgement call.

Sources: Design Tokens Community Group **Format Module** (designtokens.org/tr/drafts/format; draft/community-group report, not a W3C Recommendation) · Material 3 **Design tokens** (m3.material.io/foundations/design-tokens).

## What a token is
A named design decision: `name → value`, platform‑agnostic, machine‑readable. The value may be a literal **or a reference to another token**. Tokens are the **single source of truth** — design tools, docs, and every platform's code all reference the *same names*, so "the same color/size is used in both places" is guaranteed even when the underlying value changes.

## Three tiers (always model all three)
| Tier | Prefix | Purpose | Example |
|---|---|---|---|
| **Reference / global** | `ref` | Raw, context‑free values (palette, type scale) | `ref.palette.secondary90 = #E8DEF8` |
| **System / semantic** | `sys` | Roles + theming; **context lives here** (light/dark/RTL/density) | `sys.color.secondary-container → {ref.palette.secondary90}` |
| **Component** | `comp` | Per‑component element decisions, pointing at system tokens | `comp.fab.container.color → {sys.color.secondary-container}` |

Rule: component → system → reference. Components never hold hard‑coded values; system tokens never hold raw values when a reference exists.

## File format (DTCG-style JSON)
- JSON; a token is any object with a **`$value`**; metadata via `$type`, `$description`, `$deprecated`, `$extensions`.
- **Groups** nest tokens; **aliases** use `{group.token}`; group inheritance via `$extends`.
- **Types:** `color` (with `colorSpace`+`components`+`hex`), `dimension` (`px`|`rem`), `fontFamily`, `fontWeight` (`100–900` or `thin…black`), `duration` (`ms`|`s`), `cubicBezier`, `number`.
- **Composite types:** `typography`, `shadow`, `border`, `transition`, `gradient`, `strokeStyle`.
- MIME `application/design-tokens+json`; extension `.tokens` / `.tokens.json`.

```json
{
  "sys": { "color": { "$type": "color",
    "accent": { "$value": "{ref.brand.500}", "$description": "Primary accent / system tint" }
  } },
  "comp": { "button": { "primary": { "background": { "$type": "color",
    "$value": "{sys.color.accent}" } } } }
}
```

## Contexts
The same `sys` token resolves to different values per **context** (dark theme, high‑contrast, dense, RTL, form factor). Model contexts as overrides on system tokens — not as forked component tokens.

## The reconciliation workflow (design ↔ code)
```
design tweak ─▶ tokens (.tokens.json = SSOT) ─▶ translation (Style Dictionary / Terrazzo) ─▶ swift / xaml / css
                     ▲                                                                          │
                     └────────────────────────── reconcile gate: diff ◀───────────────────────┘
```
1. **Design is changed in tokens first** (or in Storybook, then captured as tokens). Tokens are the SSOT.
2. A **translation tool** generates platform code from the tokens (Style Dictionary, Terrazzo). Storybook documents them.
3. The **reconcile gate** regenerates from tokens and **diffs against committed platform code**. Any delta = drift.
4. Resolve drift deterministically: if code drifted → regenerate; if the design legitimately changed → update tokens first, regenerate, then adapt code. Never hand‑edit a value that a token owns.

## Platform value mapping (what a token compiles to)
| Token type | Apple (SwiftUI) | Windows (WinUI/XAML) | Web (CSS) |
|---|---|---|---|
| color | `Color`/asset catalog colorset | `ThemeResource`/`Color` in `ResourceDictionary` | `--token: #…` custom property |
| dimension | `CGFloat` pt (DesignTokens) | `x:Double` / `Thickness` | `px` / `rem` |
| typography | `Font` semantic style | `TextBlock` style / type ramp | `font` shorthand / class |
| duration + cubicBezier | `Animation` | `Storyboard`/`KeyTime` | `transition`/`@keyframes` |
| shadow/border | modifier | `BorderBrush`/`DropShadow` | `box-shadow`/`border` |

## Rules for the kit
- Every UI repo SHOULD declare a `designMap` path once it has more than a few components. It is the glossary that tells agents which Storybook stories, code paths, states, tokens, and capability claims belong together.
- Every mature UI repo SHOULD declare a `tokens` path in `architrave.config.json`. The reconcile gate is enabled when `tokens` + `tokenBuild` are present. Early repos may omit tokens and rely on Storybook/specs; in that mode reconcile must skip loudly/clearly rather than pretending token drift was checked.
- Token names are the shared vocabulary between Storybook and native code — Architrave reproduces by **token + component name**, never by raw value.
- `px`→`pt`/`dp` and `rem` conversions are the translation tool's job; agents must not hard‑convert.

## Adoption ladder
1. **Spec + Storybook only:** valid for early app work; set `designSource.spec` and Storybook path. Gates validate JSON/build/test; reconcile skips token generation.
2. **Add a design map:** copy `kit/examples/design-map.stub.json` into the app repo and map real component/story/code names. This unlocks better grounding and anti-slop review without token tooling.
3. **Add tokens:** copy or adapt `kit/examples/tokens.web-shadcn.tokens.json` or a platform-specific token file. Set `tokens` in `architrave.config.json`.
4. **Add token build:** configure Style Dictionary, Terrazzo, or a repo-local generator and set `tokenBuild`. Now `gates/reconcile.*` can mechanically detect design↔code drift.
