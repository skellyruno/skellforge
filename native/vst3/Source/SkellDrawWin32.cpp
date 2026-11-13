#ifndef NOMINMAX
#define NOMINMAX
#endif
#include "SkellDrawWin32.h"
#include <SkellDraw/Components.h>
#include <SkellDraw/Win32Painter.h>
#include <windowsx.h>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <cwchar>

namespace Skelly::NativeGain {

namespace {
constexpr wchar_t kClassName[]=L"SkellNativeSkellDrawView_0_1";
constexpr int kBaseW=skelldraw::Layout::designWidth;
constexpr int kBaseH=skelldraw::Layout::designHeight;
constexpr UINT_PTR kPollTimer=17;
const skelldraw::Theme kTheme{};
const COLORREF kBg=skelldraw::win32::color(kTheme.background);
const COLORREF kPanel=skelldraw::win32::color(kTheme.panel);
const COLORREF kGreen=skelldraw::win32::color(kTheme.accent);
const COLORREF kMuted=skelldraw::win32::color(kTheme.muted);
using skelldraw::win32::fill;
using skelldraw::win32::line;
using skelldraw::win32::label;
bool isKnob(int x,int y) noexcept {
    return skelldraw::Layout::knob.contains({x,y});
}
} // namespace

SkellDrawView::SkellDrawView(GainViewDelegate& delegate, Steinberg::FUnknown* owner)
    : Steinberg::CPluginView(), delegate_(delegate), owner_(owner) {
    setRect(Steinberg::ViewRect(0,0,kBaseW,kBaseH));
    if (owner_) owner_->addRef(); // UI remains valid while the host owns the view.
}
SkellDrawView::~SkellDrawView() {
    if (window_) removed();
    releaseBackBuffer();
    if (owner_) { owner_->release(); owner_=nullptr; }
}
Steinberg::tresult PLUGIN_API SkellDrawView::isPlatformTypeSupported(
    Steinberg::FIDString type) {
    return type && std::strcmp(type, Steinberg::kPlatformTypeHWND)==0
        ? Steinberg::kResultTrue : Steinberg::kResultFalse;
}
Steinberg::tresult PLUGIN_API SkellDrawView::attached(
    void* parent, Steinberg::FIDString type) {
    if (window_ || !parent || isPlatformTypeSupported(type)!=Steinberg::kResultTrue)
        return Steinberg::kResultFalse;
    // Subclass a standard OS control, avoiding persistent DLL-registered
    // window classes and stale WndProc addresses after host unload/reload.
    const auto& rect=getRect();
    const HWND hwnd=CreateWindowExW(0,L"STATIC",kClassName,
                     WS_CHILD|WS_VISIBLE|WS_CLIPSIBLINGS|SS_NOTIFY,
                     0,0,rect.getWidth(),rect.getHeight(),
                     static_cast<HWND>(parent),nullptr,GetModuleHandleW(nullptr),nullptr);
    if (!hwnd) return Steinberg::kResultFalse;
    SetWindowLongPtrW(hwnd,GWLP_USERDATA,reinterpret_cast<LONG_PTR>(this));
    SetLastError(0);
    const auto prior=SetWindowLongPtrW(hwnd,GWLP_WNDPROC,
                                      reinterpret_cast<LONG_PTR>(&SkellDrawView::windowProc));
    if (!prior && GetLastError()!=0) {
        SetWindowLongPtrW(hwnd,GWLP_USERDATA,0);
        DestroyWindow(hwnd);
        return Steinberg::kResultFalse;
    }
    originalWindowProc_=reinterpret_cast<WNDPROC>(prior);
    window_=hwnd;
    SetTimer(hwnd,kPollTimer,40,nullptr);
    InvalidateRect(hwnd,nullptr,FALSE);
    return Steinberg::CPluginView::attached(parent,type);
}
Steinberg::tresult PLUGIN_API SkellDrawView::removed() {
    editEnd();
    releaseBackBuffer();
    meter_.reset();
    if (window_) {
        const HWND hwnd=window_;
        window_=nullptr;
        KillTimer(hwnd,kPollTimer);
        if (originalWindowProc_)
            SetWindowLongPtrW(hwnd,GWLP_WNDPROC,
                              reinterpret_cast<LONG_PTR>(originalWindowProc_));
        SetWindowLongPtrW(hwnd,GWLP_USERDATA,0);
        originalWindowProc_=nullptr;
        DestroyWindow(hwnd);
    }
    return Steinberg::CPluginView::removed();
}
Steinberg::tresult PLUGIN_API SkellDrawView::onSize(Steinberg::ViewRect* rect) {
    if (!rect || rect->getWidth()<1 || rect->getHeight()<1)
        return Steinberg::kInvalidArgument;
    const auto result=Steinberg::CPluginView::onSize(rect);
    if (window_) MoveWindow(window_,0,0,rect->getWidth(),rect->getHeight(),TRUE);
    return result;
}
Steinberg::tresult PLUGIN_API SkellDrawView::checkSizeConstraint(
    Steinberg::ViewRect* rect) {
    if (!rect) return Steinberg::kInvalidArgument;
    const auto size=skelldraw::Layout::constrain(
        {rect->left,rect->top,rect->getWidth(),rect->getHeight()});
    rect->right=rect->left+size.width;
    rect->bottom=rect->top+size.height;
    return Steinberg::kResultTrue;
}
Steinberg::tresult PLUGIN_API SkellDrawView::onWheel(float distance) {
    if (!std::isfinite(distance) || distance==0.0f)
        return Steinberg::kResultFalse;
    adjust(distance*0.035f);
    return Steinberg::kResultTrue;
}
void SkellDrawView::adjust(float step) noexcept {
    delegate_.beginGain();
    delegate_.updateGain(skelldraw::Knob::wheel(delegate_.getGain(),step/0.035f));
    delegate_.endGain();
    redraw();
}
void SkellDrawView::editStart(int y) noexcept {
    if (dragging_) return;
    dragging_=true;
    dragStartY_=y;
    dragStartGain_=delegate_.getGain();
    delegate_.beginGain();
    if(window_) SetCapture(window_);
}
void SkellDrawView::editMove(int y) noexcept {
    if (!dragging_) return;
    delegate_.updateGain(skelldraw::Knob::drag(dragStartGain_,dragStartY_-y));
    redraw();
}
void SkellDrawView::editEnd() noexcept {
    if (!dragging_) return;
    dragging_=false;
    if(window_ && GetCapture()==window_) ReleaseCapture();
    delegate_.endGain();
    redraw();
}
void SkellDrawView::redraw() noexcept {
    if (window_) InvalidateRect(window_,nullptr,FALSE);
}
void SkellDrawView::updateTimer() noexcept {
    const bool meterChanged=meter_.update(delegate_.getPeak(),0.04f);
    const float value=skelldraw::unit(delegate_.getGain(),0.5f);
    if (meterChanged || std::abs(lastPaintGain_-value)>0.001f) redraw();
}

void SkellDrawView::releaseBackBuffer() noexcept {
    if (backDc_) {
        if (backOldBitmap_) SelectObject(backDc_,backOldBitmap_);
        if (backBitmap_) DeleteObject(backBitmap_);
        DeleteDC(backDc_);
    }
    backDc_=nullptr;
    backBitmap_=nullptr;
    backOldBitmap_=nullptr;
    backWidth_=0;
    backHeight_=0;
}

bool SkellDrawView::prepareBackBuffer(HDC screen,int width,int height) noexcept {
    if (backDc_ && backWidth_==width && backHeight_==height) return true;
    releaseBackBuffer();
    backDc_=CreateCompatibleDC(screen);
    if (!backDc_) return false;
    backBitmap_=CreateCompatibleBitmap(screen,width,height);
    if (!backBitmap_) { releaseBackBuffer(); return false; }
    backOldBitmap_=SelectObject(backDc_,backBitmap_);
    if (!backOldBitmap_ || backOldBitmap_==HGDI_ERROR) {
        backOldBitmap_=nullptr;
        releaseBackBuffer();
        return false;
    }
    backWidth_=width;
    backHeight_=height;
    return true;
}
LRESULT CALLBACK SkellDrawView::windowProc(HWND hwnd,UINT msg,WPARAM w,LPARAM l) {
    auto* self=reinterpret_cast<SkellDrawView*>(GetWindowLongPtrW(hwnd,GWLP_USERDATA));
    if (!self) return DefWindowProcW(hwnd,msg,w,l);
    return self->dispatch(hwnd,msg,w,l);
}
LRESULT SkellDrawView::dispatch(HWND hwnd,UINT msg,WPARAM w,LPARAM l) {
    switch(msg) {
    case WM_ERASEBKGND: return 1; // Double-buffered WM_PAINT owns the surface.
    case WM_SIZE: releaseBackBuffer(); return 0;
    case WM_PAINT: paint(hwnd); return 0;
    case WM_TIMER: if(w==kPollTimer) { updateTimer(); return 0; } break;
    case WM_LBUTTONDOWN:
    case WM_LBUTTONDBLCLK: {
        RECT rect{}; GetClientRect(hwnd,&rect);
        const auto logical=skelldraw::Layout::logical(
            {GET_X_LPARAM(l),GET_Y_LPARAM(l)},rect.right,rect.bottom);
        if (!isKnob(logical.x,logical.y)) return 0;
        const int y=logical.y;
        if (msg==WM_LBUTTONDBLCLK) { editEnd(); adjust(0.5f-delegate_.getGain()); }
        else editStart(y);
        return 0;
    }
    case WM_MOUSEMOVE:
        if (dragging_) {
            RECT rect{}; GetClientRect(hwnd,&rect);
            editMove(skelldraw::Layout::logical(
                {GET_X_LPARAM(l),GET_Y_LPARAM(l)},rect.right,rect.bottom).y);
        }
        return 0;
    case WM_LBUTTONUP: editEnd(); return 0;
    case WM_CAPTURECHANGED: editEnd(); return 0;
    case WM_MOUSEWHEEL: {
        const float ticks=static_cast<float>(GET_WHEEL_DELTA_WPARAM(w))/WHEEL_DELTA;
        if (std::isfinite(ticks) && ticks!=0.0f) adjust(ticks*0.035f);
        return 0;
    }
    case WM_DESTROY: editEnd(); return 0;
    default: break;
    }
    return originalWindowProc_
        ? CallWindowProcW(originalWindowProc_,hwnd,msg,w,l)
        : DefWindowProcW(hwnd,msg,w,l);
}
void SkellDrawView::paint(HWND hwnd) noexcept {
    PAINTSTRUCT paint{};
    HDC dc=BeginPaint(hwnd,&paint);
    if (!dc) return;
    RECT client{}; GetClientRect(hwnd,&client);
    const int width=std::max(1,static_cast<int>(client.right));
    const int height=std::max(1,static_cast<int>(client.bottom));
    if (!prepareBackBuffer(dc,width,height)) { EndPaint(hwnd,&paint); return; }
    const HDC buffer=backDc_;
    SetMapMode(buffer,MM_ANISOTROPIC);
    SetWindowExtEx(buffer,kBaseW,kBaseH,nullptr);
    SetViewportExtEx(buffer,width,height,nullptr);
    SetStretchBltMode(buffer,HALFTONE);

    fill(buffer,0,0,kBaseW,kBaseH,kBg);
    fill(buffer,0,0,kBaseW,3,kGreen);
    fill(buffer,18,24,444,250,kPanel);
    line(buffer,18,24,462,24,RGB(57,77,64));
    line(buffer,18,274,462,274,RGB(34,49,38));
    fill(buffer,28,34,6,21,kGreen);
    label(buffer,L"SKELL",26,FW_BOLD,45,30,83,33,RGB(241,246,240),DT_LEFT);
    label(buffer,L"NATIVE",26,FW_BOLD,127,30,111,33,kGreen,DT_LEFT);
    label(buffer,L"GAIN / SKELLDRAW v0.1",11,FW_NORMAL,284,34,164,28,kMuted,DT_RIGHT);

    // Reusable SkellDraw knob; no flat highlight or plugin-specific skull.
    const float value=skelldraw::unit(delegate_.getGain(),0.5f);
    lastPaintGain_=value;
    skelldraw::win32::knob(buffer,value,kGreen);

    fill(buffer,339,103,104,84,RGB(8,15,11));
    line(buffer,339,103,443,103,RGB(65,87,68));
    wchar_t level[48]{};
    const float amplitude=value*2.0f;
    std::swprintf(level,48,L"%.2fx",static_cast<double>(amplitude));
    label(buffer,level,26,FW_BOLD,339,111,104,43,kGreen);
    label(buffer,L"LINEAR GAIN",10,FW_NORMAL,343,156,95,17,kMuted);
    label(buffer,L"OUTPUT",10,FW_NORMAL,345,187,94,16,kMuted);
    skelldraw::win32::outputMeter(buffer,skelldraw::Layout::meter,
                                  meter_.level(),kGreen);
    label(buffer,L"DRAG / SCROLL",11,FW_NORMAL,35,206,128,22,kMuted,DT_LEFT);
    label(buffer,L"DOUBLE-CLICK TO RESET",10,FW_NORMAL,35,222,168,22,kMuted,DT_LEFT);
    label(buffer,L"SKELL AUDIO  |  NO JUCE",11,FW_NORMAL,31,254,416,16,RGB(116,139,120),DT_LEFT);
    label(buffer,L"WINDOWS VST3",10,FW_NORMAL,342,254,100,16,kMuted,DT_RIGHT);

    SetMapMode(buffer,MM_TEXT); // Source bitmap pixels, not logical UI units.
    BitBlt(dc,0,0,width,height,buffer,0,0,SRCCOPY);
    EndPaint(hwnd,&paint);
}
} // namespace Skelly::NativeGain
