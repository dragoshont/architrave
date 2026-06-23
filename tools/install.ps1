#!/usr/bin/env pwsh
# Architrave installer (PowerShell / Windows). Mirror of tools/install.sh.
# Usage: pwsh -NoProfile -File tools/install.ps1 [TargetRepoDir]   (default: CWD)
# For local agents you ALSO install the plugin once:
#   copilot plugin marketplace add dragoshont/architrave
#   copilot plugin install architrave@architrave
[CmdletBinding()]
param([string]$Target = "$PWD")
$ErrorActionPreference = 'Stop'

$kit = Split-Path (Split-Path $MyInvocation.MyCommand.Path -Parent) -Parent
$Target = (Resolve-Path $Target).Path
if ($Target -eq $kit) { [Console]::Error.WriteLine('install: refusing to install the kit into itself'); exit 1 }

$begin = '<!-- architrave:begin -->'
$end   = '<!-- architrave:end -->'

Write-Host "Architrave -> installing into: $Target"
New-Item -ItemType Directory -Force -Path "$Target/.github/agents","$Target/.github/hooks","$Target/.github/workflows","$Target/gates/hooks","$Target/harness" | Out-Null

# 1) Agents
Copy-Item "$kit/agents/*.agent.md" "$Target/.github/agents/" -Force
Write-Host "  ok agents -> .github/agents/"

# 2) Gates
Copy-Item "$kit/gates/checks.sh","$kit/gates/checks.ps1","$kit/gates/reconcile.sh","$kit/gates/reconcile.ps1","$kit/gates/quality-gate.sh","$kit/gates/quality-gate.ps1","$kit/gates/backend-checks.sh","$kit/gates/backend-checks.ps1","$kit/gates/rubric.md" "$Target/gates/" -Force
Copy-Item "$kit/gates/hooks/*.json" "$Target/gates/hooks/" -Force
Write-Host "  ok gates -> gates/ (checks/reconcile/quality-gate .sh + .ps1 + rubric)"

# 2b) Knowledge packs
New-Item -ItemType Directory -Force -Path "$Target/knowledge" | Out-Null
Copy-Item "$kit/knowledge/*.md" "$Target/knowledge/" -Force
Write-Host "  ok knowledge -> knowledge/ (apple/microsoft/web/backend/operations-ux/design-tokens/learning-loop/yagni)"

# 2c) Audit harness
Copy-Item "$kit/harness/*" "$Target/harness/" -Recurse -Force
Write-Host "  ok harness -> harness/ (init-run / validate-run / semantic-review)"

# 3) architrave.config.json — scaffold only if absent
if (-not (Test-Path "$Target/architrave.config.json")) {
@'
{
  "platform": "web",
  "stack": "react",
  "designSource": { "type": "storybook", "path": ".storybook", "url": "http://localhost:6006" },
  "designMap": "docs/design/ui-map.json",
  "tokens": "tokens/tokens.json",
  "applyTo": ["src/**"],
  "build": "npm run build",
  "test": "npm test",
  "learning": {
    "runArtifactsPath": ".architrave/runs",
    "repoProfilePath": ".architrave/learning/repo-profile.md",
    "lessonsPath": ".architrave/learning/repo-lessons.md",
    "capture": ["run-artifacts", "gate-results", "judge-verdicts", "runtime-evidence", "repo-profile", "lessons"],
    "redactionPolicy": "no-secrets",
    "staleFactPolicy": "validate-before-use",
    "promotionPolicy": "approval-required",
    "promoteAfterOccurrences": 2,
    "promoteTargets": ["architrave.config.json", "AGENTS.md", ".github/instructions", "docs"]
  }
}
'@ | Set-Content -Path "$Target/architrave.config.json" -Encoding utf8
  Write-Host "  ok scaffolded architrave.config.json  <- EDIT to match this repo"
} else { Write-Host "  - architrave.config.json present - left as-is" }

# 4) AGENTS.md stanza — idempotent
$ag = "$Target/AGENTS.md"
$stanza = (Get-Content "$kit/templates/AGENTS.stanza.md" -Raw).TrimEnd()
$content = if (Test-Path $ag) { Get-Content $ag -Raw } else { "# AGENTS.md`n" }
foreach ($pair in @(@($begin, $end))) {
  $pattern = [regex]::Escape($pair[0]) + '.*?' + [regex]::Escape($pair[1])
  $content = [regex]::Replace($content, $pattern, '', [System.Text.RegularExpressions.RegexOptions]::Singleline)
}
$content = $content.TrimEnd()
$content = $content + "`n`n$begin`n$stanza`n$end`n"
Set-Content -Path $ag -Value $content -Encoding utf8
Write-Host "  ok AGENTS.md stanza injected/refreshed"

# 5) PostToolUse hook (Windows variant -> the canonical hook name)
Copy-Item "$kit/gates/hooks/design-guard.windows.json" "$Target/.github/hooks/design-guard.json" -Force
Write-Host "  ok .github/hooks/design-guard.json (PowerShell PostToolUse guard)"

# 6) copilot-setup-steps.yml — only if absent
$setup = "$Target/.github/workflows/copilot-setup-steps.yml"
if (-not (Test-Path $setup)) {
  Copy-Item "$kit/templates/copilot-setup-steps.yml" $setup -Force
  Write-Host "  ok .github/workflows/copilot-setup-steps.yml"
} else { Write-Host "  - copilot-setup-steps.yml present - merge jq install manually" }

# 7) Version stamp - lets gates/checks.ps1 detect when these copied assets go stale.
$ver = (Get-Content "$kit/plugin.json" -Raw | ConvertFrom-Json).version
if (-not $ver) { $ver = '0.0.0' }
Set-Content -Path "$Target/gates/.kit-version" -Value $ver -Encoding utf8
Write-Host "  ok stamped gates/.kit-version = $ver"

Write-Host ""
Write-Host "Done. Next steps:"
Write-Host "  1. Edit architrave.config.json to match this repo."
Write-Host "  2. Install the agents for local Copilot surfaces:"
Write-Host "       copilot plugin marketplace add dragoshont/architrave"
Write-Host "       copilot plugin install architrave@architrave"
Write-Host "  3. (Optional, React Storybook) Wire the live Storybook MCP, then set designSource.mcp:"
Write-Host "       npx storybook add @storybook/addon-mcp"
Write-Host "       npx mcp-add --type http --url ""http://localhost:6006/mcp"" --scope project"
Write-Host "  4. (Optional, real product/UI references) Wire Mobbin MCP (browser OAuth, no API key) as a local client config:"
Write-Host "       npx mcp-add --name mobbin --type http --url ""https://api.mobbin.com/mcp"" --scope global --clients ""copilot cli,vscode,claude code"""
Write-Host "  5. (Optional, self-hosted web search) Wire SearXNG MCP pointed at your own instance; keep private instance URLs/credentials out of Git and architrave.config.json:"
Write-Host "       npx mcp-add --name searxng --type stdio --command npx --args ""-y,mcp-searxng"" --env ""SEARXNG_URL=https://searxng.your-host.example"" --scope global --clients ""copilot cli,vscode,claude code"""
Write-Host "  6. Run the Architrave agent for a non-trivial UI change."
Write-Host ""
Write-Host "After you later update the plugin, refresh this repo's copied gates + harness + knowledge:"
Write-Host "       pwsh -NoProfile -File `"$kit/tools/update.ps1`" `"$Target`""
Write-Host "Use -Agents only when you deliberately want to refresh copied Architrave agents after archiving bespoke repo agents."
