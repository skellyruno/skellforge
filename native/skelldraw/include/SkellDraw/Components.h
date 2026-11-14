#pragma once
// SkellDraw reusable component semantics v0.2.
// Pure C++17: no JUCE, Win32, VST3 or allocations; safe for unit testing.
// Rendering adapters and DAW parameter ownership remain separate.
#include <algorithm>
#include <cmath>
#include <cstdint>

namespace skelldraw {

struct Point { int x=0; int y=0; };
struct Rect {
    int x=0; int y=0; int width=0; int height=0;
    constexpr bool contains(Point p) const noexcept {
        return width>0 && height>0 &&
            p.x>=x && p.x<x+width && p.y>=y && p.y<y+height;
    }
};

struct Theme {
    std::uint32_t background=0x080b0a;
    std::uint32_t panel=0x0f1612;
    std::uint32_t accent=0x8dff44;
    std::uint32_t muted=0x8e9d8f;
    std::uint32_t text=0xf1f6f0;
    std::uint32_t frame=0x394d40;
};

// All controls exist in a single 480x300 design coordinate system.
// The host may resize to 400..960 while keeping the 8:5 aspect ratio.
struct Layout {
    static constexpr int designWidth=480;
    static constexpr int designHeight=300;
    static constexpr Rect knob{169,87,136,136};
    static constexpr Rect power{422,60,28,28};
    static constexpr Rect meter{344,205,98,25};
    static constexpr Rect gainReadout{339,103,104,84};
    static Point logical(Point device,int viewportWidth,int viewportHeight) noexcept {
        if(viewportWidth<=0 || viewportHeight<=0) return {};
        return {device.x*designWidth/viewportWidth,
                device.y*designHeight/viewportHeight};
    }
    static Rect constrain(Rect requested) noexcept {
        const int width=std::clamp(requested.width,400,960);
        return {requested.x,requested.y,width,width*5/8};
    }
};

inline float unit(float value,float fallback=0.f) noexcept {
    return std::isfinite(value) ? std::clamp(value,0.f,1.f) : fallback;
}
struct Knob {
    static constexpr float defaultValue=0.5f;
    static float drag(float from,int dy,float sensitivity=0.006f) noexcept {
        if(!std::isfinite(sensitivity)||sensitivity<0.f) return unit(from,defaultValue);
        return unit(unit(from,defaultValue)+static_cast<float>(dy)*sensitivity,
                    defaultValue);
    }
    static float wheel(float from,float ticks,float sensitivity=0.035f) noexcept {
        if(!std::isfinite(ticks)||!std::isfinite(sensitivity))
            return unit(from,defaultValue);
        return unit(unit(from,defaultValue)+ticks*sensitivity,defaultValue);
    }
    static float reset() noexcept { return defaultValue; }
};

struct PowerButton {
    bool on=true;
    bool toggle() noexcept { on=!on; return on; }
    void set(bool value) noexcept { on=value; }
};

// Meter input is the MAXIMUM OUTPUT amplitude of a real processed audio block
// delivered by the host. Do NOT fake motion from the knob value.
// Processing signal level and the GUI render timer must remain independent.
class OutputMeter {
public:
    void reset() noexcept { shown_=0.f; }
    float level() const noexcept { return shown_; }
    // Frame-time dependent decay, no synthetic activity when audio is absent.
    bool update(float measuredPeak,float elapsedSeconds) noexcept {
        const float next=unit(measuredPeak,0.f);
        const float dt=std::clamp(std::isfinite(elapsedSeconds)?elapsedSeconds:0.f,
                                  0.f,0.25f);
        const float decayed=shown_*std::exp(-6.f*dt);
        const float value=std::max(next,decayed);
        const bool changed=std::abs(value-shown_)>0.001f;
        shown_=value;
        return changed;
    }
private:
    float shown_=0.f;
};

struct RenderInvalidation {
    float lastKnob=-1.f;
    float lastMeter=-1.f;
    bool lastPowered=true;
    bool update(float knob,float meter,bool powered) noexcept {
        const auto k=unit(knob,Knob::defaultValue);
        const auto m=unit(meter);
        const bool dirty=std::abs(k-lastKnob)>0.001f ||
                         std::abs(m-lastMeter)>0.002f ||
                         powered!=lastPowered;
        lastKnob=k;lastMeter=m;lastPowered=powered;
        return dirty;
    }
};

} // namespace skelldraw
