# SkellLang 0.1 - declarative plugin design language

Status: experimental. This is NOT a general-purpose compiler and NOT a JUCE-free audio runtime. The language compiles to SkellForge Studio's validated JSON design model; generated plugins still use the current JUCE backend.

Example from examples/SkellWarmth.skell:

    skell 1
    canvas 440 310
    fx saturate warmth 2.5 on
    fx lowpass tone 8500 on
    knob drive_knob warmth "DRIVE" 18 128 105 110
    knob tone_knob tone "TONE" 315 128 105 110
    meter output_meter "OUT" 20 270 155 22
    text brand_label "SKELLY" 192 270 212 22

Supported statements:
- skell 1: required version declaration.
- canvas WIDTH HEIGHT: validated drawing area.
- fx saturate|lowpass ID VALUE on|off: add a serial effect.
- knob ID NODE "CAPTION" X Y W H: host automatable parameter control.
- meter ID "CAPTION" X Y W H: real audio output meter.
- text ID "CAPTION" X Y W H: label.
- move skull|title|gain_label|gain_knob X Y W H: move a built-in control.

Usage on Windows:

    python -m skellforge lang-check examples/SkellWarmth.skell
    python -m skellforge lang-export examples/SkellWarmth.skell scene.json
    python -m skellforge lang-new examples/SkellWarmth.skell "Skell Warmth" ../skell-warmth --code SZ91
    python -m skellforge lang-from-studio ../skell-warmth skell-warmth.skell
    python -m skellforge build-local ../skell-warmth

The compiler has no loops, eval, code imports, runtime execution or file I/O from the source language. Source size and line count are bounded; all resulting DSP, layout and parameter IDs are validated by Studio.

The export and new-project commands NEVER overwrite existing paths. Lang-new compiles and validates before creating a project, uses the original unique-code safeguards and emits the existing generated JUCE source. SkellLang now supports deterministic Studio-to-source conversion and source-to-Studio compilation for supported fields. The exporter checks exact round-trip equivalence, preserves live and retired parameter IDs via reserve statements, and fails closed if an unsupported future Studio field would be lost. A graphical live source editor and generic scripting functions do not yet exist.

Future milestones: typed parameters and units; versioned preset/state schemas; integrated visual/text editing and diffs; typed DSP graph with latency; safe compile-time DSP functions; eventually a native backend. Do not interpret user language statements on the audio thread.

**Naming:** [Skellenese and SkellCipher](BRAND_LANGUAGES.md) are fan-facing culture and artistic secret-writing, not alternate compiler names. The .skell extension and skell 1 syntax remain stable.
