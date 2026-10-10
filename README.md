# NauDemo

An editor-created scene project with shared Windows and browser rendering.
`NauDemo.nauproject`, authored `content/`, component sources and build scripts all
live in this repository root. Open `NauDemo.nauproject` in NauEditor to edit it.

## Build and run

From this directory:

```bat
run_windows.bat
run_windows.bat Release
run_web.bat
run_web.bat Release
```

The launchers build the `basic-rendering-scene` declaration in
`portable_rendering_project.json` and show the animated cube/tetrahedron scene.
Both default to Debug. Close the native window to stop Windows; use Ctrl+C to
stop the browser server. Web activates Emscripten from `EMSDK` or
`%USERPROFILE%/emsdk`.

Move the scene camera with WASD, use Q/E to move down/up, and hold the left mouse
button while dragging to look around. Click the browser scene to focus its
controls. Releasing the button ends camera rotation; changing focus clears held
controls. Windows and web use the same camera controller and sensitivity.

For build-only checks, with native host SDK/tools and OpenUSD provisioned:

```powershell
./build.ps1 -Platform Windows -Configuration Debug -Declaration ./portable_rendering_project.json
./web/build.ps1 -Configuration Debug -Declaration ./portable_rendering_project.json
```

Build outputs and cooked assets stay under `build/`. Always configure fresh
build directories after relocating the project; old CMake caches contain source
paths. Native host preparation requires a matching shared SDK, asset/pack tools,
OpenUSD 24.08 and Python 3.10; Windows uses VS 2026/v145 and CMake 4.2+, and web
adds Emscripten 6.0.9 and Ninja. Sibling engine/modules/editor checkouts supply the
local defaults. Environment variables and explicit overrides are described in
[the complete build and validation guide](web/README.md).

Direct builds without `-Declaration` retain the existing `portable_project.json`
non-rendering profile. The legacy SDK application remains available through
`CMakePresets.json`. The packaged application target is `NauDemoMain` on both
platforms; `source/portable_main.cpp` is its common entry point.

## Validate relocated deliveries

```powershell
python ./tests/verify_production_rendering.py Windows Debug
python ./tests/verify_production_rendering.py Web Debug
```

These checks inspect real scene output, motion and cleanup after copying the
package outside the checkout. See [web/README.md](web/README.md) for the observer,
archive, preparation and Debug/Release validation suites.
