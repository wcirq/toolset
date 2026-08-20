cmake_minimum_required(VERSION 3.25)

project(SSKJMFVirtualCamera VERSION 0.1.0 LANGUAGES CXX)

if(NOT WIN32)
    message(FATAL_ERROR "SSKJ MF Virtual Camera supports Windows only")
endif()
if(NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
    message(FATAL_ERROR "Only x64 builds are supported in the first milestone")
endif()

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_compile_definitions(
    UNICODE
    _UNICODE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
    WINVER=0x0A00
    _WIN32_WINNT=0x0A00
)

if(MSVC)
    add_compile_options(/W4 /permissive- /Zc:__cplusplus /utf-8)
endif()

add_subdirectory(native/protocol)
add_subdirectory(native/media_source)
add_subdirectory(native/registrar)
add_subdirectory(tools/frame_probe)

include(CTest)
if(BUILD_TESTING)
    add_subdirectory(tests/native)
endif()
