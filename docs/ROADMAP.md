# SkellForge studio roadmap and acceptance gates

## v0.1 stable baseline
- Generator for Windows x64 VST3 with known-code collision checks.
- Immutable shared SkellCore pin, 0 dB default gain and Studio UI.
- Windows/Linux generator tests and Windows-native VST3 smoke build.

## v0.2 pilot (on feature/local-studio-mvp)
1. **Testing**: validate Studio JSON/C++, native CI smoke build, PE32+ x64
   verifier, regression tests. FL Studio real-host verification remains manual.
2. **Component library**: use existing SkellCore look and feel, gain control,
   skull/key placeholder and additional text labels. Other widgets listed as planned.
3. **Visual editor**: local desktop Tk preview, component drag and inspector,
   saved versioned layout JSON and deterministic JUCE generated header.
4. **DSP flow**: serial node editor, optional saturation/lowpass default bypass,
   deterministic C++ generated header with no audio-thread allocations.
5. **Local build**: one-click native CMake/MSVC compile, verify, timestamped
   export ZIP, incremental build cache, local history.

Each step is useful but **all five are still an MVP**, not feature parity with
JUCE, a modular DAW, or a full visual VST builder.

## v0.3 implemented on experimental review branch
- Generate stable APVTS parameters for serial saturation/lowpass blocks.
- Draggable attached DSP knobs, optional bypass, and 20 ms smoothing.
- Preserve removed parameter IDs as retired entries and prevent reuse.
- Native offline JUCE signal/impulse/finite/partition tests in local builder.
- Review behind CI and manual FL Studio tests; do not force-merge.

## v0.4+ next quality gates
- Expand realtime audio fixtures into reference WAVs and CPU baselines,
  with real hardware measurements (and compare smoothing under automation).
- Preview images from the **actual** JUCE editor via SkellCore headless renderer.
- Native parameter-mapped controls: buttons, menus, additional knobs, meters,
  preset browser, parameter stability and automation.
- Accurate routable DSP graph with typed ports, bypass, host latency contracts,
  graph cycle detection and serialized parameters.
- Harden and validate the v0.2 opt-in VST3 installer: FL Studio live-file
  locks, explicit scan-folder selection, manual rollback from retained backups.
- Stable GUI installer EXE with versioned updates; device-level test on low-spec
  Ryzen/Radeon Windows machine.
- Pin and document official master skull geometry when user approves it.
- For each production plugin: read-only migration audit, golden audio/DAW save
  parity before any change; never automatically rewrite DSP.

## Release gate
Cannot call Studio production-ready until:
- Windows/Linux tests green on the exact proposed commit.
- Native VST3 smoke build green with Studio-generated UI and enabled DSP nodes.
- Real Windows GUI opened/used for generation and build.
- FL Studio actual host test for generated effect and automation/session recall.
- CPU/latency profiling and third-party licensing review.
