"""SkellForge v0.1 -- generate, validate, build and package Windows VST3 projects.

Python standard library only. No host/network access for generation or validation.
JUCE and SkellCore are resolved by the generated CMake build, pinned by revision.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from . import __version__
from .audit import audit_project, find_string_literals, strip_cmake_comments

MIN_PYTHON = (3, 10)  # Path.write_text(newline=...) needs 3.10
PARAMETER_SCAN_LIMIT = 2000
ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
KNOWN_CODES = ROOT / "config" / "known_codes.json"
CORE_REPO = "https://github.com/skellyruno/skellcore-vst-template.git"
CORE_REV = "268cf6ba43e2a7fbb7e7b39bd3855663e00089f2"

# 2-80 characters, and no trailing space (Windows strips it from the .vst3 file name).
NAME_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9 _-]{0,78}[A-Za-z0-9_-]\Z")
# The product name becomes "<name>.vst3"; Windows cannot create these file names.
WINDOWS_RESERVED_NAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{n}" for n in range(1, 10)} | {f"lpt{n}" for n in range(1, 10)})
CODE_PATTERN = re.compile(r"[A-Za-z0-9]{4}\Z")
SHA_PATTERN = re.compile(r"[a-fA-F0-9]{40}\Z")
REPO_PATTERN = re.compile(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\.git\Z")
REQUIRED = (
    "CMakeLists.txt",
    "Source/PluginProcessor.h",
    "Source/PluginProcessor.cpp",
    "Source/PluginEditor.h",
    "Source/PluginEditor.cpp",
    ".github/workflows/build.yml",
    "README.md",
    "skellforge.json",
    "skellworld.json",
)


class ForgeError(Exception):
    """Actionable validation error; never silently fix identifiers."""


def identity(name: str, code: str, core_rev: str = CORE_REV,
             core_repo: str = CORE_REPO) -> dict[str, str]:
    if not NAME_PATTERN.fullmatch(name):
        raise ForgeError("Product name: 2-80 ASCII letters, digits, spaces, underscores or hyphens; "
                         "start with a letter and do not end with a space")
    if name.casefold() in WINDOWS_RESERVED_NAMES:
        raise ForgeError(f"Product name {name!r} is a reserved Windows file name; choose another")
    if not CODE_PATTERN.fullmatch(code):
        raise ForgeError("Plugin code must be exactly four ASCII letters/digits")
    if not SHA_PATTERN.fullmatch(core_rev):
        raise ForgeError("SkellCore revision must be a full immutable 40-character Git commit SHA")
    if not REPO_PATTERN.fullmatch(core_repo):
        raise ForgeError("SkellCore repository must be an https://github.com/owner/repo.git URL")
    words = re.findall(r"[A-Za-z0-9]+", name)
    target = "".join(word[0].upper() + word[1:] for word in words)
    slug = "".join(char for char in name.lower() if char.isascii() and char.isalnum())
    if len(slug) > 50 or not slug:
        raise ForgeError("Product name is too long to form a stable SkellWorld ID")
    return {
        "name": name,
        "target": target,
        "slug": slug,
        "code": code,
        "bundle": f"audio.skell.{slug}",
        "world_id": f"skell.{slug}",
        "core_rev": core_rev.lower(),
        "core_repo": core_repo,
    }


def known_code_owner(code: str) -> str | None:
    database = json.loads(KNOWN_CODES.read_text(encoding="utf-8"))
    return next((owner for used, owner in database["codes"].items()
                 if used.casefold() == code.casefold()), None)


def render_template(source: str, data: dict[str, str]) -> str:
    substitutions = {
        "@@NAME@@": data["name"],
        "@@TARGET@@": data["target"],
        "@@SLUG@@": data["slug"],
        "@@CODE@@": data["code"],
        "@@BUNDLE@@": data["bundle"],
        "@@WORLD_ID@@": data["world_id"],
        "@@CORE_REV@@": data["core_rev"],
        "@@CORE_REPO@@": data["core_repo"],
    }
    for key, value in substitutions.items():
        source = source.replace(key, value)
    if re.search(r"@@[A-Z_]+@@", source):
        raise ForgeError("Unresolved token in a project template")
    return source


def create_project(name: str, destination: Path, code: str,
                   core_rev: str = CORE_REV, core_repo: str = CORE_REPO) -> Path:
    info = identity(name, code, core_rev, core_repo)
    collision = known_code_owner(code)
    if collision:
        raise ForgeError(f"Plugin code {code} is already used by {collision}. Choose a unique ID.")
    destination = destination.expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise ForgeError(f"Will not overwrite existing path: {destination}")
    if not destination.parent.is_dir():
        raise ForgeError(f"Destination parent directory does not exist: {destination.parent}")
    # mkdir(exist_ok=False) prevents accidental replacement of a checked-out project.
    destination.mkdir(exist_ok=False)
    try:
        paths = list(TEMPLATES.rglob("*.in"))
        if not paths:
            raise ForgeError("SkellForge template directory is missing")
        for source_path in sorted(paths):
            relative = source_path.relative_to(TEMPLATES)
            target = destination / str(relative)[:-3]
            target.parent.mkdir(parents=True, exist_ok=True)
            content = render_template(source_path.read_text(encoding="utf-8"), info)
            target.write_text(content, encoding="utf-8", newline="\n")
        manifest = {
            "schema": "skellforge/plugin/1",
            "generator_version": __version__,
            "name": info["name"],
            "target": info["target"],
            "plugin_code": info["code"],
            "manufacturer_code": "SkAu",
            "bundle_id": info["bundle"],
            "formats": ["VST3"],
            "platforms": ["Windows"],
            "core_repo": info["core_repo"],
            "core_revision": info["core_rev"],
            "parameter_ids": ["gain_db"],
        }
        world = {
            "schema": "skellworld-plugin/1",
            "product_id": info["world_id"],
            "name": info["name"],
            "manufacturer": "Skell Audio",
            "plugin_code": info["code"],
            "bundle_id": info["bundle"],
            "connection": "not-enabled",
            "capabilities": [],
        }
        for filename, content in (("skellforge.json", manifest), ("skellworld.json", world)):
            (destination / filename).write_text(json.dumps(content, indent=2) + "\n",
                                                encoding="utf-8", newline="\n")
        validate_project(destination)
    except BaseException:
        shutil.rmtree(destination)
        raise
    return destination


def _load_manifest(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError, RecursionError) as exc:  # RecursionError: absurdly nested JSON
        raise ForgeError(f"Invalid project manifest: {exc}") from exc
    if not isinstance(value, dict):
        raise ForgeError(f"Invalid project manifest: {path.name} must contain a JSON object")
    return value


def validate_project(project: Path) -> dict:
    project = project.expanduser().resolve()
    if not project.is_dir():
        raise ForgeError(f"Project directory not found: {project}")
    for path in REQUIRED:
        if not (project / path).is_file():
            raise ForgeError(f"Required project file missing: {path}")
    data = _load_manifest(project / "skellforge.json")
    world = _load_manifest(project / "skellworld.json")
    if data.get("schema") != "skellforge/plugin/1":
        raise ForgeError("Unsupported SkellForge manifest schema")
    for key in ("name", "plugin_code", "core_revision", "core_repo"):
        if not isinstance(data.get(key, ""), str):
            raise ForgeError(f"Invalid skellforge.json: {key} must be a text value")
    parameter_ids = data.get("parameter_ids", [])
    if not isinstance(parameter_ids, list) or not all(isinstance(i, str) for i in parameter_ids):
        raise ForgeError("Invalid skellforge.json: parameter_ids must be a list of text values")
    info = identity(data.get("name", ""), data.get("plugin_code", ""),
                    data.get("core_revision", ""), data.get("core_repo", ""))
    for key, expected in (("target", info["target"]), ("bundle_id", info["bundle"]),
                          ("manufacturer_code", "SkAu"), ("formats", ["VST3"]),
                          ("platforms", ["Windows"])):
        if data.get(key) != expected:
            raise ForgeError(f"Identity mismatch in skellforge.json: {key}")
    # Commented-out lines must not satisfy an identity check.
    cmake = strip_cmake_comments((project / "CMakeLists.txt").read_text(encoding="utf-8"))
    end = r"(?![A-Za-z0-9_])"  # whole-token match: "Sf01" must not accept "Sf01x"
    for expected, pattern in (
            (f"PLUGIN_CODE {info['code']}",
             r"(?<![A-Za-z0-9_])PLUGIN_CODE\s+" + re.escape(info["code"]) + end),
            (f'BUNDLE_ID "{info["bundle"]}"',
             r"(?<![A-Za-z0-9_])BUNDLE_ID\s+\"" + re.escape(info["bundle"]) + r"\""),
            (f"juce_add_plugin({info['target']}",
             r"\bjuce_add_plugin\s*\(\s*" + re.escape(info["target"]) + end),
            (f"GIT_REPOSITORY {info['core_repo']}",
             r"\bGIT_REPOSITORY\s+\"?" + re.escape(info["core_repo"]) + r"\"?(?=[\s)])"),
            (f"GIT_TAG {info['core_rev']}",
             r"\bGIT_TAG\s+" + re.escape(info["core_rev"]) + end)):
        if not re.search(pattern, cmake):
            raise ForgeError(f"CMake identity or dependency pin mismatch: {expected}")
    if not re.search(r"\bFORMATS\s+VST3\b", cmake) or re.search(r"\bStandalone\b", cmake):
        raise ForgeError("Only the Windows VST3 format is permitted in this starter")
    if world.get("plugin_code") != info["code"] or world.get("bundle_id") != info["bundle"] \
            or world.get("product_id") != info["world_id"]:
        raise ForgeError("SkellWorld manifest identity disagrees with SkellForge")
    if parameter_ids:
        # Parameter IDs are what saved projects and host automation bind to. Deliberately
        # conservative: an ID counts as present if its exact "string" appears anywhere in the
        # project's code (constants, other folders and .inl files all work), so only an ID that
        # has vanished from every source file is an error. An incomplete scan proves nothing.
        scan = find_string_literals(project, parameter_ids, limit=PARAMETER_SCAN_LIMIT)
        missing = sorted(set(parameter_ids) - scan["found"])
        if missing and scan["complete"]:
            raise ForgeError(
                f"Parameter ID(s) listed in skellforge.json no longer appear in any source file: "
                f"{', '.join(missing)}. Renaming or removing a parameter ID breaks saved projects "
                "and host automation; restore it (or, only for a never-released plugin, "
                "update parameter_ids in the manifest).")
    return data


def build_project(project: Path, juce_path: Path | None = None,
                  core_path: Path | None = None, parallel: int = 2) -> None:
    validate_project(project)
    if sys.platform != "win32":
        raise ForgeError("Windows VST3 build requires Windows; generate/validate works cross-platform")
    if shutil.which("cmake") is None:
        raise ForgeError("CMake is not installed or is missing from PATH")
    project = project.resolve()
    output = project / "build"
    cmd = ["cmake", "-S", str(project), "-B", str(output), "-A", "x64"]
    # The generated CMakeLists.txt accepts a SkellCore repo root (SkellCore/CMakeLists.txt)
    # or the library folder itself; check exactly what CMake will accept.
    for option, path, layouts in (("JUCE_PATH", juce_path, ("CMakeLists.txt",)),
                                  ("SKELLCORE_PATH", core_path,
                                   ("SkellCore/CMakeLists.txt", "CMakeLists.txt"))):
        if path is not None:
            path = path.expanduser().resolve()
            if not any((path / layout).is_file() for layout in layouts):
                raise ForgeError(f"{option} does not contain {' or '.join(layouts)}: {path}")
            cmd.append(f"-D{option}={path}")
    subprocess.run(cmd, check=True)
    subprocess.run(["cmake", "--build", str(output), "--config", "Release",
                    "--parallel", str(parallel)], check=True)


def package_project(project: Path, output: Path | None = None) -> Path:
    data = validate_project(project)
    project = project.resolve()
    artefacts = project / "build" / (data["target"] + "_artefacts")
    if not artefacts.is_dir():
        raise ForgeError(f"No build artefacts found: {artefacts}")
    # Multi-config generators write <target>_artefacts/<Config>/VST3; the build command
    # makes Release, so a stale Debug bundle must not block packaging.
    search_root = artefacts / "Release"
    if not search_root.is_dir():
        search_root = artefacts
    bundles = sorted(p for p in search_root.rglob("*.vst3") if p.is_dir())
    if len(bundles) != 1:
        raise ForgeError(f"Expected exactly one VST3 bundle, found {len(bundles)}")
    bundle = bundles[0]
    if not any(p.is_file() and p.suffix.lower() == ".vst3" for p in bundle.rglob("*")):
        raise ForgeError("VST3 bundle contains no VST3 binary")
    output = (output or (project / f"SkellForge-{data['target']}-Windows-VST3.zip")).expanduser().absolute()
    if output.exists():
        raise ForgeError(f"Will not overwrite existing package: {output}")
    if not output.parent.is_dir():
        raise ForgeError(f"Package destination parent directory missing: {output.parent}")
    created = False
    try:
        with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            created = True
            for file in sorted(bundle.rglob("*")):
                if file.is_file():
                    arcname = (Path(bundle.name) / file.relative_to(bundle)).as_posix()
                    archive.write(file, arcname=arcname)
        with zipfile.ZipFile(output, "r") as archive:
            if archive.testzip() is not None:
                raise ForgeError("Packaged ZIP failed integrity verification")
    except BaseException:
        if created:  # never leave a partial package, and never delete a file we did not create
            try:
                output.unlink(missing_ok=True)
            except OSError:
                pass  # e.g. a Windows scanner holds the file; keep the original error
        raise
    return output


def doctor() -> None:
    print(f"SkellForge {__version__} | Python {platform.python_version()} | {platform.system()}")
    for binary in ("cmake", "git"):
        print(f"  {binary}: {shutil.which(binary) or 'NOT FOUND'}")
    print(f"  Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required: "
          f"{'ok' if sys.version_info >= MIN_PYTHON else 'TOO OLD'}")
    print(f"  Windows build supported here: {sys.platform == 'win32'}")
    print(f"  shared SkellCore pin: {CORE_REV}")
    print("  Dependencies are fetched only by CMake, not by generation.")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="skellforge", description="Skelly Windows VST3 project forge")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="action", required=True)
    new = sub.add_parser("new", help="Create an independent plugin project")
    new.add_argument("name", help='Example: "Skell Pulse"')
    new.add_argument("destination", type=Path)
    new.add_argument("--code", required=True, help="Unique 4-character VST3 plugin code")
    new.add_argument("--core-rev", default=CORE_REV)
    new.add_argument("--core-repo", default=CORE_REPO)
    validate = sub.add_parser("validate", help="Check manifests, immutable IDs and template files")
    validate.add_argument("project", type=Path)
    build = sub.add_parser("build", help="Configure/build Windows x64 Release VST3")
    build.add_argument("project", type=Path)
    build.add_argument("--juce-path", type=Path)
    build.add_argument("--core-path", type=Path)
    build.add_argument("--parallel", type=int, default=2)
    package = sub.add_parser("package", help="Verify one VST3 and package its bundle")
    package.add_argument("project", type=Path)
    package.add_argument("--out", type=Path)
    audit = sub.add_parser("audit", help="Read-only audit of an existing JUCE plugin")
    audit.add_argument("project", type=Path)
    audit.add_argument("--json", action="store_true", help="Print machine-readable report")
    sub.add_parser("doctor", help="Display environment and dependency status")
    return p


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < MIN_PYTHON:
        print(f"SkellForge error: Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required "
              f"(running {platform.python_version()})", file=sys.stderr)
        return 1
    args = parser().parse_args(argv)
    try:
        if args.action == "new":
            path = create_project(args.name, args.destination, args.code,
                                  args.core_rev, args.core_repo)
            print(f"Created: {path}")
            print("Next: python -m skellforge validate " + str(path))
        elif args.action == "validate":
            data = validate_project(args.project)
            print(f"VALID: {data['name']} [{data['plugin_code']}] Windows VST3 / pinned SkellCore")
        elif args.action == "build":
            if args.parallel < 1 or args.parallel > 32:
                raise ForgeError("--parallel must be between 1 and 32")
            build_project(args.project, args.juce_path, args.core_path, args.parallel)
        elif args.action == "package":
            print(f"Packaged: {package_project(args.project, args.out)}")
        elif args.action == "audit":
            report = audit_project(args.project)
            if args.json:
                print(json.dumps(report, indent=2))
            else:
                print(f"Audit: {report['project']}")
                print(f"  VST3 code: {report['plugin_code'] or 'unknown'}")
                print(f"  Bundle ID: {report['bundle_id'] or 'unknown'}")
                print(f"  Formats: {', '.join(report['formats_detected']) or 'unknown'}")
                print(f"  SkellCore linked: {report['skellcore_dsp_link_detected']}")
                print(f"  Detected parameter IDs: {len(report['parameter_ids_detected'])}")
                for warning in report["warnings"]:
                    print(f"  CAUTION: {warning}")
                print("  Automatic migration: disabled (protect IDs and DSP)")
        elif args.action == "doctor":
            doctor()
        return 0
    except (ForgeError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"SkellForge error: {exc}", file=sys.stderr)
        return 1
