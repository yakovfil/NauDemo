# Browser scene startup

This profile builds the editor-created project for non-rendering browser startup.
It loads a native-cooked scene from a portable archive, preserves its hierarchy,
component identities, transforms and properties, activates supported components,
runs updates and supports asynchronous Stop through `Module.nauRuntime.stop()`.

Supported component types are SceneComponent, CameraComponent, StaticMeshComponent,
MyMover and MyRotator. Camera/mesh/material references are passive data. Rendering,
GPU asset views, physics, animation playback, audio and input handling are outside
this profile. Unknown or unsupported component types fail preparation or startup.

## Prerequisites

- Windows host, Visual Studio 2026 C++ tools (v145), CMake 4.2+ and Ninja.
- Activated external Emscripten SDK **6.0.9** and its `EMSDK` environment.
- A current native shared engine/modules SDK built from matching source revisions.
- Native `AssetToolCmd.exe`, `AssetPackToolCmd.exe`, their DLL dependencies and USD
  plugins, including `UsdTranslatorWrapper` and `usdGltf_plugin`.
- A matching host OpenUSD SDK and Python interpreter. The locally supported USD
  24.08 build uses Python 3.10; supply `-PythonExecutable` for a different matching
  interpreter. USD and its plugins remain on the host.

Follow the engine's OpenUSD guide and the modules tools guide to provision these
prerequisites. Locations are configurable; the helper does not install SDKs.

## Build and serve

From this project's directory, set paths for your machine:

```powershell
$env:NAU_ENGINE_SDK_DIR = 'C:/path/to/current/native-sdk'
$env:NAU_HOST_TOOLS_DIR = 'C:/path/to/native-tools/bin/Release'
$env:NAU_USD_SDK_DIR = 'C:/path/to/openusd/install'
. 'C:/path/to/emsdk/emsdk_env.ps1'
./web/build.ps1 -Configuration Debug
./web/build.ps1 -Configuration Release
python ./build/web-release/package/serve.py --port 8000 --open-browser
```

Run `run_web.bat [Debug|Release]` directly to build, cook, package and open the
browser. It activates EMSDK from its environment path or `%USERPROFILE%/emsdk`.
Without overrides, the helper discovers the sibling editor's
`dist/win_vs2026_x64_dll` SDK, `build/latest-release/bin/Release` host tools
(or the SDK's `bin`), and the engine's locally built OpenUSD install. It uses
Python 3.10 for both cooking and serving. These prerequisites must already be
installed/built; missing prerequisites produce an error with the checked paths.
The environment variables above and explicit `-HostSdk`, `-HostTools`, `-UsdSdk`
and `-PythonExecutable` parameters override discovery. For direct PowerShell
use, add `-Serve` and optionally `-Port 8000` to build and launch the server.

All new outputs are ignored under `build/`: native registration lives in
`web-host-components`, native preparation in `prepared-debug`/`prepared-release`,
and browser binaries/delivery in `web-debug`/`web-release`. Preparation uses a fresh
scratch copy of authored content on every invocation, so changed assets, metadata,
configuration or component definitions cannot reuse a stale package. It never
modifies authored content or consumes the editor's existing asset database.
Old scratch directories can be inspected and removed when no longer needed.

Serve the complete `package` directory over HTTP with COOP/COEP isolation headers.
It can be copied outside the checkout and served under a nested URL. There is no
source-tree, native SDK, loose-asset or browser USD fallback. Check
`Module.nauRuntime.status` in the browser console for Running, failure diagnostics
and completed cleanup; this milestone intentionally has no rendered output.

Runtime logs appear in the browser's developer console (F12, Console), not in
the batch file's server terminal. Enable Info, Warning and Error messages there.
The engine reports startup phases, Running, failures and completed cleanup even
when the loaded scene has no components that log. Component warnings/errors use
the matching console severity; each engine message appears once.

The profile starts with 128 MiB of WebAssembly memory and permits growth up to
512 MiB. CMake's `NAU_BROWSER_PROJECT_INITIAL_MEMORY` and
`NAU_BROWSER_PROJECT_MAXIMUM_MEMORY` configure those limits.

## Acceptance

```powershell
./web/build.ps1 -Configuration Debug -Acceptance
./web/build.ps1 -Configuration Release -Acceptance
python ./tests/verify_web_startup.py --configuration Debug
python ./tests/verify_web_startup.py --configuration Release
```

The browser test runner requires Playwright and installed Chrome. It relocates
deliveries outside the checkout, runs the real application and an independent
native-code scene observer, verifies authored component data and updates, injects
package failures and exercises repeated Stop. The observer has its own
`probe-package` delivery and is excluded from ordinary project builds. The extra
fixture is authored separately from the project's main scene.

`tests/verify_preparation.py` accepts `--python`, `--tools`, `--module`, `--sdk` and
`--usd-sdk` paths. It uses a disposable project under `build/` to check changed
authored values, rebuilt component definitions, missing references, failed
conversion and failed publication without accepting stale output.

Newly cooked components include portable type names because native and wasm32
component hashes differ. Recook older assets for browser delivery. Existing native
records without names retain their original hash-based lookup.
