param(
    [ValidateSet('Debug', 'Release')][string]$Configuration = 'Debug',
    [string]$HostSdk = $env:NAU_ENGINE_SDK_DIR,
    [string]$HostTools = $env:NAU_HOST_TOOLS_DIR,
    [string]$UsdSdk = $env:NAU_USD_SDK_DIR,
    [string]$PythonExecutable,
    [switch]$Acceptance,
    [switch]$Serve,
    [ValidateRange(1, 65535)][int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$projectDirectory = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$checkout = (Resolve-Path (Join-Path $projectDirectory '../..')).Path
$engineDirectory = (Resolve-Path (Join-Path $checkout 'NauEngineLite')).Path
$modulesDirectory = (Resolve-Path (Join-Path $checkout 'NauEngineModules')).Path
function Find-LocalDirectory($explicitPath, $candidates, $marker, $description) {
    if ($explicitPath) { $candidates = @($explicitPath) }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath (Join-Path $candidate $marker) -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    throw "Cannot find $description. Checked: $($candidates -join ', '). See web/README.md for provisioning and overrides."
}
$HostSdk = Find-LocalDirectory $HostSdk @(
    (Join-Path $checkout 'NauEditorPublic/dist/win_vs2026_x64_dll')
) 'cmake/NauModule.cmake' 'native engine SDK (NAU_ENGINE_SDK_DIR)'
$HostTools = Find-LocalDirectory $HostTools @(
    (Join-Path $checkout 'NauEditorPublic/build/latest-release/bin/Release'),
    (Join-Path $HostSdk 'bin')
) 'AssetToolCmd.exe' 'native asset tools (NAU_HOST_TOOLS_DIR)'
$UsdSdk = Find-LocalDirectory $UsdSdk @(
    (Join-Path $engineDirectory 'engine/3rdparty_libs/build/openusd/install')
) 'lib/python/pxr/__init__.py' 'OpenUSD SDK (NAU_USD_SDK_DIR)'
foreach ($required in @($HostSdk, $HostTools, $UsdSdk, $env:EMSDK)) {
    if (-not $required -or -not (Test-Path -LiteralPath $required -PathType Container)) {
        throw 'Provision HostSdk, HostTools, UsdSdk and active EMSDK 6.0.9 explicitly. See web/README.md.'
    }
}
$HostSdk = (Resolve-Path -LiteralPath $HostSdk).Path
$HostTools = (Resolve-Path -LiteralPath $HostTools).Path
$UsdSdk = (Resolve-Path -LiteralPath $UsdSdk).Path
$toolchain = Join-Path $env:EMSDK 'upstream/emscripten/cmake/Modules/Platform/Emscripten.cmake'
foreach ($required in @($toolchain, (Join-Path $HostTools 'AssetToolCmd.exe'), (Join-Path $HostTools 'AssetPackToolCmd.exe'))) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing prerequisite: $required" }
}
if (-not $PythonExecutable) {
    $PythonExecutable = (& py -3.10 -c 'import sys; print(sys.executable)')
    if ($LASTEXITCODE -ne 0) { throw 'Provide PythonExecutable matching the native USD SDK.' }
}
$PythonExecutable = (Resolve-Path -LiteralPath $PythonExecutable).Path
$pythonDirectory = Split-Path $PythonExecutable
$env:PATH = "$HostTools;$HostTools/plugins;$pythonDirectory;$UsdSdk/bin;$UsdSdk/lib;$env:PATH"
$env:PYTHONPATH = "$UsdSdk/lib/python"
$env:PXR_PLUGINPATH_NAME = "$HostTools/plugins;$UsdSdk/plugin/usd"

# Windows PowerShell treats native stderr (including CMake NOTICE/warnings) as
# error records. Native commands below are checked by their actual exit codes.
$ErrorActionPreference = 'Continue'

$hostBuild = Join-Path $projectDirectory 'build/web-host-components'
cmake -S $projectDirectory -B $hostBuild -G 'Visual Studio 18 2026' -A x64 `
    "-DNauEngineFolder=$HostSdk" '-DNAU_WEB_HOST_COMPONENTS=ON' '-DBUILD_SHARED_LIBS=ON'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
cmake --build $hostBuild --config Release --target MainGameModule --parallel 8
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$prepared = Join-Path $projectDirectory ('build/prepared-' + $Configuration.ToLowerInvariant())
$prepareArguments = @(
    (Join-Path $modulesDirectory 'tools/asset_tools/prepare_browser_project.py'),
    '--project', $projectDirectory, '--output', $prepared,
    '--asset-tool', (Join-Path $HostTools 'AssetToolCmd.exe'),
    '--pack-tool', (Join-Path $HostTools 'AssetPackToolCmd.exe'),
    '--module', (Join-Path $hostBuild 'bin/Release/MainGameModule.dll'),
    '--supported-component', 'nau::scene::SceneComponent',
    '--supported-component', 'nau::scene::CameraComponent',
    '--supported-component', 'nau::scene::StaticMeshComponent',
    '--supported-component', 'MyMover', '--supported-component', 'MyRotator'
)
if ($Acceptance) { $prepareArguments += @('--scene', 'scenes/web_startup_fixture.nausd_scene') }
& $PythonExecutable @prepareArguments
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$build = Join-Path $projectDirectory ('build/web-' + $Configuration.ToLowerInvariant())
cmake -S $engineDirectory -B $build -G Ninja `
    "-DCMAKE_TOOLCHAIN_FILE=$toolchain" "-DCMAKE_BUILD_TYPE=$Configuration" `
    '-DNAU_BUILD_BROWSER=ON' '-DNAU_RUNTIME_PROFILE=scene' '-DBUILD_SHARED_LIBS=OFF' `
    '-DNAU_CORE_SAMPLES=OFF' '-DNAU_CORE_TOOLS=OFF' '-DNAU_CORE_TESTS=OFF' `
    "-DCMAKE_PROJECT_NauEngine_INCLUDE=$modulesDirectory/cmake/attach_browser_project.cmake" `
    "-DNAU_BROWSER_PROJECT_SOURCE_DIR=$projectDirectory" `
    "-DNAU_BROWSER_PROJECT_ARCHIVE=$prepared/content.nau_pack" `
    "-DNAU_BROWSER_PROJECT_ACCEPTANCE=$($Acceptance.IsPresent)"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$targets = @('NauDemoMainWebPackage')
if ($Acceptance) { $targets += 'NauDemoStartupProbeWebPackage' }
cmake --build $build --target @targets --parallel 8
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if ($Serve) {
    & $PythonExecutable (Join-Path $build 'package/serve.py') --port $Port --open-browser
}
exit $LASTEXITCODE
