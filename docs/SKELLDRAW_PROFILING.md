# SkellNative v0.3 — CPU / GUI performance measurement

This milestone follows the user's **nine-case Ryzen DSP-only** comparison:
optimized SkellNative Gain 9/9 faster than JUCE Gain, same audio samples,
median native/JUCE processing-time ratio ~0.4846. See
[real Ryzen baseline](SKELLNATIVE_RYZEN_BASELINE_2026-11-13.md).
**That does not measure FL Studio process CPU or SkellDraw painting.**

## 1. SkellDraw native GDI overhead (repeatable Windows smoke)

The Windows SkellDraw smoke executable is compiled with
\`SKELLDRAW_PROFILE=1\` (a compile-time option **not enabled** for the normal
VST3). Its tests exercise actual Win32 UI windows with known inputs:

- 100 unchanged 40 ms timer events should trigger **zero paints**.
- 40 forced repaints should allocate **zero additional offscreen bitmaps**
  and avoid leaking GDI handles after warmup.
- Changing a real output-meter value must cause a paint.
- Resize causes a new backing buffer (at most when needed), and the previous
  GDI bitmap/DC are released correctly.
- Mouse drag, wheel and double-click still send balanced automation gestures.

The console emits \`SKELLDRAW_UI_PROFILE\` with timer ticks, draw calls,
buffer creations, mean paint microseconds and maximum paint microseconds.
Absolute timings depend on renderer/driver/runner and are NOT a performance
pass/fail gate. The profiler uses Windows QPC and does no allocations on
the audio thread. The shipping VST3 has no QPC instrumentation.

The renderer now caches fonts and metallic-knob tick/indicator pens per
editor lifetime. A prolonged real FL Studio session remains necessary to
test resource usage and responsiveness under DAW load.

## 2. Approximate full-host CPU, using existing FL Studio

A **read-only** Windows PowerShell helper measures total FL Studio process
CPU. It does not instrument the plugin or control the DAW. In the project
root, keep one FLP and one sample rate/ASIO buffer size, then run:

    powershell -NoProfile -ExecutionPolicy Bypass -File .\native\vst3\tools\Measure-FLStudioProcess.ps1 -Scenario Baseline

Change FL Studio's configuration yourself and repeat with

    ... -Scenario NativeClosed
    ... -Scenario NativeOpen

For a matched JUCE gain VST3, repeat with \`JuceClosed\` / \`JuceOpen\`.
The helper adds a row to \`Desktop\SkellNative_FLStudio_Process_CPU.csv\`.
Close unused windows, keep playing the same audio, choose the same instance
count, sample rates, power profile, and automation density. Repeat 2–3 times.

The process CPU value is normalized by **all logical processor cores**.
It includes the DAW, audio scheduling, other plugins, UI, and background
activity inside FL Studio. It is **NOT an isolated VST3 CPU measurement**.
Use it as a coarse A/B sanity check, not as evidence that one plugin backend
is faster. For isolated VST3 call timing, a dedicated matched host adapter
benchmark is still pending.

## 3. Safety and next release gates

- No plugins or FLPs are installed, edited, deleted or controlled by the
  CPU measurement helper.
- DSP, parameter IDs, Steinberg component/controller UUIDs, automation,
  saved state and the real output meter remain unchanged.
- Real FL Studio hands-on test: idle and active UI, saved state, automation,
  multiple instances, 44.1/48/96 kHz, resizes, repeated open/close, and
  playback after idle.
- Before any production release, test audio/video UI threads independently
  and benchmark the VST3 adapter vs an equivalent JUCE host wrapper.
- The read-only power button painter remains independent until a real
  bypass state and automation design is approved.
