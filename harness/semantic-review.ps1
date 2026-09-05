#!/usr/bin/env pwsh
# Optional semantic review helper. It prepares a judge prompt from run artifacts.
#
# Concrete model/effort bindings are host-local, never canonical: this gate
# resolves them from the environment. A full gate (-Execute) fails closed
# with a clear error if the model for a requested provider is unset.
#
#   ARCHITRAVE_SEMANTIC_REVIEW_COPILOT_MODEL  (required for -Execute with copilot/both)
#   ARCHITRAVE_SEMANTIC_REVIEW_COPILOT_EFFORT (optional)
#   ARCHITRAVE_SEMANTIC_REVIEW_CLAUDE_MODEL   (required for -Execute with claude/both)
#   ARCHITRAVE_SEMANTIC_REVIEW_CLAUDE_EFFORT  (optional)
#
# An exit code, nonce, and terminal VERDICT alone are not accepted as GPT or
# Claude evidence: each provider's judgment is only accepted once its own
# host-observed provider/model-family telemetry (JSON vendor/model fields,
# not self-reported prompt text) confirms the declared family.
[CmdletBinding()]
param(
  [ValidateSet('copilot','claude','both')][string]$Provider = 'both',
  [string]$RunDir,
  [switch]$Execute
)
$ErrorActionPreference = 'Stop'

if (-not $RunDir) {
  $latest = Get-ChildItem '.architrave/runs' -Directory -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if ($latest) { $RunDir = $latest.FullName }
}
if (-not $RunDir -or -not (Test-Path $RunDir -PathType Container)) { [Console]::Error.WriteLine('semantic-review: run dir not found'); exit 2 }

$prompt = Join-Path $RunDir 'semantic-review-prompt.md'
Set-Content -Path $prompt -Encoding utf8 -Value @"
You are an adversarial semantic reviewer for an Architrave run.

Review the run artifacts in $RunDir against gates/rubric.md. Focus on:
- visible intake quality;
- Tournament of Options quality;
- Recommended Plan quality;
- contract/architecture fit;
- deterministic gate evidence;
- safety, capability honesty, and missing tests.

Return PASS / REVISE / FAIL with findings ordered by severity.
"@

Write-Host "semantic-review prompt: $prompt"
if (-not (Get-Command jq -ErrorAction SilentlyContinue)) { [Console]::Error.WriteLine("semantic-review: 'jq' is required (macOS: brew install jq . Windows: winget install jqlang.jq)"); exit 2 }

$agentFile = if (Test-Path 'agents/adversarial-judge.agent.md') {
  'agents/adversarial-judge.agent.md'
} elseif (Test-Path '.github/agents/adversarial-judge.agent.md') {
  '.github/agents/adversarial-judge.agent.md'
} else {
  [Console]::Error.WriteLine('semantic-review: canonical agent not found: adversarial-judge.agent.md')
  exit 2
}

$CopilotModel = $env:ARCHITRAVE_SEMANTIC_REVIEW_COPILOT_MODEL
$CopilotEffort = $env:ARCHITRAVE_SEMANTIC_REVIEW_COPILOT_EFFORT
$ClaudeModel = $env:ARCHITRAVE_SEMANTIC_REVIEW_CLAUDE_MODEL
$ClaudeEffort = $env:ARCHITRAVE_SEMANTIC_REVIEW_CLAUDE_EFFORT

if ($Execute) {
  if ($Provider -in @('copilot','both') -and -not $CopilotModel) { [Console]::Error.WriteLine('semantic-review: set ARCHITRAVE_SEMANTIC_REVIEW_COPILOT_MODEL (host-local) to run the copilot judge as a full gate'); exit 2 }
  if ($Provider -in @('claude','both') -and -not $ClaudeModel) { [Console]::Error.WriteLine('semantic-review: set ARCHITRAVE_SEMANTIC_REVIEW_CLAUDE_MODEL (host-local) to run the claude judge as a full gate'); exit 2 }
}

$body = Get-Content $prompt -Raw
$copilotModelDisplay = if ($CopilotModel) { $CopilotModel } else { '<unset:ARCHITRAVE_SEMANTIC_REVIEW_COPILOT_MODEL>' }
$claudeModelDisplay = if ($ClaudeModel) { $ClaudeModel } else { '<unset:ARCHITRAVE_SEMANTIC_REVIEW_CLAUDE_MODEL>' }

$copilotArgs = @('-C', "$PWD", '--agent', 'architrave:adversarial-judge', '--model', $copilotModelDisplay)
if ($CopilotEffort) { $copilotArgs += @('--reasoning-effort', $CopilotEffort) }
$copilotArgs += @('--available-tools', 'view,grep,glob', '--allow-tool', 'view', '--allow-tool', 'grep', '--allow-tool', 'glob', '--no-ask-user', '--output-format', 'json', '--stream', 'off', '--silent', '--no-color', '-p', $body)

$claudeArgs = @('--model', $claudeModelDisplay)
if ($ClaudeEffort) { $claudeArgs += @('--effort', $ClaudeEffort) }
$claudeArgs += @('--tools', 'Read,Grep,Glob', '--allowedTools', 'Read,Grep,Glob', '--append-system-prompt-file', $agentFile, '--output-format', 'json', '-p', $body)

if (-not $Execute) {
  Write-Host 'suggested command(s) (review before running):'
  if ($Provider -in @('copilot','both')) { Write-Host "  copilot $($copilotArgs -join ' ')" }
  if ($Provider -in @('claude','both')) { Write-Host "  claude $($claudeArgs -join ' ')" }
  exit 0
}

# Extract the judge's final response text from provider-specific JSON
# telemetry. Copilot emits JSONL events; Claude's --output-format json emits
# one JSON object.
function Get-JudgeContent([string]$Label, [string]$Output) {
  if ($Label -eq 'claude') {
    try { $parsed = $Output | ConvertFrom-Json -ErrorAction Stop } catch { return '' }
    return [string]$parsed.result
  }
  $events = @()
  foreach ($line in @($Output -split "`r?`n")) {
    if (-not $line.Trim()) { continue }
    try { $events += , (ConvertFrom-Json $line -ErrorAction Stop) } catch { continue }
  }
  $messages = @($events | Where-Object { $_.type -eq 'assistant.message' })
  if ($messages.Count -eq 0) { return '' }
  return [string]$messages[-1].data.content
}

function Get-VendorFamily([string]$Value) {
  if ($Value -match '(?i)anthropic|claude') { return 'claude' }
  if ($Value -match '(?i)openai') { return 'gpt' }
  return $null
}

function Get-ModelFamily([string]$Value) {
  if ($Value -match '(?i)claude|anthropic') { return 'claude' }
  if ($Value -match '(?i)^(gpt-|openai/|o1|o3|o4)') { return 'gpt' }
  return $null
}

# Determine trusted, host-observed provider/model-family evidence: vendor or
# model-id telemetry reported by the CLI's own JSON output, never the judge's
# self-reported prompt text. Returns observed-vendor, observed-model, or
# unverified (no usable telemetry, or telemetry contradicting the declared
# family).
function Get-FamilyEvidence([string]$Label, [string]$Output, [string]$Declared) {
  if ($Label -eq 'claude') {
    try { $parsed = $Output | ConvertFrom-Json -ErrorAction Stop } catch { return 'unverified' }
    $models = @()
    if ($parsed.modelUsage) { $models = @($parsed.modelUsage.PSObject.Properties.Name) }
    $modelFamilies = @($models | ForEach-Object { Get-ModelFamily $_ } | Where-Object { $_ } | Sort-Object -Unique)
    if ($modelFamilies -contains $Declared) { return 'observed-model' }
    return 'unverified'
  }
  $events = @()
  foreach ($line in @($Output -split "`r?`n")) {
    if (-not $line.Trim()) { continue }
    try { $events += , (ConvertFrom-Json $line -ErrorAction Stop) } catch { continue }
  }
  $vendors = @()
  foreach ($event in $events) {
    if ($event.type -ne 'session.usage_checkpoint') { continue }
    foreach ($state in @($event.data.promptCacheBreakState)) {
      if (-not $state -or $state.conversation -ne 'main' -or -not $state.models) { continue }
      foreach ($member in $state.models.PSObject.Properties) {
        if ($member.Value.vendor) { $vendors += $member.Value.vendor }
      }
    }
  }
  $vendorFamilies = @($vendors | ForEach-Object { Get-VendorFamily $_ } | Where-Object { $_ } | Sort-Object -Unique)
  if ($vendorFamilies -contains $Declared) { return 'observed-vendor' }
  if ($vendors.Count -gt 0) { return 'unverified' }
  $models = @($events | Where-Object { $_.type -eq 'assistant.message' } | ForEach-Object { $_.data.model } | Where-Object { $_ })
  $modelFamilies = @($models | ForEach-Object { Get-ModelFamily $_ } | Where-Object { $_ } | Sort-Object -Unique)
  if ($modelFamilies -contains $Declared) { return 'observed-model' }
  return 'unverified'
}

function Test-VerifiedPass([string]$Content, [string]$Nonce) {
  # Split on `r?`n, then also strip any lone trailing `r a line may retain
  # when it is the last line of the content and lacks a following `n (e.g.
  # CRLF-terminated judge output with no final newline).
  $lines = @($Content -split "`r?`n" | ForEach-Object { $_ -replace "`r$", '' })
  $nonEmpty = @($lines | Where-Object { $_.Trim().Length -gt 0 })
  $nonceLines = @($lines | Where-Object { $_ -eq "EVIDENCE_NONCE: $Nonce" })
  $verdictLines = @($lines | Where-Object { $_ -match '^VERDICT: (PASS|REVISE|FAIL)$' })
  return $nonceLines.Count -eq 1 -and $verdictLines.Count -eq 1 -and $nonEmpty.Count -gt 0 -and $nonEmpty[-1] -eq 'VERDICT: PASS'
}

$nonceFile = [System.IO.Path]::GetTempFileName()
try {
  $nonce = [guid]::NewGuid().ToString('D').ToLowerInvariant()
  [System.IO.File]::WriteAllText($nonceFile, $nonce + "`n", [System.Text.UTF8Encoding]::new($false))
  $nonceBody = $body + "`n`nRead $nonceFile and include EVIDENCE_NONCE: <value> in your response; the value is absent from this prompt. End with one line exactly VERDICT: PASS, VERDICT: REVISE, or VERDICT: FAIL."
  $copilotArgs[$copilotArgs.Count - 1] = $nonceBody
  $claudeArgs[$claudeArgs.Count - 1] = $nonceBody
  $failed = $false

  function Invoke-Judge([string]$Label, [string]$Declared, [string[]]$CommandArgs) {
    $output = (& $Label @CommandArgs 2>&1 | Out-String)
    $exitCode = $LASTEXITCODE
    $content = Get-JudgeContent $Label $output
    Write-Host $content
    if ($exitCode -ne 0 -or -not (Test-VerifiedPass $content $nonce)) {
      [Console]::Error.WriteLine("semantic-review: $Label judge did not return a verified PASS")
      return $false
    }
    $familyEvidence = Get-FamilyEvidence $Label $output $Declared
    if ($familyEvidence -eq 'unverified') {
      [Console]::Error.WriteLine("semantic-review: $Label judge did not return verified $Declared-family evidence")
      return $false
    }
    return $true
  }

  if ($Provider -in @('copilot','both')) { if (-not (Invoke-Judge 'copilot' 'gpt' $copilotArgs)) { $failed = $true } }
  if ($Provider -in @('claude','both')) { if (-not (Invoke-Judge 'claude' 'claude' $claudeArgs)) { $failed = $true } }
  if ($failed) { exit 1 }
} finally { Remove-Item $nonceFile -Force -ErrorAction SilentlyContinue }
