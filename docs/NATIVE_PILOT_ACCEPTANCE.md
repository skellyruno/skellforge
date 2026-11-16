# SkellForge × SkellNative × SkellLang acceptance handoff 🩻

## Verified pipeline scope

The experimental `skellforge build-native` commands integrate a pinned
SkellNative checkout, its original Win32 SkellDraw components, official pinned
Steinberg VST3 SDK and the pinned SkellLang v2 control compiler used by Mini.
The Windows integration workflow builds both Mini and Spacer from the exact\nverified SkellNative commit `43fb80cb371b770b12461368054a3d9183ab9aaf`, checks shared runtime, executes Mini's loaded-DLL audio/automation gate, runs Steinberg's official validator on each product, **strictly parses RFC 8259 moduleinfo JSON and verifies both product factory class IDs**, checks PE32+ x64 binaries, and writes SHA-256 hashes to `native-pilot-build.json`.

These checks establish that the development plugins can build and pass
automated VST3 tests. They **do not** certify FL Studio compatibility or
measure DAW CPU, PDC, audio quality, or preset migration. The Studio visual
editor (SkellForge v0.4) and the general `new-native` generator remain separate
draft features; neither is silently substituted for released JUCE plugins.

## Windows FL Studio acceptance (still a manual gate)

1. Download the **experimental** Windows CI artifact and match the binary
   hashes to `native-pilot-build.json`. Do not install over any released VST3.
2. Extract Mini and Spacer to an isolated new testing VST3 folder. Add only
   that folder as a scan path in FL Studio and run a fresh scan.
3. Record Windows, FL Studio, audio driver, project, CPU and plugin versions.
   Test plugin load/unload 20 times, two simultaneous instances, editor resizing,
   80/100/125/150/200% display scaling and actual screenshots.
4. Make a new test FLP. Automate every writable parameter, including
   multiple changes in one block; save, quit, reopen and compare recalled
   parameter IDs, states and automation. Never overwrite an existing FLP.
5. Render identical dry and processed audio at 44.1/48/96 kHz and
   64/256/1024 sample buffers. Loudness-match listening A/B and log peak/RMS,
   artifacts, NaNs, denormals, silence behavior and true latency/PDC.
6. Run repeatable CPU measurements with one and multiple instances, record
   average and peak process usage, and test bypass/enable transitions.

Pass only on evidence: host log, VST3 paths/hashes, FLP test file, UI captures,
DAW renders and measured latency/CPU. Otherwise retain `NOT_RUN` or `FAILED`.
This test does not change installed production builds, SkellCore interfaces,
published automation IDs or preset/state formats.

## Branch / merge order

- [PR #23](https://github.com/skellyruno/skellforge/pull/23):
  core generator identity, package and compatibility hardening.
- [PR #24](https://github.com/skellyruno/skellforge/pull/24):
  opt-in SkellNative Mini/Spacer builder.
- [PR #25](https://github.com/skellyruno/skellforge/pull/25):
  runtime test/validator gates and this cross-repository integration workflow.
- [PR #26](https://github.com/skellyruno/skellforge/pull/26):
  separate experimental SkellLang-driven JUCE-free Gain project generation.
- Studio preview / SkellCore UI work remains on a separate series. Inspect actual
  native UI screenshots before considering any UI adoption or branch reconciliation.

Every PR remains draft until its exact head's CI passes. Do not merge nested
draft branches out of order, bypass failing CI, or modify original FL projects.
