# SkellForge / SkellNative - master roadmap (12 Nov 2026)

This is an evolving engineering handoff. It does not claim unimplemented or
untested features are production ready. The user-facing 13-page PDF blueprint
also includes architecture diagrams, delivery gates and risk controls.

## Mission

Build a visual-first Windows VST3 creation environment with local building,
reusable DSP/UI, SkellLang text-first plugin authoring and eventually a
JUCE-free backend powered by the official Steinberg SDK.

Four ownership layers:
- SkellForge: project model, UI designer, DSP graphs, local build/test/export.
- SkellLang: language front-end compiling to the same validated Studio IR.
- SkellNative SDK: portable C++17 audio engine and host-neutral contracts.
- SkellDraw: prospective native UI, not yet implemented.

SkellWorld is the product catalog; Project Hub is the developer control plane.
Neither should be a hidden requirement for realtime VST3 processing.

## Status / immutable facts

main: v0.1 working generator / pinned SkellCore.
feature/local-studio-mvp: v0.2 visual studio and local build pipeline.
feature/studio-v0.3-automation-safety: stable APVTS IDs and native DSP tests.
feature/studio-v0.4-real-ui-preview: live meters and native screenshot tool.
The VST3 and C++ DSP checks passed; the actual screenshot tool initially
failed linker and then crashed on execution. The executable is instrumented
and this gate remains OPEN until real rendered PNGs are inspected.
feature/skelllang-sdk-v0.1: compiler for a restricted declarative DSL,
source-only SkellNative processing contract; 59 Python checks per platform
and JUCE-independent native C++ tests passed on its latest checked code.

## Architecture direction

Visual Studio / SkellLang -> versioned shared Studio project IR ->
  (JUCE + SkellCore backend, current)
  (direct VST3 + SkellNative backend, future)

Both backends must eventually use the same DSP reference tests and preserve
host parameter identities. The SkellNative SDK is not a substitute for the
Steinberg VST3 host ABI; FL Studio requires the published format.

## Short/medium/long gates

A. Stabilize v0.4 native UI renderer. Exit: actual responsive PNGs and verified
   Windows native workflow on a single commit.
B. Finish SkellLang/SDK prototype. Exit: deterministic compiler, examples,
   collision guards, host-neutral C++ event/parameter tests; Windows/Linux CI.
C. Host parity and safety. Exit: FL Studio save/reopen, automation, CPU/latency,
   UI controls, mono/stereo, real signals and multiple instances.
D. Direct Steinberg SDK Windows VST3 gain effect. Exit: factory/installer,
   plugin validator, automation, state and actual host test with no JUCE.
E. Typed DSP graph and migration layer. Exit: ports, cycle/latency guards,
   44.1/48/96 kHz fixtures and ID compatibility.
F. Native UI bridge (VSTGUI interim or SkellDraw later). Exit: host embedding,
   input focus, DPI scaling, redraw and screenshot tests.
G. Dual backend selector. Exit: same design, compatible state, reference audio
   parity and safe new-plugin release.
H. Project Hub integration, release channels and opt-in install with rollback.

## Hard safeguards

- Do not rewrite old VST3s, IDs, presets, or automation to chase milestones.
- Audio callback: no heap allocation, locks, filesystem, GUI or nonfinite audio.
- New paths only; don't overwrite existing user's project/code/source.
- All build claims must distinguish Python suite, native compile, DSP test,
  actual JUCE editor render, pluginval and FL Studio in-host testing.
- Budget: use free/local tools first; minimize unneeded cloud jobs and paid
  dependencies; review licensing before commercial sales.
- Preserve master skull concept while allowing plugin-specific icon identity.

## Sources
- Steinberg VST3 SDK: https://github.com/steinbergmedia/vst3sdk
- Steinberg licensing: https://www.steinberg.net/developers/vstsdk/
- JUCE 8 license: https://juce.com/legal/juce-8-licence/
- Repository: https://github.com/skellyruno/skellforge

Ranges such as 6-18 months are planning estimates, not delivery guarantees.
