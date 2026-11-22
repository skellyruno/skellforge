# Local VST3 build and verification

## What the green button actually does

1. Validate immutable SkellForge and SkellWorld identities.
2. Validate `forge-studio.json` and regenerate `Source/ForgeUI.h` and
   `Source/ForgeGraph.h` as needed, protecting handwritten C++.
3. Run `cmake -S project -B project/build -A x64` with local dependency paths
   when provided.
4. Compile Release VST3 with MSVC and default 2 parallel jobs (bounded 1-8).
5. Find **exactly one** VST3 bundle and one nested VST3 binary; check MZ,
   PE signature, machine AMD64/0x8664 and PE32+ optional header.
6. Package into a timestamped `dist/` ZIP without overwriting previous exports.
7. Append successes/failures, duration and steps to local build history.

This catches missing/bogus outputs and wrong-architecture builds. It does NOT
load the DLL as FL Studio, inspect exported VST3 factories, or measure DSP quality.

## Windows setup

Install Python 3.10+, CMake, Git, and Visual Studio with **Desktop development
with C++**, using the MSVC x64 compiler and Windows SDK. Run:

```powershell
python -m skellforge doctor
python -m skellforge studio
```

If MSVC isn't detected, use a Developer PowerShell or repair the C++ workload.
If you clone dependencies locally, point the Studio build tab at the JUCE root
and at the SkellCore repo root (or its nested `SkellCore/` folder).

The first build may use FetchContent to download pinned dependency sources.
Subsequent builds reuse the same CMake build tree; they do not require a
GitHub Actions build or a GitHub push.

## Testing in FL Studio

Export ZIP is not installation. Use **INSTALL INTO VST3 FOLDER** only after
closing FL Studio; explicitly select a folder already in FL Studio's plugin
scan paths. Existing same-name bundles get backed up under the project's
local .skellforge/backups directory. Or unzip the ZIP manually into a known
VST3 scan path. Run FL Studio's plugin scan, then check:
mono/stereo, 44.1/48/96 kHz, plugin load/removal, editor reopen, parameter
automation and undo, preset save/project reopen, multiple instances,
dry pass-through at 0 dB, CPU and latency, and rapid bypass toggling.
Never overwrite a shipping plugin code or parameter ID to distribute a
different effect.

Don't assume a passing PE check means plugin host compatibility.

## Known limits and safety

- The Studio UI preview is schematic, not actual JUCE graphics.
- Optional DSP blocks use static settings, not automated host parameters.
- The DSP editor uses a serial chain with fixed input->gain->...->output flow.
- The optional graphical installer uses a staged local copy and backups.
  Automatic rollback is attempted if a rename fails; retained backups allow
  manual restoration if the filesystem prevents it.
- Build history stays inside the project and is ignored by Git.
- Launching the graphical editor requires a desktop session with Tkinter.
