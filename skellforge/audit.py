"""Read-only migration audit for existing Skelly/JUCE plugins.

Does NOT rewrite source, migrate DSP, or declare a plugin release-ready.
Static scans are advisory; multi-CMake and macro-based projects may be unknown.
"""
from __future__ import annotations

import re
from pathlib import Path


def _literal(text: str, key: str) -> str | None:
    match = re.search(r"(?m)^\s*" + re.escape(key) +
                      r"\s+(?:\"([^\"]+)\"|([A-Za-z0-9_.$/{}/+-]+))", text)
    return (match.group(1) or match.group(2)) if match else None


def audit_project(path: Path) -> dict:
    path = path.expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"Directory does not exist: {path}")
    cmake_file = path / "CMakeLists.txt"
    text = cmake_file.read_text(encoding="utf-8", errors="replace") if cmake_file.is_file() else ""
    formats = []
    match = re.search(r"(?m)^\s*FORMATS\s+([^\r\n#]+)", text)
    if match:
        formats = re.findall(r"[A-Za-z0-9_]+", match.group(1))
    has_juce = bool(re.search(r"\bjuce_add_plugin\s*\(", text))
    has_core = "SkellCore::DSP" in text
    sources: list[Path] = []
    for folder in (path / "Source", path / "source", path / "src"):
        if folder.is_dir():
            sources.extend(p for p in folder.rglob("*")
                           if p.is_file() and p.suffix.lower() in (".h", ".hpp", ".cpp")
                           and len(p.relative_to(folder).parts) <= 6)
    # Bound the read-only scan, so an accidental large source tree stays cheap.
    sources = sorted(set(sources))[:160]
    parameter_ids: set[str] = set()
    for file in sources:
        if file.stat().st_size > 1024 * 1024:
            continue
        content = file.read_text(encoding="utf-8", errors="replace")
        parameter_ids.update(re.findall(r'juce::ParameterID\s*\{\s*"([A-Za-z0-9_.-]+)"', content))
    warnings: list[str] = []
    if not cmake_file.is_file():
        warnings.append("No root CMakeLists.txt; inspect its actual build entrypoint")
    elif not has_juce:
        warnings.append("JUCE plugin target not detected in root CMakeLists.txt")
    if "Standalone" in formats:
        warnings.append("Standalone format detected; SkellForge starts with Windows VST3 only")
    if has_juce and not formats:
        warnings.append("Plugin formats could not be determined statically")
    if has_juce and not _literal(text, "PLUGIN_CODE"):
        warnings.append("Four-character plugin code not found in root CMakeLists.txt")
    if has_juce and not _literal(text, "BUNDLE_ID"):
        warnings.append("Bundle ID not found in root CMakeLists.txt")
    if has_juce and not has_core:
        warnings.append("SkellCore::DSP link not detected; integration is optional and needs review")
    # Check only SkellCore's block, not JUCE's separately versioned dependency.
    block = re.search(r"FetchContent_Declare\s*\(\s*SkellCore\b(.*?)\)", text, flags=re.S | re.I)
    if block:
        pin = _literal(block.group(1), "GIT_TAG")
        if pin is None or not re.fullmatch(r"[a-fA-F0-9]{40}", pin):
            warnings.append("SkellCore FetchContent does not appear pinned to a full commit SHA")
    return {
        "schema": "skellforge/audit/1",
        "project": str(path),
        "root_cmake_found": cmake_file.is_file(),
        "juce_target_detected": has_juce,
        "skellcore_dsp_link_detected": has_core,
        "plugin_code": _literal(text, "PLUGIN_CODE"),
        "bundle_id": _literal(text, "BUNDLE_ID"),
        "formats_detected": formats,
        "parameter_ids_detected": sorted(parameter_ids),
        "source_files_scanned": len(sources),
        "warnings": warnings,
        "safe_to_automatically_migrate": False,
    }
