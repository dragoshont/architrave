#!/usr/bin/env pwsh
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$RunDir,[switch]$Execute)
$ErrorActionPreference='Stop'
if (-not (Test-Path $RunDir -PathType Container)) { [Console]::Error.WriteLine('tournament-review: run dir not found'); exit 2 }
$agentFile = if (Test-Path 'agents/tournament-analyst.agent.md') { 'agents/tournament-analyst.agent.md' } elseif (Test-Path '.github/agents/tournament-analyst.agent.md') { '.github/agents/tournament-analyst.agent.md' } else { [Console]::Error.WriteLine('tournament-review: canonical Tournament Analyst not found'); exit 2 }
$prompt=Join-Path $RunDir 'tournament-review-prompt.md'
@"
Read the intake and governing repository sources for the Architrave run at $RunDir.
Compare viable options using the canonical Tournament Analyst instructions.
Do not edit files or authorize mutations. End with one line exactly TOURNAMENT: COMPLETE.
"@ | Set-Content $prompt -Encoding utf8
if (-not $Execute) { Write-Host "suggested command: claude --model claude-opus-4.8 --effort max --tools Read,Grep,Glob --allowedTools Read,Grep,Glob --append-system-prompt-file `"$agentFile`" -p (Get-Content `"$prompt`" -Raw)"; exit 0 }
$nonceFile=[System.IO.Path]::GetTempFileName()
try {
  $nonce=[guid]::NewGuid().ToString('D').ToLowerInvariant(); [IO.File]::WriteAllText($nonceFile,$nonce+"`n",[Text.UTF8Encoding]::new($false))
  $body=(Get-Content $prompt -Raw)+"`nRead $nonceFile and include EVIDENCE_NONCE: <value>; the value is absent from this prompt."
  $output=(& claude --model claude-opus-4.8 --effort max --tools Read,Grep,Glob --allowedTools Read,Grep,Glob --append-system-prompt-file $agentFile -p $body 2>&1 | Out-String); Write-Host $output -NoNewline
  $lines=@($output -split "`r?`n"); $nonEmpty=@($lines|Where-Object{$_.Trim().Length -gt 0}); $nonceLines=@($lines|Where-Object{$_ -eq "EVIDENCE_NONCE: $nonce"}); $complete=@($lines|Where-Object{$_ -eq 'TOURNAMENT: COMPLETE'})
  if ($LASTEXITCODE -ne 0 -or $nonceLines.Count -ne 1 -or $complete.Count -ne 1 -or $nonEmpty[-1] -ne 'TOURNAMENT: COMPLETE') { [Console]::Error.WriteLine('tournament-review: unverified result'); exit 1 }
} finally { Remove-Item $nonceFile -Force -ErrorAction SilentlyContinue }