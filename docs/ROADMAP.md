# SkellForge roadmap

## Stage 1 — Foundational forge (this repository, v0.1)

- Windows VST3-only project generator, zero-effect default audio path
- Keep VST3 manufacturer/product IDs and APVTS parameter IDs stable
- Pin SkellCore by Git SHA, use existing SkellCore DSP and visual components
- Automated manifest validation, unit tests, Windows VST3 CI smoke build
- Verify one bundle and package it without overwriting releases
- No existing plugin migration and no silent SkellCore DSP replacement

## Stage 2 — Reliable shared engineering

- Real FL Studio open/save/reopen and automation regression fixtures
- Audio impulse, signal parity, latency, NaN/denormal and CPU benchmark harness
- Provenance and plugin-ID registry synced safely with SkellWorld
- SkellCore-approved master skull SVG/vector asset once selected
- Reusable controls, layout constraints, meter and preset schema
- Installer, rollback and signed artifact integration with Skelly Project Hub

## Stage 3 — Visual SkellForge (later)

- JSON-backed graph of DSP blocks, audio routing and parameter connections
- Visual UI editor (drag components, anchors, responsive layouts)
- Deterministic code generation with reviewed templates and version pinning
- Preview and inspection without touching the audio processing thread
- Reversible graph->source builds; protect existing plugin preset/automation IDs
- Per-block DSP unit tests and explicit latency contracts

## Out of scope until earned

- Replacement for JUCE, independent VST3 hosting or native UI rendering
- Drag-drop visual editing as a claim before it really functions
- Automatic porting of all Skelly plugins or changing their DSP
- Public third-party plugin-building service without licensing review

## Acceptance gates

A release candidate must pass CLI tests, CI-generated native VST3 build,
manual FL Studio host tests, saved project recall, host automation/undo,
preset compatibility, varied block/sample-rate checks, honest latency/PDC
tests and CPU profiling on low-spec Windows hardware.
