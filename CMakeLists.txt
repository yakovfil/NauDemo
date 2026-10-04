cmake_minimum_required(VERSION 3.24)

if(EMSCRIPTEN AND NAU_RUNTIME_PROFILE STREQUAL "scene")
    add_executable(NauDemo src/web_main.cpp)
    option(NAU_DEMO_TEST_HOOKS "Compile controlled pending-scene acceptance fixture" OFF)
    if(NAU_DEMO_TEST_HOOKS)
        target_compile_definitions(NauDemo PRIVATE NAU_DEMO_TEST_HOOKS=1)
        target_compile_definitions(NauBrowserRenderer PRIVATE NAU_TEXT_CAPTURE_TESTS=1)
    endif()
    target_link_libraries(NauDemo PRIVATE NauFrameworkScene NauBrowserRenderer PlatformAppApi NauScreenText)
    nau_target_link_modules(NauDemo PlatformApp CoreAssets CoreScene CoreAssetsCpu)
    nau_add_compile_options(NauDemo)
    set(packageAssets "${CMAKE_CURRENT_BINARY_DIR}/assets")
    file(MAKE_DIRECTORY "${packageAssets}")
    foreach(input IN ITEMS cube.gltf cube.bin)
        configure_file("${CMAKE_CURRENT_SOURCE_DIR}/assets/${input}" "${packageAssets}/${input}" COPYONLY)
    endforeach()
    file(MAKE_DIRECTORY "${packageAssets}/fonts")
    configure_file("${CMAKE_CURRENT_SOURCE_DIR}/assets/fonts/Abel-Regular.ttf" "${packageAssets}/fonts/Abel-Regular.ttf" COPYONLY)
    foreach(input IN ITEMS cube.vert cube.frag cube.web.json app.json)
        configure_file("${CMAKE_CURRENT_SOURCE_DIR}/web/${input}" "${packageAssets}/${input}" COPYONLY)
    endforeach()
    target_link_options(NauDemo PRIVATE -sEXIT_RUNTIME=1 -sPTHREAD_POOL_SIZE=12
        -sINITIAL_MEMORY=67108864 -sALLOW_BLOCKING_ON_MAIN_THREAD=0
        -sOFFSCREENCANVAS_SUPPORT=1 "-sOFFSCREENCANVASES_TO_PTHREAD=#canvas"
        -sMIN_WEBGL_VERSION=2 -sMAX_WEBGL_VERSION=2
        "SHELL:--preload-file ${packageAssets}@/demo-package")
    set_property(TARGET NauDemo APPEND PROPERTY LINK_DEPENDS
        "${packageAssets}/cube.gltf" "${packageAssets}/cube.bin"
        "${packageAssets}/cube.vert" "${packageAssets}/cube.frag"
        "${packageAssets}/cube.web.json" "${packageAssets}/app.json")
    set_property(TARGET NauDemo APPEND PROPERTY LINK_DEPENDS "${packageAssets}/fonts/Abel-Regular.ttf")
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

add_executable(NauDemo src/main.cpp)
option(NAU_DEMO_TEST_HOOKS "Compile controlled demo acceptance fixtures" OFF)
if(NAU_DEMO_TEST_HOOKS)
    target_compile_definitions(Graphics PRIVATE NAU_TEXT_CAPTURE_TESTS=1)
endif()
target_link_libraries(NauDemo PRIVATE SampleCommonLib Animation Physics Graphics VFX NauScreenText)
nau_target_link_modules(NauDemo PlatformApp Animation CoreScene CoreAssets GraphicsAssets
    DebugRenderer CoreAssetFormats CoreInput Graphics Physics PhysicsJolt VFX)
nau_add_compile_options(NauDemo)
file(TO_CMAKE_PATH "${CMAKE_CURRENT_SOURCE_DIR}" DEMO_SOURCE_PATH)
file(TO_CMAKE_PATH "${CMAKE_SOURCE_DIR}" ENGINE_SOURCE_PATH)
file(TO_CMAKE_PATH "${NAU_SAMPLES_SOURCE_DIR}" SAMPLES_SOURCE_PATH)
target_compile_definitions(NauDemo PRIVATE NAU_DEMO_DIR="${DEMO_SOURCE_PATH}" NAU_ENGINE_DIR="${ENGINE_SOURCE_PATH}" NAU_SAMPLES_DIR="${SAMPLES_SOURCE_PATH}")
set_target_properties(NauDemo PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/bin"
    VS_DEBUGGER_WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}")
# Compiles the shared rendering shader caches used by this demo.
add_dependencies(NauDemo SceneBaseSample)
add_custom_command(TARGET NauDemo POST_BUILD
    COMMAND ${CMAKE_COMMAND}
        "-DENGINE_BIN=${CMAKE_BINARY_DIR}/bin/$<CONFIG>"
        "-DDEMO_BIN=$<TARGET_FILE_DIR:NauDemo>"
        -P "${CMAKE_CURRENT_SOURCE_DIR}/cmake/deploy_runtime.cmake"
    VERBATIM)
