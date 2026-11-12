# SkellNative Gain — JUCE-free Windows VST3 prototype

**EXPERIMENTAL. Not a commercial plugin or a replacement for SkellCore/JUCE.**

This is the first original Skelly VST3 host adapter using only Steinberg VST3
SDK 3.8.1 and the portable, JUCE-free SkellNative C++17 DSP / state headers.
Its two processor/controller class IDs are unique prototype IDs and must never
be reused for an already released plugin.

## Compile on Windows x64

Requirements: Visual Studio Desktop development with C++, CMake 3.25+, Git.
The initial build fetches the pinned SDK and its submodules; subsequent builds
reuse the local CMake cache and do not require GitHub Actions.

    cmake -S native/vst3 -B native/vst3/build -A x64
    cmake --build native/vst3/build --target SkellNativeGain --config Release --parallel 2

Optional use of a fully cloned local Steinberg SDK:

    cmake -S native/vst3 -B native/vst3/build -A x64 -DSKELLNATIVE_STEINBERG_SDK=C:/src/vst3sdk

## Current design

- VST3 processor and separate controller classes, using direct Steinberg APIs.
- Single mono or stereo bus; 32-bit and 64-bit sample format support.
- Neutral gain at 0.5 normalized, linear amplitude 1.0; 0..2 gain range.
- Host automation parameter ID 1000 with sample-offset application.
- Pure SkellNative Gain DSP in the float32 path, double-precision fallback.
- Product-bound, versioned SkellNative state save/restore.
- Reports **zero latency samples**.
- SkellDraw v0.1 is an original native Win32 embedded HWND editor (no JUCE,
  no VSTGUI) with an interactive gain control, live value display, double-click
  reset, mouse wheel, DAW edit gestures, and host-resize support.
- The provisional hardware-inspired black/green appearance is deliberately
  **not** the yet-unapproved master Skelly skull asset.

## Must be verified before a public build

1. CMake/MSVC native build and PE32+ x64 bundle verification.
2. Steinberg official VST3 validator: factory, parameter queues, buses, state.
3. Real FL Studio loading, instance deletion, multiple-instance lifecycle.
4. Host automation rendering, sample-accurate event changes and state recall.
5. Realtime allocation/glitch test, CPU cost, 44.1/48/96 kHz parity.
6. Native SkellDraw HWND lifecycle and mouse interaction smoke in Windows CI.
7. FL Studio screenshot review, plugin reopening/unloading, multiple editors,
   live automation feedback, monitor scaling and GPU/CPU performance.
8. Approved master skull and final SkellDraw component styling.

Changing from JUCE to direct SDK does **not** guarantee lower algorithmic
latency or CPU. This proof does not modify shipped Skelly plugin identities.

## Licensing

The Steinberg VST3 SDK 3.8.x is MIT-licensed; retain required notices. VST
trademark and marketing rules are separate. Never claim this source is an
independent VST *standard*; it is Skelly's developer SDK adapter to VST3.
