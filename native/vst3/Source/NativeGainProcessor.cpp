// Original Skelly VST3 audio adapter, independent of JUCE and VSTGUI.
// The gain algorithm uses native/include/SkellNative/Dsp.h.
#include "NativeGainIDs.h"
#include "NativeGainStateBridge.h"
#include <SkellNative/Dsp.h>
#include "public.sdk/source/vst/vstaudioeffect.h"
#include "pluginterfaces/vst/ivstparameterchanges.h"
#include <algorithm>
#include <cstring>
#include <cmath>

namespace Skelly::NativeGain {
using namespace Steinberg;
using namespace Steinberg::Vst;

class GainProcessor final : public AudioEffect {
public:
    GainProcessor() { setControllerClass(FUID::fromTUID(kControllerUID)); }
    static FUnknown* createInstance(void*) {
        return static_cast<IAudioProcessor*>(new GainProcessor());
    }

    tresult PLUGIN_API initialize(FUnknown* context) override {
        const auto result = AudioEffect::initialize(context);
        if (result != kResultOk) return result;
        addAudioInput(STR16("Input"), SpeakerArr::kStereo);
        addAudioOutput(STR16("Output"), SpeakerArr::kStereo);
        return kResultOk;
    }

    tresult PLUGIN_API setBusArrangements(SpeakerArrangement* ins, int32 countIn,
                                          SpeakerArrangement* outs, int32 countOut) override {
        if (!ins || !outs || countIn != 1 || countOut != 1 || ins[0] != outs[0])
            return kResultFalse;
        const int32 channels = SpeakerArr::getChannelCount(ins[0]);
        if (channels != 1 && channels != 2) return kResultFalse;
        return AudioEffect::setBusArrangements(ins, countIn, outs, countOut);
    }

    tresult PLUGIN_API canProcessSampleSize(int32 size) override {
        return (size == kSample32 || size == kSample64) ? kResultTrue : kResultFalse;
    }

    uint32 PLUGIN_API getLatencySamples() override { return 0; }

    tresult PLUGIN_API process(ProcessData& data) override {
        if (data.numSamples < 0) return kInvalidArgument;

        IParamValueQueue* gainQueue = nullptr;
        if (data.inputParameterChanges) {
            const int32 numQueues = data.inputParameterChanges->getParameterCount();
            for (int32 i = 0; i < numQueues; ++i) {
                auto* queue = data.inputParameterChanges->getParameterData(i);
                if (queue && queue->getParameterId() == kGainParam) {
                    gainQueue = queue;
                    break;
                }
            }
        }
        const int32 points = gainQueue ? gainQueue->getPointCount() : 0;
        if (data.numSamples == 0) {
            // A zero-length block can still carry parameter changes.
            for (int32 point = 0; point < points; ++point) {
                int32 at = 0;
                ParamValue value = 0.0;
                if (gainQueue->getPoint(point, at, value) == kResultTrue &&
                    at >= 0 && std::isfinite(value))
                    normalized_ = std::clamp(static_cast<float>(value), 0.0f, 1.0f);
            }
            return kResultOk;
        }

        if (!data.inputs || !data.outputs || data.numInputs < 1 || data.numOutputs < 1)
            return kResultFalse;
        auto& input = data.inputs[0];
        auto& output = data.outputs[0];
        const int32 channels = std::min(input.numChannels, output.numChannels);
        if (channels < 1 || channels > 2) return kResultFalse;
        if (data.symbolicSampleSize != kSample32 && data.symbolicSampleSize != kSample64)
            return kResultFalse;

        const bool float32 = data.symbolicSampleSize == kSample32;
        if ((float32 && (!input.channelBuffers32 || !output.channelBuffers32)) ||
            (!float32 && (!input.channelBuffers64 || !output.channelBuffers64)))
            return kResultFalse;

        const auto channelMask = (static_cast<uint64>(1) << channels) - 1;
        output.silenceFlags = input.silenceFlags & channelMask;
        const bool capturePeak = data.outputParameterChanges != nullptr;
        float processedPeak = 0.0f;

        // Validate ALL host channel pointers before changing any output.
        for (int32 ch = 0; ch < channels; ++ch) {
            const bool silent = (input.silenceFlags & (static_cast<uint64>(1) << ch)) != 0;
            if (float32) {
                if (!output.channelBuffers32[ch] || (!silent && !input.channelBuffers32[ch]))
                    return kResultFalse;
            } else {
                if (!output.channelBuffers64[ch] || (!silent && !input.channelBuffers64[ch]))
                    return kResultFalse;
            }
        }

        // Process one contiguous span per automation point, usually ONE call
        // for the whole block. No allocations, locks or per-sample host queries.
        const auto processRange = [&](int32 begin, int32 end) noexcept -> bool {
            if (end <= begin) return true;
            const auto frames = static_cast<std::size_t>(end - begin);
            const float linear = std::clamp(normalized_ * 2.0f, 0.0f, 2.0f);
            if (float32) {
                skellnative::Block block;
                block.frames = frames;
                block.channelCount = static_cast<std::size_t>(channels);
                for (int32 ch = 0; ch < channels; ++ch) {
                    float* dest = output.channelBuffers32[ch] + begin;
                    const bool silent = (input.silenceFlags &
                        (static_cast<uint64>(1) << ch)) != 0;
                    if (silent) {
                        std::fill_n(dest, frames, 0.0f);
                    } else {
                        const float* source = input.channelBuffers32[ch] + begin;
                        if (dest != source)
                            std::memmove(dest, source, frames * sizeof(float));
                    }
                    block.channel[static_cast<std::size_t>(ch)] = dest;
                }
                kernel_.setLinear(linear);
                if (!capturePeak) return kernel_.process(block);
                float spanPeak=0.0f;
                if (!kernel_.processWithPeak(block,spanPeak)) return false;
                processedPeak=std::max(processedPeak,spanPeak);
                return true;
            }
            for (int32 ch = 0; ch < channels; ++ch) {
                double* dest = output.channelBuffers64[ch] + begin;
                const bool silent = (input.silenceFlags &
                    (static_cast<uint64>(1) << ch)) != 0;
                if (silent) {
                    std::fill_n(dest, frames, 0.0);
                    continue;
                }
                const double* source = input.channelBuffers64[ch] + begin;
                for (std::size_t i = 0; i < frames; ++i) {
                    const double sample = source[i];
                    const double result = std::isfinite(sample)
                        ? sample * static_cast<double>(linear) : 0.0;
                    dest[i] = std::isfinite(result) ? result : 0.0;
                }
            }
            return true;
        };

        int32 cursor = 0;
        for (int32 point = 0; point < points; ++point) {
            int32 offset = 0;
            ParamValue value = 0.0;
            if (gainQueue->getPoint(point, offset, value) != kResultTrue ||
                offset < 0 || !std::isfinite(value))
                continue;
            const int32 at = std::min(offset, data.numSamples);
            if (at < cursor) continue;  // Ignore unsorted host events.
            if (!processRange(cursor, at)) return kResultFalse;
            normalized_ = std::clamp(static_cast<float>(value), 0.0f, 1.0f);
            cursor = at;
        }
        if (!processRange(cursor, data.numSamples)) return kResultFalse;

        // The f32 path fuses gain and peak in SSE2; the f64 path
        // deliberately uses the original second scan. On the first
        // same-runner v0.4/v0.5 measurements, tracking f64 peak inside its
        // scalar gain loop prevented efficient code generation and lost
        // performance. Keep the proven f64 path until separately optimized.
        if (capturePeak && !float32) {
            for (int32 channel=0;channel<channels;++channel) {
                const double* samples=output.channelBuffers64[channel];
                for (int32 i=0;i<data.numSamples;++i) {
                    const double value=std::abs(samples[i]);
                    processedPeak=std::max(processedPeak,std::isfinite(value)
                        ?static_cast<float>(std::min(value,1.0)):1.0f);
                }
            }
        }
        if (capturePeak) {
            int32 queueIndex=0;
            auto* meterQueue=data.outputParameterChanges->addParameterData(
                kOutputPeakParam,queueIndex);
            if(meterQueue) {
                int32 eventIndex=0;
                meterQueue->addPoint(data.numSamples-1,
                                     static_cast<double>(processedPeak),
                                     eventIndex);
            }
        }
        return kResultOk;
    }

    tresult PLUGIN_API setState(IBStream* state) override {
        const auto gain = readNormalizedGain(state);
        if (!gain) return kResultFalse;
        normalized_ = *gain;
        kernel_.setLinear(normalized_ * 2.0f);
        return kResultOk;
    }

    tresult PLUGIN_API getState(IBStream* state) override {
        return writeNormalizedGain(state, normalized_) ? kResultOk : kResultFalse;
    }

private:
    float normalized_ = 0.5f;  // Unity gain is the neutral state.
    skellnative::Gain kernel_;
};

FUnknown* createProcessor(void* context) {
    return GainProcessor::createInstance(context);
}
} // namespace Skelly::NativeGain
