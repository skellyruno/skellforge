cmake_minimum_required(VERSION 3.25)
project(SkellNativeGain VERSION 0.1.0 LANGUAGES C CXX)

if(NOT WIN32 OR NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
  message(FATAL_ERROR "SkellNative direct VST3 prototype targets Windows x64 only")
endif()

# Pin the MIT-licensed official Steinberg 3.8.1 SDK with its submodules.
# Existing local SDK source avoids network on subsequent builds.
set(SKELLNATIVE_STEINBERG_SDK "" CACHE PATH "Local complete VST3 SDK checkout")
set(SMTG_ENABLE_VSTGUI_SUPPORT OFF CACHE BOOL "" FORCE)
set(SMTG_ENABLE_VST3_PLUGIN_EXAMPLES OFF CACHE BOOL "" FORCE)
set(SMTG_ENABLE_VST3_HOSTING_EXAMPLES OFF CACHE BOOL "" FORCE)
set(SMTG_CREATE_PLUGIN_LINK OFF CACHE BOOL "" FORCE)

if(SKELLNATIVE_STEINBERG_SDK)
  if(NOT EXISTS "${SKELLNATIVE_STEINBERG_SDK}/CMakeLists.txt" OR
     NOT EXISTS "${SKELLNATIVE_STEINBERG_SDK}/public.sdk/CMakeLists.txt" OR
     NOT EXISTS "${SKELLNATIVE_STEINBERG_SDK}/pluginterfaces/CMakeLists.txt")
    message(FATAL_ERROR "SDK path must be a COMPLETE recursive VST3 SDK checkout")
  endif()
  set(SDK_ROOT "${SKELLNATIVE_STEINBERG_SDK}")
  add_subdirectory("${SDK_ROOT}" "${CMAKE_CURRENT_BINARY_DIR}/steinberg")
else()
  include(FetchContent)
  FetchContent_Declare(
    skell_steinberg_sdk
    GIT_REPOSITORY https://github.com/steinbergmedia/vst3sdk.git
    GIT_TAG 3cdf9ca5d1f5b1b21e0a86832aa4abe55607bd96
    GIT_SHALLOW FALSE
    GIT_SUBMODULES_RECURSE TRUE
  )
  FetchContent_MakeAvailable(skell_steinberg_sdk)
  set(SDK_ROOT "${skell_steinberg_sdk_SOURCE_DIR}")
endif()

add_library(SkellNativeDSP INTERFACE)
target_include_directories(SkellNativeDSP INTERFACE
  "${CMAKE_CURRENT_LIST_DIR}/../include")
target_compile_features(SkellNativeDSP INTERFACE cxx_std_17)

smtg_add_vst3plugin(SkellNativeGain
  Source/NativeGainProcessor.cpp
  Source/NativeGainController.cpp
  Source/NativeGainFactory.cpp
  Source/NativeGainIDs.h
  Source/NativeGainStateBridge.h
)
target_compile_features(SkellNativeGain PRIVATE cxx_std_17)
target_include_directories(SkellNativeGain PRIVATE "${CMAKE_CURRENT_LIST_DIR}/Source")
target_link_libraries(SkellNativeGain PRIVATE sdk SkellNativeDSP)

# Host validator and real FL Studio session tests are separate release gates.
