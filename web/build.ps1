param(
    [ValidateSet('Debug', 'Release')][string]$Configuration = 'Debug'
)

$demo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$engine = (Resolve-Path (Join-Path $demo '../NauEngineLite')).Path
$build = Join-Path $demo ('build/web-demo-' + $Configuration.ToLowerInvariant())
if (-not $env:EMSDK) {
    throw 'Activate Emscripten SDK 6.0.9 before building NauDemo.'
}
$toolchain = Join-Path $env:EMSDK 'upstream/emscripten/cmake/Modules/Platform/Emscripten.cmake'
cmake -S $engine -B $build -G Ninja `
    "-DCMAKE_TOOLCHAIN_FILE=$toolchain" `
    "-DCMAKE_BUILD_TYPE=$Configuration" `
    '-DNAU_BUILD_BROWSER=ON' '-DNAU_RUNTIME_PROFILE=scene' `
    '-DBUILD_SHARED_LIBS=OFF' '-DNAU_CORE_SAMPLES=OFF' `
    '-DNAU_CORE_TOOLS=OFF' '-DNAU_CORE_TESTS=OFF' `
    "-DCMAKE_PROJECT_NauEngine_INCLUDE=$demo/cmake/attach_demo.cmake"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
cmake --build $build --target NauDemoWebPackage --parallel 8
exit $LASTEXITCODE
