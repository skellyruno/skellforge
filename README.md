# SKELLFORGE

SkellForge is Skelly's **internal Windows VST3 development studio**.
It uses [SkellCore](https://github.com/skellyruno/skellcore-vst-template) for
shared C++ DSP and JUCE UI. It is designed to make new Skelly plugins and to
build them **locally** without using GitHub Actions for every edit.

Current stage: **Studio v0.2 MVP / pilot**. The original v0.1 generator is preserved.
Existing Skelly plugins are not modified automatically.

## Fast start on Windows

Python 3.10+, Visual Studio C++ desktop tooling, Git, and CMake are required.
Tkinter ships with standard Windows Python installations.

```powershell
git clone https://github.com/skellyruno/skellforge.git
cd skellforge
python -m skellforge doctor
python -m skellforge studio
```

In Studio choose **NEW PLUGIN**, enter a unique four-character code and choose
a parent folder. In **UI DESIGNER**, drag built-in controls and add text labels.
In **DSP CHAIN**, add optional serial Saturation or Lowpass blocks; newly added
effects are **bypassed by default**, so an untouched plugin is neutral. Choose
**SAVE DESIGN** and then **BUILD VST3** → **BUILD + VERIFY + EXPORT**.

The builder runs CMake and Visual Studio on **your own PC**, verifies a Windows
x64 PE32+ binary and exports a uniquely named ZIP under the generated project's
`dist/` folder. It records duration, outcome, failures and paths in local
`.skellforge/history.jsonl`. The build thread does not freeze the desktop UI.
No VST3 is silently installed into FL Studio, and no GitHub push is required.

**Important:** On the first configure, CMake may download pinned JUCE and
SkellCore sources unless they have been cached. Supply local JUCE/SkellCore
folders in the Build tab to use previously checked-out dependencies.

## CLI (still supported)

```powershell
python -m skellforge new "Skell Pulse" ../skell-pulse --code SF01
python -m skellforge validate ../skell-pulse
python -m skellforge regenerate ../skell-pulse
python -m skellforge build-local ../skell-pulse --parallel 2
```

With local dependencies:

```powershell
python -m skellforge build-local ../skell-pulse --parallel 2 --juce-path C:/JUCE --core-path C:/src/skellcore-vst-template
```

Older `build` and `package` CLI commands are retained, and generated projects
still include optional GitHub CI. **Local build is the primary workflow.**

## What's in Studio v0.2

| Milestone | Current capability | Limit |
| --- | --- | --- |
| Testing | CLI regression suite, manifest/schema checks, real Windows native build in CI, local PE x64 check and ZIP verification | Not a substitute for FL Studio host/audio/CPU tests |
| Component library | SkellCore StudioUI controls, positioned title/skull/gain knob/label, additional visual text labels | Buttons, meters and additional parameter-mapped knobs are future integrations |
| Visual UI editor | Drag controls on an approximate Tk preview, adjust bounds and text, save JSON, generate C++ JUCE layout | Preview is not native JUCE pixel-perfect rendering |
| DSP graph | Serial, reorderable bypassable saturation/one-pole lowpass after automatable gain, compile-time graph C++ generation | No parallel routing or realtime automation of optional nodes yet |
| Local build/export | Desktop one-click CMake x64 Release, verify PE, package unique ZIP, history | Build tooling must be installed on user's Windows machine |

## Stability principles

- The original plugin code, manufacturer code and bundle ID are immutable once
  released; Forge refuses to reuse known SkellWorld product codes.
- The generator uses a pinned immutable SkellCore commit and JUCE 8.0.12.
- Studio writes `forge-studio.json` and two explicitly GENERATED headers,
  never overwriting manually edited C++ or the SkellCore repository.
- The initial 0 dB gain passes audio unchanged. Optional effects start bypassed.
- The existing shared skull-key design remains a placeholder until the Skelly
  master skull is approved. The GUI editor shows simplified approximations.
- Studio edits are saved intentionally, not in a background audio callback.
- New plugins are Windows VST3 only, no standalone executable.

## Development/testing

```sh
python -m unittest discover -s tests -v
python -m compileall -q skellforge tests
```

CI includes Windows/Linux CLI suites and a separate Windows VST3 smoke build.
A passing compile does not mean the plugin has passed FL Studio save/reopen,
automation, CPU, glitch, input safety or host compatibility tests.

See [local build details](docs/LOCAL_BUILD.md) and [staged roadmap](docs/ROADMAP.md).

JUCE/Steinberg and additional source licensing must be reviewed before offering
Forge as a public plugin generator.
