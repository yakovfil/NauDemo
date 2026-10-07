# Packaged Windows and web startup

EditorProject provides the same portable, non-rendering scene application on
Windows and web. It loads a cooked archive, activates real scene objects and
supported components, runs updates and performs checked cleanup. Camera and
mesh/material references remain passive data. Rendering, physics, animation
playback, audio and input services are outside this profile.

The existing rendered Windows SDK build remains separately available through
its existing presets/CMake route. `run_windows.bat` selects the new portable
application, so its window intentionally has no rendered scene.

## Build and run

From EditorProject:

```powershell
./build.ps1 -Platform Windows -Configuration Debug
./build.ps1 -Platform Windows -Configuration Release
./run_windows.bat Debug
./run_windows.bat Release
./run_web.bat Debug
./run_web.bat Release
```

The batch wrappers freshly build and launch their target. Web activates EMSDK
from its environment path or `%USERPROFILE%/emsdk`, serves the package with
COOP/COEP headers and opens the browser. Close the native window to stop the
Windows application; press Ctrl+C to stop the web server. Browser runtime Stop
remains available through `Module.nauRuntime.stop()`.

Windows requires VS 2026/v145 and CMake 4.2+. Fresh asset preparation requires a
matching native shared SDK, asset/pack tools, OpenUSD 24.08 and Python 3.10.
Web additionally requires Ninja and Emscripten 6.0.9. These must already be
provisioned. Known local defaults discover the sibling editor's
`dist/win_vs2026_x64_dll` SDK, `build/latest-release/bin/Release` tools (or SDK
`bin`), and the engine's local OpenUSD install. Other machines can override:

```powershell
$env:NAU_ENGINE_SDK_DIR = 'C:/sdk/nau'
$env:NAU_HOST_TOOLS_DIR = 'C:/tools/nau/bin/Release'
$env:NAU_USD_SDK_DIR = 'C:/sdk/openusd'
./build.ps1 -Platform Windows -Configuration Debug `
  -PythonExecutable C:/Python310/python.exe -Run
. 'C:/tools/emsdk/emsdk_env.ps1'
./build.ps1 -Platform Web -Configuration Release -Serve -Port 8000
```

Explicit `-HostSdk`, `-HostTools`, `-UsdSdk` and `-PythonExecutable` parameters
also override discovery. Existing `web/build.ps1` calls remain supported; its
default platform is Web, whereas `build.ps1` defaults to Windows.

## One declaration and one archive

`portable_project.json` declares the profile, modules, game module, startup
configuration and supported component names. Both target builds, cooking and
runtime validation use it. The shared `source/portable_main.cpp` reads the
generated policy; the rendered desktop launcher remains `source/main.cpp`.

Normal builds rebuild host component registration and freshly prepare assets.
To deliver an already prepared snapshot without cooking tools, use:

```powershell
$archive = 'C:/packages/content.nau_pack'
./build.ps1 -Platform Windows -Configuration Debug -PreparedArchive $archive
./build.ps1 -Platform Web -Configuration Debug -PreparedArchive $archive
```

Both deliveries contain exactly the selected archive bytes. This mode validates
the archive/profile but does not verify that the snapshot matches current source
assets. Python and target compilers are still required. Use a normal fresh build
to include source, metadata, component or declaration changes.

All generated files are ignored under `build/`: `portable-host-components`,
`prepared-debug`/`prepared-release`, `windows-debug`/`windows-release` and
`web-debug`/`web-release`. Each target has a `selected-input` snapshot and
`package`. Builds of the same project are serialized; an overlapping invocation
fails with a retry diagnostic. Authored content is never imported in place.

Native packages resolve their archive beside the executable and work from an
unrelated working directory. Web packages can be served from a nested URL
outside the checkout. Runtime access to source assets, host SDK or USD is not
required. Windows needs the corresponding MSVC runtime on its host.

Logs appear in the native console or in F12 -> Console in the browser. Enable
Info, Warning and Error messages there. The browser reports lifecycle status
even when the scene has no logging components; warnings/errors retain severity
and each component message appears once. The server terminal displays HTTP
requests. Browser memory starts at 128 MiB and can grow to 512 MiB, configurable
through the existing browser project CMake memory settings.

## Acceptance

Prepare the component fixture once, then select its archive for every target:

```powershell
./build.ps1 -Platform Windows -Configuration Debug -Acceptance
$archive = (Resolve-Path ./build/prepared-debug/content.nau_pack).Path
./build.ps1 -Platform Windows -Configuration Release -Acceptance -PreparedArchive $archive
./build.ps1 -Platform Web -Configuration Debug -Acceptance -PreparedArchive $archive
./build.ps1 -Platform Web -Configuration Release -Acceptance -PreparedArchive $archive
python ./tests/verify_native_startup.py --configuration Debug
python ./tests/verify_native_startup.py --configuration Release
python ./tests/verify_web_startup.py --configuration Debug
python ./tests/verify_web_startup.py --configuration Release
```

Acceptance builds add the independent observer's separate `probe-package`.
Production application behavior is exercised separately from scene observation.
The runners verify authored hierarchy, identities, transforms, properties,
component movement, relocation, errors and cleanup. Native runs also check exit
codes and repeated Stop; browser runs cover pending load and asynchronous Stop.
Browser tests require Playwright and installed Chrome. Preparation tests use a
scratch project and verify source/metadata/component/declaration invalidation and
failed conversion/publication; use `tests/verify_preparation.py --help` for paths.

The portable type-name records support native64 and wasm32 lookup. Legacy native
records keep their original platform hash fallback; recook old content for web.
See the [reusable integration guide](../../../NauEngineModules/cmake/packaged_project/README.md)
for generic source locations, declaration fields and compatibility interfaces.
