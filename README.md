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
`portable_rendering_project.json` and open a playable Battlezone-style scene:
green wireframe tanks and obstacles, a mountain/volcano/moon horizon, radar,
crosshair, score and lives on black. This reproduces the retro appearance with
simple combat rather than the original arcade simulation.
Both default to Debug. Close the native window to stop Windows; use Ctrl+C to
stop the browser server. Web activates Emscripten from `EMSDK` or
`%USERPROFILE%/emsdk`.

Use W/S to drive, A/D to turn, and Space or left-click to fire. Each new press
fires once when the cooldown permits. Destroy enemy tanks for 1000 points;
obstacles block movement and shots. You have three lives, with R to restart
after game over. Focus the browser scene to play. Gameplay pauses when focus
is lost, and firing/explosion effects activate through your first trusted
interaction. Both targets use the same packaged scene and shared game code.

The original animated mesh/billboard scene remains available:

```bat
run_windows.bat Debug original
run_web.bat Release original
```

Its declaration is `portable_original_project.json`. In that scene, move the
camera with WASD, use Q/E to move down/up, and hold the left mouse
button while dragging to look around. Click the browser scene to focus its
controls. Releasing the button ends camera rotation; changing focus clears held
controls. Windows and web use the same camera controller and sensitivity.

The demo plays a short click for each press of the left, middle or right mouse
button or W/A/S/D/Q/E. Holding a control or dragging plays one click for its
initial press. The sound comes from the shared scene archive. Browser output
activates on your first eligible interaction with the focused demo; that press
also plays its click. Focus loss discards pending feedback.

Build the original declaration with `-Acceptance`, then run `python tests/verify_audio.py Windows Debug`
and `python tests/verify_audio.py Web Debug` (also run Release). Native output
capture requires `soundcard` and `numpy`; browser checks use Playwright and
Chrome. Output evidence is written under
`build/basic-rendering-scene/audio-<platform>-<configuration>/`.

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

Build the default declaration, enable the observer and stage its package:

```powershell
./build.ps1 -Platform Windows -Configuration Debug -Declaration ./portable_rendering_project.json -Acceptance
cmake --build build/basic-rendering-scene/windows-debug --config Debug --target NauBattlezoneProbePackage
python ./tests/verify_battlezone.py --platform Windows --configuration Debug
```

For web, build with `./web/build.ps1` and stage `NauBattlezoneProbeWebPackage`.
Run the same verifier with `--platform Web`; repeat both targets in Release.
Evidence lives in `build/basic-rendering-scene/battlezone-<platform>-<configuration>/`.
The verifier separates production screenshots from scene-state observations
and checks combat, focus pause, restart, vector failures and actual audio output.
Its native screenshot checks require Orca; Python dependencies are Playwright,
Pillow, soundcard and NumPy. Visual references: [Battlezone](https://6502disassembly.com/va-battlezone/).

The battlefield tank, radar dish, tread animation, obstacles, shells and debris
use extracted original Battlezone geometry. HUD and control text use the original
vector glyphs. [Art provenance and regeneration](content/reference/battlezone/README.md)
describe the source data, coordinate conversion and extractor. The mountain
panorama, crosshair and radar display retain the demo's authored presentation.

Build the explicitly selected original declaration before running the existing
rendering, billboard, free-camera and click-feedback suites:

```powershell
python ./tests/verify_production_rendering.py Windows Debug
python ./tests/verify_production_rendering.py Web Debug
```

These checks inspect real scene output, motion and cleanup after copying the
package outside the checkout. See [web/README.md](web/README.md) for the observer,
archive, preparation and Debug/Release validation suites.
