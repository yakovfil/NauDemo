# NauDemo web package

This package is produced from the C++20 toolchain-standard-library engine and
demo sources. If source or package contents are rebuilt, rebuild the matching
engine/demo components together; do not mix packages from the pre-migration ABI.
EASTL and EABase are not runtime package dependencies.

Run `python serve.py --port 8000` and open the printed URL in Chrome.
Use Stop for orderly cleanup. Reload to retry after Stop or failure.

The package requires cross-origin isolation, WebGL 2 and OffscreenCanvas.
Scene rotation uses the elapsed time between presentation callbacks. The browser
material uses blue diffuse directional lighting and ambient light; native HDR,
shadows and the desktop renderer are outside this browser milestone.

NauDemo.data contains the mounted runtime copy of the listed configuration,
material, shaders and cube files. The loose originals are included for inspection;
editing them requires rebuilding the package to update the preload archive.
manifest.json records exact hashes. No SDK or source checkout is needed to serve.

`fonts/Abel-Regular.ttf` is the screen-text font, embedded in NauDemo.data and
mounted at `/demo/fonts/Abel-Regular.ttf`. Its license is `fonts/OFL-Abel.txt`.
Both loose files are required package inputs and have manifest hashes. The label
is drawn in the canvas at (24,24), size 24 CSS pixels, with DPR-aware coverage.
