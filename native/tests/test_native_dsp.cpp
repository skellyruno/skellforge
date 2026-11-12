#include <SkellNative/Dsp.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <limits>

using namespace skellnative;
static constexpr double tau = 6.283185307179586;

static Block block(float* l, float* r, std::size_t n) {
    return {{{l, r}}, 2, n};
}

static bool rateTest(double rate) {
    constexpr std::size_t samples = 1536;
    std::array<float, samples> l{}, r{};
    for (std::size_t i=0; i<samples; ++i) {
        l[i] = static_cast<float>(0.65 * std::sin(tau * 440.0 * static_cast<double>(i) / rate));
        r[i] = -0.6f * l[i];
    }
    auto unityL=l, unityR=r;
    Gain gain;
    if (!gain.process(block(unityL.data(), unityR.data(), samples))) return false;
    for (std::size_t i=0; i<samples; ++i)
        if (unityL[i] != l[i] || unityR[i] != r[i]) return false;

    auto splitL=l, splitR=r, entireL=l, entireR=r;
    Lowpass whole, split;
    whole.prepare(rate); split.prepare(rate);
    whole.setCutoff(4200.0f); split.setCutoff(4200.0f);
    if (!whole.process(block(entireL.data(),entireR.data(),samples))) return false;
    std::array<std::size_t,8> sizes{{1,9,64,3,128,11,257,2}};
    std::size_t pos=0, step=0;
    while (pos < samples) {
        const auto count=std::min(samples-pos,sizes[step++%sizes.size()]);
        if (!split.process(block(splitL.data()+pos,splitR.data()+pos,count))) return false;
        pos += count;
    }
    for (std::size_t i=0; i<samples; ++i)
        if (std::abs(splitL[i]-entireL[i]) > 2e-5f
            || std::abs(splitR[i]-entireR[i]) > 2e-5f) return false;

    Saturate saturator;
    saturator.setDrive(3.0f);
    if (!saturator.process(block(splitL.data(),splitR.data(),samples))) return false;
    PeakSource peak;
    peak.measure(block(splitL.data(),splitR.data(),samples));
    if (!std::isfinite(peak.read()) || peak.read()<0 || peak.read()>1) return false;
    for (float x: splitL) if (!std::isfinite(x) || std::abs(x)>1.0f) return false;
    for (float x: splitR) if (!std::isfinite(x) || std::abs(x)>1.0f) return false;

    // No pointers are accessed for zero frames.
    if (!split.process(block(nullptr,nullptr,0))) return false;

    std::array<float,8> a{}, b{};
    a[0]=std::numeric_limits<float>::quiet_NaN();
    b[1]=std::numeric_limits<float>::infinity();
    if (!gain.process(block(a.data(),b.data(),a.size()))) return false;
    for (float x:a) if (!std::isfinite(x)) return false;
    for (float x:b) if (!std::isfinite(x)) return false;
    Lowpass guard;
    guard.prepare(rate);
    if (!guard.process(block(a.data(),b.data(),a.size()))) return false;
    if (gain.process(block(nullptr,b.data(),8))) return false;
    return true;
}

int main() {
    for (double rate: {44100.0, 48000.0, 96000.0}) {
        if (!rateTest(rate)) {
            std::fprintf(stderr,"SkellNative DSP test failed at %.0f Hz\n",rate);
            return 1;
        }
    }
    std::puts("SkellNative JUCE-free DSP tests passed at 44.1/48/96 kHz");
    return 0;
}
