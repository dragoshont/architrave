#!/usr/bin/env pwsh
# Optional independent semantic review helper. Model selection is inherited from
# the invoking host and is never configured by Architrave.
[CmdletBinding()]
param(
  [ValidateSet('copilot','claude','both')][string]$Provider = 'both',
  [string]$RunDir,
  [switch]$Execute
)
$ErrorActionPreference = 'Stop'

if (-not $RunDir) {
  $latest = Get-ChildItem '.architrave/runs' -Directory -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if ($latest) { $RunDir = $latest.FullName }
}
if (-not $RunDir -or -not (Test-Path $RunDir -PathType Container)) {
  [Console]::Error.WriteLine('semantic-review: run dir not found')
  exit 2
}

$agentFile = if (Test-Path 'agents/adversarial-judge.agent.md') {
  'agents/adversarial-judge.agent.md'
} elseif (Test-Path '.github/agents/adversarial-judge.agent.md') {
  '.github/agents/adversarial-judge.agent.md'
} else {
  [Console]::Error.WriteLine('semantic-review: adversarial judge agent not found')
  exit 2
}

$body = @"
Review canonical state and referenced evidence in $RunDir against gates/rubric.md.
Focus on Outcome/acceptance coverage, TaskGraph scope, repository contract fit,
deterministic and runtime evidence, safety, capability honesty, and missing tests.
Return concise findings ordered by severity, then VERDICT: PASS|REVISE|FAIL.
"@
$copilotArgs = @('-C', "$PWD", '--agent', 'architrave:adversarial-judge', '--available-tools', 'view,grep,glob', '--allow-tool', 'view', '--allow-tool', 'grep', '--allow-tool', 'glob', '--no-ask-user', '--output-format', 'json', '--stream', 'off', '--silent', '--no-color', '-p', $body)
$claudeArgs = @('--tools', 'Read,Grep,Glob', '--allowedTools', 'Read,Grep,Glob', '--append-system-prompt-file', $agentFile, '--output-format', 'json', '-p', $body)

if (-not $Execute) {
  Write-Host 'suggested command(s) (host-selected model):'
  if ($Provider -in @('copilot','both')) { Write-Host "  copilot $($copilotArgs -join ' ')" }
  if ($Provider -in @('claude','both')) { Write-Host "  claude $($claudeArgs -join ' ')" }
  exit 0
}

$nonceFile = [System.IO.Path]::GetTempFileName()
try {
  $nonce = [guid]::NewGuid().ToString('D').ToLowerInvariant()
  [System.IO.File]::WriteAllText($nonceFile, $nonce + "`n", [System.Text.UTF8Encoding]::new($false))
  $noncePrompt = "Read $nonceFile and include EVIDENCE_NONCE: <value>. End with exactly VERDICT: PASS, VERDICT: REVISE, or VERDICT: FAIL."
  $copilotArgs[-1] = "$body`n`n$noncePrompt"
  $claudeArgs[-1] = "$body`n`n$noncePrompt"

  function Invoke-Judge([string]$Label, [string[]]$CommandArgs) {
    $output = (& $Label @CommandArgs 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) { return $false }
    if ($Label -eq 'claude') {
      try { $content = [string](($output | ConvertFrom-Json).result) } catch { return $false }
    } else {
      $events = @()
      foreach ($line in @($output -split "`r?`n")) {
        if (-not $line.Trim()) { continue }
        try { $events += , (ConvertFrom-Json $line) } catch { continue }
      }
      $messages = @($events | Where-Object { $_.type -eq 'assistant.message' })
      if ($messages.Count -eq 0) { return $false }
      $content = [string]$messages[-1].data.content
    }
    Write-Host $content
    $lines = @($content -split "`r?`n" | ForEach-Object { $_ -replace "`r$", '' })
    $nonEmpty = @($lines | Where-Object { $_.Trim() })
    return @($lines | Where-Object { $_ -eq "EVIDENCE_NONCE: $nonce" }).Count -eq 1 -and
      @($lines | Where-Object { $_ -match '^VERDICT: (PASS|REVISE|FAIL)$' }).Count -eq 1 -and
      $nonEmpty[-1] -eq 'VERDICT: PASS'
  }

  $failed = $false
  if ($Provider -in @('copilot','both')) { if (-not (Invoke-Judge 'copilot' $copilotArgs)) { $failed = $true } }
  if ($Provider -in @('claude','both')) { if (-not (Invoke-Judge 'claude' $claudeArgs)) { $failed = $true } }
  if ($failed) { exit 1 }
} finally {
  Remove-Item $nonceFile -Force -ErrorAction SilentlyContinue
}
