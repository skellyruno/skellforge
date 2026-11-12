// Original Skelly VST3 audio adapter, independent of JUCE and VSTGUI.
// The gain algorithm uses native/include/SkellNative/Dsp.h.
#include "NativeGainIDs.h"
#include "NativeGainStateBridge.h"
#include <SkellNative/Dsp.h>
#include "public.sdk/source/vst/vstaudioeffect.h"
#include "pluginterfaces/vst/ivstparameterchanges.h"
#include <algorithm>
#include <array>
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
        int32 nextPoint = 0;
        int32 nextOffset = 0;
        ParamValue nextValue = 0.0;
        const auto applyAutomation = [&](int32 frame) noexcept {
            while (gainQueue && nextPoint < points) {
                if (gainQueue->getPoint(nextPoint, nextOffset, nextValue) != kResultTrue) {
                    ++nextPoint;
                    continue;
                }
                if (nextOffset > frame) break;
                if (nextOffset >= 0 && std::isfinite(nextValue))
                    normalized_ = std::clamp(static_cast<float>(nextValue), 0.0f, 1.0f);
                ++nextPoint;
            }
        };

        if (data.numSamples == 0) {
            applyAutomation(0);
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
        if ((data.symbolicSampleSize == kSample32 &&
             (!input.channelBuffers32 || !output.channelBuffers32)) ||
            (data.symbolicSampleSize == kSample64 &&
             (!input.channelBuffers64 || !output.channelBuffers64)))
            return kResultFalse;

        const auto channelMask = (static_cast<uint64>(1) << channels) - 1;
        const bool silentInput = (input.silenceFlags & channelMask) == channelMask;
        output.silenceFlags = silentInput ? channelMask : 0;

        // Each host event is applied at its sample offset (not block-end).
        // There are no heap allocations, locks, GUI calls or file accesses.
        for (int32 i = 0; i < data.numSamples; ++i) {
            applyAutomation(i);
            const float gain = std::clamp(normalized_ * 2.0f, 0.0f, 2.0f);
            if (data.symbolicSampleSize == kSample32) {
                kernel_.setLinear(gain);
                skellnative::Block oneSample;
                oneSample.channelCount = static_cast<std::size_t>(channels);
                oneSample.frames = 1;
                for (int32 ch = 0; ch < channels; ++ch) {
                    auto* dest = output.channelBuffers32[ch];
                    const auto* src = input.channelBuffers32[ch];
                    if (!dest || (!src && !silentInput)) return kResultFalse;
                    dest[i] = silentInput ? 0.0f : skellnative::finiteOrZero(src[i]);
                    oneSample.channel[ch] = dest + i;
                }
                if (!kernel_.process(oneSample)) return kResultFalse;
            } else {
                for (int32 ch = 0; ch < channels; ++ch) {
                    auto* dest = output.channelBuffers64[ch];
                    const auto* src = input.channelBuffers64[ch];
                    if (!dest || (!src && !silentInput)) return kResultFalse;
                    const double sample = silentInput ? 0.0 : src[i];
                    dest[i] = std::isfinite(sample)
                        ? sample * static_cast<double>(gain) : 0.0;
                }
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
