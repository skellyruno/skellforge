#pragma once
// SkellDraw v0.1 — ORIGINAL native Win32 VST3 editor.
// No JUCE or VSTGUI. HWND child view embedded through Steinberg IPlugView.
// This is a provisional renderer, not the unapproved master skull artwork.
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <cstdint>
#include "public.sdk/source/common/pluginview.h"

namespace Skelly::NativeGain {

class GainViewDelegate {
public:
    virtual ~GainViewDelegate() = default;
    virtual float getGain() const noexcept = 0;
    virtual void beginGain() noexcept = 0;
    virtual void updateGain(float value) noexcept = 0;
    virtual void endGain() noexcept = 0;
};

class SkellDrawView final : public Steinberg::CPluginView {
public:
    SkellDrawView(GainViewDelegate& delegate, Steinberg::FUnknown* owner);
    ~SkellDrawView() override;
    Steinberg::tresult PLUGIN_API isPlatformTypeSupported(Steinberg::FIDString type) override;
    Steinberg::tresult PLUGIN_API attached(void* parent, Steinberg::FIDString type) override;
    Steinberg::tresult PLUGIN_API removed() override;
    Steinberg::tresult PLUGIN_API onSize(Steinberg::ViewRect* size) override;
    Steinberg::tresult PLUGIN_API canResize() override { return Steinberg::kResultTrue; }
    Steinberg::tresult PLUGIN_API checkSizeConstraint(Steinberg::ViewRect* rect) override;
    Steinberg::tresult PLUGIN_API onWheel(float distance) override;

private:
    static LRESULT CALLBACK windowProc(HWND window, UINT message, WPARAM w, LPARAM l);
    LRESULT dispatch(HWND window, UINT message, WPARAM w, LPARAM l);
    static bool registerWindowClass() noexcept;
    void paint(HWND window) noexcept;
    void editStart(int y) noexcept;
    void editMove(int y) noexcept;
    void editEnd() noexcept;
    void adjust(float step) noexcept;
    void redraw() noexcept;
    void updateTimer() noexcept;

    GainViewDelegate& delegate_;
    Steinberg::FUnknown* owner_ = nullptr;
    HWND window_ = nullptr;
    bool dragging_ = false;
    int dragStartY_ = 0;
    float dragStartGain_ = 0.5f;
    float lastPaintGain_ = -1.0f;
};

} // namespace Skelly::NativeGain
