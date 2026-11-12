"""Build and capture a generated plugin's ACTUAL JUCE editor on Windows.

This is distinct from the fast Tk schematic design canvas. It links the same
C++ processor and editor as the VST3, then uses SkellCore::UIRenderer to save
real screenshots at three tested resolutions.
"""
from __future__ import annotations

import json
import shutil
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .forge import ForgeError, validate_project
from .local import _run_command
from .studio import regenerate

SCENES = {"compact": (390, 260), "default": (440, 310), "large": (900, 600)}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def verify_preview_outputs(folder: Path) -> dict:
    """Validate screenshot manifest, file paths, PNG headers and exact sizes."""
    manifest = folder / "manifest.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ForgeError(f"Actual JUCE editor did not produce a valid manifest: {exc}") from exc
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or data.get("count") != len(SCENES):
        raise ForgeError("Real-editor capture count is incomplete")
    if len(scenes) != len(SCENES):
        raise ForgeError("Unexpected number of real-editor captures")
    results = {}
    for item in scenes:
        if not isinstance(item, dict):
            raise ForgeError("Malformed real-editor screenshot metadata")
        name = item.get("file")
        if not isinstance(name, str) or not name.endswith(".png"):
            raise ForgeError("Invalid real-editor PNG filename")
        if name != Path(name).name or "\\" in name or "/" in name:
            raise ForgeError("Unsafe real-editor screenshot path")
        scene = name[:-4]
        if scene not in SCENES or scene in results:
            raise ForgeError("Duplicate/unrecognized real-editor scene")
        width, height = SCENES[scene]
        if item.get("width") != width or item.get("height") != height:
            raise ForgeError("Real-editor scene metadata dimensions mismatch")
        image = folder / name
        if not image.is_file() or image.is_symlink() or image.stat().st_size < 1024:
            raise ForgeError(f"Missing, linked or empty UI screenshot: {name}")
        with image.open("rb") as stream:
            header = stream.read(24)
        if len(header) < 24 or header[:8] != PNG_SIGNATURE or header[12:16] != b"IHDR":
            raise ForgeError(f"Corrupt PNG signature in {name}")
        png_width, png_height = struct.unpack(">II", header[16:24])
        if (png_width, png_height) != (width, height):
            raise ForgeError(f"PNG image size mismatch in {name}")
        results[scene] = str(image.resolve())
    if set(results) != set(SCENES):
        raise ForgeError("Required real-editor scenes were not all captured")
    return {
        "preview_folder": str(folder.resolve()),
        "scenes": results,
        "type": "real-juce-editor",
        "sizes": {key: list(dim) for key, dim in SCENES.items()},
    }


def render_real_preview(
    project: Path, *,
    juce_path: Path | None = None,
    core_path: Path | None = None,
    log: Callable[[str], None] | None = None,
) -> dict:
    """Compile an opt-in native JUCE preview executable and validate PNGs."""
    log = log or (lambda _: None)
    if sys.platform != "win32":
        raise ForgeError("Real JUCE preview build requires Windows with a GUI session")
    if shutil.which("cmake") is None:
        raise ForgeError("CMake not found; install CMake and Visual Studio C++ tools")
    project = project.expanduser().resolve()
    validate_project(project)
    changed = regenerate(project)
    log("Generated headers: " + (", ".join(changed) if changed else "already current"))
    build = project / "build"
    command = [
        "cmake", "-S", str(project), "-B", str(build), "-A", "x64",
        "-DSKELLFORGE_BUILD_UI_PREVIEW=ON",
    ]
    for key, location in (("JUCE_PATH", juce_path), ("SKELLCORE_PATH", core_path)):
        if location is None:
            continue
        location = location.expanduser().resolve()
        valid = (location / "CMakeLists.txt").is_file()
        if key == "SKELLCORE_PATH":
            valid = valid or (location / "SkellCore" / "CMakeLists.txt").is_file()
        if not valid:
            raise ForgeError(f"Invalid {key}: {location}")
        command.append(f"-D{key}={location}")
    log("Configuring preview tool using the real generated plugin sources")
    _run_command(command, log, cwd=project)
    log("Building SkellForgeUiPreview.exe (not rebuilding the VST3)")
    _run_command(
        ["cmake", "--build", str(build), "--target", "SkellForgeUiPreview",
         "--config", "Release", "--parallel", "2"],
        log, cwd=project,
    )
    executables = sorted(p for p in build.rglob("SkellForgeUiPreview.exe") if p.is_file())
    if len(executables) != 1:
        raise ForgeError(
            f"Expected one SkellForgeUiPreview.exe; found {len(executables)}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    output = project / ".skellforge" / "ui-preview" / stamp
    if output.exists():
        raise ForgeError("Refusing to overwrite existing screenshots")
    output.parent.mkdir(parents=True, exist_ok=True)
    log("Capturing compact, default, and large native JUCE editor screenshots")
    _run_command([str(executables[0]), str(output)], log, cwd=project)
    result = verify_preview_outputs(output)
    log("Preview verified: " + str(output))
    return result
