#!/usr/bin/env pwsh
# Architrave installer (PowerShell / Windows). Mirror of tools/install.sh.
# Usage: pwsh -NoProfile -File tools/install.ps1 [TargetRepoDir] [-Profile application|knowledge] [-Codex]
# For local agents you ALSO install the plugin once:
#   copilot plugin marketplace add dragoshont/architrave
#   copilot plugin install architrave@architrave
[CmdletBinding()]
param(
  [Parameter(Position = 0)]
  [string]$Target = "$PWD",
  [string]$Profile = 'application',
  [switch]$Codex,
  [switch]$Help
)
$ErrorActionPreference = 'Stop'

if ($Help) {
  Write-Host 'Usage: tools/install.ps1 [TargetRepoDir] [-Profile application|knowledge] [-Codex]'
  exit 0
}
if ($Profile -notin @('application', 'knowledge')) {
  [Console]::Error.WriteLine("install: unknown profile '$Profile' (expected application or knowledge)")
  exit 2
}

$kit = Split-Path (Split-Path $MyInvocation.MyCommand.Path -Parent) -Parent
. (Join-Path $kit 'tools/ManagedPaths.ps1')
$Target = (Resolve-Path -LiteralPath $Target).Path
if ($Target -eq $kit) { [Console]::Error.WriteLine('install: refusing to install the kit into itself'); exit 1 }
Initialize-ManagedPaths $Target install
$Target = $script:ManagedRoot

$python = $null
if ($Codex) {
  $pythonCommand = Get-Command python3 -ErrorAction SilentlyContinue
  if (-not $pythonCommand) { $pythonCommand = Get-Command python -ErrorAction SilentlyContinue }
  if (-not $pythonCommand) { [Console]::Error.WriteLine('install: -Codex requires Python 3.11+'); exit 2 }
  $python = $pythonCommand.Source
  & $python "$kit/tools/codex-roles.py" --kit $kit --target $Target --preflight
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$begin = '<!-- architrave:begin -->'
$end   = '<!-- architrave:end -->'

foreach ($SourceTree in 'agents','gates','knowledge','harness') { Assert-PackagedTree (Join-Path $kit $SourceTree) }
foreach ($SourceFile in 'templates/AGENTS.stanza.md','templates/copilot-setup-steps.yml','plugin.json') { Assert-PackagedFile (Join-Path $kit $SourceFile) }
if ($Profile -eq 'application') {
  Get-ChildItem -LiteralPath $kit -Filter 'constitution-*.md' -File | ForEach-Object { Assert-PackagedFile $_.FullName }
} else {
  Assert-PackagedFile (Join-Path $kit 'kit/examples/knowledge.architrave.json')
}
foreach ($Tree in '.github/agents','.github/hooks','.github/workflows','gates','gates/hooks','knowledge','harness') { Assert-ManagedTree $Tree }
foreach ($File in 'architrave.config.json','.gitignore','AGENTS.md','constitution-apple.md','constitution-windows.md','.github/hooks/design-guard.json','.github/workflows/copilot-setup-steps.yml','gates/.kit-version') { Assert-ManagedFilePreflight $File }

Write-Host "Architrave -> installing into: $Target"
foreach ($Directory in '.github/agents','.github/hooks','.github/workflows','gates/hooks','knowledge','harness') { New-ManagedDirectory $Directory }

# 1) Agents - knowledge repos get only the crew their lane uses; applications get all.
if ($Profile -eq 'knowledge') {
  foreach ($a in 'architrave','adversarial-judge','tournament-analyst','product-research','runtime-observer') {
    $src = "$kit/agents/$a.agent.md"
    Copy-ManagedFile $src ".github/agents/$a.agent.md"
  }
  Write-Host '  ok agents -> .github/agents/ (knowledge crew: architrave/adversarial-judge/tournament-analyst/product-research/runtime-observer)'
} else {
  Get-ChildItem (Join-Path $kit 'agents') -Filter '*.agent.md' -File | ForEach-Object { Copy-ManagedFile $_.FullName ".github/agents/$($_.Name)" }
  Write-Host "  ok agents -> .github/agents/"
}

# 2) Gates
foreach ($SourceFile in 'checks.sh','checks.ps1','reconcile.sh','reconcile.ps1','quality-gate.sh','quality-gate.ps1','backend-checks.sh','backend-checks.ps1','rubric.md') {
  Copy-ManagedFile (Join-Path $kit "gates/$SourceFile") "gates/$SourceFile"
}
Copy-ManagedTree (Join-Path $kit 'gates/hooks') 'gates/hooks'
Write-Host "  ok gates -> gates/ (checks/reconcile/quality-gate .sh + .ps1 + rubric)"

# 2b) Knowledge packs
Copy-ManagedTree (Join-Path $kit 'knowledge') 'knowledge'
Write-Host "  ok knowledge -> knowledge/ (apple/microsoft/web/backend/operations-ux/design-tokens/execution-policy/learning-loop/yagni/runtime-v2)"

# 2b-ii) Platform constitution(s) - application profile only.
if ($Profile -eq 'knowledge') {
  Write-Host '  - constitution-*.md skipped (knowledge profile: no native-app UI)'
} else {
  Get-ChildItem -LiteralPath $kit -Filter 'constitution-*.md' -File | ForEach-Object { Copy-ManagedFile $_.FullName $_.Name }
  Write-Host "  ok constitution -> constitution-*.md (deep native-app synthesis; Apple + Windows)"
}

# 2c) Audit harness
Copy-ManagedTree (Join-Path $kit 'harness') 'harness'
Write-Host "  ok harness -> harness/ (init-run / validate-run / semantic-review / semantic learning recovery)"

# 3) architrave.config.json — scaffold only if absent
if (-not (Test-Path "$Target/architrave.config.json")) {
if ($Profile -eq 'knowledge') {
  Copy-ManagedFile (Join-Path $kit 'kit/examples/knowledge.architrave.json') 'architrave.config.json' -CreateOnly
} else {
$ConfigContent = @'
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
'@
  Set-ManagedContent 'architrave.config.json' $ConfigContent -CreateOnly
}
  Write-Host "  ok scaffolded architrave.config.json (profile: $Profile)  <- EDIT build/test and paths to match this repo"
} else { Write-Host "  - architrave.config.json present - left as-is" }

# 3b) Agent session run artifacts are local by default; learning files stay tracked.
$gi = "$Target/.gitignore"
$IgnoreContent = if (Test-Path -LiteralPath $gi) { Assert-ManagedFile '.gitignore'; [IO.File]::ReadAllText($gi) } else { '' }
$IgnoreRules = @('.architrave/runs/','.architrave/worktrees/','.architrave/runtime.key','.architrave/resources.lock')
$ExistingIgnoreLines = @($IgnoreContent -split "`r?`n")
$MissingIgnoreRules = @($IgnoreRules | Where-Object { $_ -notin $ExistingIgnoreLines })
if ($MissingIgnoreRules.Count -eq 0) {
  Write-Host '  - .gitignore already ignores Architrave private runtime files'
} else {
  $IgnoreContent += "`n# Architrave: private run evidence and isolated worker trees stay local.`n"
  foreach ($IgnoreRule in $MissingIgnoreRules) { $IgnoreContent += "$IgnoreRule`n" }
  Set-ManagedContent '.gitignore' $IgnoreContent
  Write-Host '  ok .gitignore -> ignoring runs, worktrees, and runtime key'
}

# 4) AGENTS.md stanza — idempotent
$ag = "$Target/AGENTS.md"
$stanza = (Get-Content "$kit/templates/AGENTS.stanza.md" -Raw).TrimEnd()
$content = if (Test-Path -LiteralPath $ag) { Assert-ManagedFile 'AGENTS.md'; [IO.File]::ReadAllText($ag) } else { "# AGENTS.md`n" }
foreach ($pair in @(@($begin, $end))) {
  $pattern = [regex]::Escape($pair[0]) + '.*?' + [regex]::Escape($pair[1])
  $content = [regex]::Replace($content, $pattern, '', [System.Text.RegularExpressions.RegexOptions]::Singleline)
}
$content = $content.TrimEnd()
$content = $content + "`n`n$begin`n$stanza`n$end`n"
Set-ManagedContent 'AGENTS.md' $content
Write-Host "  ok AGENTS.md stanza injected/refreshed"

# 5) PostToolUse hook (Windows variant -> the canonical hook name)
Copy-ManagedFile (Join-Path $kit 'gates/hooks/design-guard.windows.json') '.github/hooks/design-guard.json'
Write-Host "  ok .github/hooks/design-guard.json (PowerShell PostToolUse guard)"

# 6) copilot-setup-steps.yml — only if absent
$setup = "$Target/.github/workflows/copilot-setup-steps.yml"
if (-not (Test-Path $setup)) {
  Copy-ManagedFile (Join-Path $kit 'templates/copilot-setup-steps.yml') '.github/workflows/copilot-setup-steps.yml' -CreateOnly
  Write-Host "  ok .github/workflows/copilot-setup-steps.yml"
} else { Write-Host "  - copilot-setup-steps.yml present - merge jq install manually" }

# 7) Version stamp - lets gates/checks.ps1 detect when these copied assets go stale.
if ($Codex) {
  & $python "$kit/tools/codex-roles.py" --kit $kit --target $Target
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$ver = (Get-Content "$kit/plugin.json" -Raw | ConvertFrom-Json).version
if (-not $ver) { $ver = '0.0.0' }
Set-ManagedContent 'gates/.kit-version' "$ver`n"
Write-Host "  ok stamped gates/.kit-version = $ver"

Write-Host ""
Write-Host "Done. Next steps:"
Write-Host "  1. Edit architrave.config.json to match this repo (profile: $Profile)."
Write-Host "  2. Install the agents for local Copilot surfaces:"
Write-Host "       copilot plugin marketplace add dragoshont/architrave"
Write-Host "       copilot plugin install architrave@architrave"
if ($Profile -eq 'application') {
  Write-Host "  3. (Optional, React Storybook) Wire the live Storybook MCP, then set designSource.mcp:"
  Write-Host "       npx storybook add @storybook/addon-mcp"
  Write-Host "       npx mcp-add --type http --url ""http://localhost:6006/mcp"" --scope project"
  Write-Host "  4. (Optional, real product/UI references) Wire Mobbin MCP (browser OAuth, no API key) as a local client config:"
  Write-Host "       npx mcp-add --name mobbin --type http --url ""https://api.mobbin.com/mcp"" --scope global --clients ""copilot cli,vscode,claude code"""
  Write-Host "  5. (Optional, self-hosted web search) Wire SearXNG MCP pointed at your own instance; keep private instance URLs/credentials out of Git and architrave.config.json:"
  Write-Host "       npx mcp-add --name searxng --type stdio --command npx --args ""-y,mcp-searxng"" --env ""SEARXNG_URL=https://searxng.your-host.example"" --scope global --clients ""copilot cli,vscode,claude code"""
  Write-Host "  6. Run the Architrave agent for a non-trivial change."
} else {
  Write-Host "  3. Run gates/checks.ps1 and edit the knowledge profile's build/test commands if needed."
  Write-Host "  4. Start a new agent session and ask Architrave to summarize the configured repository profile."
}
Write-Host ""
Write-Host "After you later update the plugin, refresh this repo's copied gates + harness + knowledge:"
Write-Host "       pwsh -NoProfile -File `"$kit/tools/update.ps1`" `"$Target`""
Write-Host "Use -Agents only when you deliberately want to refresh copied Architrave agents after archiving bespoke repo agents."
Write-Host "Use -Codex to refresh only generated Codex roles and managed role registrations. Skills come from the plugin only."
