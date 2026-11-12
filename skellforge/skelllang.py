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
from .automation import SPEC, registry_specs

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
        elif op == "reserve":
            # Keep previously published host IDs, including retired nodes.
            if len(parts) != 5:
                raise SkellLangError(f"Line {line_no}: reserve expects id node kind default")
            _, pid, node_id, kind, value = parts
            if kind not in SPEC:
                raise SkellLangError(f"Line {line_no}: unknown reserved kind")
            item = SPEC[kind]
            if pid != f"fx_{node_id}_{item['field']}":
                raise SkellLangError(f"Line {line_no}: reserved parameter ID mismatch")
            scene.setdefault("parameter_registry", []).append({
                "id": pid, "node": node_id, "kind": kind,
                "field": item["field"], "minimum": item["minimum"],
                "maximum": item["maximum"], "step": item["step"],
                "default": _number(value, line_no, "default"),
            })
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


def format_source(scene: dict) -> str:
    """Export a Studio design deterministically; never lose unknown data."""
    from .automation import ParameterError
    try:
        validate_studio(scene)
        registry = registry_specs(scene)
    except (StudioError, ParameterError) as exc:
        raise SkellLangError(f"Invalid Studio document: {exc}") from exc
    if set(scene) - {"schema", "canvas", "components", "chain", "parameter_registry"}:
        raise SkellLangError("Unknown Studio fields would be lost")
    if set(scene["canvas"]) != {"width", "height"}:
        raise SkellLangError("Unknown canvas fields would be lost")
    lines = ["# Generated SkellLang design - stable IDs are preserved",
             "skell 1",
             f"canvas {scene['canvas']['width']} {scene['canvas']['height']}", ""]
    for node in scene["chain"]:
        expected = {"id", "type", "enabled"}
        if node["type"] != "gain":
            expected.add("drive" if node["type"] == "saturate" else "cutoff_hz")
        if set(node) != expected:
            raise SkellLangError(f"Unknown attributes on DSP node {node['id']}")
    for comp in scene["components"]:
        expected = {"id", "type", "x", "y", "w", "h"}
        if comp["type"] in ("text", "meter", "effect_knob"):
            expected.add("text")
        if comp["type"] == "effect_knob":
            expected.add("parameter_id")
        if set(comp) != expected:
            raise SkellLangError(f"Unknown attributes on UI {comp['id']}")
    for spec in registry:
        lines.append(f"reserve {spec['id']} {spec['node']} {spec['kind']} {spec['default']!r}")
    if registry:
        lines.append("")
    for node in scene["chain"][1:]:
        field = "drive" if node["type"] == "saturate" else "cutoff_hz"
        lines.append(f"fx {node['type']} {node['id']} {node[field]!r} "
                     + ("on" if node["enabled"] else "off"))
    if len(scene["chain"]) > 1:
        lines.append("")
    defaults = {c["id"]: c for c in default_studio()["components"]}
    for comp in scene["components"]:
        rect = " ".join(str(comp[k]) for k in ("x", "y", "w", "h"))
        if comp["id"] in defaults:
            if any(comp[k] != defaults[comp["id"]][k] for k in ("x", "y", "w", "h")):
                lines.append(f"move {comp['id']} {rect}")
            continue
        caption = shlex.quote(comp["text"])
        if comp["type"] == "effect_knob":
            bound = next((n for n in scene["chain"][1:] if comp["parameter_id"]
                          == f"fx_{n['id']}_" + ("drive" if n["type"] == "saturate"
                                                  else "cutoff_hz")), None)
            if bound is None:
                raise SkellLangError("Effect control refers to a missing processor")
            lines.append(f"knob {comp['id']} {bound['id']} {caption} {rect}")
        else:
            lines.append(f"{comp['type']} {comp['id']} {caption} {rect}")
    output = "\n".join(lines).rstrip() + "\n"
    recovered = compile_source(output)
    def canonical(document):
        copy = dict(document)
        if not copy.get("parameter_registry"):
            copy.pop("parameter_registry", None)
        return copy
    if canonical(recovered) != canonical(scene):
        raise SkellLangError("Round-trip changed the Studio document; export refused")
    return output


def export_from_studio(project: Path, destination: Path) -> Path:
    """Read saved Studio JSON and exclusively create its .skell source file."""
    from .studio import load_studio
    try:
        output_text = format_source(load_studio(Path(project)))
    except (OSError, StudioError) as exc:
        raise SkellLangError(f"Cannot read Studio design: {exc}") from exc
    output = Path(destination).expanduser()
    if output.suffix != ".skell":
        raise SkellLangError("Source files must use the .skell extension")
    if not output.parent.is_dir():
        raise SkellLangError("Destination folder does not exist")
    try:
        with output.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(output_text)
    except FileExistsError as exc:
        raise SkellLangError(f"Refusing to overwrite existing file: {output}") from exc
    return output
