#include <SkellDraw/Components.h>
#include <cassert>
#include <cmath>
#include <limits>
#include <cstdio>

int main() {
    using namespace skelldraw;
    static_assert(Layout::designWidth==480);
    static_assert(Layout::knob.contains({237,155}));
    static_assert(!Layout::knob.contains({10,10}));
    assert(Layout::logical({350,219},700,437).x==240);
    const auto sized=Layout::constrain({0,0,700,300});
    assert(sized.width==700 && sized.height==437);
    assert(Layout::constrain({0,0,-20,100}).width==400);
    assert(Layout::constrain({0,0,10000,100}).width==960);
    assert(Knob::drag(0.5f,60)>0.85f);
    assert(Knob::reset()==0.5f);
    assert(Knob::wheel(0.5f,1.f)>0.5f);
    assert(Knob::wheel(0.5f,std::numeric_limits<float>::quiet_NaN())==0.5f);
    assert(Knob::drag(0.5f,-10000)==0.f);
    assert(Knob::drag(0.5f,10000)==1.f);
    PowerButton power;
    assert(power.on && !power.toggle() && power.toggle());
    OutputMeter meter;
    assert(meter.level()==0.f);
    assert(meter.update(0.8f,0.016f));
    assert(std::abs(meter.level()-0.8f)<1e-5f);
    assert(meter.update(0.f,0.1f));
    assert(meter.level()<0.8f && meter.level()>0.f);
    meter.reset();
    assert(meter.level()==0.f);
    meter.update(std::numeric_limits<float>::infinity(),0.1f);
    assert(meter.level()==0.f);
    RenderInvalidation inv;
    assert(inv.update(0.5f,0.f,true));
    assert(!inv.update(0.5f,0.f,true));
    assert(inv.update(0.5f,0.5f,true));
    assert(inv.update(0.5f,0.5f,false));
    std::puts("PASS: SkellDraw portable layout, knob, power, meter, redraw semantics");
    return 0;
}
