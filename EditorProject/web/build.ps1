param(
    [ValidateSet('Debug', 'Release')][string]$Configuration = 'Debug',
    [string]$HostSdk = $env:NAU_ENGINE_SDK_DIR,
    [string]$HostTools = $env:NAU_HOST_TOOLS_DIR,
    [string]$UsdSdk = $env:NAU_USD_SDK_DIR,
    [string]$PythonExecutable,
    [switch]$Acceptance,
    [switch]$Serve,
    [ValidateRange(1,65535)][int]$Port = 8000,
    [string]$PreparedArchive,
    [string]$Declaration,
    [ValidateSet('Windows','Web')][string]$Platform = 'Web',
    [switch]$Run
)
$ErrorActionPreference = 'Stop'
$projectDirectory = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$checkout = (Resolve-Path (Join-Path $projectDirectory '../..')).Path
$arguments = @{} + $PSBoundParameters
$arguments.Platform = $Platform
$arguments.ApplicationTarget = 'NauDemoMain'
$arguments.AcceptanceScenes = @('scenes/web_startup_fixture.nausd_scene')
$arguments.ProjectDirectory = $projectDirectory
$arguments.EngineDirectory = Join-Path $checkout 'NauEngineLite'
$arguments.ModulesDirectory = Join-Path $checkout 'NauEngineModules'
& (Join-Path $arguments.ModulesDirectory 'cmake/packaged_project/build.ps1') @arguments
exit $LASTEXITCODE
