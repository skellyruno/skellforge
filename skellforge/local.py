"""Local-only SkellForge Windows VST3 build/verify/export pipeline.

No GitHub Actions. A first build may fetch JUCE/SkellCore if not cached
and local dependency paths are not provided. Never installs VST3 automatically.
"""
from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .forge import ForgeError, validate_project, package_project
from .studio import regenerate

LogCallback = Callable[[str], None]


def check_pe_x64(path: Path) -> None:
    """Validate essential PE32+ x64 header fields, NOT a Windows load test."""
    with path.open("rb") as source:
        head = source.read(64)
        if len(head) < 64 or head[:2] != b"MZ":
            raise ForgeError(f"Not a Windows PE executable: {path.name}")
        pe_offset = struct.unpack_from("<I", head, 0x3C)[0]
        if pe_offset < 64 or pe_offset > 1024 * 1024:
            raise ForgeError(f"Suspicious PE header offset: {path.name}")
        source.seek(pe_offset)
        pe = source.read(26)
        if len(pe) < 26 or pe[:4] != b"PE\x00\x00":
            raise ForgeError(f"Invalid PE signature: {path.name}")
        machine = struct.unpack_from("<H", pe, 4)[0]
        optional_magic = struct.unpack_from("<H", pe, 24)[0]
        if machine != 0x8664 or optional_magic != 0x20B:
            raise ForgeError(f"Not an x64 PE32+ VST3 binary: {path.name}")


def find_verified_vst3(project: Path) -> tuple[Path, Path]:
    data = validate_project(project)
    artefacts = project.resolve() / "build" / (data["target"] + "_artefacts")
    if not artefacts.is_dir():
        raise ForgeError(f"Plugin build output missing: {artefacts}")
    bundles = sorted(p for p in artefacts.rglob("*.vst3") if p.is_dir())
    if len(bundles) != 1:
        raise ForgeError(f"Expected one built VST3 bundle, found {len(bundles)}")
    bundle = bundles[0]
    if bundle.is_symlink() or any(p.is_symlink() for p in bundle.rglob("*")):
        raise ForgeError("VST3 build contains symlinks; refusing export")
    binaries = sorted(p for p in bundle.rglob("*.vst3") if p.is_file())
    if len(binaries) != 1:
        raise ForgeError(f"Expected exactly one VST3 binary, found {len(binaries)}")
    binary = binaries[0]
    check_pe_x64(binary)
    return bundle, binary


def _run_command(command: list[str], log: LogCallback, *, cwd: Path) -> None:
    log("EXEC: " + subprocess.list2cmdline(command))
    process = subprocess.Popen(command, cwd=str(cwd), shell=False, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, errors="replace",
                               bufsize=1)
    assert process.stdout is not None
    for line in process.stdout:
        log(line.rstrip("\r\n"))
    code = process.wait()
    if code != 0:
        raise ForgeError(f"Build tool failed (exit {code}): {command[0]}")


def build_and_export(project: Path, *, juce_path: Path | None = None,
                     core_path: Path | None = None, parallel: int = 2,
                     log: LogCallback | None = None) -> dict:
    """Execute entire local workflow, save durable history, return result.

    Verifies a native PE32+ binary but DOES NOT pretend to replace FL Studio
    tests, pluginval, audio regression fixtures, or actual performance profiling.
    """
    log = log or (lambda _: None)
    project = project.expanduser().resolve()
    if sys.platform != "win32":
        raise ForgeError("Local VST3 build requires Windows; visual editing works everywhere")
    if not isinstance(parallel, int) or isinstance(parallel, bool) or not 1 <= parallel <= 8:
        raise ForgeError("Build parallelism must be 1 to 8")
    if shutil.which("cmake") is None:
        raise ForgeError("CMake not found. Install it or select a valid Windows build environment")
    started = time.monotonic()
    history_dir = project / ".skellforge"
    history_dir.mkdir(exist_ok=True)
    record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "project": str(project), "status": "failed",
        "steps": [], "duration_seconds": 0.0,
    }
    try:
        data = validate_project(project)
        log("[1/5] Validating project and visual/DSP documents")
        if (project / "forge-studio.json").is_file():
            changed = regenerate(project)
            log("Generated code " + (", ".join(changed) if changed else "is current"))
        record["steps"].append("validate")
        cmake_args = ["cmake", "-S", str(project), "-B", str(project / "build"), "-A", "x64"]
        for name, path in (("JUCE_PATH", juce_path), ("SKELLCORE_PATH", core_path)):
            if path is None:
                continue
            path = path.expanduser().resolve()
            direct = path / "CMakeLists.txt"
            nested = path / "SkellCore" / "CMakeLists.txt"
            if not direct.is_file() and not (name == "SKELLCORE_PATH" and nested.is_file()):
                raise ForgeError(f"Invalid {name}: {path}")
            cmake_args.append(f"-D{name}={path}")
        log("[2/5] Configuring Windows x64 VST3 (local CMake)")
        _run_command(cmake_args, log, cwd=project)
        record["steps"].append("configure")
        log("[3/5] Compiling Release plugin locally")
        _run_command(["cmake", "--build", str(project / "build"), "--config", "Release",
                      "--parallel", str(parallel)], log, cwd=project)
        record["steps"].append("compile")
        log("[4/5] Verifying one real Windows x64 PE32+ VST3 binary")
        bundle, binary = find_verified_vst3(project)
        record["steps"].append("verify_pe")
        log(f"Verified: {binary} ({binary.stat().st_size:,} bytes)")
        log("[5/5] Exporting ZIP (no installation or overwrite)")
        dist = project / "dist"
        dist.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        output = dist / f"{data['target']}-Windows-VST3-{stamp}.zip"
        archive = package_project(project, output)
        record.update({
            "status": "success",
            "bundle": str(bundle), "binary": str(binary), "archive": str(archive),
        })
        record["steps"].append("export")
        log(f"SUCCESS: {archive}")
        return record
    except (ForgeError, OSError, subprocess.SubprocessError) as exc:
        record["error"] = str(exc)
        log(f"ERROR: {exc}")
        raise
    finally:
        record["duration_seconds"] = round(time.monotonic() - started, 3)
        with (history_dir / "history.jsonl").open("a", encoding="utf-8") as out:
            out.write(json.dumps(record, ensure_ascii=True) + "\n")


def read_history(project: Path, limit: int = 50) -> list[dict]:
    path = project / ".skellforge" / "history.jsonl"
    if not path.is_file():
        return []
    # Bound UI memory, even if a user has thousands of builds.
    lines = path.read_text(encoding="utf-8").splitlines()[-max(1, min(limit, 200)):]
    records = []
    for line in reversed(lines):
        try:
            records.append(json.loads(line))
        except ValueError:
            continue
    return records
