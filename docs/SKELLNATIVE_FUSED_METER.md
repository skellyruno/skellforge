# SkellNative v0.5 — fused gain and real output metering

## Why this matters

In the actual native VST3 adapter benchmark v0.4 on Windows CI, the
32-bit stereo 256-frame callback (no automation) cost approximately:
- No output queue: 81 ns per call.
- With a real output peak queue: 315 ns per call.

These are **CI runner measurements**, not Ryzen laptop data. The separate
full-buffer peak scan accounts for a meaningful part of the measured cost.

## Implementation

- Gain::processWithPeak(Block, float&) tracks the maximum processed output
  amplitude while computing the gain, avoiding a second audio-buffer scan.
- SSE2 finite-safe four-lane gain processing tracks peak in vector registers;
  the scalar fallback does the same on non-SSE2 hosts.
- Peaks are clipped to 1.0 in the existing Output Peak VST3 parameter.
  Extreme finite values that overflow float multiplication still register
  as clipped, not falsely silent.
- Gain::process() is still called when the VST3 host does not request
  metering, retaining its previous no-meter performance.
- Double-precision samples track the peak as output is written.
- No allocations, locks or timing instruments were added to the audio callback.

## Verification

The native C++ regression suite requires **bit-identical** Gain vs
Gain+Peak output over mono/stereo, zero/odd frames, unaligned channel buffers,
gains 0/0.5/1/2/4, NaN/Inf inputs, denormals and float overflow.
Output-peak values must match an independent scan of processed output.
Tests also compile with SIMD disabled.

The VST3 adapter benchmark additionally verifies 72 scenarios spanning
three sample rates, three block sizes, f32/f64, 0/4 automation points, and
output meter on/off. The Steinberg validator runs 47 host checks; the
Windows GUI interaction/lifecycle smoke also remains mandatory.

## Unchanged

Processor/controller IDs, Gain parameter ID 1000, Output Peak ID 1001,
serialized state, sample-offset automation, JUCE-free Win32 SkellDraw UI
and VST3 bundle structure. The meter remains tied to real audio values,
not an invented animation.

The first hardware-specific confirmation will be a repeated Ryzen
v0.4/v0.5 adapter test with the same buffer, compiler and host settings.
No CPU or latency advantage across complete DAWs is claimed yet.


## Repeat the adapter benchmark on the Ryzen laptop

Once this PR is validated and merged, from the already-cloned SkellForge
checkout use PowerShell:

    git pull --ff-only
    powershell -NoProfile -ExecutionPolicy Bypass -File .\native\vst3\tools\Run-AdapterBenchmark.ps1

The script auto-detects CMake bundled with Visual Studio using vswhere.exe
(the same detection as the working gain/JUCE runner). It builds the real
VST3 adapter benchmark in Release x64 with --parallel 2, verifies all 72
scenarios and writes clean CSV to
Desktop\SkellNative_VST3_Adapter_Local.csv. Nothing is installed into FL
Studio and no project is modified.

The v0.4 Windows CI adapter baseline is archived as GitHub Actions
artifact in run 43559488119. Compare it with the v0.5 CI benchmark only
as directional evidence; local measured data should be collected repeatedly
under consistent thermal and background-load conditions before claiming
a measured Ryzen speedup.
