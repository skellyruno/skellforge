# SkellNative performance and FL Studio acceptance

## User-reported FL Studio acceptance, November 12, 2026

The user confirmed five successful checks in FL Studio for SkellNative Gain
with SkellDraw native UI:

1. Gain knob changes real audio level.
2. 0.00x mutes and 1.00x preserves the original volume.
3. DAW automation changes gain during playback.
4. Gain state is recalled after saving, closing and reopening the FLP.
5. Three instances work simultaneously without crashes.

These are **user-reported acceptance observations**, not automated FL Studio
test results. The installed binary's SHA-256 was not independently captured.
The reported session and precise version may differ from a future download.
No objective CPU/latency measurement was provided.

The corresponding native GUI-enabled VST3 revision separately passed 47/47
Steinberg validator tests and Windows HWND/interaction smoke tests:
https://github.com/skellyruno/skellforge/actions/runs/43285507518

## Portable performance benchmark

An optional JUCE-free C++17 benchmark measures in-place float32 stereo DSP
on the machine running it. It exercises gain, lowpass, peak measurement,
and gain plus peak at 44.1, 48 and 96 kHz for 64/256/1024 frame blocks.

Windows / MSVC:
    cmake -S native -B native-build -DSKELLNATIVE_BUILD_BENCHMARKS=ON
    cmake --build native-build --config Release --parallel 2
    ctest --test-dir native-build -C Release -R SkellNativeBenchmarkSmoke -V

The output is CSV:
mode,rate_hz,block_frames,ns_per_frame_per_channel,realtime_fraction,checksum

The benchmark allocates its stereo buffers before measuring, warms up once,
and reports the median of five repetitions. Realtime_fraction is measured
wall time divided by simulated audio duration; it is NOT FL Studio CPU %,
the total plugin-host cost, or a JUCE-versus-SkellNative comparison.

CI validates compilation, basic execution and finite output only. Hardware,
thermal state and other processes affect the times. Never use fixed-speed
thresholds to gate code correctness.

## Next checks before product release

- Collect CPU usage from the same FL Studio session and buffer sizes, with
  matching JUCE gain processing and identical audio.
- Measure host-reported latency separately from DSP algorithm latency.
- Stress unusual buffers, 32/64-bit sample paths, 44.1/48/96 kHz, long
  sessions, plug-in reloads, UI resize and DPI.
- Test under CPU pressure and with multiple active GUI instances.
- Confirm automation gestures are editable in the Playlist and saved reliably.
- Preserve plugin/controller IDs and parameter state compatibility.
- Review final shared SkellDraw knobs and official skull independently.
