#include <SkellNative/Dsp.h>
#include <SkellNative/PluginApi.h>
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

static bool testSdkContract() {
    using namespace skellnative::sdk;
    const std::array<Parameter, 2> params{{
        {"gain_db", "Gain", -24.0f, 24.0f, 0.0f},
        {"fx_warmth_drive", "Drive", 1.0f, 10.0f, 2.5f}
    }};
    const Descriptor identity{
        "skell.example", "Skell SDK Example", "Skell Audio",
        params.data(), params.size()
    };
    if (!identity.valid()) return false;
    const std::array<Parameter, 2> duplicates{{
        {"gain_db", "Gain", -24, 24, 0},
        {"gain_db", "Second", -24, 24, 0}
    }};
    if (Descriptor{"skell.example", "test", "Skell",
                   duplicates.data(), duplicates.size()}.valid()) return false;

    std::array<float, 8> left{}, right{};
    left.fill(0.25f);
    right.fill(-0.25f);
    const ParameterChange event{"gain_db", 0.5f, 0};
    ProcessContext context{
        block(left.data(), right.data(), left.size()),
        48000.0, 0, true, &event, 1
    };
    if (!context.valid()) return false;
    const ParameterChange invalidEvent{"gain_db", 2.0f, 0};
    ProcessContext invalid = context;
    invalid.changes = &invalidEvent;
    if (invalid.valid()) return false;
    invalid = context;
    const ParameterChange lateEvent{"gain_db", 0.4f, 8};
    invalid.changes = &lateEvent;
    if (invalid.valid()) return false;

    class Example final : public Processor {
    public:
        bool prepare(double rate, std::uint32_t frames) noexcept override {
            return std::isfinite(rate) && rate >= 1000.0 && frames <= 65536;
        }
        void reset() noexcept override { gain_.setLinear(1.0f); }
        bool process(const ProcessContext& c) noexcept override {
            if (!c.valid()) return false;
            for (std::size_t i = 0; i < c.changeCount; ++i) {
                if (c.changes[i].sampleOffset == 0)
                    gain_.setLinear(c.changes[i].normalized * 2.0f);
            }
            return gain_.process(c.audio);
        }
        std::uint32_t latencySamples() const noexcept override { return 0; }
    private:
        Gain gain_;
    } example;
    if (!example.prepare(context.sampleRate, 512)) return false;
    if (!example.process(context)) return false;
    if (example.latencySamples() != 0) return false;
    for (float value : left) if (value != 0.25f) return false;
    for (float value : right) if (value != -0.25f) return false;
    return true;
}

int main() {
    if (!testSdkContract()) {
        std::fprintf(stderr, "SkellNative source SDK contract failed\n");
        return 1;
    }
    for (double rate: {44100.0, 48000.0, 96000.0}) {
        if (!rateTest(rate)) {
            std::fprintf(stderr,"SkellNative DSP test failed at %.0f Hz\n",rate);
            return 1;
        }
    }
    std::puts("SkellNative JUCE-free DSP tests passed at 44.1/48/96 kHz");
    return 0;
}
