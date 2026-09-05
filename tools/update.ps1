#!/usr/bin/env pwsh
# Architrave - refresh an adopted repo's COPIED kit assets (gates + knowledge + harness + constitution +
# the AGENTS.md grounding stanza) to match THIS kit, and re-stamp the version.
# PowerShell mirror of tools/update.sh. Never touches architrave.config.json. By default
# it does not touch .github/agents; pass -Agents to refresh Architrave-managed copied
# agent files after archiving bespoke repo agents to avoid split authority.
#
# Usage: pwsh -NoProfile -File tools/update.ps1 [TargetRepoDir] [-Agents] [-Codex]   (default: CWD)
[CmdletBinding()]
param(
  [Parameter(Position = 0)]
  [string]$Target = "$PWD",
  [switch]$Agents,
  [switch]$Codex
)
$ErrorActionPreference = 'Stop'

$kit = Split-Path (Split-Path $MyInvocation.MyCommand.Path -Parent) -Parent
. (Join-Path $kit 'tools/ManagedPaths.ps1')
$Target = (Resolve-Path -LiteralPath $Target).Path
if ($Target -eq $kit) { [Console]::Error.WriteLine('update: refusing to update the kit into itself'); exit 1 }
Initialize-ManagedPaths $Target update
$Target = $script:ManagedRoot
try {
  Assert-ManagedFile 'architrave.config.json'
  $JsonText = [IO.File]::ReadAllText((Get-ManagedPath 'architrave.config.json'))
  $Document = [Text.Json.JsonDocument]::Parse($JsonText)
  try {
    if ($Document.RootElement.ValueKind -ne [Text.Json.JsonValueKind]::Object) { throw 'root must be a JSON object' }
    $KindLikeProperties = @($Document.RootElement.EnumerateObject() | Where-Object { $_.Name -ieq 'kind' })
    $KindProperties = @($Document.RootElement.EnumerateObject() | Where-Object { $_.Name -ceq 'kind' })
    if ($KindLikeProperties.Count -ne $KindProperties.Count) { throw 'kind property is case-sensitive' }
    if ($KindProperties.Count -gt 1) { throw 'kind must occur at most once' }
    if ($KindProperties.Count -eq 1) {
      if ($KindProperties[0].Value.ValueKind -ne [Text.Json.JsonValueKind]::String -or $KindProperties[0].Value.GetString() -cne 'knowledge') {
        throw "kind must be absent or 'knowledge'"
      }
      $kind = 'knowledge'
    } else {
      $kind = 'application'
    }
  } finally {
    $Document.Dispose()
  }
} catch {
  [Console]::Error.WriteLine("update: invalid architrave.config.json ($($_.Exception.Message))")
  exit 2
}

$python = $null
if ($Codex) {
  $pythonCommand = Get-Command python3 -ErrorAction SilentlyContinue
  if (-not $pythonCommand) { $pythonCommand = Get-Command python -ErrorAction SilentlyContinue }
  if (-not $pythonCommand) { [Console]::Error.WriteLine('update: -Codex requires Python 3.11+'); exit 2 }
  $python = $pythonCommand.Source
  & $python "$kit/tools/codex-roles.py" --kit $kit --target $Target --preflight
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$ver = (Get-Content (Join-Path $kit 'plugin.json') -Raw | ConvertFrom-Json).version
if (-not $ver) { $ver = '0.0.0' }
$begin = '<!-- architrave:begin -->'
$end   = '<!-- architrave:end -->'

foreach ($SourceTree in 'gates','knowledge','harness') { Assert-PackagedTree (Join-Path $kit $SourceTree) }
if ($Agents) { Assert-PackagedTree (Join-Path $kit 'agents') }
Assert-PackagedFile (Join-Path $kit 'templates/AGENTS.stanza.md')
Assert-PackagedFile (Join-Path $kit 'plugin.json')
if ($kind -eq 'application') { Get-ChildItem -LiteralPath $kit -Filter 'constitution-*.md' -File | ForEach-Object { Assert-PackagedFile $_.FullName } }
foreach ($Tree in '.github/hooks','gates','gates/hooks','knowledge','harness') { Assert-ManagedTree $Tree }
if ($Agents) { Assert-ManagedTree '.github/agents' }
foreach ($File in 'architrave.config.json','.gitignore','AGENTS.md','constitution-apple.md','constitution-windows.md','.github/hooks/design-guard.json','gates/.kit-version') { Assert-ManagedFilePreflight $File }

Write-Host "Architrave -> refreshing assets in: $Target (kit v$ver)"
foreach ($Directory in '.github/hooks','gates/hooks','knowledge','harness') { New-ManagedDirectory $Directory }

if ($Agents) {
  New-ManagedDirectory '.github/agents'
  Assert-ManagedTree '.github/agents'
  if ($kind -eq 'knowledge') {
    $KnowledgeAgents = @('architrave','adversarial-judge','tournament-analyst','product-research','runtime-observer')
    $KnowledgeAgentFiles = @($KnowledgeAgents | ForEach-Object { "$_.agent.md" })
    foreach ($PackagedAgent in Get-ChildItem (Join-Path $kit 'agents/*.agent.md') -File) {
      if ($PackagedAgent.Name -notin $KnowledgeAgentFiles) {
        Remove-ManagedFile ".github/agents/$($PackagedAgent.Name)"
      }
    }
    foreach ($a in $KnowledgeAgents) {
      Copy-ManagedFile "$kit/agents/$a.agent.md" ".github/agents/$a.agent.md"
    }
    Write-Host '  ok agents refreshed (knowledge crew: architrave/adversarial-judge/tournament-analyst/product-research/runtime-observer)'
  } else {
    Get-ChildItem (Join-Path $kit 'agents') -Filter '*.agent.md' -File | ForEach-Object { Copy-ManagedFile $_.FullName ".github/agents/$($_.Name)" }
    Write-Host '  ok agents refreshed'
  }
} else {
  Write-Host '  - agents left unchanged (use -Agents to refresh .github/agents/)'
}

# Gates - copied because they EXECUTE in the repo.
foreach ($SourceFile in 'checks.sh','checks.ps1','reconcile.sh','reconcile.ps1','quality-gate.sh','quality-gate.ps1','backend-checks.sh','backend-checks.ps1','rubric.md') {
  Copy-ManagedFile (Join-Path $kit "gates/$SourceFile") "gates/$SourceFile"
}
Copy-ManagedTree (Join-Path $kit 'gates/hooks') 'gates/hooks'
Write-Host '  ok gates refreshed'

# Active workspace hook. PowerShell updater installs the Windows command variant.
Copy-ManagedFile (Join-Path $kit 'gates/hooks/design-guard.windows.json') '.github/hooks/design-guard.json'
Write-Host '  ok active workspace hook refreshed'

# Knowledge packs - copied so the cloud agent (no plugin) can read them.
Copy-ManagedTree (Join-Path $kit 'knowledge') 'knowledge'
Write-Host '  ok knowledge refreshed (apple/microsoft/web/backend/operations-ux/design-tokens/execution-policy/learning-loop/yagni/runtime-v2)'

# Platform constitution(s) - application profile only; knowledge updates remove managed copies.
if ($kind -eq 'knowledge') {
  foreach ($Constitution in 'constitution-apple.md','constitution-windows.md') {
    Remove-ManagedFile $Constitution
  }
  Write-Host '  ok constitution removed/skipped (knowledge profile: no native-app UI)'
} else {
  Get-ChildItem -LiteralPath $kit -Filter 'constitution-*.md' -File | ForEach-Object { Copy-ManagedFile $_.FullName $_.Name }
  Write-Host '  ok constitution refreshed (constitution-*.md; Apple + Windows native-app synthesis)'
}

# Audit harness.
Copy-ManagedTree (Join-Path $kit 'harness') 'harness'
Write-Host '  ok harness refreshed'

# Agent session run artifacts are local by default; learning files stay tracked.
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
  Write-Host '  ok .gitignore updated (runs, worktrees, and runtime key stay local)'
}

# AGENTS.md grounding stanza - idempotent.
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
Write-Host '  ok AGENTS.md stanza refreshed'

# Version stamp.
if ($Codex) {
  & $python "$kit/tools/codex-roles.py" --kit $kit --target $Target
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Set-ManagedContent 'gates/.kit-version' "$ver`n"
Write-Host "  ok stamped gates/.kit-version = $ver"
Write-Host 'Done. (architrave.config.json left untouched.)'
