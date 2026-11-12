# SkellForge without JUCE — staged SkellNative plan

## Is it possible?
Yes. JUCE is an application framework, not a requirement for VST3. Steinberg's
VST3 SDK (v3.8+) is MIT-licensed. SkellForge can use that SDK directly on
Windows while SkellNative owns DSP and future SkellDraw owns the UI.

Sources:
- https://github.com/steinbergmedia/vst3sdk
- https://www.steinberg.net/developers/vstsdk/
- https://juce.com/legal/juce-8-licence/

## What currently works?
- Studio design documents, parameter identity registry, validation, project
  generation, and build orchestration: Python, already independent of JUCE.
- native/ contains a real JUCE-FREE C++17 DSP-only foundation: gain,
  saturation, lowpass and peak measurement, separate CMake/CTest on Windows
  and Linux. THIS IS NOT A DIRECT-VST3 WRAPPER.
- The current generated VST3 still uses JUCE for plugin factory, processing
  host adapter, APVTS, editing, and actual UI rendering.
- Native host automation, GUI embedding, sample-rate negotiation,
  parameter state, and VST3 factory/lifecycle are not yet implemented.

## Intended architecture

SkellForge JSON schema and UI/DSP graph
  => immutable plugin/parameter IDs and DSP model
  => code generators
     => JUCE/VST3 backend for current shipping plug-ins
     => SkellNative/VST3 backend after the SDK adapter is validated

SkellCore remains the common musical/DSP behavior contract; adapters to
JUCE or direct VST3 should not silently change the sound, preset IDs, latency,
host state, or plugin identity.

## Milestones
1. Extract portable CPU-efficient audio modules, implement impulse, reference
   WAV, NaN/denormal, multirate, low-end CPU, and parity tests.
2. Implement a minimal Windows x64 plugin with Steinberg VST3 SDK alone.
   Factory, buses, lifecycle, process(), MIDI where relevant, host parameter
   queues, parameter gestures, save/restore state, and host PDC.
3. Build an independent graphics layer. Initially VSTGUI (SDK-provided) is a
   legitimate interim choice; later SkellDraw could use Win32/Direct2D.
   Must support host embedding, DPI, resizing, skins and automation gestures.
4. Allow Studio to export either backend once the native version passes the
   same VST3 validator, FL Studio session/automation and DSP parity checks.
5. Migrate conservatively: new small plugins first. Do not replace the
   backend of production plugins without explicit verification.

A production-capable custom Windows-only plugin framework is realistically
many months of work (roughly 6–18+ months for a focused solo effort), and a
full cross-platform JUCE alternative is a multi-year engineering project.
These are planning approximations, not guaranteed dates.

## Licensing and performance
Steinberg's SDK is MIT-licensed; comply with copyright/license notices.
VST branding/trademarks have additional guidelines. JUCE-based plugins
remain subject to JUCE licensing (AGPL or applicable commercial terms).
Review licensing for each DSP dependency and graphic asset separately.
Neither a JUCE replacement nor a new SDK guarantees lower latency or CPU:
host buffering, DSP architecture and algorithmic cost are usually decisive.

RELEASE RULE: JUCE remains the proven backend until native-generated VST3s
have real FL Studio validation, audio parity, automation and state recall.
