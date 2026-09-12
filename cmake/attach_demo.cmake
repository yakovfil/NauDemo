# CMAKE_PROJECT_NauEngine_INCLUDE hook: no engine source edits are needed.
set(NAU_DEMO_SOURCE_DIR "${CMAKE_CURRENT_LIST_DIR}/.." CACHE PATH "Rotating cube demo source")
cmake_language(DEFER CALL add_subdirectory "${NAU_DEMO_SOURCE_DIR}" "${CMAKE_BINARY_DIR}/nau_demo")
