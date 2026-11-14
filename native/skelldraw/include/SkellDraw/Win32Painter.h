#pragma once
// SkellDraw Windows GDI adapter: reusable controls for any native plugin.
// Host-neutral state/layout lives in Components.h; HWND owns rendering.
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <SkellDraw/Components.h>
#include <windows.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>

namespace skelldraw::win32 {

inline COLORREF color(std::uint32_t rgb) noexcept {
    return RGB((rgb>>16)&255u,(rgb>>8)&255u,rgb&255u);
}
inline void fill(HDC dc,int x,int y,int width,int height,COLORREF c) noexcept {
    const RECT rect{x,y,x+width,y+height};
    HBRUSH brush=CreateSolidBrush(c);
    if(brush) { FillRect(dc,&rect,brush); DeleteObject(brush); }
}
inline void line(HDC dc,int x0,int y0,int x1,int y1,COLORREF c,int thick=1) noexcept {
    HPEN pen=CreatePen(PS_SOLID,thick,c);
    if(!pen) return;
    auto old=SelectObject(dc,pen);
    MoveToEx(dc,x0,y0,nullptr);
    LineTo(dc,x1,y1);
    SelectObject(dc,old);
    DeleteObject(pen);
}
inline void ellipse(HDC dc,int x0,int y0,int x1,int y1,
                    COLORREF inside,COLORREF border,int width=1) noexcept {
    HBRUSH brush=CreateSolidBrush(inside);
    HPEN pen=CreatePen(PS_SOLID,width,border);
    if(brush && pen) {
        const auto oldBrush=SelectObject(dc,brush);
        const auto oldPen=SelectObject(dc,pen);
        Ellipse(dc,x0,y0,x1,y1);
        SelectObject(dc,oldPen);
        SelectObject(dc,oldBrush);
    }
    if(pen) DeleteObject(pen);
    if(brush) DeleteObject(brush);
}
inline void label(HDC dc,const wchar_t* content,int fontSize,int weight,
                  int x,int y,int w,int h,COLORREF c,UINT alignment=DT_CENTER) noexcept {
    HFONT font=CreateFontW(-fontSize,0,0,0,weight,FALSE,FALSE,FALSE,DEFAULT_CHARSET,
                           OUT_DEFAULT_PRECIS,CLIP_DEFAULT_PRECIS,CLEARTYPE_QUALITY,
                           DEFAULT_PITCH|FF_SWISS,L"Segoe UI");
    if(!font) return;
    const auto old=SelectObject(dc,font);
    SetBkMode(dc,TRANSPARENT);
    SetTextColor(dc,c);
    RECT rect{x,y,x+w,y+h};
    DrawTextW(dc,content,-1,&rect,DT_SINGLELINE|DT_VCENTER|DT_NOPREFIX|alignment);
    SelectObject(dc,old);
    DeleteObject(font);
}

// Caches label fonts per editor instead of creating/deleting GDI font
// handles eight times on every meter repaint. No allocation after warmup.
// Each Win32 view owns its own cache; never share across DLL unloads.
class LabelFontCache {
public:
    LabelFontCache()=default;
    LabelFontCache(const LabelFontCache&)=delete;
    LabelFontCache& operator=(const LabelFontCache&)=delete;
    ~LabelFontCache() noexcept {
        for (const auto& slot:slots_)
            if (slot.font) DeleteObject(slot.font);
    }
    void draw(HDC dc,const wchar_t* content,int fontSize,int weight,
              int x,int y,int w,int h,COLORREF ink,
              UINT alignment=DT_CENTER) noexcept {
        HFONT font=findFont(fontSize,weight);
        if(!font) {
            label(dc,content,fontSize,weight,x,y,w,h,ink,alignment);
            return;
        }
        const HGDIOBJ old=SelectObject(dc,font);
        if(!old || old==HGDI_ERROR) return;
        SetBkMode(dc,TRANSPARENT);
        SetTextColor(dc,ink);
        RECT rect{x,y,x+w,y+h};
        DrawTextW(dc,content,-1,&rect,
                  DT_SINGLELINE|DT_VCENTER|DT_NOPREFIX|alignment);
        SelectObject(dc,old);
    }
private:
    struct Slot { int size=0; int weight=0; HFONT font=nullptr; };
    std::array<Slot,6> slots_{};
    HFONT findFont(int size,int weight) noexcept {
        for(const auto& slot:slots_)
            if(slot.font && slot.size==size && slot.weight==weight) return slot.font;
        for(auto& slot:slots_) {
            if(slot.font) continue;
            slot.font=CreateFontW(-size,0,0,0,weight,FALSE,FALSE,FALSE,
                DEFAULT_CHARSET,OUT_DEFAULT_PRECIS,CLIP_DEFAULT_PRECIS,
                CLEARTYPE_QUALITY,DEFAULT_PITCH|FF_SWISS,L"Segoe UI");
            if(slot.font) { slot.size=size; slot.weight=weight; }
            return slot.font;
        }
        return nullptr;
    }
};

// Hot path reuses three pen handles for 35 tick marks plus the indicator.
// Color is supplied at construction for plugin-specific themes.
class KnobPens {
public:
    explicit KnobPens(COLORREF accent=RGB(141,255,68)) noexcept {
        bright_=CreatePen(PS_SOLID,3,accent);
        dim_=CreatePen(PS_SOLID,1,RGB(59,76,65));
        indicator_=CreatePen(PS_SOLID,4,accent);
    }
    KnobPens(const KnobPens&)=delete;
    KnobPens& operator=(const KnobPens&)=delete;
    ~KnobPens() noexcept {
        if(bright_) DeleteObject(bright_);
        if(dim_) DeleteObject(dim_);
        if(indicator_) DeleteObject(indicator_);
    }
    void drawTick(HDC dc,bool selected,int x0,int y0,int x1,int y1,
                  COLORREF accent) const noexcept {
        const HPEN pen=selected?bright_:dim_;
        if(!pen) { line(dc,x0,y0,x1,y1,selected?accent:RGB(59,76,65),
                       selected?3:1); return; }
        const HGDIOBJ old=SelectObject(dc,pen);
        MoveToEx(dc,x0,y0,nullptr);
        LineTo(dc,x1,y1);
        SelectObject(dc,old);
    }
    void drawIndicator(HDC dc,int x0,int y0,int x1,int y1,
                       COLORREF accent) const noexcept {
        if(!indicator_) { line(dc,x0,y0,x1,y1,accent,4); return; }
        const HGDIOBJ old=SelectObject(dc,indicator_);
        MoveToEx(dc,x0,y0,nullptr);
        LineTo(dc,x1,y1);
        SelectObject(dc,old);
    }
private:
    HPEN bright_=nullptr;
    HPEN dim_=nullptr;
    HPEN indicator_=nullptr;
};

// Preserves the v0.1 metallic knob shape: no artificial horizontal highlight.
inline void knob(HDC dc,float normalized,COLORREF accent=RGB(141,255,68),
                 const KnobPens* pens=nullptr) noexcept {
    normalized=unit(normalized,Knob::defaultValue);
    ellipse(dc,161,79,313,231,RGB(30,39,33),RGB(9,14,11),3);
    ellipse(dc,169,87,305,223,RGB(56,67,61),RGB(122,134,125),2);
    ellipse(dc,175,93,299,217,RGB(20,27,24),RGB(5,8,7),4);
    ellipse(dc,185,103,289,207,RGB(39,50,44),RGB(70,84,74),2);
    ellipse(dc,193,111,281,199,RGB(19,26,22),RGB(111,126,114),1);
    constexpr float pi=3.14159265358979323846f;
    for(int step=0;step<=34;++step) {
        const float a=(140.f+260.f*static_cast<float>(step)/34.f)*pi/180.f;
        const int x0=237+static_cast<int>(78*std::cos(a));
        const int y0=155+static_cast<int>(78*std::sin(a));
        const int x1=237+static_cast<int>(85*std::cos(a));
        const int y1=155+static_cast<int>(85*std::sin(a));
        const bool selected=step<=static_cast<int>(normalized*34.f);
        if(pens) pens->drawTick(dc,selected,x0,y0,x1,y1,accent);
        else line(dc,x0,y0,x1,y1,selected?accent:RGB(59,76,65),selected?3:1);
    }
    const float a=(140.f+260.f*normalized)*pi/180.f;
    const int tipX=237+static_cast<int>(36*std::cos(a));
    const int tipY=155+static_cast<int>(36*std::sin(a));
    if(pens) pens->drawIndicator(dc,237,155,tipX,tipY,accent);
    else line(dc,237,155,tipX,tipY,accent,4);
}

// Opt-in, actual state-driven power button. Never paint an interactive power
// control unless the owning plugin supplies persistent bypass semantics.
inline void powerButton(HDC dc,Rect bounds,bool powered,
                        COLORREF accent=RGB(141,255,68)) noexcept {
    const auto cx=bounds.x+bounds.width/2;
    const auto cy=bounds.y+bounds.height/2;
    const auto radius=std::max(4,std::min(bounds.width,bounds.height)/2-3);
    const auto glow=powered?accent:RGB(64,77,66);
    ellipse(dc,cx-radius,cy-radius,cx+radius,cy+radius,
            RGB(17,24,19),glow,2);
    line(dc,cx,cy-radius+3,cx,cy+2,glow,3);
}

inline void outputMeter(HDC dc,Rect bounds,float amplitude,
                        COLORREF accent=RGB(141,255,68)) noexcept {
    amplitude=unit(amplitude);
    fill(dc,bounds.x,bounds.y,bounds.width,bounds.height,RGB(9,14,11));
    const int segments=12;
    const int gap=2;
    const int barW=std::max(1,(bounds.width-(segments-1)*gap)/segments);
    const int active=static_cast<int>(std::ceil(amplitude*segments));
    for(int i=0;i<segments;++i) {
        const int x=bounds.x+i*(barW+gap);
        const int w=std::min(barW,bounds.x+bounds.width-x);
        if(w<=0) break;
        const COLORREF ink=i<active?accent:RGB(42,59,46);
        fill(dc,x,bounds.y+4,w,std::max(1,bounds.height-8),ink);
    }
}
} // namespace skelldraw::win32
