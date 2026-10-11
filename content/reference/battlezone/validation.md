# Original art integration validation

Validated on 2026-10-11 with the default Battlezone declaration.

## Source and extraction

- 42 populated object slots and 41 glyph-table entries extracted from the
  Battlezone rev-2 disassembly; two empty object slots preserved in the manifest.
- All 2,749 object table/geometry/draw-command bytes and every executed font
  instruction matched the original ROM files linked by the disassembly site.
- Four Python regression tests pass: signed short vectors and blank moves,
  call/return/jump and signed long vectors, invalid/looping commands, and
  original letter shapes/aliases plus runtime art coverage.
- Regenerating runtime geometry from the saved manifests is byte-identical.
- Runtime game JSON SHA-256:
  `a1765567185e9f01d5c00d02224c283bdafc6febfc17e6d465d97f28eaadf7c8`.
- Glyph contact sheet reviewed: all digits, letters, spaces and special symbols
  render with the original outlines and baseline/advance.

## Runtime

Windows and real Chrome, Debug and Release, build and pass the Battlezone
acceptance suite. The five gameplay unit tests also pass in native and Node
Debug/Release. The four deliveries use the same prepared archive SHA-256:

`9fbb77a9168709329bdc2865151237e3b9c070d33e0f6bc35aadad98068d84a8`

Coverage includes production screenshots, combat/score/restart, focus pause,
real audio output, resize/zero-size recovery, removed contributors, vector
capacity and graphics failures, missing/corrupt content, and repeated Stop.
The added missing-glyph case verifies that removing A from packaged geometry
fails startup and cleans up rather than drawing incomplete text. Native
packages are relocated outside the checkout; browser packages use nested URLs
with normal audio activation policy.

Production screenshots and result JSON files are under
`NauDemo/build/basic-rendering-scene/battlezone-<platform>-<configuration>/`.
The font preview capture is `NauDemo/build/battlezone-font.png`.

Representative commands from the parent checkout:

```powershell
python NauDemo/tests/test_battlezone_art.py
./NauDemo/build.ps1 -Platform Windows -Configuration Debug -Declaration D:/Programming/github/Nau/NauDemo/portable_rendering_project.json
cmake -S NauEngineLite -B NauDemo/build/basic-rendering-scene/windows-debug -DNAU_BROWSER_PROJECT_ACCEPTANCE=ON
cmake --build NauDemo/build/basic-rendering-scene/windows-debug --config Debug --target NauDemoMainPackage NauBattlezoneProbePackage NauBattlezoneTests --parallel 8
python NauDemo/tests/verify_battlezone.py --platform Windows --configuration Debug
```

Repeat for Release. For web, activate the installed Emscripten SDK, build with
`-Platform Web`, and use `NauBattlezoneProbeWebPackage` as the probe target;
run the verifier with `--platform Web`.

Tools: MSVC v145, CMake 4.2.1, Emscripten 6.0.9, Node 24.19.0, Python 3.14
for acceptance, Python 3.10/OpenUSD for native cooking, and installed Chrome
through Playwright. Existing Emscripten thread/memory-growth, engine literal
operator and Pillow deprecation warnings remain.

This is an art replacement within the existing compact game. It does not
implement the arcade's full enemy roster, original CRT intensity behavior,
2D projectile explosion program or original landscape/HUD drawing programs.
