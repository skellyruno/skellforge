// Real Windows HWND lifecycle and mouse/host-gesture smoke for native SkellDraw.
// No JUCE, VSTGUI, plugin host, external assets or audio thread involved.
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include "SkellDrawWin32.h"
#include <SkellDraw/Win32Painter.h>
#include <windows.h>
#include <cmath>
#include <cstdio>

using namespace Skelly::NativeGain;
using namespace Steinberg;

namespace {
struct DemoController final : GainViewDelegate {
    float gain=0.5f;
    float peak=0.7f;
    float getPeak() const noexcept override { return peak; }
    int beginCount=0, editCount=0, endCount=0;
    float getGain() const noexcept override { return gain; }
    void beginGain() noexcept override { ++beginCount; }
    void updateGain(float v) noexcept override {
        gain=v;
        ++editCount;
    }
    void endGain() noexcept override { ++endCount; }
};
bool verify(bool condition,const char* name) {
    if (!condition) std::fprintf(stderr,"SkellDraw UI smoke failed: %s\n",name);
    return condition;
}
} // namespace

int main() {
    DemoController controller;
    SkellDrawView view(controller,nullptr);
    if (!verify(view.isPlatformTypeSupported(kPlatformTypeHWND)==kResultTrue,
                "Windows HWND platform supported")) return 1;
    if (!verify(view.isPlatformTypeSupported(kPlatformTypeNSView)==kResultFalse,
                "macOS view rejected by Win32 prototype")) return 1;
    ViewRect initial{};
    if (!verify(view.getSize(&initial)==kResultTrue && initial.getWidth()==480
                && initial.getHeight()==300, "initial size 480x300")) return 1;
    HWND parent=CreateWindowExW(0,L"STATIC",L"SkellDraw HWND smoke",
                                WS_OVERLAPPEDWINDOW|WS_VISIBLE,80,80,760,500,
                                nullptr,nullptr,GetModuleHandleW(nullptr),nullptr);
    if (!verify(parent!=nullptr,"create host parent HWND")) return 1;
    const auto cleanup=[&] { DestroyWindow(parent); };
    if (!verify(view.attached(parent,kPlatformTypeHWND)==kResultOk,
                "VST3 editor HWND attach")) { cleanup(); return 1; }
    if (!verify(view.attached(parent,kPlatformTypeHWND)==kResultFalse,
                "duplicate attach rejected")) { view.removed(); cleanup(); return 1; }

    HWND child=FindWindowExW(parent,nullptr,L"STATIC",L"SkellNativeSkellDrawView_0_1");
    if (!verify(child!=nullptr && IsWindow(child),
                "actual child window embedded")) { view.removed(); cleanup(); return 1; }
    SendMessageW(child,WM_TIMER,17,0); // host peak value arrives at editor
    InvalidateRect(child,nullptr,FALSE);
    UpdateWindow(child);
    HDC dc=GetDC(child);
    const COLORREF top=dc ? GetPixel(dc,240,1) : CLR_INVALID;
    const COLORREF knobTop=dc ? GetPixel(dc,220,115) : CLR_INVALID;
    const COLORREF outputBar=dc ? GetPixel(dc,346,215) : CLR_INVALID;
    if(dc) ReleaseDC(child,dc);
    if (!verify(top==RGB(141,255,68),"custom green painted top trim")) {
        view.removed(); cleanup(); return 1;
    }
    if (!verify(outputBar==RGB(141,255,68),
                "meter uses actual positive host-provided level")) {
        view.removed(); cleanup(); return 1;
    }
    // Regression: an old artificial specular highlight crossed the knob
    // face between logical x=198..270 at y=115. Keep that strip clear.
    if (!verify(knobTop!=CLR_INVALID && knobTop!=RGB(75,91,79),
                "no straight highlight across upper knob face")) {
        view.removed(); cleanup(); return 1;
    }

    // The 40 ms timer polls the parameter and real meter, but an unchanged
    // value must not trigger extra WM_PAINT (a major idle CPU cause).
    const auto stable=view.profileStats();
    if (!verify(stable.paintCalls>0 && stable.backBufferCreates==1,
                "first paint created exactly one backing bitmap")) {
        view.removed(); cleanup(); return 1;
    }
    const DWORD gdiWarm=GetGuiResources(GetCurrentProcess(),GR_GDIOBJECTS);
    for(int tick=0;tick<100;++tick)
        SendMessageW(child,WM_TIMER,17,0);
    UpdateWindow(child);
    const auto idle=view.profileStats();
    if (!verify(idle.timerTicks==stable.timerTicks+100 &&
                idle.paintCalls==stable.paintCalls &&
                idle.redrawRequests==stable.redrawRequests,
                "100 unchanged meter/knob timer ticks cause ZERO redraws")) {
        view.removed(); cleanup(); return 1;
    }

    // Forced repaints must recycle cached GDI fonts, knob pens and bitmap.
    for(int frame=0;frame<40;++frame) {
        InvalidateRect(child,nullptr,FALSE);
        UpdateWindow(child);
    }
    const auto warmed=view.profileStats();
    const DWORD gdiAfter=GetGuiResources(GetCurrentProcess(),GR_GDIOBJECTS);
    if (!verify(warmed.paintCalls==idle.paintCalls+40 &&
                warmed.backBufferCreates==idle.backBufferCreates &&
                gdiAfter<=gdiWarm+2,
                "40 repaints reuse GDI resources without handle growth")) {
        view.removed(); cleanup(); return 1;
    }

    // New audio peak MUST request painting; no random or gain-derived meter.
    controller.peak=0.11f;
    SendMessageW(child,WM_TIMER,17,0);
    UpdateWindow(child);
    const auto changed=view.profileStats();
    if (!verify(changed.redrawRequests>idle.redrawRequests &&
                changed.paintCalls>warmed.paintCalls,
                "real output-peak change triggers repaint")) {
        view.removed(); cleanup(); return 1;
    }

    ViewRect constraint(0,0,700,330);
    if (!verify(view.checkSizeConstraint(&constraint)==kResultTrue
                && constraint.getWidth()==700 && constraint.getHeight()==437,
                "bounded 8:5 constraint")) { view.removed(); cleanup(); return 1; }
    if (!verify(view.onSize(&constraint)==kResultTrue,
                "host resize accepted")) { view.removed(); cleanup(); return 1; }
    RECT childRect{};
    GetClientRect(child,&childRect);
    if (!verify(childRect.right==700 && childRect.bottom==437,
                "platform HWND resized with host")) { view.removed(); cleanup(); return 1; }
    UpdateWindow(child);
    const auto resized=view.profileStats();
    if (!verify(resized.backBufferCreates>=2,
                "resizing recreates the offscreen bitmap exactly when needed")) {
        view.removed(); cleanup(); return 1;
    }

    // Coordinates scaled from logical 480x300 to new 700x437 window.
    const int mx=237*700/480, my=155*437/300;
    SendMessageW(child,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(mx,my));
    SendMessageW(child,WM_MOUSEMOVE,MK_LBUTTON,MAKELPARAM(mx,my-60));
    SendMessageW(child,WM_LBUTTONUP,0,MAKELPARAM(mx,my-60));
    if (!verify(controller.gain>0.65f && controller.beginCount==1
                && controller.editCount>=1 && controller.endCount==1,
                "mouse drag emits balanced host edit gesture")) {
        view.removed(); cleanup(); return 1;
    }
    SendMessageW(child,WM_LBUTTONDBLCLK,MK_LBUTTON,MAKELPARAM(mx,my));
    if (!verify(std::abs(controller.gain-0.5f)<0.0001f,
                "double-click resets gain to unity")) { view.removed(); cleanup(); return 1; }
    if (!verify(view.onWheel(1.0f)==kResultTrue && controller.gain>0.5f,
                "wheel updates parameter")) { view.removed(); cleanup(); return 1; }
    if (!verify(controller.beginCount==controller.endCount,
                "all edit gestures balanced")) { view.removed(); cleanup(); return 1; }

    // Shared power is a standalone reusable control; it is NOT wired to
    // Gain until Gain gains a persistent bypass parameter/host contract.
    HDC screen=GetDC(parent);
    HDC powerDC=screen?CreateCompatibleDC(screen):nullptr;
    HBITMAP powerBitmap=(screen&&powerDC)
        ?CreateCompatibleBitmap(screen,64,64):nullptr;
    if(!verify(powerDC!=nullptr && powerBitmap!=nullptr,
               "allocate reusable power control GDI test bitmap")) {
        if(powerBitmap) DeleteObject(powerBitmap);
        if(powerDC) DeleteDC(powerDC);
        if(screen) ReleaseDC(parent,screen);
        view.removed(); cleanup(); return 1;
    }
    const auto original=SelectObject(powerDC,powerBitmap);
    skelldraw::win32::fill(powerDC,0,0,64,64,RGB(8,11,10));
    skelldraw::win32::powerButton(powerDC,{10,10,36,36},true);
    bool foundAccent=false;
    for(int y=10;y<46 && !foundAccent;++y)
        for(int x=10;x<46;++x)
            if(GetPixel(powerDC,x,y)==RGB(141,255,68)) foundAccent=true;
    SelectObject(powerDC,original);
    DeleteObject(powerBitmap);
    DeleteDC(powerDC);
    ReleaseDC(parent,screen);
    if(!verify(foundAccent,"reusable power button draws lit state")) {
        view.removed(); cleanup(); return 1;
    }

    if (!verify(view.removed()==kResultOk && !IsWindow(child),
                "view removed and child window destroyed")) { cleanup(); return 1; }

    // Twenty-five simulated DAW close/reopen cycles, creating and destroying
    // an independent editor each time. GDI handles and WndProc must not leak
    // across reused host windows (a common DAW unload/reload failure mode).
    const DWORD beforeCycles=GetGuiResources(GetCurrentProcess(),GR_GDIOBJECTS);
    for(int cycle=0;cycle<25;++cycle) {
        SkellDrawView reopen(controller,nullptr);
        const bool attached=reopen.attached(parent,kPlatformTypeHWND)==kResultOk;
        const HWND reopened=FindWindowExW(parent,nullptr,L"STATIC",
                                          L"SkellNativeSkellDrawView_0_1");
        const bool created=attached && reopened && IsWindow(reopened);
        if(created) {
            SendMessageW(reopened,WM_TIMER,17,0);
            UpdateWindow(reopened);
        }
        if(attached) reopen.removed();
        if(!verify(created && (!reopened || !IsWindow(reopened)),
                   "25 independent editor create/close cycles")) {
            cleanup(); return 1;
        }
    }
    const DWORD afterCycles=GetGuiResources(GetCurrentProcess(),GR_GDIOBJECTS);
    if(!verify(afterCycles<=beforeCycles+2,
               "25 editor lifecycles do not leak per-view GDI objects")) {
        cleanup(); return 1;
    }
    cleanup();
    const auto stats=view.profileStats();
    if (!verify(stats.paintCalls>0 &&
                stats.totalPaintMicroseconds>0.0 &&
                stats.maxPaintMicroseconds>0.0,
                "high-resolution paint profiler records actual GDI time")) return 1;
    std::printf("SKELLDRAW_UI_PROFILE,paint_calls=%llu,redraws=%llu,timer_ticks=%llu,"
                "backbuffer_creates=%llu,mean_paint_us=%.2f,max_paint_us=%.2f\n",
                static_cast<unsigned long long>(stats.paintCalls),
                static_cast<unsigned long long>(stats.redrawRequests),
                static_cast<unsigned long long>(stats.timerTicks),
                static_cast<unsigned long long>(stats.backBufferCreates),
                stats.totalPaintMicroseconds/static_cast<double>(stats.paintCalls),
                stats.maxPaintMicroseconds);
    std::puts("PASS: SkellDraw native Win32 attach, paint, resize, drag, reset and wheel");
    return 0;
}
