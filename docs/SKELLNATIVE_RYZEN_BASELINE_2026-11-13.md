# SkellNative gain — user-measured Ryzen baseline (2026-11-13)

## Provenance and scope

User supplied a screenshot of the local PowerShell `SkellGainCompare`
results, running under Windows on their AMD Ryzen laptop. The CSV stored at
`native/benchmarks/juce_compare/results/user_ryzen_2026-11-13.csv`
is a **manual transcription of the screenshot**, not an original CSV upload,
machine-attested measurement or average of multiple local sessions.

Same executable compares optimized SIMD SkellNative Gain, original pre-SIMD
finite-safe scalar Gain, and `juce::dsp::Gain<float>`. Five timed trials,
median per combination, one warmup; 44.1/48/96 kHz and 64/256/1024 frames.
Both output channel signals use the same finite test inputs, gain changes
between 0.5 and 2.0 per block, processing prepares outside the timed loop.

These are **isolated DSP loop wall times**, not ASIO/FL Studio CPU percentages,
whole-plugin overhead, GUI render times, reported latency or a framework-wide
generalization. No laptop processor SKU, clocks, power state, FL audio driver,
compiler build hash or full raw run log was provided.

## Findings

- `native_over_juce`: 0.3978–0.5863, median **0.4846**. SkellNative's
  optimized gain took **about 48.5% of JUCE gain's time** in the median case
  (about **2.06x faster** as a gain-only kernel). Faster in all nine cases.
- `old_scalar_over_native`: 2.8008–12.3625, median **4.7356**. The
  optimized gain is about **4.74x faster** than the original finite-safe
  scalar implementation at the median configuration.
- `max_error`: **0.000000000** in each printed row, matching output to
  the benchmark's reporting precision; parity checks reject differences
  greater than 1e-5.
- CI's separate results are not the user's machine and must not be
  substituted for this field measurement.

## Engineering decision

**Stop optimizing this microkernel by default.** Native gain is now faster
than JUCE for the measured microkernel. Treat further SIMD work as lower
priority unless regressions appear.

### Next, use two separate performance gates

1. **Full VST3 audio-thread and host overhead**, with a matched JUCE gain
   plugin, identical signal, buffer sizes, sample rate, automation density,
   and number of instances. Collect FL Studio CPU or plugin performance
   readings with no GUI visible first, then when visible. A generic
   JUCE comparison executable is *not* a substitute for this host test.
2. **SkellDraw Win32 GUI cost:** measure redraw/paint duration and redraw
   frequency at idle, during audio-meter movement, knob drag and resize,
   with no allocations in the audio callback. Keep normal real output
   meter behavior; no decorative/fake meter animation.

More FL Studio stability gates: multiple live instances, automated gain
changes, saving/reopening state, resizing, startup/shutdown, load/unload,
44.1/48/96 kHz, project session duration and unusual buffer sizes.

### Collecting a repeat local measurement

Run `native/benchmarks/juce_compare/Run-GainCompare.ps1` on the user's
computer and compare CSVs with:
`python -m tools.summarize_gain_compare path/to/file.csv`.

No benchmark output implies a release-ready DAW engine.
