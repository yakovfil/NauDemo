cmake_minimum_required(VERSION 3.24)

# Added to the engine build by cmake/attach_demo.cmake after its targets exist.
if(NOT TARGET SampleCommonLib)
    message(FATAL_ERROR "Configure the engine with -DCMAKE_PROJECT_NauEngine_INCLUDE=<NauDemo>/cmake/attach_demo.cmake. See README.md.")
endif()

add_executable(NauDemo src/main.cpp)
target_link_libraries(NauDemo PRIVATE SampleCommonLib Animation Physics Graphics VFX)
nau_target_link_modules(NauDemo PlatformApp Animation CoreScene CoreAssets GraphicsAssets
    DebugRenderer CoreAssetFormats CoreInput Graphics Physics PhysicsJolt VFX)
nau_add_compile_options(NauDemo)
file(TO_CMAKE_PATH "${CMAKE_CURRENT_SOURCE_DIR}" DEMO_SOURCE_PATH)
file(TO_CMAKE_PATH "${CMAKE_SOURCE_DIR}" ENGINE_SOURCE_PATH)
target_compile_definitions(NauDemo PRIVATE NAU_DEMO_DIR="${DEMO_SOURCE_PATH}" NAU_ENGINE_DIR="${ENGINE_SOURCE_PATH}")
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
