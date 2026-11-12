# SkellNative developer SDK 0.1 - source-only prototype

The SkellNative SDK is the Skelly-owned programmer-facing interface for real-time audio processors. This does NOT replace the Steinberg VST3 SDK or implement a VST3 plugin yet.

Working paths:
- native/include/SkellNative/Dsp.h: portable C++17 gain, saturation, lowpass, lock-free peak meter.
- native/include/SkellNative/PluginApi.h: plugin identity, stable parameter descriptors, normalized parameter changes, host process context, and Processor class.
- native/tests/test_native_dsp.cpp: independent cross-platform source tests.
- native/CMakeLists.txt: zero JUCE or Steinberg dependencies.

The process contract:
- Host provides planar float32 mono/stereo buffers and event arrays; the processor does not own their memory.
- No allocations, locks, GUI access, filesystem calls, exceptions or dynamic memory in process().
- Parameter IDs are persistent strings, not positional indices.
- Parameter changes specify normalized values from 0 to 1 and a bounded sample offset.
- Implementations report latency in samples. Integration with the host's latency and state APIs is still pending.
- prepare and reset happen outside the hard real-time callback.

This is a C++ SOURCE-level interface. It is NOT a stable dynamic-link binary ABI across compilers. A versioned C ABI with explicit memory ownership, compatibility fields and stable calling conventions is necessary before distributing binary third-party modules.

## Experimental versioned state snapshots

The portable `native/include/SkellNative/State.h` now provides a bounded,
deterministic state encoding for normalized parameter values with a persistent
product ID and parameter IDs. It uses explicit little-endian fields, format
version 1, bounds checks, and an FNV-1a integrity checksum.

This is **off-audio-thread only**: it allocates and must not be called in
`process()`. The checksum is for accidental corruption detection, **not
authentication or encryption**. The native VST3 adapter must map this safely
onto actual host getState/setState and verify backwards compatibility.

C++ regression fixtures check exact round trips, duplicate IDs, truncated
buffers, wrong product identity, nonfinite values and corrupted payloads.

Roadmap:
1. Audit DSP parity and runtime cost against the JUCE path.
2. Implement a direct-Steinberg-SDK Windows gain plugin that adapts this contract.
3. Add host automation, project save/restore, reliable instance lifecycle, and VST3 validation.
4. Add the native UI bridge (initially SDK VSTGUI or future SkellDraw).
5. Only enable SkellNative output in Forge after it passes real FL Studio tests.

Steinberg SDK official: https://github.com/steinbergmedia/vst3sdk
Steinberg licensing: https://www.steinberg.net/developers/vstsdk/

A custom SDK is viable, but a plugin intended for FL Studio must comply with the external VST3 host protocol. Do not remove JUCE support prematurely.
