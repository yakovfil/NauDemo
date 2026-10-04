# Portable screen text

NauDemo draws `Nau Demo` through `NauScreenText`, a feature library in
NauEngineModules. Native Graphics consumes its immutable frame snapshot after
the scene; NauBrowserRenderer consumes the same snapshot before presentation.
The text is part of the rendered surface.

```cpp
auto& text = nau::getServiceProvider().get<nau::text::ScreenText>();
auto font = text.loadFont(filesystem, "/demo/fonts/Abel-Regular.ttf");
if (!font) return font.getError();
auto line = text.createText(*font, "Nau Demo", 24);
if (!line) return line.getError();
return text.draw(*line, {24, 24}, {1, 1, 1, 1});
```

Register the service with `addService<nau::text::ScreenText>()`. Font and line
handles own their bytes and coverage. Retain a prepared line and submit it every
frame; `draw` replaces the frame with one label, while `publish` accepts several
labels in a single replacement snapshot. Position and color do not rerasterize.
The render thread retains accepted snapshots until drawing finishes. Weak CPU
caches reclaim released handles; renderers evict textures absent from the latest
frame. Stop clears submissions and rejects new work. `whenPresented()` supplies
one startup task, settled by the renderer after its first accepted text draw.

Position is the upper-left of the font's ascent box. Size is the ascent-to-descent
pixel height. Native uses engine client pixels. Browser uses CSS pixels and
rasterizes at the drawable scale, refreshing coverage when DPR changes. Negative
bearings are preserved, and the viewport clips rectangles. Empty strings and
spaces produce no coverage; absent glyphs use the font's missing-glyph outline.

Supported input is a single UTF-8 line with TrueType outlines and pair kerning.
There is no shaping, bidi, wrapping, fallback, or rich text. Limits are 16 MiB
per font, 4096 codepoints, size up to 512, raster scale up to 8, dimensions up to
4096, 16 MiB per coverage image, and 128 live preparations/submitted labels.
Only project-controlled fonts are supported: envelope checks detect missing,
unsupported and truncated tables but do not harden stb against hostile glyph
structures.

The bundled Abel font is under the SIL Open Font License; source, hash and license
are in [the font assets](../assets/fonts/README.md). Browser staging copies both
the font and license, records their hashes, and embeds the runtime font in
NauDemo.data. Rebuild after changing font bytes. Build commands are in
[README](../README.md); outputs and acceptance artifacts remain in NauDemo/build.

## Acceptance

Build CPU fixtures with CMake from `tests/demo_scene` on Windows and Emscripten,
then run CTest. The `FontDerivedRenderReferences` case writes coverage references
into the build's fixtures directory. Browser acceptance uses the native fixture
references under `build/text-tests-native/fixtures` by default.

Build both browser configurations with `web/build.ps1 -Configuration Debug
-TestHooks` (and Release), then run `python web/test_text_acceptance.py`.
The fixtures compare actual canvas glyphs with font coverage, change text/size/
color/font metrics, change DPR, and exercise missing assets and upload failure.
Test hooks supply exact framebuffer readback before Chrome screenshot resampling.
Both browser configurations prove normal Stop settles.

For native acceptance configure `build/native-text` with
`-DNAU_DEMO_TEST_HOOKS=ON`, build Debug and Release, and run
`python tests/test_native_text.py`. Its private Graphics hook reads the actual
backbuffer on the render thread, so desktop occlusion cannot affect results.
The runner freezes the cube, compares glyphs against a blank-label baseline,
checks all pixels outside the glyph rectangle, resizes, clips, and closes normally.
Results distinguish existing renderer validation messages from text checks.

Diagnostic environment variables `NAU_DEMO_TEXT`, `NAU_DEMO_TEXT_FONT`,
`NAU_DEMO_TEXT_SIZE`, `NAU_DEMO_TEXT_X/Y`, and `NAU_DEMO_TEXT_R/G/B/A` override the
label inputs for acceptance. Normal runs use the documented defaults.
`NAU_DEMO_FREEZE` freezes rotation for image comparisons. Native readback exists
only in test-hook builds and writes to the requested `NAU_SCREEN_TEXT_CAPTURE`
path. Missing fonts fail initialization with the VFS asset path and a nonzero
native exit code; browser initialization reports Failed and completes cleanup.
