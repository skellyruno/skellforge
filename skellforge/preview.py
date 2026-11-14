"""Build and capture a generated plugin's ACTUAL JUCE editor on Windows.

This is distinct from the fast Tk schematic design canvas. It links the same
C++ processor and editor as the VST3, then uses SkellCore::UIRenderer to save
real screenshots at three tested resolutions.
"""
from __future__ import annotations

import json
import shutil
import struct
import zlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .forge import ForgeError, validate_project
from .local import _run_command
from .studio import regenerate

SCENES = {"compact": (390, 260), "default": (440, 310), "large": (900, 600)}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _verify_png_pixels(image: Path, width: int, height: int) -> None:
    """Validate complete native JUCE PNGs, including CRC and decoded pixels.

    This deliberately accepts JUCE's 8-bit, non-interlaced RGB/RGBA output.
    It is not a general-purpose PNG decoder or a visual design-quality test.
    """
    payload = image.read_bytes()
    if not (64 <= len(payload) <= 16 * 1024 * 1024) or not payload.startswith(PNG_SIGNATURE):
        raise ForgeError("Corrupt PNG signature or file size")
    position = len(PNG_SIGNATURE)
    seen_header = seen_pixels = seen_end = False
    idat_finished = False
    compressed = bytearray()
    channels = None
    while position < len(payload):
        if len(payload) - position < 12:
            raise ForgeError("Corrupt PNG: truncated chunk header")
        length = struct.unpack_from(">I", payload, position)[0]
        stop = position + 12 + length
        if stop > len(payload):
            raise ForgeError("Corrupt PNG: truncated chunk payload")
        chunk_type = payload[position + 4:position + 8]
        data = payload[position + 8:stop - 4]
        supplied_crc = struct.unpack_from(">I", payload, stop - 4)[0]
        if (zlib.crc32(chunk_type + data) & 0xffffffff) != supplied_crc:
            raise ForgeError("Corrupt PNG: chunk CRC mismatch")
        if not seen_header:
            if chunk_type != b"IHDR" or length != 13:
                raise ForgeError("Corrupt PNG: missing IHDR")
            seen_header = True
            actual_width, actual_height, depth, color, compression, filtering, interlace = (
                struct.unpack(">IIBBBBB", data))
            if (actual_width, actual_height) != (width, height):
                raise ForgeError("PNG image size mismatch")
            if (depth != 8 or color not in (2, 6) or compression != 0
                    or filtering != 0 or interlace != 0):
                raise ForgeError("Unsupported real-editor PNG encoding")
            channels = 3 if color == 2 else 4
        elif chunk_type == b"IHDR":
            raise ForgeError("Corrupt PNG: duplicate IHDR")
        elif chunk_type == b"IDAT":
            if idat_finished or length == 0:
                raise ForgeError("Corrupt PNG: invalid or reordered IDAT")
            seen_pixels = True
            compressed.extend(data)
        elif chunk_type == b"IEND":
            if length or not seen_pixels or stop != len(payload):
                raise ForgeError("Corrupt PNG: invalid IEND")
            seen_end = True
            break
        elif chunk_type[0] & 0x20 == 0:
            # Only true-color IHDR/IDAT/IEND critical chunks are supported.
            # Ancillary metadata such as JUCE's sBIT is permitted.
            raise ForgeError("Corrupt PNG: unexpected critical chunk")
        if seen_pixels and chunk_type != b"IDAT":
            idat_finished = True
        position = stop
    if not seen_end:
        raise ForgeError("Corrupt PNG: missing IEND")
    stride = 1 + width * channels
    expected = height * stride
    try:
        inflater = zlib.decompressobj()
        pixels = inflater.decompress(bytes(compressed), expected + 1)
    except zlib.error as exc:
        raise ForgeError("Corrupt PNG: invalid IDAT compression") from exc
    if (len(pixels) != expected or not inflater.eof or inflater.unused_data
            or inflater.unconsumed_tail):
        raise ForgeError("Corrupt PNG: incomplete or oversized pixel stream")
    if any(pixels[i] > 4 for i in range(0, expected, stride)):
        raise ForgeError("Corrupt PNG: invalid scanline filter")


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
    # Validate all identities before sizes, so duplicate screenshots cannot be
    # masked by a confusing dimensions error from a different scene.
    seen = set()
    for item in scenes:
        if not isinstance(item, dict):
            raise ForgeError("Malformed real-editor screenshot metadata")
        name = item.get("file")
        if not isinstance(name, str) or not name.endswith(".png"):
            raise ForgeError("Invalid real-editor PNG filename")
        if name != Path(name).name or "\\" in name or "/" in name:
            raise ForgeError("Unsafe real-editor screenshot path")
        scene = name[:-4]
        if scene not in SCENES or scene in seen:
            raise ForgeError("Duplicate/unrecognized real-editor scene")
        seen.add(scene)
    results = {}
    for item in scenes:
        name = item["file"]
        scene = name[:-4]
        width, height = SCENES[scene]
        if item.get("width") != width or item.get("height") != height:
            raise ForgeError("Real-editor scene metadata dimensions mismatch")
        image = folder / name
        if not image.is_file() or image.is_symlink() or image.stat().st_size < 1024:
            raise ForgeError(f"Missing, linked or empty UI screenshot: {name}")
        _verify_png_pixels(image, width, height)
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
