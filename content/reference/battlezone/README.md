# Original Battlezone wireframe models

42 Wavefront OBJ files extracted from the original game's 44-entry object table.
Slots `22` and `23` are empty. The running NauDemo scene uses these original
models for its tank, radar dish, animated treads, obstacles, shells and debris.
Other object types remain available as reference exports.

Sources:

- [Object list and format](https://6502disassembly.com/va-battlezone/objects.html)
- [Battlezone rev-2 disassembly](https://6502disassembly.com/va-battlezone/Battlezone.html)
- [Original source and ROM files](https://github.com/historicalsource/battlezone)
- [ROM memory layout](https://6502disassembly.com/va-battlezone/bingen.html)

Game geometry is original Atari data (Battlezone, copyright 1980 Atari, Inc.),
not newly authored Nau geometry. Extraction does not assign it the repository's
license. Disassembly annotations and object descriptions are by Andy McFadden.

## Files and object inventory

Each filename starts with its original hexadecimal object index.
`models.json` lists all 44 slots, names, ROM addresses, raw signed coordinates,
converted coordinates, zero-based edges and points, original command bytes,
special commands, source URL and source HTML SHA-256.

`glyphs.json` contains all 41 original character-table entries: spaces, digits,
A–Z, dash, copyright and phonogram symbols. Each entry retains its ROM address,
executed AVG words, visible segments and final beam advance. `glyphs.svg` is a
contact sheet. The decoder follows VJSR/VRTS and VJMP shared routines, handles
signed short and long vectors, and omits blank beam movements from visible art.
All glyphs advance 24 units and return to the baseline; their nominal cell is
16 by 24 units. The ROM uses identical art for O/0 and S/5.

| Indices | Objects |
| --- | --- |
| 00, 01, 0c, 0f | Narrow pyramid, tall box, wide pyramid, short box |
| 02, 21 | Slow tank body, super tank |
| 03 | Cannon projectile |
| 04–07, 08–0b | Four rear and four front tread animation frames |
| 0d | Rotating radar dish |
| 0e | Projectile explosion anchor (see below) |
| 10–15 | Tank destruction pieces, including shared geometry aliases |
| 16 | Missile |
| 17, 1e, 1f | Three pre-tilted logo pieces: Ba, ttle, Zone |
| 18–1d | Missile destruction pieces, including shared geometry aliases |
| 20 | Saucer |
| 22, 23 | Empty slots; no OBJ files |
| 24–2b | Eight missile spatter frames, drawn as points |

The slow tank is assembled at runtime from its body, radar dish and one tread
frame selected according to view and animation. Its OBJ body alone is not that
complete animated assembly. Shared table entries are exported individually to
preserve the original index mapping. Mountains, moon, sights and HUD are not
members of this 3D object table.

## Format and coordinates

OBJ uses `v` vertices, `l` visible wire segments, and `p` points. There are no
invented faces, triangulation diagonals, normals or textures. Use an importer
that supports OBJ lines and points; a polygon-only importer may show nothing.
Drawing moves do not create edges. Original segment order and duplicate edges
are retained. Intensity commands are retained in JSON, not represented as OBJ
materials; runtime distance fading and logo/saucer brightness are not baked in.

The exported frame is right-handed: +X right, +Y up, -Z forward. Source units
are preserved, with no centering, grounding or per-object normalization. For
the three signed 16-bit words `(a, b, c)` stored in each ROM vertex:

```text
OBJ (x, y, z) = (-b / 2, c, -a / 2)
```

The stored order is depth, horizontal, vertical in the disassembly's rendering
conventions. Halving the two horizontal-plane coordinates compensates for the
math-box transform; negating the horizontal coordinate corrects the game's
screen mirror. Negating depth makes the OBJ frame right-handed. Logo pieces
retain their original common origin and pre-tilt. Raw data in JSON permits a
different axis convention without information loss.

Object `0e` contains one anchor and command 5, which invokes the screen-space
AVG explosion routine at `347a`. Its OBJ exports that anchor as a point, not a
fabricated 3D particle mesh. This effect needs a separate screen-space decoder
to reproduce it. Spatter objects `24–2b` are genuine 3D point sets.

## Reproduce and validate

From the checkout root:

```powershell
python NauDemo/tools/extract_battlezone_models.py
```

For an offline saved HTML listing or another output directory:

```powershell
python NauDemo/tools/extract_battlezone_models.py --source-html NauDemo/build/battlezone-extraction/Battlezone.html --output NauDemo/build/battlezone-models
```

To regenerate the runtime art in the packaged game JSON while preserving its
obstacle layout, add `--game-content NauDemo/content/game/battlezone.json`.
The runtime uses a uniform model scale of 1/200 and raises ground-based models
by the ROM ground offset of 320 units. Obstacle scaling still follows the
existing collision radii. The radar mounts at the body's original rear pivot;
the tread frame is selected by movement and whether the front or rear faces
the player. Text uses the original 16-by-24 cell and 24-unit advance. Since the
original font has no slash, control hints use spaces and the word OR.

Extraction validates signed vertex records, vertex count, command termination,
vertex references and the two empty slots. All 2,749 unique bytes used by the
tables, vertices and drawing commands were independently compared with the
eight original 2 KB ROM files in the linked historical source repository and
matched. OBJ output was read back to verify coordinates, edge and point indices.
Every executed glyph instruction also matched the original vector ROM bytes.
Run `python NauDemo/tests/test_battlezone_art.py` for decoder regression checks.
