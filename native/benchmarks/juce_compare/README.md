# Fair gain DSP benchmark on your Windows Ryzen laptop

This project runs JUCE and SkellNative gain in **the same compiled executable**,
on the same Windows CPU/compiler, with matching finite stereo sample buffers.
It does **not** measure the FL Studio host, driver, VST3 wrapper, GUI redraws,
latency or whole-plugin CPU. No unmeasured speed advantage is claimed.

## One-command local run

Open PowerShell in the SkellForge checkout:

    .\native\benchmarks\juce_compare\Run-GainCompare.ps1

If JUCE 8.0.12 is already cloned:

    .\native\benchmarks\juce_compare\Run-GainCompare.ps1 -JucePath C:\src\JUCE

Requires CMake, Git and Visual Studio Desktop C++ (MSVC). First configuration
downloads the pinned JUCE revision if a local JUCE_PATH is not supplied.
The script uses Release x64 and --parallel 2 to limit laptop resource use,
then saves a CSV on the Desktop.

## Method and interpretation

- Both processors get the same float32 planar stereo data.
- Both change the gain value each block: 0.5x then 2.0x.
- The alternating gain pattern avoids benchmarking an optimized-away unity
  gain and prevents cumulative fading, while keeping data finite.
- All nine combinations: 44.1, 48 and 96 kHz × 64/256/1024 frames.
- One warmup plus five timed trials per case; median time reported.
- Output checks reject absolute sample errors above 1e-5.
- native_over_juce below 1 means native timed faster **for that DSP kernel
  on the particular computer during that run**, not in every VST3 host.
- CPU governor, background activity, turbo, thermals and compiler flags can
  affect results. Repeat when possible.

## Separate host/GUI measurement still needed

To compare whole-plugin CPU in FL Studio, use equivalent gain-only JUCE and
SkellNative builds, identical ASIO buffer, input audio, sample rate,
automation density and active instance count. Measure with and without GUIs
opened for at least 30 seconds each. Include dropouts and host-reported
latency separately. The local script does not automate FL Studio.

This is meant for the user's own laptop. Cloud runners only check the
build and signal parity; their timings do not establish laptop performance.
