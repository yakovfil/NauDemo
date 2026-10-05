# Nau Demo: Rotating Cube

The `Nau Demo` label uses the shared engine screen-text API and a bundled TTF on
native and web. See [screen text](doc/screen_text.md) for API and acceptance details.

## Toolchain and migration

NauDemo consumes the engine's C++20 toolchain-standard-library interfaces. The
migration is source/ABI breaking: rebuild the engine, shared sample support, and
NauDemo together in fresh Debug and Release build directories. Do not reuse a
pre-migration CMake cache or link this demo against old engine binaries. EASTL
and EABase are not required demo dependencies. Native and browser commands,
toolchain pins, and coordinated rebuild guidance are in the repository
[build guide](../build.md) and [prerequisites](../prerequisites.md).

## Browser build

The separate web profile runs the real rotating cube with a simplified blue
material in Chrome. On Windows, from `NauDemo/` run `run_web.bat` for Debug or
`run_web.bat Release` for Release. It activates SDK 6.0.9 if installed under
`%USERPROFILE%\emsdk`, builds the package, starts the local server, and opens
the browser. Press Ctrl+C to stop serving; answer Y if CMD prompts you.

For the manual steps, from `NauDemo/` after activating SDK 6.0.9:

```powershell
. "$HOME/emsdk/emsdk_env.ps1"
./web/build.ps1 -Configuration Debug
./web/build.ps1 -Configuration Release
python build/web-demo-debug/package/serve.py --port 8000
```

Open the printed URL. The canvas fills the viewport. To request cleanup from the
browser console, call `Module.nauRuntime.stop()`; reload to retry. Copy the entire
package to serve elsewhere. Browser updates follow the presentation callback;
rotation uses elapsed time rather than a fixed 100 ms step. See the
[complete browser guide](doc/naudemo_web.md) for prerequisites,
package inventory, tests, failure behavior and the fresh-checkout walkthrough.

## Native application

A native Nau Engine application showing a lit blue cube rotating around the
vertical **Y axis** at **45 degrees per second** (one revolution every eight
seconds). A fixed perspective camera and the engine's sample environment provide
a clear view of the motion. Close the window to exit.

![Native demo baseline before web integration](preview.png)

## Run

The Debug executable has been built in this checkout. From PowerShell:

```powershell
./run.ps1
```

You can also launch `bin/Debug/NauDemo.exe` directly. Keep its runtime DLLs,
`app.json` and `NauDemo.nau_pack` beside the executable. This delivery can be
copied outside the checkout and launched from any working directory. Windows
x64 and a DirectX 12 capable GPU are required.

## Rebuild the integrated target

Configure and build under the demo checkout so binaries and generated files remain here:

```powershell
./cmake/build_asset_packer.ps1
$env:VCPKG_ROOT = 'D:/Programming/vcpkg'
cmake --preset win_vs2026_x64 -S ../NauEngineLite -B build/native-text -DCMAKE_PROJECT_NauEngine_INCLUDE="$((Get-Location).Path)/cmake/attach_demo.cmake"
python build.py --config Debug
python build.py --config Release
```

`build.py` builds the generated NauDemo target and its dependencies together. It
rejects older caches that contain only SceneBaseSample rather than silently
linking a demo without its screen-text dependency.

## Build from engine sources with CMake

For a fresh checkout, follow the prerequisites in [the repository build guide](../build.md).
The supplied CMake hook adds the demo after the engine targets are defined,
using the engine's optional `NAU_DEMO_SOURCE_DIR` integration. From `NauDemo/`, in a configured development
shell with `VCPKG_ROOT`, Python, `cymbal`, and `clang` available:

```powershell
./cmake/build_asset_packer.ps1
$demoPath = (Get-Location).Path.Replace('\', '/')
Push-Location ../NauEngineLite
cmake --preset win_vs2026_x64 -B "$demoPath/build/engine" "-DCMAKE_PROJECT_NauEngine_INCLUDE=$demoPath/cmake/attach_demo.cmake"
cmake --build "$demoPath/build/engine" --config Debug --target NauDemo
Pop-Location
./run.ps1
```

This builds the engine dependencies and generates demo-owned shader caches
and the native archive under the selected demo build directory. The executable is still written to `NauDemo/bin/Debug/`, and runtime DLLs
are copied there automatically. Both configurations have passed native visual acceptance
with the external NauSamples integration.

## Files and customization

- `src/main.cpp`: common native/browser entry point using the engine-owned host.
- `src/demo_application.cpp`: shared scene startup, pre-update rotation/text, and post-update presentation dispatch.
- `src/platform/native.cpp`: native configuration, window and material/light/environment integration.
- `src/platform/web.cpp`: web package mounting, browser renderer integration and diagnostics.
- `src/demo_scene.h`: shared cube/camera construction and elapsed-time rotation.
  Change `radiansPerSecond` to adjust rotation speed or direction.
- `assets/cube.gltf` and `cube.bin`: a centered 2 × 2 × 2 cube with six hard-edged
  faces, normals, UVs, and tangents; no external modeling tool is needed.
- `assets/cube.nmat_json`: blue material using Nau's standard shader pipelines.
- `config/app.json`: native bootstrap/log configuration deployed beside the executable.
- `cmake/native_assets.json.in` and `cmake/web_assets.json.in`: explicit archive manifests.
- `build.py`, `CMakeLists.txt`, and `cmake/attach_demo.cmake`: the two build routes.

Logs are written to `%LOCALAPPDATA%/nau/NauDemo/logs/`. The engine's Debug renderer
currently emits DirectX 12 resource-initialization validation messages during
environment processing; these were observed during the visual check. If assets
are missing, verify the sibling engine checkout and its compiled
`../NauSamples/sceneBase/resources/shaders/cache/shader_cache.nsbc` before launching.

The material and application setup follow Nau's sample implementation. Nau's
license is retained in `NAU-LICENSE.txt`; engine assets and third-party components
retain their upstream licenses.

## Retired Cocos UI

The Cocos2d-backed `ui` module and its widget API, UiSampleApp, GUI editor, UI synchronization, and USD UI translation have been retired. Existing UI assets are unsupported; retained tools report this without converting or deleting them. Rebuild engine, modules, editor, samples, and installed SDK consumers together in fresh output directories. Old UI DLLs, headers, and SDK exports are incompatible.

Asset-backed single-line text remains available through `NauScreenText`; see `NauDemo/doc/screen_text.md`. ImGui diagnostic interfaces and the editor's Qt interface remain available.

## Engine asset packages

Both platforms mount an engine `NauDemo.nau_pack` through the portable kernel VFS
reader. Platform manifests share cube/font data; native includes its material,
environment, renderer textures/materials and generated shader cache, while web
includes browser GLSL and asset configuration. Source assets are required at
build time; runtime source-directory fallbacks are removed. Required missing or
invalid archives/entries cause diagnostic startup failure.

The host packer uses Visual Studio 2026/CMake 4.2 and builds separately in
`build/asset-pack-host`. Web/build.ps1 builds it before the Emscripten target.
For direct CMake builds, run cmake/build_asset_packer.ps1 first or pass
`-DNAU_ASSET_PACKER=<compatible native AssetPackToolCmd.exe>`. The browser link
does not consume this executable or desktop runtime libraries.

Web preloads only the engine archive into NauDemo.data. The generated raw
archive is in `build/web-demo-<configuration>/external/NauDemo/assets/`; loose
asset copies are not part of the staged delivery. Native generated content is
in the target build's `external/NauDemo/native-assets/<configuration>/` and the
archive is deployed beside the executable. Asset-only rebuilds update deployment.

Focused package tests and tool documentation are in
[AssetPackTool](../NauEngineModules/tools/asset_pack_tool/README.md), and the
[kernel API guide](../NauEngineLite/doc/asset_packages.md) describes limits and
ownership. Acceptance scripts read package contents directly and cover native
and browser relocation and package failures without production demo test hooks.
