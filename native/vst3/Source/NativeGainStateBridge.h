#pragma once
// Versioned SkellNative snapshot bridge. Only on host state threads,
// NEVER called from the real-time process() callback.
#include "pluginterfaces/base/ibstream.h"
#include <SkellNative/State.h>
#include "NativeGainIDs.h"
#include <array>
#include <cmath>
#include <cstdint>
#include <optional>
#include <vector>

namespace Skelly::NativeGain {

inline std::optional<float> readNormalizedGain(Steinberg::IBStream* stream) {
    if (!stream) return std::nullopt;
    std::vector<std::uint8_t> bytes;
    bytes.reserve(128);
    std::array<std::uint8_t, 512> chunk{};
    while (bytes.size() <= 16384) {
        Steinberg::int32 actual = 0;
        const auto result = stream->read(chunk.data(),
                                         static_cast<Steinberg::int32>(chunk.size()),
                                         &actual);
        if (actual < 0 || actual > static_cast<Steinberg::int32>(chunk.size()))
            return std::nullopt;
        if (actual > 0) {
            if (bytes.size() + static_cast<std::size_t>(actual) > 16384)
                return std::nullopt;
            bytes.insert(bytes.end(), chunk.begin(), chunk.begin() + actual);
        }
        if (actual == 0) break;
        if (result != Steinberg::kResultOk) return std::nullopt;
    }
    const auto decoded = skellnative::sdk::decodeState(kProductId, bytes);
    if (!decoded || decoded->parameters.size() != 1 ||
        decoded->parameters[0].persistentId != kParamId)
        return std::nullopt;
    return decoded->parameters[0].normalized;
}

inline bool writeNormalizedGain(Steinberg::IBStream* stream, float value) {
    if (!stream || !std::isfinite(value) || value < 0.0f || value > 1.0f)
        return false;
    skellnative::sdk::StateSnapshot state;
    state.parameters.push_back({kParamId, value});
    const auto encoded = skellnative::sdk::encodeState(kProductId, state);
    if (!encoded) return false;
    Steinberg::int32 written = 0;
    const auto result = stream->write(encoded->data(),
                                      static_cast<Steinberg::int32>(encoded->size()),
                                      &written);
    return result == Steinberg::kResultOk
        && written == static_cast<Steinberg::int32>(encoded->size());
}
} // namespace Skelly::NativeGain
