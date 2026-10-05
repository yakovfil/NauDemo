cmake_minimum_required(VERSION 3.24)
include(cmake/asset_packages.cmake)

if(EMSCRIPTEN AND NAU_RUNTIME_PROFILE STREQUAL "scene")
    add_executable(NauDemo src/main.cpp src/demo_application.cpp src/platform/web.cpp)
    target_link_libraries(NauDemo PRIVATE NauFrameworkScene NauBrowserRenderer PlatformAppApi NauScreenText)
    nau_target_link_modules(NauDemo PlatformApp CoreAssets CoreScene CoreAssetsCpu)
    nau_add_compile_options(NauDemo)
    set(assetArchive "${CMAKE_CURRENT_BINARY_DIR}/assets/NauDemo.nau_pack")
    nau_demo_package("${CMAKE_CURRENT_SOURCE_DIR}/cmake/web_assets.json.in" "${CMAKE_CURRENT_BINARY_DIR}/web_assets.json" "${assetArchive}")
    add_custom_target(NauDemoAssets DEPENDS "${assetArchive}")
    add_dependencies(NauDemo NauDemoAssets)
    target_link_options(NauDemo PRIVATE -sEXIT_RUNTIME=1 -sPTHREAD_POOL_SIZE=12
        -sINITIAL_MEMORY=67108864 -sALLOW_BLOCKING_ON_MAIN_THREAD=0
        -sOFFSCREENCANVAS_SUPPORT=1 "-sOFFSCREENCANVASES_TO_PTHREAD=#canvas"
        -sMIN_WEBGL_VERSION=2 -sMAX_WEBGL_VERSION=2
        "SHELL:--preload-file ${assetArchive}@/demo-package/NauDemo.nau_pack")
    set_property(TARGET NauDemo APPEND PROPERTY LINK_DEPENDS "${assetArchive}")
    add_custom_target(NauDemoWebPackage ALL
        COMMAND ${CMAKE_COMMAND}
            "-DBUILD_ROOT=${CMAKE_BINARY_DIR}"
            "-DDESTINATION=${CMAKE_BINARY_DIR}/package"
            "-DLOADER=$<TARGET_FILE:NauDemo>"
            "-DWASM=$<TARGET_FILE_DIR:NauDemo>/NauDemo.wasm"
            "-DDATA=$<TARGET_FILE_DIR:NauDemo>/NauDemo.data"
            "-DASSETS=${CMAKE_CURRENT_SOURCE_DIR}/web"
            "-DMESH_ASSETS=${CMAKE_CURRENT_SOURCE_DIR}/assets"
            "-DCONFIGURATION=$<CONFIG>"
            -P "${CMAKE_CURRENT_SOURCE_DIR}/web/stage.cmake"
        DEPENDS NauDemo VERBATIM)
    return()
endif()

# Added to the engine build by cmake/attach_demo.cmake after its targets exist.
if(NOT TARGET SampleCommonLib)
    message(FATAL_ERROR "Configure the engine with -DCMAKE_PROJECT_NauEngine_INCLUDE=<NauDemo>/cmake/attach_demo.cmake. See README.md.")
endif()

add_executable(NauDemo src/main.cpp src/demo_application.cpp src/platform/native.cpp)
target_link_libraries(NauDemo PRIVATE SampleCommonLib Animation Physics Graphics VFX NauScreenText)
nau_target_link_modules(NauDemo PlatformApp Animation CoreScene CoreAssets GraphicsAssets
    DebugRenderer CoreAssetFormats CoreInput Graphics Physics PhysicsJolt VFX)
nau_add_compile_options(NauDemo)
file(TO_CMAKE_PATH "${CMAKE_CURRENT_SOURCE_DIR}" DEMO_SOURCE_PATH)
file(TO_CMAKE_PATH "${CMAKE_SOURCE_DIR}" ENGINE_SOURCE_PATH)
file(TO_CMAKE_PATH "${NAU_SAMPLES_SOURCE_DIR}" SAMPLES_SOURCE_PATH)
set_target_properties(NauDemo PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/bin"
    VS_DEBUGGER_WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}")
set(shaderSource "${NAU_SAMPLES_SOURCE_DIR}/sceneBase/content/shaders")
set(SHADER_CACHE "${CMAKE_CURRENT_BINARY_DIR}/native-assets/$<CONFIG>/shader_cache.nsbc")
file(GLOB_RECURSE shaderInputs CONFIGURE_DEPENDS "${shaderSource}/src/*.hlsl" "${shaderSource}/include/*.hlsli" "${shaderSource}/meta/*.blk" "${NAU_MODULES_SOURCE_DIR}/modules/render/include/nau/shaders/*.hlsli")
add_custom_command(OUTPUT "${SHADER_CACHE}"
  COMMAND ${CMAKE_COMMAND} -E make_directory "${CMAKE_CURRENT_BINARY_DIR}/native-assets/$<CONFIG>"
  COMMAND $<TARGET_FILE:ShaderCompilerTool> -c shader_cache.nsbc -o "${CMAKE_CURRENT_BINARY_DIR}/native-assets/$<CONFIG>"
    -s "${shaderSource}/src" -m "${shaderSource}/meta" -i "${shaderSource}/include"
    -i "${NAU_MODULES_SOURCE_DIR}/modules/render/include/nau/shaders" $<$<CONFIG:Debug>:-De>
  DEPENDS ShaderCompilerTool ${shaderInputs} COMMAND_EXPAND_LISTS VERBATIM)
set(nativeArchive "${CMAKE_CURRENT_BINARY_DIR}/native-assets/$<CONFIG>/NauDemo.nau_pack")
nau_demo_package("${CMAKE_CURRENT_SOURCE_DIR}/cmake/native_assets.json.in" "${CMAKE_CURRENT_BINARY_DIR}/native-assets/$<CONFIG>/manifest.json" "${nativeArchive}")
set(requiredHeader "#pragma once\nnamespace nau::demo { inline constexpr const char* RequiredPackageEntries[] = {\n")
foreach(path IN LISTS NAU_DEMO_PACKAGED_PATHS)
  string(APPEND requiredHeader "\"${path}\",\n")
endforeach()
string(APPEND requiredHeader "}; }\n")
file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/generated/demo_asset_manifest.h" CONTENT "${requiredHeader}")
target_include_directories(NauDemo PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/generated")
add_custom_target(NauDemoAssets
  COMMAND ${CMAKE_COMMAND} -E make_directory "${CMAKE_CURRENT_SOURCE_DIR}/bin/$<CONFIG>"
  COMMAND ${CMAKE_COMMAND} -E copy_if_different "${nativeArchive}" "${CMAKE_CURRENT_SOURCE_DIR}/bin/$<CONFIG>/NauDemo.nau_pack"
  COMMAND ${CMAKE_COMMAND} -E copy_if_different "${CMAKE_CURRENT_SOURCE_DIR}/config/app.json" "${CMAKE_CURRENT_SOURCE_DIR}/bin/$<CONFIG>/app.json"
  DEPENDS "${nativeArchive}" "${CMAKE_CURRENT_SOURCE_DIR}/config/app.json" VERBATIM)
add_dependencies(NauDemo NauDemoAssets)
add_custom_command(TARGET NauDemo POST_BUILD
    COMMAND ${CMAKE_COMMAND}
        "-DENGINE_BIN=${CMAKE_BINARY_DIR}/bin/$<CONFIG>"
        "-DDEMO_BIN=$<TARGET_FILE_DIR:NauDemo>"
        -P "${CMAKE_CURRENT_SOURCE_DIR}/cmake/deploy_runtime.cmake"
    VERBATIM)
