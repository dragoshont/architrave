#!/usr/bin/env pwsh
# Architrave - refresh an adopted repo's COPIED kit assets (gates + knowledge + harness + constitution +
# the AGENTS.md grounding stanza) to match THIS kit, and re-stamp the version.
# PowerShell mirror of tools/update.sh. Never touches architrave.config.json. By default
# it does not touch .github/agents; pass -Agents to refresh Architrave-managed copied
# agent files after archiving bespoke repo agents to avoid split authority.
#
# Usage: pwsh -NoProfile -File tools/update.ps1 [TargetRepoDir] [-Agents]   (default: CWD)
[CmdletBinding()]
param(
  [Parameter(Position = 0)]
  [string]$Target = "$PWD",
  [switch]$Agents
)
$ErrorActionPreference = 'Stop'

$kit = Split-Path (Split-Path $MyInvocation.MyCommand.Path -Parent) -Parent
$Target = (Resolve-Path $Target).Path
if ($Target -eq $kit) { [Console]::Error.WriteLine('update: refusing to update the kit into itself'); exit 1 }
if (-not (Test-Path (Join-Path $Target 'architrave.config.json'))) {
  [Console]::Error.WriteLine("update: $Target has no architrave.config.json - run tools/install.ps1 first"); exit 1
}

$ver = (Get-Content (Join-Path $kit 'plugin.json') -Raw | ConvertFrom-Json).version
if (-not $ver) { $ver = '0.0.0' }
$begin = '<!-- architrave:begin -->'
$end   = '<!-- architrave:end -->'

Write-Host "Architrave -> refreshing assets in: $Target (kit v$ver)"
New-Item -ItemType Directory -Force -Path "$Target/gates/hooks","$Target/knowledge","$Target/harness" | Out-Null

if ($Agents) {
  New-Item -ItemType Directory -Force -Path "$Target/.github/agents" | Out-Null
  Copy-Item "$kit/agents/*.agent.md" "$Target/.github/agents/" -Force
  Write-Host '  ok agents refreshed'
} else {
  Write-Host '  - agents left unchanged (use -Agents to refresh .github/agents/)'
}

# Gates - copied because they EXECUTE in the repo.
Copy-Item "$kit/gates/checks.sh","$kit/gates/checks.ps1","$kit/gates/reconcile.sh","$kit/gates/reconcile.ps1","$kit/gates/quality-gate.sh","$kit/gates/quality-gate.ps1","$kit/gates/backend-checks.sh","$kit/gates/backend-checks.ps1","$kit/gates/rubric.md" "$Target/gates/" -Force
Copy-Item "$kit/gates/hooks/*.json" "$Target/gates/hooks/" -Force
Write-Host '  ok gates refreshed'

# Knowledge packs - copied so the cloud agent (no plugin) can read them.
Copy-Item "$kit/knowledge/*.md" "$Target/knowledge/" -Force
Write-Host '  ok knowledge refreshed (apple/microsoft/web/backend/operations-ux/design-tokens/learning-loop/yagni)'

# Platform constitution(s) - deep native-app synthesis (Apple + Windows), for the cloud agent.
Copy-Item "$kit/constitution-*.md" "$Target/" -Force -ErrorAction SilentlyContinue
Write-Host '  ok constitution refreshed (constitution-*.md; Apple + Windows native-app synthesis)'

# Audit harness.
Copy-Item "$kit/harness/*" "$Target/harness/" -Recurse -Force
Write-Host '  ok harness refreshed'

# AGENTS.md grounding stanza - idempotent.
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
Write-Host '  ok AGENTS.md stanza refreshed'

# Version stamp.
Set-Content -Path "$Target/gates/.kit-version" -Value $ver -Encoding utf8
Write-Host "  ok stamped gates/.kit-version = $ver"
Write-Host 'Done. (architrave.config.json left untouched.)'
