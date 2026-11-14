// SkellNative v0.4 — genuine IAudioProcessor::process() host-adapter benchmark.
// This compiles the EXACT processor source also used by the VST3 bundle.
// It is an in-process simulated host (not FL Studio, not DLL load/scan/GUI).
// No heap allocations, host-queue edits or wall-clock queries inside process.
#include "NativeGainIDs.h"
#include <SkellNative/Dsp.h>
#include "public.sdk/source/vst/hosting/parameterchanges.h"
#include "pluginterfaces/vst/ivstaudioprocessor.h"
#include "pluginterfaces/vst/ivstcomponent.h"
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include <limits>
#include <vector>

namespace {
using namespace Steinberg;
using namespace Steinberg::Vst;
using Clock=std::chrono::steady_clock;
constexpr std::array<double,3> rates{{44100.0,48000.0,96000.0}};
constexpr std::array<int32,3> frameCounts{{64,256,1024}};
constexpr int trials=5;
constexpr int referenceFrames=262144;
volatile double outputSink=0.0;

extern "C" void neverCalled(); // no external host dependencies

} // namespace

namespace Skelly::NativeGain {
Steinberg::FUnknown* createProcessor(void*);
}

namespace {
struct Processor {
    FUnknown* raw=nullptr;
    IAudioProcessor* audio=nullptr;
    IComponent* component=nullptr;
    bool initialized=false;
    explicit Processor(double rate,int32 frames,int32 sampleSize) {
        raw=Skelly::NativeGain::createProcessor(nullptr);
        if (!raw) return;
        if(raw->queryInterface(IAudioProcessor::iid,
                               reinterpret_cast<void**>(&audio))!=kResultOk)
            return;
        if(raw->queryInterface(IComponent::iid,
                               reinterpret_cast<void**>(&component))!=kResultOk)
            return;
        if(component->initialize(nullptr)!=kResultOk) return;
        initialized=true;
        SpeakerArrangement stereo=SpeakerArr::kStereo;
        if(audio->setBusArrangements(&stereo,1,&stereo,1)!=kResultOk) return;
        ProcessSetup setup{};
        setup.processMode=kRealtime;
        setup.symbolicSampleSize=sampleSize;
        setup.maxSamplesPerBlock=frames;
        setup.sampleRate=rate;
        if(audio->setupProcessing(setup)!=kResultOk) return;
        ready=true;
    }
    ~Processor() {
        if(component && initialized) component->terminate();
        if(component) component->release();
        if(audio) audio->release();
        if(raw) raw->release();
    }
    Processor(const Processor&)=delete;
    Processor& operator=(const Processor&)=delete;
    bool ready=false;
};

struct Trial {
    std::vector<float> input32L,input32R,output32L,output32R;
    std::vector<double> input64L,input64R,output64L,output64R;
    std::array<float*,2> in32{},out32{};
    std::array<double*,2> in64{},out64{};
    AudioBusBuffers inBus{},outBus{};
    ParameterChanges inParameters{1},outParameters{1};
    ProcessData data{};
    Trial(int32 frames,int32 sampleSize,bool automation,bool meter)
        :input32L(static_cast<std::size_t>(frames)),
         input32R(static_cast<std::size_t>(frames)),
         output32L(static_cast<std::size_t>(frames)),
         output32R(static_cast<std::size_t>(frames)),
         input64L(static_cast<std::size_t>(frames)),
         input64R(static_cast<std::size_t>(frames)),
         output64L(static_cast<std::size_t>(frames)),
         output64R(static_cast<std::size_t>(frames)) {
        for(int32 i=0;i<frames;++i) {
            const double left=0.25*std::sin(6.283185307179586*double(i)/73.0);
            const double right=0.2*std::cos(6.283185307179586*double(i)/61.0);
            input32L[static_cast<std::size_t>(i)]=static_cast<float>(left);
            input32R[static_cast<std::size_t>(i)]=static_cast<float>(right);
            input64L[static_cast<std::size_t>(i)]=left;
            input64R[static_cast<std::size_t>(i)]=right;
        }
        in32={{input32L.data(),input32R.data()}};
        out32={{output32L.data(),output32R.data()}};
        in64={{input64L.data(),input64R.data()}};
        out64={{output64L.data(),output64R.data()}};
        inBus.numChannels=2;
        outBus.numChannels=2;
        inBus.silenceFlags=0;
        outBus.silenceFlags=0;
        // AudioBusBuffers uses a UNION: only assign the active sample
        // precision. Assigning both would overwrite 32-bit pointers.
        if(sampleSize==kSample32) {
            inBus.channelBuffers32=in32.data();
            outBus.channelBuffers32=out32.data();
        } else {
            inBus.channelBuffers64=in64.data();
            outBus.channelBuffers64=out64.data();
        }
        data.processMode=kRealtime;
        data.symbolicSampleSize=sampleSize;
        data.numSamples=frames;
        data.numInputs=1;
        data.numOutputs=1;
        data.inputs=&inBus;
        data.outputs=&outBus;
        if(automation) {
            int32 index=0,point=0;
            auto* queue=inParameters.addParameterData(Skelly::NativeGain::kGainParam,index);
            if(queue) {
                // Gain changes at genuine host sample offsets.
                queue->addPoint(0,0.5,point);
                queue->addPoint(frames/4,0.25,point);
                queue->addPoint(frames/2,0.0,point);
                queue->addPoint((frames*3)/4,1.0,point);
                data.inputParameterChanges=&inParameters;
            }
        }
        if(meter) {
            // Prewarm the host queue; repeated addPoint overwrites one point.
            int32 index=0,point=0;
            auto* queue=outParameters.addParameterData(
                Skelly::NativeGain::kOutputPeakParam,index);
            if(queue) queue->addPoint(frames-1,0.0,point);
            data.outputParameterChanges=&outParameters;
        }
    }

    bool verify(float tolerance=1e-5f) const {
        const auto samples=static_cast<std::size_t>(data.numSamples);
        if(data.symbolicSampleSize==kSample32) {
            for(std::size_t i=0;i<samples;++i) {
                float gain=1.0f;
                if(data.inputParameterChanges) {
                    if(i>=samples/4) gain=0.5f;
                    if(i>=samples/2) gain=0.f;
                    if(i>=samples*3/4) gain=2.f;
                }
                if(std::abs(output32L[i]-input32L[i]*gain)>tolerance ||
                   std::abs(output32R[i]-input32R[i]*gain)>tolerance)
                    return false;
            }
        } else {
            for(std::size_t i=0;i<samples;++i) {
                double gain=1.0;
                if(data.inputParameterChanges) {
                    if(i>=samples/4) gain=0.5;
                    if(i>=samples/2) gain=0.0;
                    if(i>=samples*3/4) gain=2.0;
                }
                if(std::abs(output64L[i]-input64L[i]*gain)>1e-10 ||
                   std::abs(output64R[i]-input64R[i]*gain)>1e-10)
                    return false;
            }
        }
        if(data.outputParameterChanges) {
            auto* q=data.outputParameterChanges->getParameterData(0);
            int32 offset=-1;
            ParamValue peak=-1.0;
            if(!q || q->getParameterId()!=Skelly::NativeGain::kOutputPeakParam ||
               q->getPointCount()<1 ||
               q->getPoint(0,offset,peak)!=kResultOk ||
               offset!=data.numSamples-1 || !std::isfinite(peak))
                return false;
            double expected=0.0;
            if(data.symbolicSampleSize==kSample32)
                for(std::size_t i=0;i<samples;++i)
                    expected=std::max(expected,
                        double(std::max(std::abs(output32L[i]),std::abs(output32R[i]))));
            else
                for(std::size_t i=0;i<samples;++i)
                    expected=std::max(expected,
                        std::max(std::abs(output64L[i]),std::abs(output64R[i])));
            if(std::abs(peak-std::min(expected,1.0))>1e-5) return false;
        }
        return true;
    }
};

struct Measurement {
    bool ok=false;
    double medianNanosecondsPerCall=0.0;
};
Measurement measure(double rate,int32 frames,int32 format,bool automation,bool meter) {
    Processor processor(rate,frames,format);
    if(!processor.ready || processor.audio->getLatencySamples()!=0) return {};
    Trial trial(frames,format,automation,meter);
    // Validate processing and meter queue BEFORE measuring.
    if(processor.audio->process(trial.data)!=kResultOk || !trial.verify()) return {};
    const int loops=(referenceFrames+frames-1)/frames;
    std::array<double,trials> elapsed{};
    for(int pass=0;pass<trials+1;++pass) {
        const auto start=Clock::now();
        for(int i=0;i<loops;++i) {
            if(processor.audio->process(trial.data)!=kResultOk) return {};
        }
        const auto end=Clock::now();
        if(pass>0) elapsed[static_cast<std::size_t>(pass-1)]=
            std::chrono::duration<double,std::nano>(end-start).count() /
            double(loops);
        if(format==kSample32)
            outputSink+=trial.output32L[0]+trial.output32R.back();
        else
            outputSink+=trial.output64L[0]+trial.output64R.back();
    }
    std::sort(elapsed.begin(),elapsed.end());
    const double result=elapsed[trials/2];
    return {std::isfinite(result) && result>0.0,result};
}
} // namespace

int main() {
    std::puts("SkellNative in-process IAudioProcessor host-adapter v0.4");
    std::puts("Real GainProcessor::process; not FL Studio/ASIO, not a DLL-load benchmark");
    std::puts("rate_hz,block_frames,sample_bits,automation_points,output_meter,ns_per_process_call");
    for(double rate:rates) {
        for(int32 frames:frameCounts) {
            for(int format:{kSample32,kSample64}) {
                for(bool automation:{false,true}) {
                    for(bool meter:{false,true}) {
                        auto measurement=measure(rate,frames,format,automation,meter);
                        if(!measurement.ok) {
                            std::fprintf(stderr,
                                "ERROR: VST3 adapter signal/parity/latency test failed at "
                                "%.0fHz, %d samples, %d format, automation=%d, meter=%d\n",
                                rate,frames,format,int(automation),int(meter));
                            return 1;
                        }
                        std::printf("%.0f,%d,%d,%d,%d,%.3f\n",
                            rate,frames,format==kSample32?32:64,
                            automation?4:0,meter?1:0,
                            measurement.medianNanosecondsPerCall);
                    }
                }
            }
        }
    }
    return 0;
}
