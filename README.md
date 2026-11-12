# SKELLFORGE

SkellForge is Skelly's **internal Windows VST3 development studio**.
It uses [SkellCore](https://github.com/skellyruno/skellcore-vst-template) for
shared C++ DSP and JUCE UI. It is designed to make new Skelly plugins and to
build them **locally** without using GitHub Actions for every edit.

Current stage: **Studio v0.4 experimental development branch** (based on the v0.2 pilot). The original v0.1 generator is preserved.
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
effects are **bypassed by default**, so an untouched plugin is neutral. Then
use **+ ADD FX KNOB** in the UI designer to connect an automatable rotary
control to drive/cutoff, and **+ ADD OUTPUT METER** for an optional live meter.
Choose **SAVE DESIGN** and then **BUILD VST3** → **BUILD + VERIFY + EXPORT**.
**RENDER ACTUAL JUCE EDITOR** compiles a separate optional preview executable
and opens verified 390×260 / 440×310 / 900×600 screenshots rendered by
SkellCore from the exact generated plugin editor (not Tk mockups).

The builder runs CMake and Visual Studio on **your own PC**, runs JUCE C++
offline DSP tests at 44.1/48/96 kHz, verifies a Windows x64 PE32+
binary and exports a uniquely named ZIP under the generated project's
`dist/` folder. It records duration, outcome, failures and paths in local
`.skellforge/history.jsonl`. The build thread does not freeze the desktop UI.
No VST3 is silently installed into FL Studio, and no GitHub push is required.
After a verified build, **INSTALL INTO VST3 FOLDER** is an explicit opt-in action:
choose a folder already in FL Studio's scan paths, confirm, and Forge backs up
any existing same-name VST3 before replacing it. Close FL Studio first.

**Important:** On the first configure, CMake may download pinned JUCE and
SkellCore sources unless they have been cached. Supply local JUCE/SkellCore
folders in the Build tab to use previously checked-out dependencies.

## CLI (still supported)

```powershell
python -m skellforge new "Skell Pulse" ../skell-pulse --code SF01
python -m skellforge validate ../skell-pulse
python -m skellforge regenerate ../skell-pulse
python -m skellforge preview ../skell-pulse
python -m skellforge build-local ../skell-pulse --parallel 2
```

With local dependencies:

```powershell
python -m skellforge build-local ../skell-pulse --parallel 2 --juce-path C:/JUCE --core-path C:/src/skellcore-vst-template
```

Older `build` and `package` CLI commands are retained, and generated projects
still include optional GitHub CI. **Local build is the primary workflow.**

## SkellLang and the SkellNative SDK - experimental

You can now describe a small plugin in SkellLang and generate the same
validated Windows VST3 project that the visual editor uses. Example:

    python -m skellforge lang-check examples/SkellWarmth.skell
    python -m skellforge lang-export examples/SkellWarmth.skell new-scene.json
    python -m skellforge lang-new examples/SkellWarmth.skell "Skell Warmth" ../skell-warmth --code SZ91
    python -m skellforge build-local ../skell-warmth

The language is declarative and does not execute arbitrary code, run inside the
audio callback, or replace C++ compilation. Project creation never overwrites
an existing path. See [SkellLang v0.1](docs/SKELLLANG.md).

The separate JUCE-free [SkellNative source SDK](docs/NATIVE_SDK.md) now defines
plugin metadata, normalized parameter events, audio blocks and processing
lifecycle. It is **not yet** a compatible direct-VST3 backend, nor a stable
binary ABI. See the [master engineering plan](docs/MASTER_PLAN.md).

## What's in Studio v0.4 (experimental)

| Milestone | Current capability | Limit |
| --- | --- | --- |
| Testing | Python regression suite, native JUCE impulse/signal/zero-block tests at 44.1/48/96 kHz in local build, binary and ZIP verification | Not a substitute for FL Studio host/CPU tests |
| Component library | SkellCore StudioUI widgets, gain control, text labels, bound extra DSP knobs and optional realtime output meters | Preset browser and arbitrary controls remain planned |
| Visual UI editor | Drag controls on Tk design canvas; independently compile and capture the **real JUCE editor** in 3 sizes | Tk canvas remains approximate; actual JUCE preview compiles on Windows |
| DSP graph | Serial, reorderable saturation/one-pole lowpass after gain; drive/cutoff are host-automatable and smoothed | No parallel routing yet; DSP prototypes need ear/CPU tests |
| Local build/export | Desktop one-click CMake x64 Release, verify PE, package unique ZIP, history and confirmed VST3 installation with backup | Build tooling must be installed on user's Windows machine |

### Independent DSP groundwork

The separate native/ project is **pure C++17 DSP with no JUCE**. It has gain,
saturation, lowpass and atomic peak source components with Windows/Linux tests.
This is **not a working JUCE-free VST3 wrapper**. The current plugin generator
still uses JUCE to connect to FL Studio. See
[SkellNative independence roadmap](docs/JUCE_INDEPENDENCE.md).

## Stability principles

- The original plugin code, manufacturer code and bundle ID are immutable once
  released; Forge refuses to reuse known SkellWorld product codes.
- The generator uses a pinned immutable SkellCore commit and JUCE 8.0.12.
- Studio writes `forge-studio.json` and three explicitly GENERATED headers
  (UI, DSP, parameters), never overwriting manually edited C++ or SkellCore.
- The initial 0 dB gain passes audio unchanged. Optional effects start bypassed.
- New DSP parameter IDs are tied to stable node IDs. Removed nodes leave retired
  parameter registrations to protect existing saved automation and presets.
- Do not rename/edit these parameter IDs or force a different generator onto
  a plugin that has already shipped. Default parameter values lock on first save.
- The existing shared skull-key design remains a placeholder until the Skelly
  master skull is approved. The GUI editor shows simplified approximations.
- Studio edits are saved intentionally, not in a background audio callback.
- New plugins are Windows VST3 only, no standalone executable.

## Development/testing

```sh
python -m unittest discover -s tests -v
python -m compileall -q skellforge tests
cmake -S native -B native-build
cmake --build native-build --config Release
ctest --test-dir native-build -C Release --output-on-failure
```

CI includes Windows/Linux CLI suites and a separate Windows VST3 smoke build.
A passing compile does not mean the plugin has passed FL Studio save/reopen,
automation, CPU, glitch, input safety or host compatibility tests.

See [local build details](docs/LOCAL_BUILD.md) and [staged roadmap](docs/ROADMAP.md).

JUCE/Steinberg and additional source licensing must be reviewed before offering
Forge as a public plugin generator.
