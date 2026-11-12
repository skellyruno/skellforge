#pragma once
// SkellNative v0: framework-independent, allocation-free stereo DSP primitives.
// No JUCE or Steinberg headers. Plain C++17.
//
// This does not yet implement a VST3 host interface or a native UI.
// Input/output float planes are owned by the caller. Never allocate in process().
#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstddef>

namespace skellnative {

struct Block {
    std::array<float*, 2> channel{{nullptr, nullptr}};
    std::size_t channelCount = 0;
    std::size_t frames = 0;

    bool valid() const noexcept {
        if (channelCount < 1 || channelCount > channel.size()) return false;
        for (std::size_t ch = 0; ch < channelCount; ++ch)
            if (channel[ch] == nullptr) return frames == 0;
        return true;
    }
};

inline float finiteOrZero(float sample) noexcept {
    return std::isfinite(sample) ? sample : 0.0f;
}

inline float clampFinite(float value, float low, float high, float fallback) noexcept {
    return std::isfinite(value) ? std::clamp(value, low, high) : fallback;
}

class Gain final {
public:
    void setLinear(float value) noexcept {
        linear_ = clampFinite(value, 0.0f, 4.0f, 1.0f);
    }
    float value() const noexcept { return linear_; }

    bool process(Block block) const noexcept {
        if (!block.valid()) return false;
        for (std::size_t ch = 0; ch < block.channelCount; ++ch) {
            for (std::size_t i = 0; i < block.frames; ++i) {
                const float clean = finiteOrZero(block.channel[ch][i]);
                block.channel[ch][i] = clean * linear_;
            }
        }
        return true;
    }
private:
    float linear_ = 1.0f;
};

class Saturate final {
public:
    void setDrive(float value) noexcept {
        drive_ = clampFinite(value, 1.0f, 10.0f, 1.0f);
        inverse_ = 1.0f / std::tanh(drive_);
    }

    bool process(Block block) const noexcept {
        if (!block.valid()) return false;
        for (std::size_t ch = 0; ch < block.channelCount; ++ch) {
            for (std::size_t i = 0; i < block.frames; ++i)
                block.channel[ch][i] = std::tanh(finiteOrZero(block.channel[ch][i]) * drive_) * inverse_;
        }
        return true;
    }
private:
    float drive_ = 1.0f;
    float inverse_ = 1.0f / std::tanh(1.0f);
};

class Lowpass final {
public:
    void prepare(double sampleRate) noexcept {
        rate_ = (std::isfinite(sampleRate) && sampleRate > 1000.0)
            ? std::min(sampleRate, 192000.0) : 48000.0;
        state_.fill(0.0f);
        setCutoff(cutoff_);
    }

    void setCutoff(float frequency) noexcept {
        cutoff_ = clampFinite(frequency, 20.0f, 20000.0f, 8000.0f);
        const double hz = std::min(static_cast<double>(cutoff_), 0.45 * rate_);
        coefficient_ = static_cast<float>(std::exp(-6.283185307179586 * hz / rate_));
    }

    bool process(Block block) noexcept {
        if (!block.valid()) return false;
        for (std::size_t ch = 0; ch < block.channelCount; ++ch) {
            float history = state_[ch];
            for (std::size_t i = 0; i < block.frames; ++i) {
                const float clean = finiteOrZero(block.channel[ch][i]);
                history = coefficient_ * history + (1.0f - coefficient_) * clean;
                block.channel[ch][i] = history;
            }
            state_[ch] = std::abs(history) < 1.0e-20f ? 0.0f : history;
        }
        return true;
    }
private:
    double rate_ = 48000.0;
    float cutoff_ = 8000.0f;
    float coefficient_ = 0.0f;
    std::array<float, 2> state_{{0.0f, 0.0f}};
};

class PeakSource final {
public:
    void measure(Block block) noexcept {
        if (!block.valid()) {
            peak_.store(0.0f, std::memory_order_relaxed);
            return;
        }
        float maxMagnitude = 0.0f;
        for (std::size_t ch = 0; ch < block.channelCount; ++ch)
            for (std::size_t i = 0; i < block.frames; ++i)
                maxMagnitude = std::max(maxMagnitude,
                                         std::abs(finiteOrZero(block.channel[ch][i])));
        peak_.store(std::min(maxMagnitude, 1.0f), std::memory_order_relaxed);
    }

    float read() const noexcept { return peak_.load(std::memory_order_relaxed); }
private:
    std::atomic<float> peak_{0.0f};
};

} // namespace skellnative
