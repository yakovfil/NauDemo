# NauDemo in Chrome

NauDemo uses real Nau scene objects, camera transforms and asset-loaded cube
geometry. Its separate `scene` profile includes CoreScene, CoreAssets,
CoreAssetsCpu, PlatformApp, NauScreenText, NauFrameworkScene and NauBrowserRenderer. It does not
build the desktop Graphics/Render, UI, VFX, physics or shader-tool graphs.

## Build and run

Keep NauDemo beside NauEngineLite in the parent Nau checkout. Initialize these
two required submodules (`git submodule update --init NauEngineLite NauDemo`).
Install SDK **6.0.9** explicitly as described in [Emscripten build guide](../../NauSamples/doc/emscripten_build.md).
Use CMake 3.25+, Ninja and Git; tested versions are CMake 4.2.1 and Ninja 1.13.2.
From NauDemo in PowerShell:

```powershell
. "$HOME/emsdk/emsdk_env.ps1"
../NauEngineLite/cmake/check_emscripten.ps1
./web/build.ps1 -Configuration Debug
./web/build.ps1 -Configuration Release
python build/web-demo-debug/package/serve.py --port 8000
```

Open the printed URL in Chrome. Use the Release package path for Release.
The server binds loopback and supplies COOP/COEP and the WebAssembly MIME type.
Serving needs Python 3.9+ and Chrome with WebGL 2, OffscreenCanvas, workers and
SharedArrayBuffer. A local `file:` URL cannot supply isolation. Use Stop to wait
for cleanup; reload after Stop or Failed to create a fresh canvas and runtime.

The browser material is blue opaque diffuse shading with directional and ambient
light. The native HDR environment and desktop material remain in the native
adapter. Rotation is 45 degrees per simulation second. The demo's cooperative
worker loop now steps and draws on each presentation callback using elapsed time,
so the browser controls the cadence. It permits Chrome to present OffscreenCanvas
frames without Asyncify. Existing minimal callers retain their original loop mode
and graph.

CSS canvas size and device pixel ratio determine drawable size, proportionally
clamped to reported graphics limits. Zero area pauses drawing. Context/host loss
is terminal and requires reload. A checked error reports its cause and cleanup
status; fatal aborts do not claim successful cleanup.

## Package

`NauDemo/build/web-demo-{debug,release}/package/` contains `NauDemo.js`, `.wasm`,
`.data`, `index.html`, `serve.py`, `README.md`, `fonts/OFL-Abel.txt` and a SHA-256
`manifest.json`. SDK 6.0.9 embeds its pthread worker in the loader.
`NauDemo.data` preloads one engine archive at `/demo-package/NauDemo.nau_pack`.
The portable Nau package filesystem mounts mesh/font/browser shader/configuration
entries through VFS at `/demo`. Loose source assets are not staged as substitutes.

The build also requires a host-native AssetPackToolCmd executable. Web/build.ps1
builds it in `NauDemo/build/asset-pack-host` using VS 2026/CMake 4.2 before invoking
the separate Emscripten build. Direct CMake users can pass `NAU_ASSET_PACKER`.
The packer has an isolated kernel-only dependency graph and is not linked into wasm.

Rebuild after editing source assets so the engine archive and preload transport
are updated. Staging replaces the exact inventory, rejects missing inputs and
retains the previous package if input validation fails. Missing archives, corrupt
indexes or absent required entries cause identified startup failure.

Copy the whole package anywhere and run its `serve.py`. For a nested URL:

```powershell
python serve.py --port 8000 --base-path /games/nau/
```

## Acceptance

Use Python with `playwright==1.63.0` and `Pillow==12.1.1`. The runner uses installed
Chrome, a disposable profile and Chrome's new headless mode; it validates actual
rendered PNGs. No Playwright browser download is required. From the parent Nau:

```powershell
python NauDemo/web/test_package.py --package NauDemo/build/web-demo-debug/package --output NauDemo/build/demo-check-debug
python NauDemo/web/test_package.py --package NauDemo/build/web-demo-release/package --output NauDemo/build/demo-check-release
python NauDemo/web/test_staging.py
```

The success case checks scene-derived matrices and nearest-face shading, blue
pixels, rotation, frame-driven foreground cadence, responsive page heartbeat, real
visibility changes, resize/DPR/zero-area/graphics-limit behavior, repeated Stop
and reload. `--scenario` also accepts `host-loss`, `context-loss`, `missing-buffer`,
`bad-shader`, `bad-link`, `bad-config`, `missing-canvas`, `no-context`, `missing-loader`, `missing-wasm`, `missing-data`,
`missing-headers`, `file-url`, and `no-offscreen`.
`blank-frame` and `runner-failure` deliberately return nonzero and write failed
structured results. Context and asset fault cases instrument served responses;
they do not edit the package or generated files.

The focused native/Node/Chrome scene suite is
`python NauDemo/tests/demo_scene/run.py` from the parent checkout,
with SDK setup active. Initialize the engine's googletest submodule first for
this suite. Native testing also requires VS 2026 C++ tools (v145) and CMake 4.2+.

## Fresh-checkout walkthrough

For uncommitted development, the helper creates fresh local Git checkouts and
applies a recorded patch bundle plus hashed untracked source files. It copies no
build cache, libraries or generated inputs. This records the actual working
source rather than misidentifying it as the base commit. From the parent Nau:

```powershell
. "$HOME/emsdk/emsdk_env.ps1"
python NauDemo/web/reproduce.py --destination C:/temp/nau-demo-fresh --sdk "$HOME/emsdk"
```

Choose a new destination outside the checkout. The helper clones Nau, NauEngineLite,
NauSamples and NauDemo, and records their base revisions, patch/file hashes,
SDK/tool identities and commands. It builds minimal and demo packages in Debug/Release,
checks minimal update/Stop and Chrome demo rendering/Stop at `/fresh/demo/`, and verifies that builds did not edit
tracked source. Evidence is in `NauDemo/build/demo-fresh-evidence/`.
It creates no commits and publishes nothing. After committing the changes,
ordinary remote clones at the recorded component revisions can use the build
commands above without a patch bundle.

Native coexistence commands remain in [NauDemo README](../../NauDemo/README.md).
The original web milestone's [validation record](../../openspec/changes/archive/2026-09-20-naudemo-web/validation.md)
retains its historical evidence. The [sample extraction validation](../../openspec/changes/archive/2026-09-20-extract-nau-samples/validation.md)
records the external sample layout and subsequent native visual acceptance.
