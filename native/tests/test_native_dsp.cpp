#include <SkellNative/Dsp.h>
#include <SkellNative/PluginApi.h>
#include <SkellNative/State.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <limits>
#include <cstring>
#include <vector>

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

static bool testStateSerialization() {
    using namespace skellnative::sdk;
    StateSnapshot snapshot;
    snapshot.parameters.push_back({"gain_db",0.5f});
    snapshot.parameters.push_back({"fx_warmth_drive",0.25f});
    const auto encoded=encodeState("skell.example",snapshot);
    if (!encoded || encoded->size()<16) return false;
    const auto again=encodeState("skell.example",snapshot);
    if (!again || *again!=*encoded) return false;
    const auto decoded=decodeState("skell.example",*encoded);
    if (!decoded || decoded->parameters.size()!=2) return false;
    if (decoded->parameters[0].persistentId!="gain_db"
        || decoded->parameters[0].normalized!=0.5f
        || decoded->parameters[1].persistentId!="fx_warmth_drive"
        || decoded->parameters[1].normalized!=0.25f) return false;
    if (decodeState("skell.other",*encoded)) return false;
    auto corrupt=*encoded;
    corrupt[corrupt.size()-6]^=0x20u;
    if (decodeState("skell.example",corrupt)) return false;
    corrupt=*encoded;
    corrupt.pop_back();
    if (decodeState("skell.example",corrupt)) return false;
    corrupt=*encoded;
    corrupt.push_back(0);
    if (decodeState("skell.example",corrupt)) return false;
    snapshot.parameters.push_back({"gain_db",0.8f});
    if (encodeState("skell.example",snapshot)) return false;
    snapshot.parameters.pop_back();
    snapshot.parameters[1].normalized=std::numeric_limits<float>::infinity();
    if (encodeState("skell.example",snapshot)) return false;
    snapshot.parameters[1].normalized=0.25f;
    snapshot.parameters[1].persistentId="../escape";
    if (encodeState("skell.example",snapshot)) return false;
    snapshot.parameters[1].persistentId="fx_warmth_drive";
    if (encodeState("skell.example\nother",snapshot)) return false;
    // Blank state is supported and tied to the same product identity.
    StateSnapshot blank;
    const auto empty=encodeState("skell.blank",blank);
    if (!empty) return false;
    const auto restored=decodeState("skell.blank",*empty);
    if (!restored || !restored->parameters.empty()) return false;
    return true;
}

static bool testSampleOffsetGainSpans() {
    // Reference scalar processing and block-span processing must match,
    // even for multiple parameter events at the same sample offset.
    constexpr std::size_t count=256;
    std::array<float,count> sourceL{},sourceR{},spansL{},spansR{};
    for (std::size_t i=0; i<count; ++i) {
        sourceL[i]=static_cast<float>(0.2*std::sin(6.283185307179586*i/13.0));
        sourceR[i]=-0.6f*sourceL[i];
    }
    spansL=sourceL; spansR=sourceR;
    const std::array<std::size_t,7> offsets{{0,1,17,17,64,127,255}};
    const std::array<float,7> normalized{{0.5f,0.2f,0.8f,0.0f,1.0f,0.3f,0.5f}};
    std::array<float,count> expectedL{},expectedR{};
    float current=0.5f;
    std::size_t event=0;
    for (std::size_t i=0;i<count;++i) {
        while (event<offsets.size() && offsets[event]==i)
            current=normalized[event++];
        expectedL[i]=sourceL[i]*current*2.0f;
        expectedR[i]=sourceR[i]*current*2.0f;
    }
    Gain kernel;
    current=0.5f;
    std::size_t begin=0;
    for (std::size_t i=0;i<offsets.size();++i) {
        const auto end=offsets[i];
        if (end>begin) {
            kernel.setLinear(current*2.0f);
            if (!kernel.process(block(spansL.data()+begin,spansR.data()+begin,end-begin)))
                return false;
        }
        current=normalized[i];
        begin=end;
    }
    kernel.setLinear(current*2.0f);
    if (!kernel.process(block(spansL.data()+begin,spansR.data()+begin,count-begin)))
        return false;
    for (std::size_t i=0; i<count; ++i) {
        if (std::abs(spansL[i]-expectedL[i])>2e-6f ||
            std::abs(spansR[i]-expectedR[i])>2e-6f) return false;
    }
    return true;
}

static bool testFiniteSafeGainAcrossVectorBoundaries() {
    // Check all SIMD lane positions and scalar tails, plus deliberately
    // unaligned float addresses and mono/stereo channel configurations.
    const std::array<std::size_t,15> lengths{{
        0,1,2,3,4,5,6,7,8,9,15,16,17,63,65
    }};
    for (const std::size_t frames:lengths) {
        for (std::size_t channels:{1u,2u}) {
            std::vector<float> left(frames+2,123.0f);
            std::vector<float> right(frames+2,-234.0f);
            std::vector<float> expectedL(frames),expectedR(frames);
            for (std::size_t i=0;i<frames;++i) {
                float value=static_cast<float>(i*0.013-0.22);
                switch (i%9) {
                    case 0: value=std::numeric_limits<float>::quiet_NaN();break;
                    case 1: value=std::numeric_limits<float>::infinity();break;
                    case 2: value=-std::numeric_limits<float>::infinity();break;
                    case 3: value=-0.0f;break;
                    case 4: value=std::numeric_limits<float>::denorm_min();break;
                    case 5: value=-std::numeric_limits<float>::denorm_min();break;
                }
                left[i+1]=value;
                right[i+1]=-value;
                expectedL[i]=finiteOrZero(left[i+1])*1.5f;
                expectedR[i]=finiteOrZero(right[i+1])*1.5f;
            }
            Gain gain;
            gain.setLinear(1.5f);
            const Block audio{{{left.data()+1,right.data()+1}},channels,frames};
            if (!gain.process(audio)) return false;
            for (std::size_t i=0;i<frames;++i) {
                if (std::memcmp(&left[i+1],&expectedL[i],sizeof(float))!=0)
                    return false;
                if (channels==2 &&
                    std::memcmp(&right[i+1],&expectedR[i],sizeof(float))!=0)
                    return false;
                if (!std::isfinite(left[i+1])) return false;
            }
            if (left.front()!=123.0f || left.back()!=123.0f ||
                right.front()!=-234.0f || right.back()!=-234.0f)
                return false;
        }
    }
    // Invalid buffers must be rejected as before.
    Gain gain;
    std::array<float,4> values{};
    if (gain.process(Block{{{nullptr,values.data()}},2,4}))
        return false;
    if (!gain.process(Block{{{nullptr,nullptr}},2,0}))
        return false;
    return true;
}

static bool testFusedGainOutputMeterParity() {
    // Exact output samples against non-metered gain and independent
    // post-processing peak reference. Both SIMD and scalar-only builds run.
    const std::array<std::size_t,10> lengths{{0,1,2,3,4,5,7,16,65,129}};
    const std::array<float,5> linearGains{{0.f,0.5f,1.f,2.f,4.f}};
    for (auto frames:lengths) {
        for(std::size_t channels:{1u,2u}) {
            for(float gainValue:linearGains) {
                std::vector<float> inputL(frames+2,0.f),inputR(frames+2,0.f);
                for(std::size_t i=0;i<frames;++i) {
                    float sample=static_cast<float>(0.049*double(i)-0.8);
                    switch (i%11) {
                        case 0: sample=std::numeric_limits<float>::quiet_NaN();break;
                        case 1: sample=std::numeric_limits<float>::infinity();break;
                        case 2: sample=-std::numeric_limits<float>::infinity();break;
                        case 3: sample=std::numeric_limits<float>::max();break;
                        case 4: sample=-std::numeric_limits<float>::max();break;
                        case 5: sample=std::numeric_limits<float>::denorm_min();break;
                        case 6: sample=-0.0f;break;
                    }
                    inputL[i+1]=sample;
                    inputR[i+1]=-sample;
                }
                auto expectedL=inputL,expectedR=inputR;
                auto actualL=inputL,actualR=inputR;
                Gain gain;
                gain.setLinear(gainValue);
                Block expected{{{expectedL.data()+1,expectedR.data()+1}},channels,frames};
                Block actual{{{actualL.data()+1,actualR.data()+1}},channels,frames};
                if(!gain.process(expected)) return false;
                float fusedPeak=-1.0f;
                if(!gain.processWithPeak(actual,fusedPeak)) return false;
                float referencePeak=0.f;
                for(std::size_t ch=0;ch<channels;++ch) {
                    for(std::size_t i=0;i<frames;++i) {
                        const float x=(ch==0 ? expectedL[i+1] : expectedR[i+1]);
                        const float y=(ch==0 ? actualL[i+1] : actualR[i+1]);
                        if(std::memcmp(&x,&y,sizeof(float))!=0) return false;
                        const float absolute=std::abs(x);
                        referencePeak=std::max(referencePeak,
                            std::isfinite(absolute)?std::min(absolute,1.0f):1.0f);
                    }
                }
                if(std::abs(fusedPeak-referencePeak)>1e-6f) return false;
                if(actualL.front()!=0.f || actualL.back()!=0.f) return false;
            }
        }
    }
    Gain gain;
    float peak=123.f;
    if (gain.processWithPeak(Block{{{nullptr,nullptr}},2,4},peak))
        return false;
    if(peak!=0.f) return false;
    return true;
}

int main() {
    if (!testFusedGainOutputMeterParity()) {
        std::fprintf(stderr, "SkellNative fused gain peak exact-parity regression failed\n");
        return 1;
    }
    if (!testFiniteSafeGainAcrossVectorBoundaries()) {
        std::fprintf(stderr, "SkellNative finite-safe vector gain parity failed\n");
        return 1;
    }
    if (!testSampleOffsetGainSpans()) {
        std::fprintf(stderr, "SkellNative sample-offset span processing regression failed\n");
        return 1;
    }
    if (!testStateSerialization()) {
        std::fprintf(stderr, "SkellNative versioned state serialization failed\n");
        return 1;
    }
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
