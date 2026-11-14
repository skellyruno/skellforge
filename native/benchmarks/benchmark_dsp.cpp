// Portable SkellNative DSP microbenchmark, C++17; no plugin SDK or GUI.
// NOT FL Studio CPU %, and NOT a JUCE-vs-native performance comparison.
#include <SkellNative/Dsp.h>
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdio>
#include <vector>

namespace {
using Clock = std::chrono::steady_clock;
constexpr std::array<double,3> rates{{44100.0,48000.0,96000.0}};
constexpr std::array<std::size_t,3> sizes{{64,256,1024}};
constexpr std::size_t trials=5;
constexpr std::size_t targetFrames=1048576;
enum class Mode { gain, lowpass, peak, gain_peak };
const char* modeName(Mode m) {
    switch(m) {
        case Mode::gain: return "gain";
        case Mode::lowpass: return "lowpass";
        case Mode::peak: return "peak";
        case Mode::gain_peak: return "gain_peak";
    }
    return "unknown";
}
struct Result { bool ok=false; double nsPerSampleChannel=0; double realTimeRatio=0; double checksum=0; };

Result measure(Mode mode,double rate,std::size_t frames) {
    // Buffer allocation and synthetic audio setup are not timed.
    std::vector<float> left(frames),right(frames);
    for(std::size_t i=0;i<frames;++i) {
        const double phase=6.283185307179586*463.0*static_cast<double>(i)/rate;
        left[i]=static_cast<float>(0.2*std::sin(phase));
        right[i]=static_cast<float>(0.15*std::cos(phase));
    }
    const skellnative::Block block{{{left.data(),right.data()}},2,frames};
    skellnative::Gain gain;
    gain.setLinear(1.0f); // Set a nontrivial gain in each timed block below.
    skellnative::Lowpass lowpass;
    lowpass.prepare(rate);
    lowpass.setCutoff(7500.0f);
    skellnative::PeakSource peak;
    const auto run=[&]() -> bool {
        switch(mode) {
            case Mode::gain: return gain.process(block);
            case Mode::lowpass: return lowpass.process(block);
            case Mode::peak: peak.measure(block); return true;
            case Mode::gain_peak:
                if(!gain.process(block)) return false;
                peak.measure(block); return true;
        }
        return false;
    };
    const auto count=(targetFrames+frames-1)/frames;
    const double sampleCount=static_cast<double>(count*frames);
    std::array<double,trials> measured{};
    for(std::size_t trial=0;trial<trials+1;++trial) {
        const auto start=Clock::now();
        for(std::size_t blockIndex=0;blockIndex<count;++blockIndex) {
            // Non-unity gain prevents an optimizing compiler from treating
            // in-place gain as a no-op. The 0.5/2.0 pair avoids fading.
            if(mode==Mode::gain || mode==Mode::gain_peak)
                gain.setLinear((blockIndex & 1u) ? 2.0f : 0.5f);
            if(mode==Mode::peak) {
                // Vary the observed peak so the entire test cannot be
                // hoisted out of the timed loop by constant propagation.
                left[0]=static_cast<float>(0.02+0.001*(blockIndex%211u));
            }
            if(!run()) return {};
        }
        const auto end=Clock::now();
        if(trial) measured[trial-1]=
            std::chrono::duration<double,std::nano>(end-start).count();
    }
    std::sort(measured.begin(),measured.end());
    const double median=measured[trials/2];
    const double perChannel=median/(sampleCount*2.0);
    const double ratio=median/(sampleCount/rate*1.0e9);
    const double checksum=static_cast<double>(left.front()) +
        static_cast<double>(right.back()) + static_cast<double>(peak.read());
    return {std::isfinite(perChannel)&&perChannel>0&&std::isfinite(ratio)&&ratio>0&&
            std::isfinite(checksum), perChannel, ratio,checksum};
}
} // namespace

int main() {
    std::puts("SkellNative C++ DSP benchmark v0.1; in-place stereo f32");
    std::puts("Measured on this machine only; not FL Studio CPU %, not JUCE performance.");
    std::puts("mode,rate_hz,block_frames,ns_per_frame_per_channel,realtime_fraction,checksum");
    for(const double rate:rates)
        for(const std::size_t frames:sizes)
            for(const auto mode:{Mode::gain,Mode::lowpass,Mode::peak,Mode::gain_peak}) {
                const auto result=measure(mode,rate,frames);
                if(!result.ok) {
                    std::fprintf(stderr,"Invalid benchmark result: %s %.0f %zu\n",
                                 modeName(mode),rate,frames);
                    return 1;
                }
                std::printf("%s,%.0f,%zu,%.6f,%.8f,%.6f\n",modeName(mode),rate,frames,
                            result.nsPerSampleChannel,result.realTimeRatio,result.checksum);
            }
    return 0;
}
