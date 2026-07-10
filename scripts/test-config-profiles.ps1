#!/usr/bin/env pwsh
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root
$Schema = Join-Path $Root 'kit/architrave.config.schema.json'
$Tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("architrave-config-profiles-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $Tmp | Out-Null

function Test-Config([string]$Path) {
  & npx --yes ajv-cli@5 validate --spec=draft7 -s $Schema -d $Path *> $null
  return $LASTEXITCODE
}
function Expect-Pass([string]$Name, [string]$Path) {
  if ((Test-Config $Path) -ne 0) { throw "FAIL $Name should pass" }
  Write-Host "ok    $Name"
}
function Expect-Fail([string]$Name, [string]$Path) {
  if ((Test-Config $Path) -eq 0) { throw "FAIL $Name should fail" }
  Write-Host "ok    $Name rejected"
}
function Write-Json([object]$Value, [string]$Path) {
  $Value | ConvertTo-Json -Depth 20 | Set-Content -Path $Path -Encoding utf8
}

try {
  $Knowledge = Get-Content 'kit/examples/knowledge.architrave.json' -Raw | ConvertFrom-Json -AsHashtable
  $KnowledgePath = Join-Path $Tmp 'knowledge.json'; Write-Json $Knowledge $KnowledgePath
  Expect-Pass 'knowledge-positive' $KnowledgePath

  foreach ($Missing in @('build', 'test')) {
    $Value = $Knowledge.Clone(); $Value.Remove($Missing)
    $Path = Join-Path $Tmp "missing-$Missing.json"; Write-Json $Value $Path
    Expect-Fail "knowledge-missing-$Missing" $Path
  }
  $Unknown = $Knowledge.Clone(); $Unknown.kind = 'automation'
  $UnknownPath = Join-Path $Tmp 'unknown-kind.json'; Write-Json $Unknown $UnknownPath
  Expect-Fail 'knowledge-unknown-kind' $UnknownPath

  $Forbidden = @{
    platform='web'; stack='other'; designSource=@{type='design-doc';path='README.md'}; designMap='map.json';
    tokens='tokens.json'; tokenBuild='echo tokens'; knowledgePack='web'; applyTo=@('**'); generate='echo generate';
    screenshot='echo screenshot'; backend=@{}; iac=@{}; ops=@{}
  }
  foreach ($Field in $Forbidden.Keys) {
    $Value = $Knowledge.Clone(); $Value[$Field] = $Forbidden[$Field]
    $Path = Join-Path $Tmp "forbidden-$Field.json"; Write-Json $Value $Path
    Expect-Fail "knowledge-forbids-$Field" $Path
  }
  foreach ($Example in @('phonodeck','sideport','tessera')) {
    Expect-Pass "legacy-$Example" "kit/examples/$Example.architrave.json"
  }
  $Legacy = Get-Content 'kit/examples/sideport.architrave.json' -Raw | ConvertFrom-Json -AsHashtable
  $Legacy.Remove('platform'); $LegacyPath = Join-Path $Tmp 'legacy-missing-platform.json'; Write-Json $Legacy $LegacyPath
  Expect-Fail 'legacy-missing-platform' $LegacyPath
  Write-Host 'CONFIG-PROFILES: PASS'
}
finally { Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue }