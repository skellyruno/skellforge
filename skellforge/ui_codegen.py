"""Generate the JUCE layout and fully bound extra rotary controls.

No audio-thread allocations. Controls/attachments exist only while a plugin
editor is open and always use the saved APVTS parameter IDs.
"""
from __future__ import annotations

import json


def _rect(component: dict) -> str:
    return ", ".join(str(component[key]) for key in ("x", "y", "w", "h"))


def _literal(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def render_ui(data: dict, header: str) -> str:
    width = data["canvas"]["width"]
    height = data["canvas"]["height"]
    components = {c["id"]: c for c in data["components"]}
    params = [c for c in data["components"] if c["type"] == "effect_knob"]
    lines = [
        header, "#pragma once\n#include <JuceHeader.h>\n",
        "#include <SkellCore/StudioUI.h>\n#include <memory>\n#include <vector>\n",
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
        "class ExtraControls {\npublic:\n",
        "    void setup(juce::Component& parent, juce::AudioProcessorValueTreeState& state) {\n",
    ])
    for c in params:
        lines.extend([
            "        {\n",
            "            auto knob = std::make_unique<juce::Slider>();\n",
            f"            knob->setName({_literal(c.get('text', c['id']))});\n",
            "            parent.addAndMakeVisible(*knob);\n",
            f"            auto attachment = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment>"
            f"(state, {_literal(c['parameter_id'])}, *knob);\n",
            "            skellcore::ui::configureStudioKnob(*knob, knob->getValue());\n",
            "            knobs_.push_back(std::move(knob));\n",
            "            attachments_.push_back(std::move(attachment));\n",
            "        }\n",
        ])
    lines.extend([
        "        (void)parent;\n        (void)state;\n    }\n",
        "    void layout(int width, int height) {\n",
    ])
    for i,c in enumerate(params):
        lines.append(f"        knobs_[{i}]->setBounds(scaled({_rect(c)}, width, height));\n")
    lines.extend([
        "        (void)width;\n        (void)height;\n    }\n",
        "private:\n",
        "    std::vector<std::unique_ptr<juce::Slider>> knobs_;\n",
        "    // Attachments must be destroyed before the sliders they reference.\n",
        "    std::vector<std::unique_ptr<juce::AudioProcessorValueTreeState::SliderAttachment>> attachments_;\n",
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
