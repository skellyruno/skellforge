#ifndef NOMINMAX
#define NOMINMAX
#endif
#include "SkellDrawWin32.h"
#include <windowsx.h>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <cwchar>

namespace Skelly::NativeGain {

namespace {
constexpr wchar_t kClassName[] = L"SkellNativeSkellDrawView_0_1";
constexpr int kBaseW = 480;
constexpr int kBaseH = 300;
constexpr UINT_PTR kPollTimer = 17;
constexpr COLORREF kBg = RGB(8, 11, 10);
constexpr COLORREF kPanel = RGB(15, 22, 18);
constexpr COLORREF kGreen = RGB(141, 255, 68);
constexpr COLORREF kMuted = RGB(142, 157, 143);
constexpr float kPi = 3.14159265358979323846f;

void fill(HDC dc, int x, int y, int w, int h, COLORREF color) noexcept {
    const RECT rect{x, y, x+w, y+h};
    if (HBRUSH brush = CreateSolidBrush(color)) {
        FillRect(dc, &rect, brush);
        DeleteObject(brush);
    }
}
void line(HDC dc, int x0, int y0, int x1, int y1, COLORREF color, int thickness=1) noexcept {
    if (HPEN pen = CreatePen(PS_SOLID, thickness, color)) {
        const auto old = SelectObject(dc, pen);
        MoveToEx(dc, x0, y0, nullptr);
        LineTo(dc, x1, y1);
        SelectObject(dc, old);
        DeleteObject(pen);
    }
}
void ellipse(HDC dc, int x0, int y0, int x1, int y1,
             COLORREF inner, COLORREF outline, int border=1) noexcept {
    HBRUSH brush = CreateSolidBrush(inner);
    HPEN pen = CreatePen(PS_SOLID, border, outline);
    if (brush && pen) {
        auto oldB = SelectObject(dc,brush);
        auto oldP = SelectObject(dc,pen);
        Ellipse(dc,x0,y0,x1,y1);
        SelectObject(dc,oldP);
        SelectObject(dc,oldB);
    }
    if (pen) DeleteObject(pen);
    if (brush) DeleteObject(brush);
}
void label(HDC dc, const wchar_t* value, int size, int weight, int x, int y, int w,
           int h, COLORREF color, UINT alignment=DT_CENTER) noexcept {
    HFONT font = CreateFontW(-size,0,0,0,weight,FALSE,FALSE,FALSE,DEFAULT_CHARSET,
                            OUT_DEFAULT_PRECIS,CLIP_DEFAULT_PRECIS,CLEARTYPE_QUALITY,
                            DEFAULT_PITCH|FF_SWISS,L"Segoe UI");
    if (!font) return;
    const auto oldFont = SelectObject(dc,font);
    SetBkMode(dc,TRANSPARENT);
    SetTextColor(dc,color);
    RECT rect{x,y,x+w,y+h};
    DrawTextW(dc,value,-1,&rect,DT_SINGLELINE|DT_VCENTER|DT_NOPREFIX|alignment);
    SelectObject(dc,oldFont);
    DeleteObject(font);
}
bool isKnob(int x,int y) noexcept {
    const int dx=x-237;
    const int dy=y-155;
    return dx*dx+dy*dy < 68*68;
}
int scaledCoordinate(int coordinate,int sourceSpan,int targetSpan) noexcept {
    return targetSpan > 0 ? coordinate*sourceSpan/targetSpan : 0;
}
} // namespace

SkellDrawView::SkellDrawView(GainViewDelegate& delegate, Steinberg::FUnknown* owner)
    : Steinberg::CPluginView(), delegate_(delegate), owner_(owner) {
    setRect(Steinberg::ViewRect(0,0,kBaseW,kBaseH));
    if (owner_) owner_->addRef(); // UI remains valid while the host owns the view.
}
SkellDrawView::~SkellDrawView() {
    if (window_) removed();
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
    // Fixed 8:5 ratio, bounded to fit small and large FL Studio windows.
    const int width=std::clamp(rect->getWidth(),400,960);
    rect->right=rect->left+width;
    rect->bottom=rect->top+(width*5/8);
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
    delegate_.updateGain(std::clamp(delegate_.getGain()+step,0.0f,1.0f));
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
    delegate_.updateGain(std::clamp(dragStartGain_+
                                   (dragStartY_-y)*0.006f,0.0f,1.0f));
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
    const float value=delegate_.getGain();
    if (std::abs(lastPaintGain_-value)>0.001f) redraw();
}
LRESULT CALLBACK SkellDrawView::windowProc(HWND hwnd,UINT msg,WPARAM w,LPARAM l) {
    auto* self=reinterpret_cast<SkellDrawView*>(GetWindowLongPtrW(hwnd,GWLP_USERDATA));
    if (!self) return DefWindowProcW(hwnd,msg,w,l);
    return self->dispatch(hwnd,msg,w,l);
}
LRESULT SkellDrawView::dispatch(HWND hwnd,UINT msg,WPARAM w,LPARAM l) {
    switch(msg) {
    case WM_ERASEBKGND: return 1; // Double-buffered WM_PAINT owns the surface.
    case WM_PAINT: paint(hwnd); return 0;
    case WM_TIMER: if(w==kPollTimer) { updateTimer(); return 0; } break;
    case WM_LBUTTONDOWN:
    case WM_LBUTTONDBLCLK: {
        RECT rect{}; GetClientRect(hwnd,&rect);
        const int x=scaledCoordinate(GET_X_LPARAM(l),kBaseW,rect.right);
        const int y=scaledCoordinate(GET_Y_LPARAM(l),kBaseH,rect.bottom);
        if (!isKnob(x,y)) return 0;
        if (msg==WM_LBUTTONDBLCLK) { editEnd(); adjust(0.5f-delegate_.getGain()); }
        else editStart(y);
        return 0;
    }
    case WM_MOUSEMOVE:
        if (dragging_) {
            RECT rect{}; GetClientRect(hwnd,&rect);
            editMove(scaledCoordinate(GET_Y_LPARAM(l),kBaseH,rect.bottom));
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
    const int width=std::max(1,client.right);
    const int height=std::max(1,client.bottom);
    HDC buffer=CreateCompatibleDC(dc);
    HBITMAP bitmap=buffer ? CreateCompatibleBitmap(dc,width,height):nullptr;
    if(!buffer || !bitmap) {
        if(bitmap) DeleteObject(bitmap);
        if(buffer) DeleteDC(buffer);
        EndPaint(hwnd,&paint);
        return;
    }
    const auto original=SelectObject(buffer,bitmap);
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

    // Shaped metallic concentric rings. No plugin-specific skull asset yet.
    ellipse(buffer,161,79,313,231,RGB(30,39,33),RGB(9,14,11),3);
    ellipse(buffer,169,87,305,223,RGB(56,67,61),RGB(122,134,125),2);
    ellipse(buffer,175,93,299,217,RGB(20,27,24),RGB(5,8,7),4);
    ellipse(buffer,185,103,289,207,RGB(39,50,44),RGB(70,84,74),2);
    ellipse(buffer,193,111,281,199,RGB(19,26,22),RGB(111,126,114),1);
    line(buffer,198,115,270,115,RGB(75,91,79),2);
    const float value=std::clamp(delegate_.getGain(),0.0f,1.0f);
    lastPaintGain_=value;
    for(int t=0;t<=34;++t) {
        const float angle=(140.0f+260.0f*t/34.0f)*kPi/180.0f;
        const int x0=237+static_cast<int>(78*std::cos(angle));
        const int y0=155+static_cast<int>(78*std::sin(angle));
        const int x1=237+static_cast<int>(85*std::cos(angle));
        const int y1=155+static_cast<int>(85*std::sin(angle));
        line(buffer,x0,y0,x1,y1,t<=static_cast<int>(value*34.0f)?kGreen:
             RGB(59,76,65),t<=static_cast<int>(value*34.0f)?3:1);
    }
    const float angle=(140.0f+260.0f*value)*kPi/180.0f;
    line(buffer,237,155,237+static_cast<int>(36*std::cos(angle)),
         155+static_cast<int>(36*std::sin(angle)),kGreen,4);

    fill(buffer,339,103,104,84,RGB(8,15,11));
    line(buffer,339,103,443,103,RGB(65,87,68));
    wchar_t level[48]{};
    const float amplitude=value*2.0f;
    std::swprintf(level,48,L"%.2fx",static_cast<double>(amplitude));
    label(buffer,level,26,FW_BOLD,339,111,104,43,kGreen);
    label(buffer,L"LINEAR GAIN",10,FW_NORMAL,343,156,95,17,kMuted);
    label(buffer,L"DRAG / SCROLL",11,FW_NORMAL,35,206,128,22,kMuted,DT_LEFT);
    label(buffer,L"DOUBLE-CLICK TO RESET",10,FW_NORMAL,35,222,168,22,kMuted,DT_LEFT);
    label(buffer,L"SKELL AUDIO  |  NO JUCE",11,FW_NORMAL,31,254,416,16,RGB(116,139,120),DT_LEFT);
    label(buffer,L"WINDOWS VST3",10,FW_NORMAL,342,254,100,16,kMuted,DT_RIGHT);

    SetMapMode(buffer,MM_TEXT); // Source bitmap pixels, not logical UI units.
    BitBlt(dc,0,0,width,height,buffer,0,0,SRCCOPY);
    SelectObject(buffer,original);
    DeleteObject(bitmap);
    DeleteDC(buffer);
    EndPaint(hwnd,&paint);
}
} // namespace Skelly::NativeGain
