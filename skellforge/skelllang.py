"""SkellLang 0.1: tiny, deterministic, declarative plugin design language.

Not a general-purpose programming language. No eval, imports, loops, Python
execution or audio-thread interpreter. Compiles to SkellForge Studio's validated
and backend-neutral JSON scene + DSP model. Generated VST3 still uses JUCE.
"""
from __future__ import annotations

import json
import os
import shlex
from pathlib import Path

from .studio import default_studio, validate_studio, StudioError

MAX_BYTES = 32768
MAX_LINES = 256
VERSION = "1"


class SkellLangError(ValueError):
    """Source text error with a meaningful line number."""


def _number(text: str, line: int, key: str) -> float:
    try:
        number = float(text)
    except (TypeError, ValueError) as exc:
        raise SkellLangError(f"Line {line}: invalid {key} value {text!r}") from exc
    import math
    if not math.isfinite(number):
        raise SkellLangError(f"Line {line}: {key} must be finite")
    return number


def _integer(text: str, line: int, key: str) -> int:
    if not text.isascii() or not text.isdecimal():
        raise SkellLangError(f"Line {line}: {key} requires an unsigned integer")
    return int(text)


def _bounds(tokens: list[str], line: int) -> dict:
    if len(tokens) != 4:
        raise SkellLangError(f"Line {line}: expected x y width height")
    return {name: _integer(value, line, name)
            for name, value in zip(("x", "y", "w", "h"), tokens)}


def compile_source(source: str) -> dict:
    """Return a new safe Studio document. Never touches a project or the disk."""
    if not isinstance(source, str):
        raise SkellLangError("SkellLang source must be text")
    if len(source.encode("utf-8")) > MAX_BYTES:
        raise SkellLangError("SkellLang source exceeds 32 KiB")
    lines = source.splitlines()
    if len(lines) > MAX_LINES:
        raise SkellLangError("SkellLang source exceeds 256 lines")
    scene = default_studio()
    declared = False
    canvas_seen = False
    objects = set(c["id"] for c in scene["components"])
    nodes = {"gain"}
    for line_no, raw in enumerate(lines, start=1):
        try:
            parts = shlex.split(raw, comments=True, posix=True)
        except ValueError as exc:
            raise SkellLangError(f"Line {line_no}: invalid quotes: {exc}") from exc
        if not parts:
            continue
        op = parts[0].lower()
        if not declared:
            if parts != ["skell", VERSION]:
                raise SkellLangError(f"Line {line_no}: first statement must be 'skell 1'")
            declared = True
            continue
        if op == "skell":
            raise SkellLangError(f"Line {line_no}: duplicate language version")
        if op == "canvas":
            if canvas_seen or len(parts) != 3:
                raise SkellLangError(f"Line {line_no}: canvas expects width height exactly once")
            scene["canvas"] = {
                "width": _integer(parts[1], line_no, "canvas width"),
                "height": _integer(parts[2], line_no, "canvas height"),
            }
            canvas_seen = True
        elif op == "fx":
            if len(parts) != 5 or parts[1] not in ("saturate", "lowpass"):
                raise SkellLangError(
                    f"Line {line_no}: fx expects 'saturate|lowpass id value on|off'")
            kind, name, amount, status = parts[1:]
            if name in nodes:
                raise SkellLangError(f"Line {line_no}: duplicate FX node id {name!r}")
            if status not in ("on", "off"):
                raise SkellLangError(f"Line {line_no}: FX status must be on or off")
            field = "drive" if kind == "saturate" else "cutoff_hz"
            scene["chain"].append({
                "id": name, "type": kind, "enabled": status == "on",
                field: _number(amount, line_no, field),
            })
            nodes.add(name)
        elif op == "move":
            if len(parts) != 6 or parts[1] not in (
                    "skull", "title", "gain_label", "gain_knob"):
                raise SkellLangError(
                    f"Line {line_no}: move expects a built-in control id plus x y w h")
            update = next(c for c in scene["components"] if c["id"] == parts[1])
            update.update(_bounds(parts[2:], line_no))
        elif op in ("text", "meter"):
            if len(parts) != 7:
                raise SkellLangError(
                    f"Line {line_no}: {op} expects id caption x y width height")
            _, name, caption, *geometry = parts
            if name in objects:
                raise SkellLangError(f"Line {line_no}: duplicate UI component id {name!r}")
            scene["components"].append({
                "id": name, "type": op, "text": caption,
                **_bounds(geometry, line_no),
            })
            objects.add(name)
        elif op == "knob":
            if len(parts) != 8:
                raise SkellLangError(
                    f"Line {line_no}: knob expects id fx_node caption x y width height")
            _, name, fx_node, caption, *geometry = parts
            if name in objects:
                raise SkellLangError(f"Line {line_no}: duplicate UI component id {name!r}")
            # Resolution occurs after parsing, so DSP nodes can be declared
            # before or after their visual controls.
            scene["components"].append({
                "id": name, "type": "effect_knob",
                "_source_node": fx_node, "text": caption,
                **_bounds(geometry, line_no),
            })
            objects.add(name)
        else:
            raise SkellLangError(f"Line {line_no}: unknown SkellLang statement {op!r}")
    if not declared:
        raise SkellLangError("No SkellLang version header; expected 'skell 1'")
    for component in scene["components"]:
        if component["type"] != "effect_knob":
            continue
        source_node = component.pop("_source_node")
        node = next((item for item in scene["chain"][1:]
                     if item["id"] == source_node), None)
        if node is None:
            raise SkellLangError(f"Knob {component['id']} references missing FX {source_node!r}")
        field = "drive" if node["type"] == "saturate" else "cutoff_hz"
        component["parameter_id"] = f"fx_{source_node}_{field}"
    try:
        validate_studio(scene)
    except StudioError as exc:
        raise SkellLangError(f"SkellLang scene validation failed: {exc}") from exc
    return scene


def compile_file(path: Path) -> dict:
    path = Path(path).expanduser()
    if path.is_symlink() or not path.is_file():
        raise SkellLangError("SkellLang source must be an existing regular file")
    if path.stat().st_size > MAX_BYTES:
        raise SkellLangError("SkellLang source exceeds 32 KiB")
    try:
        return compile_source(path.read_text(encoding="utf-8-sig"))
    except UnicodeDecodeError as exc:
        raise SkellLangError("SkellLang files must be UTF-8") from exc


def export_json(source: Path, destination: Path) -> Path:
    """Compile, validate, and CREATE a JSON file; never overwrite any path."""
    scene = compile_file(source)
    output = Path(destination).expanduser()
    if not output.parent.is_dir():
        raise SkellLangError("Destination parent folder does not exist")
    # Exclusive creation also refuses existing symlinks.
    try:
        with output.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(scene, handle, indent=2, ensure_ascii=True)
            handle.write("\n")
    except FileExistsError as exc:
        raise SkellLangError(f"Refusing to overwrite existing file: {output}") from exc
    except OSError as exc:
        raise SkellLangError(f"Cannot export SkellLang JSON: {exc}") from exc
    return output
