# SkellDraw reusable components — v0.2 (experimental)

Goal: one reusable native UI layer across Skelly plugins, independent of JUCE
and of each individual VST3 class identity.

## Layered architecture

- native/skelldraw/include/SkellDraw/Components.h:
  **portable C++17**, no OS/host/SDK includes. Theme palette, Rect/Point,
  responsive 8:5 layout, normalized knob/drag/wheel behavior, power state
  toggle semantics, peak-meter smoothing, redraw dirty checks.
- native/skelldraw/include/SkellDraw/Win32Painter.h:
  Windows GDI adapter; shared metallic knob, powered indicator, meter,
  labels and drawing helpers. No VST3 dependency.
- native/vst3/Source/SkellDrawWin32.cpp:
  A host-embedded HWND adapter. Keeps a reusable double-buffered bitmap
  across redraws and recreates it only when the host resizes. Only
  invalidates on parameter/meter changes. The original approved gain
  knob geometry and shade are preserved. No flat line across knob.
- native/skelldraw/tests/test_components.cpp:
  independent layout/gesture/power/meter tests on Windows and Linux.
- native/vst3/tests/SkellDrawUiSmoke.cpp:
  real Win32 UI embedding, power rendering, peak bar pixels, scale
  constraint, mouse gesture and clean resource lifecycle.

## Output meter: real audio, not animation

SkellNative Gain adds read-only VST3 output parameter ID 1001 (Output Peak).
The audio processor measures the actual processed block and reports the
peak through VST3 outputParameterChanges if a host supplies that queue.
The UI controller reads that same parameter and forwards it to the
SkellDraw output-meter model.

**Host limitation:** VST3 hosts differ in whether/how they forward read-only
output parameters from processor to controller/UI. An idle meter in FL Studio
would require a different communication bridge; it must NEVER be animated
from gain setting, audio assumptions, or fake random levels. The user reported that the output meter responds during playback in
FL Studio, along with working gain automation and compatibility with saved
state from the earlier version (November 13, 2026). Those are MANUAL,
USER-REPORTED acceptance observations; exact meter calibration, peak mapping,
dropout behavior and cross-host compatibility have not been independently
measured. The UI smoke separately tests painting with known values; the
official Steinberg validator tests general VST3 contracts.

## Power button

SkellDraw includes reusable PowerButton (on/off state) and native painter.
It is tested separately, but **is not added to Gain yet**: production bypass
requires parameter identity, DAW automation and saved state semantics.
Don't draw an inert button merely for decoration.

## DSP/DAW identity invariants

- Existing Gain parameter ID 1000 and original processor/controller FUIDs
  remain unchanged to protect saved projects.
- Existing Gain state blob persists just Gain; read-only meter is not saved.
- Zero-latency gain algorithm and sample-offset automation remain untouched.
- Meter scans output only when the VST3 host provides outputParameterChanges.
- GUI handles are owned and released on the host UI thread, not audio thread.
- Cross-platform portable tests and native Win32 GUI tests must pass separately.

## Next

1. FL Studio follow-up: verify output-peak accuracy and stopping/decay,
   project save/reopen, resize and close/reopen, without fake movement.
   Initial meter movement, automation and legacy state recall were user-reported as passing.
2. Share the control palette through a proper SkellCore/SkellDraw bridge
   without imposing Skell Key's icon on other plugins.
3. Add per-component presets and accessible keyboard/focus behaviors.
4. Measure idle/editor paint cost and actual CPU using host + local
   matched JUCE vs native gain benchmarks on the user's laptop.
5. Approve plugin-specific skull geometry, power artwork and knobs before
   they become product defaults.
