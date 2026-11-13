// Matched DSP-only gain test: native/ JUCE on the SAME Windows CPU/compiler.
// Does not measure DAW wrapper, UI, ASIO, or plugin total CPU.
#include <SkellNative/Dsp.h>
#include <juce_dsp/juce_dsp.h>
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <vector>

using Clock=std::chrono::steady_clock;
constexpr std::size_t nSamples=1048576;
constexpr std::size_t nTrials=5;
volatile double resultSink=0.0;
struct Stereo {
    std::vector<float> l,r;
    explicit Stereo(std::size_t n):l(n),r(n) { reset(); }
    void reset() {
        for(std::size_t i=0;i<l.size();++i) {
            l[i]=static_cast<float>(0.14*std::sin(6.283185307179586*i/127.));
            r[i]=static_cast<float>(0.10*std::cos(6.283185307179586*i/97.));
        }
    }
};
void native(Stereo& p,std::size_t loops) {
    skellnative::Gain gain;
    skellnative::Block b{{{p.l.data(),p.r.data()}},2,p.l.size()};
    for(std::size_t i=0;i<loops;++i) {
        gain.setLinear((i&1u)?2.f:0.5f);
        if(!gain.process(b)) std::abort();
    }
}
void juceGain(Stereo& p,double rate,std::size_t loops) {
    juce::dsp::Gain<float> gain;
    gain.setRampDurationSeconds(0.0);
    gain.prepare({rate,static_cast<juce::uint32>(p.l.size()),2u});
    std::array<float*,2> channels{{p.l.data(),p.r.data()}};
    juce::dsp::AudioBlock<float> audio(channels.data(),2,p.l.size());
    juce::dsp::ProcessContextReplacing<float> context(audio);
    for(std::size_t i=0;i<loops;++i) {
        gain.setGainLinear((i&1u)?2.f:0.5f);
        gain.process(context);
    }
}
double measure(bool useJuce,double rate,std::size_t frames) {
    Stereo p(frames);
    const std::size_t loops=(nSamples+frames-1)/frames;
    std::array<double,nTrials> samples{};
    for(std::size_t pass=0;pass<=nTrials;++pass) {
        p.reset();
        const auto start=Clock::now();
        if(useJuce) juceGain(p,rate,loops);
        else native(p,loops);
        const auto finish=Clock::now();
        if(pass) samples[pass-1]=
            std::chrono::duration<double,std::milli>(finish-start).count();
        resultSink+=p.l.front()+p.r.back();
    }
    std::sort(samples.begin(),samples.end());
    return samples[nTrials/2];
}
double parity(double rate,std::size_t frames) {
    Stereo a(frames),b(a);
    native(a,128);
    juceGain(b,rate,128);
    double worst=0.0;
    for(std::size_t i=0;i<frames;++i) {
        worst=std::max(worst,std::abs(static_cast<double>(a.l[i])-b.l[i]));
        worst=std::max(worst,std::abs(static_cast<double>(a.r[i])-b.r[i]));
    }
    return worst;
}
int main() {
    std::fprintf(stderr,"Equal-buffer DSP-only benchmark, not host CPU or plugin performance.\n");
    std::puts("rate_hz,block_frames,native_ms,juce_ms,native_over_juce,max_error");
    for (double rate:{44100.,48000.,96000.})
        for (std::size_t frames:{64u,256u,1024u}) {
            const double worst=parity(rate,frames);
            if(!std::isfinite(worst)||worst>1.0e-5) {
                std::fprintf(stderr,"Audio parity FAILED: %.0f/%zu error %.8f\n",
                             rate,frames,worst);
                return 1;
            }
            const double a=measure(false,rate,frames);
            const double b=measure(true,rate,frames);
            if(!std::isfinite(a)||!std::isfinite(b)||a<=0.||b<=0.) return 1;
            std::printf("%.0f,%zu,%.6f,%.6f,%.4f,%.9f\n",
                        rate,frames,a,b,a/b,worst);
        }
    return 0;
}
