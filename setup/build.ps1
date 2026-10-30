param([string]$Compiler = 'C:\Program Files\Inno Setup 7\ISCC.exe')
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
if (-not (Test-Path -LiteralPath $Compiler)) { throw 'Install Inno Setup 7.1.1 or specify -Compiler.' }
$project = Get-Content -LiteralPath (Join-Path $repo 'pyproject.toml') -Raw
$version = [regex]::Match($project, '(?m)^version\s*=\s*"([^"]+)"').Groups[1].Value
if (-not $version) { throw 'Version is missing from pyproject.toml.' }
& $Compiler "/DScriptVersion=$version" (Join-Path $PSScriptRoot 'setup.iss')
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed: $LASTEXITCODE" }
