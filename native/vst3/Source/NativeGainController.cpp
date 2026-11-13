// Native gain controller + custom SkellDraw Win32 view; no JUCE or VSTGUI.
#include "NativeGainIDs.h"
#include "NativeGainStateBridge.h"
#include "SkellDrawWin32.h"
#include "public.sdk/source/vst/vsteditcontroller.h"
#include "pluginterfaces/base/ibstream.h"
#include <algorithm>
#include <cmath>
#include <cstring>

namespace Skelly::NativeGain {
using namespace Steinberg;
using namespace Steinberg::Vst;

class GainController final : public EditController, private GainViewDelegate {
public:
    static FUnknown* createInstance(void*) {
        return static_cast<IEditController*>(new GainController());
    }

    tresult PLUGIN_API initialize(FUnknown* context) override {
        const auto result = EditController::initialize(context);
        if (result != kResultOk) return result;
        parameters.addParameter(STR16("Gain"), nullptr, 0, 0.5,
                                ParameterInfo::kCanAutomate, kGainParam);
        // Output level is an indicator only. Host automation & saved gain
        // remain bound to kGainParam=1000 and the existing state format.
        parameters.addParameter(STR16("Output Peak"), nullptr, 0, 0.0,
                                ParameterInfo::kIsReadOnly, kOutputPeakParam);
        return kResultOk;
    }

    tresult PLUGIN_API setComponentState(IBStream* state) override {
        const auto normalized = readNormalizedGain(state);
        if (!normalized) return kResultFalse;
        return setParamNormalized(kGainParam, *normalized);
    }

    IPlugView* PLUGIN_API createView(FIDString name) override {
        if (!name || std::strcmp(name, ViewType::kEditor)!=0)
            return nullptr;
        // The view retains a COM/FUnknown reference to this controller so
        // its delegate can't dangle if the host releases the controller first.
        return new SkellDrawView(*this, static_cast<IEditController*>(this));
    }

private:
    float getPeak() const noexcept override {
        const double value=const_cast<GainController*>(this)
                                ->getParamNormalized(kOutputPeakParam);
        return std::isfinite(value)
            ? std::clamp(static_cast<float>(value),0.0f,1.0f) : 0.0f;
    }
    float getGain() const noexcept override {
        const double value = const_cast<GainController*>(this)
                                 ->getParamNormalized(kGainParam);
        return std::isfinite(value)
            ? std::clamp(static_cast<float>(value),0.0f,1.0f) : 0.5f;
    }
    void beginGain() noexcept override {
        beginEdit(kGainParam);
    }
    void updateGain(float value) noexcept override {
        if (!std::isfinite(value)) return;
        const auto normalized=std::clamp(static_cast<double>(value),0.0,1.0);
        setParamNormalized(kGainParam,normalized);  // update local GUI immediately
        performEdit(kGainParam,normalized);          // send DAW automation gesture
    }
    void endGain() noexcept override {
        endEdit(kGainParam);
    }
};

FUnknown* createController(void* context) {
    return GainController::createInstance(context);
}
} // namespace Skelly::NativeGain
