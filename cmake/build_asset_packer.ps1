param([ValidateSet('Debug','Release')][string]$Configuration='Release')
$demo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$source = Join-Path $demo '../NauEngineModules/cmake/probes/asset_pack'
$build = Join-Path $demo 'build/asset-pack-host'
cmake -S $source -B $build -G 'Visual Studio 18 2026' -A x64
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
cmake --build $build --config $Configuration --target AssetPackToolCmd --parallel 8
exit $LASTEXITCODE
