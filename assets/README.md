# README images

Three images are **generated** from the HTML in `_src/` via headless Edge. Regenerate after editing the sources:

```bash
node assets/_src/shoot.js
```

| File | Source | Shows |
|---|---|---|
| `overview.png` | `_src/overview.html` | The 4‑stage method (Ground → Agents → Gate → Ship) + the surfaces it runs on. |
| `flows.png` | `_src/flows.html` | The UX Architect designing a flow: screens + every state, Storybook‑first, before native code. |
| `cli.png` | `_src/cli.html` | Plugin install in the Copilot CLI + a green `gates/checks.sh` run. |

Optional real screenshots you can add (drop the PNG here, then reference it from `README.md`):

| File | What to capture |
|---|---|
| `phonodeck.png` | **Included.** The PhonoDeck `screens--home` story — captured from its live Storybook (`cd ../phonodeck/ui-lab && npm run storybook` → http://localhost:6007) via headless Edge, element `#storybook-root`, `deviceScaleFactor: 2`. The flagship native-macOS showcase. |
| `agents.png` | The Copilot agent picker (VS Code chat, the desktop app, or `copilot` CLI) showing the five agents. |
| `feature-builder.png` | A Feature Builder session: the acceptance‑criteria checklist + an Adversarial Judge PASS verdict. |

Embed with: `![alt text](assets/overview.png)`.
