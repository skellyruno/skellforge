#pragma once
// SkellNative SDK draft (C++ source-level contract, NOT a VST3 SDK replacement).
// Backend-neutral, host-owned audio buffers, normalized parameter updates.
// No JUCE or Steinberg headers. This is NOT a stable binary/FFI ABI yet.
#include <SkellNative/Dsp.h>
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>

namespace skellnative::sdk {

inline constexpr std::uint32_t kVersionMajor = 0;
inline constexpr std::uint32_t kVersionMinor = 1;

struct Parameter {
    const char* persistentId = nullptr;  // Never recycle after release.
    const char* displayName = nullptr;
    float minimum = 0.0f;
    float maximum = 1.0f;
    float initial = 0.0f;

    bool valid() const noexcept {
        return persistentId && *persistentId && displayName
            && std::isfinite(minimum) && std::isfinite(maximum)
            && std::isfinite(initial) && minimum < maximum
            && initial >= minimum && initial <= maximum;
    }
};

struct Descriptor {
    const char* productId = nullptr;
    const char* displayName = nullptr;
    const char* vendor = nullptr;
    const Parameter* parameters = nullptr;
    std::size_t parameterCount = 0;

    bool valid() const noexcept {
        if (!productId || !*productId || !displayName || !*displayName
            || !vendor || !*vendor || parameterCount > 128
            || (parameterCount && !parameters)) return false;
        for (std::size_t i = 0; i < parameterCount; ++i) {
            if (!parameters[i].valid()) return false;
            for (std::size_t other = 0; other < i; ++other) {
                const char* a = parameters[i].persistentId;
                const char* b = parameters[other].persistentId;
                // Compare without std::string allocations.
                std::size_t index = 0;
                while (a[index] && b[index] && a[index] == b[index]) ++index;
                if (!a[index] && !b[index]) return false;
            }
        }
        return true;
    }
};

struct ParameterChange {
    const char* persistentId = nullptr;
    float normalized = 0.0f;       // 0..1; physical scaling handled by processor.
    std::uint32_t sampleOffset = 0; // Offset inside current audio block.
};

struct ProcessContext {
    skellnative::Block audio;       // Two max, planar f32, caller-owned.
    double sampleRate = 48000.0;
    std::uint64_t projectSample = 0;
    bool playing = false;
    const ParameterChange* changes = nullptr;
    std::size_t changeCount = 0;

    bool valid() const noexcept {
        if (!audio.valid() || !std::isfinite(sampleRate)
            || sampleRate < 1000.0 || sampleRate > 384000.0
            || changeCount > 1024 || (changeCount && !changes)) return false;
        for (std::size_t i = 0; i < changeCount; ++i) {
            const auto& event = changes[i];
            if (!event.persistentId || !*event.persistentId
                || !std::isfinite(event.normalized)
                || event.normalized < 0.0f || event.normalized > 1.0f
                || event.sampleOffset >= audio.frames) return false;
        }
        return true;
    }
};

// C++ source interface, NOT an ABI promise across different compilers.
// Implementations must process without allocation, exceptions, mutexes,
// filesystem or GUI operations on the audio callback.
class Processor {
public:
    virtual ~Processor() = default;
    virtual bool prepare(double sampleRate, std::uint32_t maxFrames) noexcept = 0;
    virtual void reset() noexcept = 0;
    virtual bool process(const ProcessContext& context) noexcept = 0;
    virtual std::uint32_t latencySamples() const noexcept = 0;
};

} // namespace skellnative::sdk
