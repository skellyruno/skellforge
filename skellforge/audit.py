"""Read-only migration audit for existing Skelly/JUCE plugins.

Does NOT rewrite source, migrate DSP, or declare a plugin release-ready.
Static scans are advisory; multi-CMake and macro-based projects may be unknown.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

SOURCE_FOLDERS = ("Source", "source", "src")
SOURCE_SUFFIXES = (".h", ".hpp", ".cpp", ".cc", ".cxx")
# Wider set used when asking "does this string appear anywhere in the project's code?"
LITERAL_SUFFIXES = SOURCE_SUFFIXES + (".hh", ".hxx", ".inl", ".ipp", ".c", ".mm")
SKIPPED_FOLDERS = {".git", ".vs", "node_modules"}
MAX_SOURCE_FILES = 160
MAX_SOURCE_BYTES = 1024 * 1024
MAX_SOURCE_DEPTH = 6
# JUCE format keywords are case-sensitive in CMake, but report them canonically.
JUCE_FORMATS = {name.casefold(): name for name in
                ("AAX", "AU", "AUv3", "LV2", "Standalone", "Unity", "VST", "VST3")}

_BRACKET_OPEN = re.compile(r"\[(=*)\[")
_CMAKE_SPECIAL = re.compile(r'["\[#]')
_CPP_SPECIAL = re.compile(r"[\"'/]")
_KEYWORD = re.compile(r"[A-Z][A-Z0-9_]*")
_PARAMETER_ID_PATTERNS = (
    # juce::ParameterID{"id", 1} / juce::ParameterID("id", 1)
    re.compile(r'\bParameterID\s*[{(]\s*"([A-Za-z0-9_.-]+)"'),
    # Legacy: std::make_unique<juce::AudioParameterFloat>("id", ...) / new AudioParameterBool("id", ...)
    re.compile(r'\bAudioParameter(?:Float|Int|Bool|Choice)\b\s*>?\s*[{(]\s*"([A-Za-z0-9_.-]+)"'),
)


def strip_cmake_comments(text: str) -> str:
    """Remove CMake comments in one linear left-to-right pass.

    Quoted arguments and bracket arguments are copied verbatim, so a '#' or '#[[' inside
    them never starts a comment; an unterminated bracket comment swallows the rest.
    """
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        special = _CMAKE_SPECIAL.search(text, i)
        if special is None:
            out.append(text[i:])
            break
        out.append(text[i:special.start()])
        i = special.start()
        char = text[i]
        if char == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            j = min(j + 1, n)
            out.append(text[i:j])
            i = j
        elif char == "[":
            opener = _BRACKET_OPEN.match(text, i)
            if opener is None:
                out.append(char)
                i += 1
            else:  # bracket argument: verbatim
                end = text.find("]" + opener.group(1) + "]", opener.end())
                j = n if end == -1 else end + len(opener.group(1)) + 2
                out.append(text[i:j])
                i = j
        else:  # '#': bracket comment or line comment
            opener = _BRACKET_OPEN.match(text, i + 1)
            if opener is not None:
                end = text.find("]" + opener.group(1) + "]", opener.end())
                i = n if end == -1 else end + len(opener.group(1)) + 2
                out.append(" ")
            else:
                newline = text.find("\n", i)
                i = n if newline == -1 else newline  # keep the newline itself
    return "".join(out)


def _strip_cpp_comments(text: str) -> str:
    """Remove C++ comments in one linear pass, keeping string and character literals."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        special = _CPP_SPECIAL.search(text, i)
        if special is None:
            out.append(text[i:])
            break
        out.append(text[i:special.start()])
        i = special.start()
        char = text[i]
        if char == '"':
            if i > 0 and text[i - 1] == "R":  # raw string literal R"delim( ... )delim"
                paren = text.find("(", i + 1, i + 18)
                delimiter = text[i + 1:paren] if paren != -1 else None
                if delimiter is not None and not set(delimiter) & set(' )\\\t\n"'):
                    end = text.find(")" + delimiter + '"', paren + 1)
                    j = n if end == -1 else end + len(delimiter) + 2
                    out.append(text[i:j])
                    i = j
                    continue
            j = i + 1
            while j < n and text[j] not in '"\n':
                j += 2 if text[j] == "\\" else 1
            if j < n and text[j] == '"':
                j += 1
            j = min(j, n)
            out.append(text[i:j])
            i = j
        elif char == "'":
            if i > 0 and text[i - 1].isalnum():  # digit separator such as 1'000'000
                out.append(char)
                i += 1
                continue
            j = i + 1
            while j < n and text[j] not in "'\n":
                j += 2 if text[j] == "\\" else 1
            if j < n and text[j] == "'":
                j += 1
            j = min(j, n)
            out.append(text[i:j])
            i = j
        elif text.startswith("//", i):
            newline = text.find("\n", i)
            i = n if newline == -1 else newline
            out.append(" ")
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
            out.append(" ")
        else:
            out.append(char)
            i += 1
    return "".join(out)


def _plugin_args(text: str) -> str:
    """The argument list of juce_add_plugin(...), or the whole text if there is no such call."""
    match = re.search(r"\bjuce_add_plugin\s*\(", text, flags=re.I)
    if match is None:
        return text
    depth, quoted, i = 1, False, match.end()
    while i < len(text):
        char = text[i]
        if char == "\\":
            i += 2
            continue
        if char == '"':
            quoted = not quoted
        elif not quoted and char == "(":
            depth += 1
        elif not quoted and char == ")":
            depth -= 1
            if depth == 0:
                return text[match.end():i]
        i += 1
    return text[match.end():]


def _literal(text: str, key: str) -> str | None:
    match = re.search(r"(?<![A-Za-z0-9_])" + re.escape(key) +
                      r"\s+(?:\"([^\"]+)\"|([A-Za-z0-9_.$/{}+-]+))", text)
    return (match.group(1) or match.group(2)) if match else None


def _formats(text: str) -> list[str]:
    """Collect JUCE format keywords following every FORMATS keyword, across lines.

    Handles ';'-separated lists and skips variable references such as ${FORMATS};
    stops at the closing parenthesis or the next ALL-CAPS CMake keyword argument.
    """
    found: list[str] = []
    for match in re.finditer(r"(?<![A-Za-z0-9_])FORMATS(?![A-Za-z0-9_])", text):
        for token in re.finditer(r"\)|[^\s();]+", text[match.end():]):
            word = token.group(0).strip('"')
            if word == ")":
                break
            canonical = JUCE_FORMATS.get(word.casefold())
            if canonical is not None:
                if canonical not in found:
                    found.append(canonical)
            elif _KEYWORD.fullmatch(word):  # the next juce_add_plugin keyword
                break
    return found


def find_string_literals(project: Path, literals, limit: int = 2000) -> dict:
    """Which of `literals` appear as a "quoted" string in any C/C++ file of the project?

    Comments are ignored; build output and VCS folders are skipped. `complete` is False
    when a file cap, size cap or unreadable file stopped the scan from covering everything,
    so callers must not treat "not found" as proof in that case.
    """
    remaining = set(literals)
    found: set[str] = set()
    complete, seen = True, 0
    for folder, subfolders, filenames in os.walk(project):
        subfolders[:] = sorted(d for d in subfolders if d not in SKIPPED_FOLDERS
                               and d != "build" and not d.startswith("build-"))
        for name in sorted(filenames):
            if Path(name).suffix.lower() not in LITERAL_SUFFIXES:
                continue
            seen += 1
            if seen > limit:
                return {"found": found, "complete": False}
            file = Path(folder) / name
            try:
                if file.stat().st_size > MAX_SOURCE_BYTES:
                    complete = False
                    continue
                text = _strip_cpp_comments(file.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                complete = False
                continue
            for literal in sorted(remaining):
                if f'"{literal}"' in text:
                    found.add(literal)
                    remaining.discard(literal)
            if not remaining:
                return {"found": found, "complete": True}
    return {"found": found, "complete": complete}


def scan_parameter_ids(path: Path, limit: int = MAX_SOURCE_FILES) -> dict:
    """Statically find APVTS parameter IDs declared under Source/, source/ or src/.

    Returns the IDs plus how much of the tree was actually read, so callers can
    tell a complete scan from a truncated one.
    """
    path = Path(path)
    files: set[Path] = set()
    for folder in (path / name for name in SOURCE_FOLDERS):
        if folder.is_dir():
            files.update(p for p in folder.rglob("*")
                         if p.is_file() and p.suffix.lower() in SOURCE_SUFFIXES
                         and len(p.relative_to(folder).parts) <= MAX_SOURCE_DEPTH)
    # Bound the read-only scan, so an accidental large source tree stays cheap.
    ordered = sorted(files)
    scanned = ordered[:limit]
    ids: set[str] = set()
    skipped_large = 0
    for file in scanned:
        if file.stat().st_size > MAX_SOURCE_BYTES:
            skipped_large += 1
            continue
        content = _strip_cpp_comments(file.read_text(encoding="utf-8", errors="replace"))
        for pattern in _PARAMETER_ID_PATTERNS:
            ids.update(pattern.findall(content))
    return {
        "parameter_ids": ids,
        "files_scanned": len(scanned),
        "files_skipped_large": skipped_large,
        "truncated": len(ordered) > limit,
    }


def audit_project(path: Path) -> dict:
    path = path.expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"Directory does not exist: {path}")
    cmake_file = path / "CMakeLists.txt"
    text = strip_cmake_comments(
        cmake_file.read_text(encoding="utf-8", errors="replace")) if cmake_file.is_file() else ""
    formats = _formats(text)
    has_juce = bool(re.search(r"\bjuce_add_plugin\s*\(", text, flags=re.I))
    has_core = "SkellCore::DSP" in text
    # Read identity keywords only from the plugin call, not from set()/message()/if() lines.
    plugin_args = _plugin_args(text)
    plugin_code = _literal(plugin_args, "PLUGIN_CODE")
    bundle_id = _literal(plugin_args, "BUNDLE_ID")
    scan = scan_parameter_ids(path)
    parameter_ids = scan["parameter_ids"]
    warnings: list[str] = []
    if not cmake_file.is_file():
        warnings.append("No root CMakeLists.txt; inspect its actual build entrypoint")
    elif not has_juce:
        warnings.append("JUCE plugin target not detected in root CMakeLists.txt")
    if "Standalone" in formats:
        warnings.append("Standalone format detected; SkellForge starts with Windows VST3 only")
    if has_juce and not formats:
        warnings.append("Plugin formats could not be determined statically")
    if has_juce and not plugin_code:
        warnings.append("Four-character plugin code not found in root CMakeLists.txt")
    if has_juce and not bundle_id:
        warnings.append("Bundle ID not found in root CMakeLists.txt")
    if has_juce and not has_core:
        warnings.append("SkellCore::DSP link not detected; integration is optional and needs review")
    if has_juce and not parameter_ids:
        warnings.append("No parameter IDs detected statically; check how automatable parameters are declared")
    if scan["truncated"]:
        warnings.append(f"Source scan stopped after {MAX_SOURCE_FILES} files; "
                        "parameter IDs may be incomplete")
    if scan["files_skipped_large"]:
        warnings.append(f"{scan['files_skipped_large']} source file(s) over 1 MiB were not scanned")
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
        "plugin_code": plugin_code,
        "bundle_id": bundle_id,
        "formats_detected": formats,
        "parameter_ids_detected": sorted(parameter_ids),
        "source_files_scanned": scan["files_scanned"],
        "warnings": warnings,
        "safe_to_automatically_migrate": False,
    }
