# NauDemo browser dependency boundary

The implemented profile is recorded in [naudemo_sources.json](../cmake/naudemo_sources.json)
and selected by NauDemoRuntime.cmake. It builds real scene/assets and the small
application-worker WebGL 2 renderer. [naudemo_web.md](naudemo_web.md) contains
build/acceptance commands and the remaining native visual-check limitation.

The kernel uses the minimal source manifest without extra translation units.
The initially considered stream_utils.cpp and nau_container.cpp were not required
by the verified link and are identified as unused candidates in the inventory.
The active browser dependency boundary is the toolchain C++20 standard library plus tiny-utf8, fmt, utfcpp, ModifiedSonyMath, jsoncpp, wyhash, fast_float and tinyimageformat. EASTL and EABase are not active browser dependencies. Nau adapters preserve the selected allocation, ownership and container contracts without reintroducing a parallel standard-library dependency. Focused tests add googletest.

Static modules are PlatformApp, CoreAssets, CoreScene and CoreAssetsCpu.
CoreAssets includes paths/references, descriptors, reloadable views, the file
content provider, asset manager and database registration. CoreScene retains
real scene/object/component ownership, factory/manager and camera state. Shared
component declarations such as skinned mesh and environment do not enable their
excluded rendering/animation backends.

CoreAssetsCpu reuses asset_formats/src/gltf/gltf_file.cpp and gltf_mesh_accessor.cpp
through the existing IMeshAssetAccessor contract. Its narrow loader validates
indices, supported primitive/attribute formats, lengths, offsets, binary presence,
finite positions/normals and triangle indices before exposing an owned CpuMeshView.
It rejects unsupported required data. A read-only filesystem mounts the preloaded
cube through Nau VFS; the unsupported browser native-file contract is unchanged.

NauBrowserRenderer exists only in the browser demo graph. It uploads the asset
view and consumes scene world/camera matrices. NauDemo's checked application
service owns it through initialization, post-scene drawing and shutdown. An
optional cooperative mode in the shared browser runtime permits OffscreenCanvas
presentation without Asyncify; minimal callers keep their original mode.

The graph audit verifies exact module/renderer sources, dependency allowlists,
missing-source diagnostics, SDK pinning and unchanged existing preset objects.
It rejects Graphics, GraphicsAssets, Render/DX12, full CoreAssetFormats, Animation,
physics, UI, VFX and desktop tools in the web graph. Native/minimal graphs do not
include NauBrowserRenderer. Runtime tests separately verify ownership, checked
errors and rendering; an inventory alone is not runtime evidence.
