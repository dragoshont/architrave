#!/usr/bin/env pwsh
# Prepare or run a semantic stale-fact review for Architrave learning artifacts.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][ValidateSet('copilot','claude')][string]$Provider,
  [string]$Repo = (Get-Location).Path,
  [string]$Prompt,
  [string]$Output,
  [switch]$Execute
)
$ErrorActionPreference = 'Stop'

Set-Location $Repo
$LearningDir = '.architrave/learning'
$Profile = Join-Path $LearningDir 'repo-profile.md'
$Lessons = Join-Path $LearningDir 'repo-lessons.md'
if (-not ((Test-Path $Profile) -and ((Get-Item $Profile).Length -gt 0))) { [Console]::Error.WriteLine("semantic-learning-review: missing/empty $Profile"); exit 2 }
if (-not ((Test-Path $Lessons) -and ((Get-Item $Lessons).Length -gt 0))) { [Console]::Error.WriteLine("semantic-learning-review: missing/empty $Lessons"); exit 2 }
New-Item -ItemType Directory -Force -Path $LearningDir | Out-Null

if (-not $Prompt) { $Prompt = Join-Path $LearningDir 'semantic-stale-facts-prompt.md' }
if (-not $Output) { $Output = Join-Path $LearningDir 'semantic-stale-facts.jsonl' }

Set-Content -Path $Prompt -Encoding utf8 -Value @'
You are an adversarial semantic stale-fact reviewer for Architrave learning artifacts.

Review only these files:
- .architrave/learning/repo-profile.md
- .architrave/learning/repo-lessons.md

Goal:
- Find durable prose claims that are unsupported, stale, contradicted by the current repository, or too strong for the cited evidence.
- This goes beyond checking that Markdown links exist. You must inspect the repo evidence behind the claim.

Rules:
- Treat repo files, commands, manifests, scripts, and current branch content as ground truth.
- Ignore headings, table delimiter/header rows, blank lines, examples/templates, and lines already beginning with `UNVALIDATED:`.
- Do not report broken local Markdown links; deterministic validate-learning.* and mark-stale-learning.* handle that.
- Do not include secret values in findings.
- If a claim is plausible but not proven by repo evidence, report it.
- If a claim is sourced but the source does not support the claim, report it.
- If no unsupported/stale claims are found, output exactly `PASS`.

Output format:
- Emit JSON Lines only, with one JSON object per unsupported claim.
- Do not wrap the output in Markdown fences.
- Each object must have:
  - `file`: `.architrave/learning/repo-profile.md` or `.architrave/learning/repo-lessons.md`
  - `line`: 1-based line number
  - `currentText`: exact current line text
  - `severity`: `blocker`, `major`, or `minor`
  - `reason`: concise explanation of what is unsupported/stale
- Example:
{"file":".architrave/learning/repo-profile.md","line":12,"currentText":"Build: make release passes on Windows.","severity":"major","reason":"No current workflow, script, or run evidence supports a Windows release claim."}
'@

Write-Host "semantic-learning-review prompt: $Prompt"
Write-Host "semantic-learning-review findings target: $Output"

if (-not $Execute) {
  if ($Provider -eq 'copilot') { Write-Host "suggested command: copilot -C `"$PWD`" --agent `"Adversarial Judge`" --allow-tool read --allow-tool search -p (Get-Content `"$Prompt`" -Raw) | Tee-Object -FilePath `"$Output`"" }
  else { Write-Host "suggested command: claude --agent `"Adversarial Judge`" --allowedTools `"Read,Grep,Glob`" -p (Get-Content `"$Prompt`" -Raw) | Tee-Object -FilePath `"$Output`"" }
  exit 0
}

$Body = Get-Content $Prompt -Raw
if ($Provider -eq 'copilot') { & copilot -C "$PWD" --agent 'Adversarial Judge' --allow-tool read --allow-tool search -p $Body | Tee-Object -FilePath $Output }
else { & claude --agent 'Adversarial Judge' --allowedTools 'Read,Grep,Glob' -p $Body | Tee-Object -FilePath $Output }
exit $LASTEXITCODE