"""Generate the JUCE layout and fully bound extra rotary controls.

No audio-thread allocations. Controls/attachments exist only while a plugin
editor is open and always use the saved APVTS parameter IDs.
"""
from __future__ import annotations

import json
from .automation import unified_specs


def _rect(component: dict) -> str:
    return ", ".join(str(component[key]) for key in ("x", "y", "w", "h"))


def _literal(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def render_ui(data: dict, header: str) -> str:
    width = data["canvas"]["width"]
    height = data["canvas"]["height"]
    components = {c["id"]: c for c in data["components"]}
    params = [c for c in data["components"] if c["type"] == "effect_knob"]
    meters = [c for c in data["components"] if c["type"] == "meter"]
    specs = {s["id"]: s for s in unified_specs(data)}
    lines = [
        header, "#pragma once\n#include <JuceHeader.h>\n",
        "#include <SkellCore/StudioUI.h>\n#include <algorithm>\n#include <atomic>\n#include <cmath>\n#include <memory>\n#include <utility>\n#include <vector>\n",
        "namespace forgeui {\n",
        f"inline constexpr int referenceWidth = {width};\n",
        f"inline constexpr int referenceHeight = {height};\n",
        "inline juce::Rectangle<int> scaled(int x, int y, int w, int h, int currentW, int currentH) {\n",
        "    const float sx = static_cast<float>(currentW) / referenceWidth;\n",
        "    const float sy = static_cast<float>(currentH) / referenceHeight;\n",
        "    return {juce::roundToInt(x * sx), juce::roundToInt(y * sy),\n",
        "            juce::roundToInt(w * sx), juce::roundToInt(h * sy)};\n}\n",
        "inline void layout(juce::Component& skull, juce::Component& title,\n",
        "                   juce::Component& gainLabel, juce::Component& gainKnob,\n",
        "                   int width, int height) {\n",
    ]
    for cid, var in (("skull", "skull"), ("title", "title"),
                     ("gain_label", "gainLabel"), ("gain_knob", "gainKnob")):
        lines.append(f"    {var}.setBounds(scaled({_rect(components[cid])}, width, height));\n")
    lines.append("}\n")
    lines.extend([
        "class OutputMeter final : public juce::Component, private juce::Timer {\n",
        "public:\n",
        "    OutputMeter(const std::atomic<float>* source, juce::String caption)\n",
        "        : source_(source), caption_(std::move(caption)) {\n",
        "        setInterceptsMouseClicks(false, false);\n",
        "        startTimerHz(24); // Paint only on GUI thread, never on audio thread.\n",
        "    }\n",
        "    void paint(juce::Graphics& g) override {\n",
        "        const auto area = getLocalBounds().toFloat();\n",
        "        g.setColour(juce::Colour(0xff172019));\n",
        "        g.fillRoundedRectangle(area, 5.0f);\n",
        "        g.setColour(juce::Colour(0xff35483b));\n",
        "        g.drawRoundedRectangle(area.reduced(0.5f), 5.0f, 1.0f);\n",
        "        auto fill = area.reduced(3.0f);\n",
        "        const float captionWidth = std::min(44.0f, fill.getWidth() * 0.35f);\n",
        "        g.setColour(juce::Colour(0xffc5d2c6));\n",
        "        g.setFont(juce::Font(juce::FontOptions(10.0f)));\n",
        "        g.drawFittedText(caption_, fill.removeFromLeft(captionWidth).toNearestInt(),\n",
        "                         juce::Justification::centredLeft, 1);\n",
        "        if (fill.getWidth() > 1.0f && display_ > 0.0f) {\n",
        "            fill.setWidth(std::max(1.0f, fill.getWidth() * display_));\n",
        "            g.setColour(juce::Colour(0xff90ff44));\n",
        "            g.fillRoundedRectangle(fill, 3.0f);\n",
        "        }\n",
        "    }\n",
        "private:\n",
        "    void timerCallback() override {\n",
        "        const float raw = source_ ? source_->load(std::memory_order_relaxed) : 0.0f;\n",
        "        const float target = std::isfinite(raw) ? juce::jlimit(0.0f, 1.0f, raw) : 0.0f;\n",
        "        const float next = std::max(target, display_ * 0.85f);\n",
        "        if (std::abs(next - display_) > 0.003f) { display_ = next; repaint(); }\n",
        "        else if (next < 0.003f && display_ != 0.0f) { display_ = 0.0f; repaint(); }\n",
        "    }\n",
        "    const std::atomic<float>* source_ = nullptr;\n",
        "    juce::String caption_;\n",
        "    float display_ = 0.0f;\n",
        "};\n",
        "class ExtraControls {\npublic:\n",
        "    void setup(juce::Component& parent, juce::AudioProcessorValueTreeState& state,\n",
        "               const std::atomic<float>* outputPeak = nullptr) {\n",
    ])
    for c in params:
        lines.extend([
            "        {\n",
            "            auto knob = std::make_unique<juce::Slider>();\n",
            f"            knob->setName({_literal(c.get('text', c['id']))});\n",
            f"            skellcore::ui::configureStudioKnob(*knob, {specs[c['parameter_id']]['default']:.9g});\n",
            "            parent.addAndMakeVisible(*knob);\n",
            f"            auto attachment = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment>"
            f"(state, {_literal(c['parameter_id'])}, *knob);\n",
            "            knobs_.push_back(std::move(knob));\n",
            "            attachments_.push_back(std::move(attachment));\n",
            "        }\n",
        ])
    for c in meters:
        lines.extend([
            "        {\n",
            f"            auto meter = std::make_unique<OutputMeter>(outputPeak, {_literal(c['text'])});\n",
            "            parent.addAndMakeVisible(*meter);\n",
            "            meters_.push_back(std::move(meter));\n",
            "        }\n",
        ])
    lines.extend([
        "        (void)parent;\n        (void)state;\n        (void)outputPeak;\n    }\n",
        "    void layout(int width, int height) {\n",
    ])
    for i,c in enumerate(params):
        lines.append(f"        knobs_[{i}]->setBounds(scaled({_rect(c)}, width, height));\n")
    for i,c in enumerate(meters):
        lines.append(f"        meters_[{i}]->setBounds(scaled({_rect(c)}, width, height));\n")
    lines.extend([
        "        (void)width;\n        (void)height;\n    }\n",
        "private:\n",
        "    std::vector<std::unique_ptr<juce::Slider>> knobs_;\n",
        "    // Attachments must be destroyed before the sliders they reference.\n",
        "    std::vector<std::unique_ptr<juce::AudioProcessorValueTreeState::SliderAttachment>> attachments_;\n",
        "    std::vector<std::unique_ptr<OutputMeter>> meters_;\n",
        "};\n",
        "inline void drawLabels(juce::Graphics& g, int width, int height, juce::Colour colour) {\n",
        "    g.setColour(colour);\n",
        "    g.setFont(juce::Font(juce::FontOptions(13.0f)));\n",
    ])
    for c in data["components"]:
        if c["type"] == "text":
            lines.append(
                f"    g.drawFittedText({_literal(c['text'])}, "
                f"scaled({_rect(c)}, width, height), juce::Justification::centred, 1);\n"
            )
        elif c["type"] == "effect_knob":
            label_y = max(0, c["y"] - 17)
            lines.append(
                f"    g.drawFittedText({_literal(c.get('text', c['id']))}, "
                f"scaled({c['x']}, {label_y}, {c['w']}, 16, width, height), "
                "juce::Justification::centred, 1);\n"
            )
    lines.append("}\n} // namespace forgeui\n")
    return "".join(lines)
