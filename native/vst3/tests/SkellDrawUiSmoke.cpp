// Real Windows HWND lifecycle and mouse/host-gesture smoke for native SkellDraw.
// No JUCE, VSTGUI, plugin host, external assets or audio thread involved.
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include "SkellDrawWin32.h"
#include <windows.h>
#include <cmath>
#include <cstdio>

using namespace Skelly::NativeGain;
using namespace Steinberg;

namespace {
struct DemoController final : GainViewDelegate {
    float gain=0.5f;
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
    InvalidateRect(child,nullptr,FALSE);
    UpdateWindow(child);
    HDC dc=GetDC(child);
    const COLORREF top=dc ? GetPixel(dc,240,1) : CLR_INVALID;
    if(dc) ReleaseDC(child,dc);
    if (!verify(top==RGB(141,255,68),"custom green painted top trim")) {
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

    if (!verify(view.removed()==kResultOk && !IsWindow(child),
                "view removed and child window destroyed")) { cleanup(); return 1; }
    cleanup();
    std::puts("PASS: SkellDraw native Win32 attach, paint, resize, drag, reset and wheel");
    return 0;
}
