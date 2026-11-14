# Changelog

## Unreleased

Hardening pass on v0.1. No change to the generated plugin's identity, DSP or C++ sources;
generated projects differ only in the CMake dependency-path logic and one `.gitignore` line.

### Fixed
- `validate`, `build` and `package` crashed with a traceback when `skellforge.json` or
  `skellworld.json` was valid JSON of the wrong shape (a list, `null`, absurdly deep nesting)
  or had a non-text `name`/`plugin_code`/`core_revision`/`core_repo`. They now report an
  actionable error and exit 1.
- `build --core-path <SkellCore repo root>` was rejected although the generated CMake and
  the README support that layout. The CLI now accepts exactly the layouts CMake accepts.
- `package` failed with "found 2" if a stale Debug bundle sat next to the Release one.
  It now packages from `Release/` when that folder exists.
- An error while writing the ZIP (disk full, ...) left a partial package behind; it is now
  removed. A pre-existing file at `--out` is never touched, and failing to delete the partial
  file no longer hides the original error.
- New plugins reject trailing-space or reserved Windows device names, but validation
  now preserves original v0.1 names and IDs. Existing projects need an explicit
  compatibility-tested migration before Windows distribution, not a silent rename.
- `audit` missed `Standalone` when `FORMATS` spanned several lines or used `;`/`${VAR}`,
  read `PLUGIN_CODE`/`BUNDLE_ID` from unrelated `set()`/`message()` lines, and treated
  commented-out CMake/C++ as real.
- Generated `CMakeLists.txt` silently downloaded JUCE/SkellCore when an explicit but wrong
  `JUCE_PATH`/`SKELLCORE_PATH` was given (including values like `OFF`/`0`). It now stops with
  an error. (An empty value still means "download the pinned dependency".)
- Manifest JSON files are written with `
` line endings on every OS, like the other generated files.

### Changed
- Packaging preflight now rejects symbolic links, multiple VST3 binaries, binaries
  outside Contents/x86_64-win and ZIP output inside the source bundle.
- `validate` now guards `parameter_ids`: an ID listed in `skellforge.json` that no longer
  appears as a `"quoted string"` in any source file (comments and `build/` ignored) is an error.
  This is intentionally conservative so valid refactors (constants, other folders, `.inl`
  files) keep working. It catches an ID renamed or removed everywhere, not one that is merely
  no longer declared while its string survives elsewhere. An incomplete scan (file cap,
  oversized or unreadable file) never raises this error.
- `validate` CMake identity checks match whole tokens (`PLUGIN_CODE Sf01` no longer accepts
  `Sf01x`), ignore commented-out lines, and also verify `GIT_REPOSITORY` against the manifest.
  A hand-edited project must therefore keep a literal repository URL (quotes allowed), as it
  already had to for the commit SHA.
- CMake and C++ comment stripping is a single linear pass: `#`, `#[[` or `//` inside a string
  can no longer hide real code, and unterminated comments no longer cause quadratic run time.
- `audit` detects legacy `AudioParameterFloat("id", ...)`-style IDs, reports truncated or
  oversized source scans, and warns when no parameter IDs were found.
- Running on Python older than 3.10 prints a clear message instead of a traceback;
  `doctor` reports the requirement.
- Generated `.gitignore` ignores the packaged `SkellForge-*.zip`.

### Added
- `tests/test_hardening.py`: regression tests for everything above, a mocked Windows build test,
  and a stub-based CMake configure test (skipped on Windows and when cmake or a compiler is missing).
- CI runs `audit` on the generated sample (as its own step: on Windows only the last command of a
  multi-line `run:` block decides the step result).
- Repository `.gitignore`.

### Not changed / not verified
- The C++ templates were left untouched, and nothing here compiles JUCE or builds a real VST3;
  the Windows smoke workflow remains the check for that.
