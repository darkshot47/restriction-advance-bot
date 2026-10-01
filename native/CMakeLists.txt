cmake_minimum_required(VERSION 3.13)
project(restriction_engine CXX)

# The bot itself is Python; CMake is only here so the native engine can be
# compiled on hosts that prefer it (Windows/MSVC, IDEs, packaging pipelines).
# The Makefile next to this file is what native_engine.py calls by default.

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

add_library(restriction_engine SHARED restriction_engine.cpp)
target_include_directories(restriction_engine PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
set_target_properties(restriction_engine PROPERTIES
    OUTPUT_NAME "restriction_engine"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/build"
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/build")

find_package(Threads REQUIRED)
target_link_libraries(restriction_engine PRIVATE Threads::Threads)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(restriction_engine PRIVATE -O3 -Wall -Wextra)
endif()

add_executable(native_selftest tests/native_selftest.cpp restriction_engine.cpp)
target_include_directories(native_selftest PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(native_selftest PRIVATE Threads::Threads)

add_executable(native_bench tests/native_bench.cpp restriction_engine.cpp)
target_include_directories(native_bench PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(native_bench PRIVATE Threads::Threads)

add_test(NAME native_selftest COMMAND native_selftest)
