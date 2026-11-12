// Original Skelly controller/parameter adapter, independent of JUCE.
#include "NativeGainIDs.h"
#include "NativeGainStateBridge.h"
#include "public.sdk/source/vst/vsteditcontroller.h"
#include "pluginterfaces/base/ibstream.h"

namespace Skelly::NativeGain {
using namespace Steinberg;
using namespace Steinberg::Vst;

class GainController final : public EditController {
public:
    static FUnknown* createInstance(void*) {
        return static_cast<IEditController*>(new GainController());
    }

    tresult PLUGIN_API initialize(FUnknown* context) override {
        const auto result = EditController::initialize(context);
        if (result != kResultOk) return result;
        parameters.addParameter(STR16("Gain"), nullptr, 0, 0.5,
                                ParameterInfo::kCanAutomate, kGainParam);
        return kResultOk;
    }

    tresult PLUGIN_API setComponentState(IBStream* state) override {
        const auto normalized = readNormalizedGain(state);
        if (!normalized) return kResultFalse;
        return setParamNormalized(kGainParam, *normalized);
    }

    IPlugView* PLUGIN_API createView(FIDString) override {
        return nullptr; // For now: use the host's generic parameter UI
    }
};

FUnknown* createController(void* context) {
    return GainController::createInstance(context);
}
} // namespace Skelly::NativeGain
