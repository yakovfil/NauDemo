param([ValidateSet('Debug', 'Release')][string]$Configuration = 'Debug')
$ErrorActionPreference = 'Stop'
$demoExe = Join-Path $PSScriptRoot "bin/$Configuration/NauDemo.exe"
if (-not (Test-Path -LiteralPath $demoExe)) {
    throw 'Build the demo first: python ./build.py'
}
Push-Location (Split-Path -Parent $demoExe)
try { & $demoExe } finally { Pop-Location }
