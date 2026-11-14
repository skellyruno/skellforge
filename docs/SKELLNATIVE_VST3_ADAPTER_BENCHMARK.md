# SkellNative v0.4 — VST3 processing adapter benchmark

This phase advances beyond the Ryzen gain-kernel benchmark and benchmarks
the **actual original GainProcessor::process** implementation (the C++ source
linked into SkellNativeGain.vst3). The test runs it through actual Steinberg
IAudioProcessor/IComponent interfaces and ParameterChanges queues in a
simulated in-process host. It is **not** dynamic DLL loading, FL Studio,
JUCE VST3 host integration, ASIO, a GPU/UI benchmark, or whole DAW CPU%.

## Verification matrix (72 cases)

- 44,100 / 48,000 / 96,000 Hz × 64 / 256 / 1024 samples.
- 32-bit and 64-bit planar stereo.
- No automation or four sample-offset Gain events per audio block.
- No output meter or a real host output-parameter queue.
- Checks correct processed samples (including mid-block gain changes),
  native processor-reported latency == 0 samples, real output peak
  and exact output-parameter ID/offset.
- Tests fail immediately if actual VST3 processing or parity fails.
- Five median timed repetitions per configuration, one warmup.
  No arbitrary CPU speed thresholds. Buffer allocation, DAW-queue setup
  and processor initialization happen outside timed loops.

The executable produces a CSV with:
\`rate_hz,block_frames,sample_bits,automation_points,output_meter,ns_per_process_call\`.

The "meter" cases include actual f32/f64 peak scanning and sending a VST3
parameter point; "automation" includes queue reads and multiple spans.
Importantly, this instrument runs processor code directly but not through
the dynamic VST3 module loader, Steinberg factory, or a real DAW process.
It is a useful **adapter overhead microbenchmark**, not a complete
VST3-vs-JUCE comparison and not proof of FL Studio CPU superiority.

## Build and run on Windows x64

In **Developer PowerShell for Visual Studio** from the SkellForge repo:

    cmake -S native/vst3 -B native/vst3/build -A x64
    cmake --build native/vst3/build --target SkellNativeVst3AdapterBench --config Release --parallel 2

The executable lives in a subfolder of the CMake build tree; search for
\`SkellNativeVst3AdapterBench.exe\` and run it to print the CSV.

Running CMake the first time may fetch the pinned Steinberg SDK and
submodules; local CMake cache avoids downloading on later runs. This
does not install or alter the user's VST3 or any saved FL Studio session.

## What we know from user field tests

The user's Ryzen laptop gain kernel benchmark previously reported optimized
SkellNative gain faster than JUCE gain in 9/9 configurations (median
SkellNative/JUCE processing time ratio ~0.4846) with reported zero audio
error. This test includes VST3 adapter paths that gain-only testing omits.
**Do not combine or divide the two different timing datasets as if they were
the same workload.**

## Later milestones

1. Matched JUCE plugin VST3 adapter benchmark with identical format,
   host setup, output meter, and sample-offset automation.
2. FL Studio process CPU/ASIO stable A/B across instance count/GUI open/closed,
   separate from plugin DSP and editor timing.
3. Long-running native component/controller factory lifecycle, in-host
   sample rate changes and complete session migration tests.
4. Actual native SkellDraw editor idle/resize/paint measurements on laptop;
   the existing CI smoke's QPC timings reflect CI runners only.
