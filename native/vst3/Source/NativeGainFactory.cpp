// Original Skelly VST3 factory, two classes: audio processor and controller.
#include "NativeGainIDs.h"
#include "pluginterfaces/vst/vsttypes.h"
#include "pluginterfaces/vst/ivstaudioprocessor.h"
#include "pluginterfaces/vst/ivsteditcontroller.h"
// Must be last: ivstcomponent.h defines the older factory macros.
// The constexpr factory header replaces those macros and fixes factory export.
#include "public.sdk/source/main/pluginfactory_constexpr.h"

namespace Skelly::NativeGain {
Steinberg::FUnknown* createProcessor(void*);
Steinberg::FUnknown* createController(void*);
}

using namespace Steinberg;
using namespace Steinberg::Vst;

BEGIN_FACTORY_DEF("Skell Audio", "https://skellyr.uno", "info@skellyr.uno", 2)

DEF_CLASS(Skelly::NativeGain::kProcessorUID, PClassInfo::kManyInstances,
          kVstAudioEffectClass, "SkellNative Gain Prototype",
          Vst::kDistributable, "Fx|Tools", "0.1.0",
          kVstVersionString, Skelly::NativeGain::createProcessor, nullptr)

DEF_CLASS(Skelly::NativeGain::kControllerUID, PClassInfo::kManyInstances,
          kVstComponentControllerClass, "SkellNative Gain Controller",
          0, "", "0.1.0",
          kVstVersionString, Skelly::NativeGain::createController, nullptr)

END_FACTORY
