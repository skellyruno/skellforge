"""Generate a NEW experimental JUCE-free Gain project from SkellNative source.

The first native template intentionally supports Gain only; SkellLang v2 owns
the resulting two host parameter declarations. No migration of existing IDs.
"""
from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path

SOURCE = ("NativeGainProcessor.cpp", "NativeGainController.cpp",
          "NativeGainFactory.cpp", "NativeGainIDs.h", "NativeGainStateBridge.h",
          "SkellDrawWin32.cpp", "SkellDrawWin32.h")
SDK_PIN = "3cdf9ca5d1f5b1b21e0a86832aa4abe55607bd96"
LANG_PIN = "93871860d9d2b5b70ecfa6a9f5ddcd444e463431"

CMAKE = r'''cmake_minimum_required(VERSION 3.25)
project(@TARGET@ VERSION 0.1.0 LANGUAGES C CXX)
if(NOT WIN32 OR NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
  message(FATAL_ERROR "Experimental SkellNative VST3 requires Windows x64")
endif()
set(SKELLNATIVE_ROOT "" CACHE PATH "SkellNative source checkout")
if(NOT EXISTS "@@D@@{SKELLNATIVE_ROOT}/native/include/SkellNative/Dsp.h" OR
   NOT EXISTS "@@D@@{SKELLNATIVE_ROOT}/native/vst3/Source/ControlParameter.h" OR
   NOT EXISTS "@@D@@{SKELLNATIVE_ROOT}/native/skelldraw/include/SkellDraw/Win32Painter.h")
  message(FATAL_ERROR "Pass -DSKELLNATIVE_ROOT=... with the complete native checkout")
endif()
set(SKELLNATIVE_STEINBERG_SDK "" CACHE PATH "Local complete official VST3 SDK")
set(SKELLNATIVE_SKELLLANG_SOURCE "" CACHE PATH "Local SkellLang compiler checkout")
set(SMTG_ENABLE_VSTGUI_SUPPORT OFF CACHE BOOL "" FORCE)
set(SMTG_ENABLE_VST3_PLUGIN_EXAMPLES OFF CACHE BOOL "" FORCE)
set(SMTG_ENABLE_VST3_HOSTING_EXAMPLES ON CACHE BOOL "" FORCE)
set(SMTG_CREATE_PLUGIN_LINK OFF CACHE BOOL "" FORCE)
include(FetchContent)
if(SKELLNATIVE_STEINBERG_SDK)
  foreach(required IN ITEMS CMakeLists.txt public.sdk/source/vst/vstaudioeffect.h
      pluginterfaces/vst/ivstaudioprocessor.h base/source/fobject.h
      cmake/modules/SMTG_AddVST3Library.cmake)
    if(NOT EXISTS "@@D@@{SKELLNATIVE_STEINBERG_SDK}/@@D@@{required}")
      message(FATAL_ERROR "Steinberg SDK must be complete (recursive): missing @@D@@{required}")
    endif()
  endforeach()
  add_subdirectory("@@D@@{SKELLNATIVE_STEINBERG_SDK}" "@@D@@{CMAKE_BINARY_DIR}/steinberg")
else()
  FetchContent_Declare(skell_steinberg_sdk
    GIT_REPOSITORY https://github.com/steinbergmedia/vst3sdk.git
    GIT_TAG @SDK_PIN@ GIT_SHALLOW FALSE GIT_SUBMODULES_RECURSE TRUE)
  FetchContent_MakeAvailable(skell_steinberg_sdk)
endif()
find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
if(SKELLNATIVE_SKELLLANG_SOURCE)
  if(NOT EXISTS "@@D@@{SKELLNATIVE_SKELLLANG_SOURCE}/skelllang/native_controls.py")
    message(FATAL_ERROR "Invalid SkellLang compiler checkout")
  endif()
  set(FETCHCONTENT_SOURCE_DIR_SKELLLANG_COMPILER "@@D@@{SKELLNATIVE_SKELLLANG_SOURCE}")
endif()
FetchContent_Declare(skelllang_compiler
  GIT_REPOSITORY https://github.com/skellyruno/skellLang.git
  GIT_TAG @LANG_PIN@ SOURCE_SUBDIR compiler-only)
FetchContent_MakeAvailable(skelllang_compiler)
set(GAIN_CONTROLS "@@D@@{CMAKE_CURRENT_BINARY_DIR}/GainControls.inc")
add_custom_command(OUTPUT "@@D@@{GAIN_CONTROLS}"
  COMMAND "@@D@@{Python3_EXECUTABLE}" -B -m skelllang.native_controls
    "@@D@@{CMAKE_CURRENT_LIST_DIR}/Gain.skell" "@@D@@{GAIN_CONTROLS}"
  WORKING_DIRECTORY "@@D@@{skelllang_compiler_SOURCE_DIR}"
  DEPENDS "@@D@@{CMAKE_CURRENT_LIST_DIR}/Gain.skell"
          "@@D@@{skelllang_compiler_SOURCE_DIR}/skelllang/native_controls.py"
  VERBATIM)
set(SMTG_RUN_VST_VALIDATOR OFF)
smtg_add_vst3plugin(@TARGET@ PACKAGE_NAME "@NAME@"
  Source/NativeGainProcessor.cpp Source/NativeGainController.cpp
  Source/NativeGainFactory.cpp Source/NativeGainIDs.h
  Source/NativeGainStateBridge.h Source/SkellDrawWin32.cpp
  Source/SkellDrawWin32.h "@@D@@{GAIN_CONTROLS}")
target_compile_features(@TARGET@ PRIVATE cxx_std_17)
target_include_directories(@TARGET@ PRIVATE
  "@@D@@{CMAKE_CURRENT_LIST_DIR}/Source" "@@D@@{CMAKE_CURRENT_BINARY_DIR}"
  "@@D@@{SKELLNATIVE_ROOT}/native/include"
  "@@D@@{SKELLNATIVE_ROOT}/native/vst3/Source"
  "@@D@@{SKELLNATIVE_ROOT}/native/skelldraw/include")
target_link_libraries(@TARGET@ PRIVATE sdk user32 gdi32)
add_custom_command(TARGET @TARGET@ POST_BUILD
  COMMAND "@@D@@{Python3_EXECUTABLE}" "@@D@@{CMAKE_CURRENT_LIST_DIR}/tools/normalize_moduleinfo.py"
    "@@D@@{CMAKE_BINARY_DIR}" "@NAME@" "@PROCESSOR@" "@CONTROLLER@"
  VERBATIM)
add_dependencies(@TARGET@ validator)
enable_testing()
add_test(NAME @TARGET@_SteinbergValidator COMMAND $<TARGET_FILE:validator>
  "@@D@@{CMAKE_BINARY_DIR}/VST3/$<CONFIG>/@NAME@.vst3")
'''

NORMALIZE = r'''"""Fail closed on wrong plugin IDs; repair only JSON trailing commas."""
import json
import sys
from pathlib import Path

def strip_commas(text):
    result = []
    quoted = escaped = False
    for i, char in enumerate(text):
        if quoted:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
            result.append(char)
        elif char == "," and text[i+1:].lstrip()[:1] in ("}", "]"):
            continue
        else:
            result.append(char)
    return "".join(result)

def normalize(folder, name, processor, controller):
    matches = [x for x in folder.rglob(name + ".vst3") if x.is_dir()]
    if len(matches) != 1:
        raise ValueError("Expected exactly one VST3 bundle")
    metadata = matches[0] / "Contents" / "Resources" / "moduleinfo.json"
    source = metadata.read_text(encoding="utf-8")
    try:
        data = json.loads(source)
    except json.JSONDecodeError:
        data = json.loads(strip_commas(source))
    classes = data.get("Classes", [])
    if not isinstance(classes, list) or len(classes) != 2:
        raise ValueError("Expected exactly two factory classes")
    ids = {str(c.get("CID", "")).upper() for c in classes}
    categories = {c.get("Category") for c in classes}
    if data.get("Name") != name or data.get("Version") != "0.1.0" or (
        ids != {processor.upper(), controller.upper()} or categories !=
        {"Audio Module Class", "Component Controller Class"}
    ):
        raise ValueError("Unexpected product or factory class IDs")
    strict = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if strict != source:
        metadata.write_text(strict, encoding="utf-8", newline="\n")
    if json.loads(metadata.read_text(encoding="utf-8")) != data:
        raise ValueError("Metadata round-trip failed")

if __name__ == "__main__":
    if len(sys.argv) != 5:
        sys.exit("Usage: normalize_moduleinfo BUILD PRODUCT PROCESSOR CONTROLLER")
    normalize(Path(sys.argv[1]).resolve(), *sys.argv[2:])
'''


def _substitute_once(text: str, old: str, new: str) -> str:
    from .forge import ForgeError
    if text.count(old) != 1:
        raise ForgeError("Unsupported or modified SkellNative source: expected unique marker")
    return text.replace(old, new)


def _uid(bundle: str, code: str, kind: str) -> str:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"https://skellyr.uno/{bundle}/{code}/{kind}").hex.upper()


def _declared_uid(value: str) -> str:
    return ", ".join("0x" + value[n:n+8] for n in (0, 8, 16, 24))


def create_native_project(name: str, destination: Path, code: str, sdk: Path) -> Path:
    from .forge import ForgeError, identity, known_code_owner
    details = identity(name, code)
    owner = known_code_owner(code)
    if owner:
        raise ForgeError(f"Plugin code {code} reserved by {owner}")
    root = sdk.expanduser().resolve(strict=True)
    source = root / "native/vst3/Source"
    for item in SOURCE:
        if not (source / item).is_file() or (source / item).is_symlink():
            raise ForgeError(f"Missing SkellNative source template: {item}")
    for item in ("native/include/SkellNative/Dsp.h", "native/vst3/Source/ControlParameter.h",
                 "native/skelldraw/include/SkellDraw/Win32Painter.h"):
        if not (root / item).is_file():
            raise ForgeError(f"Incomplete SkellNative SDK: {item}")
    requested = destination.expanduser().absolute()
    # Resolve Windows 8.3 paths and junction aliases before verifying the
    # containment boundary. Compare the canonical SDK and destination paths;
    # otherwise an alias such as RUNNER~1 can bypass the no-write-inside-SDK rule.
    if requested.exists() or requested.is_symlink():
        raise ForgeError(f"Will not overwrite existing project: {requested}")
    dest = requested.resolve(strict=False)
    if dest.exists() or dest.is_symlink():
        raise ForgeError(f"Will not overwrite existing project: {dest}")
    if not dest.parent.is_dir() or dest == root or root in dest.parents:
        raise ForgeError("Destination must have an existing parent outside SkellNative")

    processor = _uid(details["bundle"], code, "processor")
    controller = _uid(details["bundle"], code, "controller")
    ids = (source / "NativeGainIDs.h").read_text(encoding="utf-8")
    for field, value in (("kProcessorUID", processor), ("kControllerUID", controller)):
        pattern = r"static DECLARE_UID\(" + field + r", [^\n]*\);"
        replacement = "static DECLARE_UID(" + field + ", " + _declared_uid(value) + ");"
        ids, count = re.subn(pattern, replacement, ids)
        if count != 1:
            raise ForgeError("SkellNative UID marker missing; do not silently regenerate identities")
    ids = _substitute_once(ids, '"skellnative.gain.prototype"', json.dumps(details["bundle"]))

    factory = (source / "NativeGainFactory.cpp").read_text(encoding="utf-8")
    factory = _substitute_once(factory, '"SkellNative Gain Prototype"', json.dumps(name))
    factory = _substitute_once(factory, '"SkellNative Gain Controller"', json.dumps(name + " Controller"))
    ctrl = (source / "NativeGainController.cpp").read_text(encoding="utf-8")
    ctrl = _substitute_once(ctrl, '#include "SkellDrawWin32.h"',
                            '#include "SkellDrawWin32.h"\n#include "ControlParameter.h"')
    ctrl = _substitute_once(ctrl, "using namespace Steinberg::Vst;",
        'using namespace Steinberg::Vst;\n'
        'using skellnative::sdk::NativeControl;\n'
        'using skellnative::sdk::NativeControlFlags;\n'
        'using skellnative::vst3::ControlParameter;\n'
        '#include "GainControls.inc"\n'
        'static_assert(controlCount == 2, "Expected gain and output meter");\n'
        'static_assert(controls[0].id == kGainParam && controls[1].id == kOutputPeakParam,\n'
        '              "Changing IDs breaks host automation");')
    ctrl = _substitute_once(ctrl, 'parameters.addParameter(STR16("Gain"), nullptr, 0, 0.5,\n'
                            '                                ParameterInfo::kCanAutomate, kGainParam);',
                            'parameters.addParameter(new ControlParameter(controls[0]));')
    ctrl = _substitute_once(ctrl, 'parameters.addParameter(STR16("Output Peak"), nullptr, 0, 0.0,\n'
                            '                                ParameterInfo::kIsReadOnly, kOutputPeakParam);',
                            'parameters.addParameter(new ControlParameter(controls[1]));')
    cmake = CMAKE.replace("@@D@@", "$")
    for a, b in (("@TARGET@", details["target"]), ("@NAME@", name),
                 ("@SDK_PIN@", SDK_PIN), ("@LANG_PIN@", LANG_PIN),
                 ("@PROCESSOR@", processor), ("@CONTROLLER@", controller)):
        cmake = cmake.replace(a, b)
    files = {
        "CMakeLists.txt": cmake,
        "Gain.skell": ('skell-native 2\n'
                       'parameter gain 1000 "Gain" 0 2 1 1 0 "x" automate\n'
                       'parameter peak 1001 "Output Peak" 0 1 0 1 0 "" readonly\n'),
        "tools/normalize_moduleinfo.py": NORMALIZE,
        "Source/NativeGainIDs.h": ids,
        "Source/NativeGainFactory.cpp": factory,
        "Source/NativeGainController.cpp": ctrl,
    }
    for item in SOURCE:
        path = "Source/" + item
        if path not in files:
            files[path] = (source / item).read_text(encoding="utf-8")
    files["skellnative.json"] = json.dumps({
        "schema": "skellforge/native-gain/1", "status": "experimental",
        "name": name, "target": details["target"], "plugin_code": code,
        "bundle_id": details["bundle"], "processor_cid": processor,
        "controller_cid": controller, "state_product_key": details["bundle"],
        "parameter_ids": [1000, 1001], "steinberg_sdk_commit": SDK_PIN,
        "skelllang_commit": LANG_PIN,
    }, indent=2) + "\n"
    files["README.md"] = (
        "# " + name + " — SkellNative experimental Gain VST3\n\n"
        "Direct Steinberg SDK, original SkellDraw Win32 GUI and SkellLang-generated "
        "gain/meter controls; no JUCE or VSTGUI. Experimental gain template only, "
        "not a general DSP-graph compiler or shipping release.\n\n"
        "Windows: cmake -S . -B build -A x64 -DSKELLNATIVE_ROOT=C:/src/skellnative\n"
        "Then: cmake --build build --config Release --parallel 2\n"
        "Then: ctest --test-dir build -C Release --output-on-failure\n\n"
        "Optional complete local checkouts: SKELLNATIVE_STEINBERG_SDK and "
        "SKELLNATIVE_SKELLLANG_SOURCE. Test in FL Studio before release.\n")
    try:
        dest.mkdir(exist_ok=False)
        for rel, text in sorted(files.items()):
            output = dest / rel
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(text, encoding="utf-8", newline="\n")
    except BaseException:
        shutil.rmtree(dest)
        raise
    return dest
