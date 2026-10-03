# Compile the recorded CPU decoder boundary before adding its asset adapter.
get_filename_component(assetFormats "${engine}/engine/core/modules/asset_formats/src" ABSOLUTE)
add_library(NauDemoMeshDecoder STATIC
  "${assetFormats}/gltf/gltf_file.cpp"
  "${assetFormats}/gltf/gltf_mesh_accessor.cpp")
target_link_libraries(NauDemoMeshDecoder PUBLIC CoreAssets)
target_include_directories(NauDemoMeshDecoder PUBLIC "${assetFormats}")
target_precompile_headers(NauDemoMeshDecoder PRIVATE "${assetFormats}/pch.h")
nau_add_compile_options(NauDemoMeshDecoder)
