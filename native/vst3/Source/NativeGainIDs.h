#pragma once
#include "pluginterfaces/base/funknown.h"
#include "pluginterfaces/vst/vsttypes.h"

namespace Skelly::NativeGain {

// Prototype-only FUIDs. Do not reuse for any released Skelly product.
// Two independent UUID v4 identifiers generated for this test product.
static DECLARE_UID(kProcessorUID, 0xD74FB65B, 0xC388486F, 0xA8ACC80F, 0x23B6DA4E);
static DECLARE_UID(kControllerUID, 0x79BFB11F, 0xA5BD4C50, 0x9602ED4E, 0xC4E515D8);

inline constexpr Steinberg::Vst::ParamID kGainParam = 1000u;
// Read-only output metering: never renumber the existing automatable gain 1000.
inline constexpr Steinberg::Vst::ParamID kOutputPeakParam = 1001u;
inline constexpr char kProductId[] = "skellnative.gain.prototype";
inline constexpr char kParamId[] = "gain_linear";
} // namespace Skelly::NativeGain
