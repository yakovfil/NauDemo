# NauDemo web package

This package is produced from the C++20 toolchain-standard-library engine and
demo sources. If source or package contents are rebuilt, rebuild the matching
engine/demo components together; do not mix packages from the pre-migration ABI.
EASTL and EABase are not runtime package dependencies.

Run `python serve.py --port 8000` and open the printed URL in Chrome.
The demo canvas fills the browser viewport with no surrounding HTML controls.
Diagnostics appear in the browser console. For orderly cleanup from the console,
call `Module.nauRuntime.stop()`. Reload to restart after shutdown or failure.

The package requires cross-origin isolation, WebGL 2 and OffscreenCanvas.
Scene rotation uses the elapsed time between presentation callbacks. The browser
material uses blue diffuse directional lighting and ambient light; native HDR,
shadows and the desktop renderer are outside this browser milestone.

NauDemo.data transports a single engine NauDemo.nau_pack archive. The engine
mounts it through its portable read-only package filesystem. Mesh/buffer, browser
material/shaders, JSON configuration and the Abel TTF are archive entries.
Source content lives under `NauDemo/assets/`, including browser variants in
`materials/web/` and `config/web/`. The common manifest supplies the same mesh
and font inputs to both platforms.
Loose source assets are not included as runtime substitutes. Rebuild the delivery
after changing assets; manifest.json records exact delivery hashes.
No SDK or source checkout is needed to serve.

The font is mounted at `/demo/fonts/Abel-Regular.ttf`; its license is provided as
`fonts/OFL-Abel.txt` and also included in the archive. The label is drawn in the
canvas at (24,24), size 24 CSS pixels, with DPR-aware coverage. Missing or malformed
archive content reports diagnostic startup failure and requires reload after repair.

Building requires the supported Emscripten SDK and a native host compiler for the
isolated AssetPackToolCmd packaging build; neither the packer nor desktop runtime
libraries are linked into the browser runtime.
